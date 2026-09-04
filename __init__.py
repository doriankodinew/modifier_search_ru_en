"""
Modifier Search RU/EN
----------------------
Позволяет искать и добавлять модификаторы по названию на английском ИЛИ
русском языке, даже если интерфейс Blender полностью локализован на русский.

Метаданные аддона (имя, версия, автор, минимальная версия Blender и т.д.)
находятся в файле blender_manifest.toml рядом с этим файлом — это
современный формат Blender Extensions (Blender 4.2+), пришедший на смену
словарю bl_info.
"""

import bpy

# Список модификаторов и их английские названия НЕ хранятся здесь вручную.
# Вместо этого они берутся напрямую из RNA самого Blender (то есть всегда
# ровно тот набор, что реально доступен в установленной версии), а перевод
# на текущий язык интерфейса запрашивается через встроенный переводчик
# Blender (bpy.app.translations) — тот же самый каталог, которым Blender
# пользуется, чтобы нарисовать пункт "Подразделение поверхности" в самом
# меню. Так список гарантированно полный и не может разойтись с реальным
# Blender: ни лишних, ни пропущенных пунктов, и работает для любого языка
# интерфейса, а не только русского.

# Кэш для enum-элементов: Blender требует, чтобы список,
# возвращаемый callback-функцией EnumProperty, не был собран сборщиком мусора,
# пока popup открыт — поэтому храним его в модульной переменной.
_enum_items_cache = []


# Некоторые identifier'ы присутствуют в общем RNA-перечислении 'type', но
# на самом деле не предназначены для ручного добавления через modifier_add —
# Blender заводит их сам при определённых обстоятельствах. Пример: 'SURFACE' —
# служебная метка позиции в стеке модификаторов для объектов типа Force Field
# "Surface"; добавляется автоматически, ручной bpy.ops.object.modifier_add
# с этим type всегда падает с TypeError. Такие пункты явно исключаем из поиска.
EXCLUDED_MODIFIER_IDS = {'SURFACE'}


def get_modifier_enum_items(self, context):
    global _enum_items_cache

    try:
        rna_enum = bpy.ops.object.modifier_add.get_rna_type().properties['type'].enum_items
    except Exception:
        rna_enum = []

    # Общий RNA-список 'type' не разделён по типам объектов: в нём вперемешку
    # лежат и обычные модификаторы (для меша/кривой/решётки и т.д.), и модификаторы
    # Grease Pencil (identifier с префиксом GREASE_PENCIL_), у многих из которых
    # то же самое отображаемое имя ("Armature" и для меша, и для Grease Pencil).
    # Из-за этого при активном обычном объекте в списке визуально "двоился"
    # пункт вроде "Арматура", а клик по "чужому" варианту падал с TypeError.
    # Поэтому показываем только те, что реально подходят активному объекту.
    obj = context.active_object
    is_gpencil_object = obj is not None and obj.type in {'GPENCIL', 'GREASEPENCIL'}

    items = []
    seen_ids = set()
    for entry in rna_enum:
        ident = entry.identifier
        if ident in EXCLUDED_MODIFIER_IDS:
            continue
        if ident in seen_ids:
            continue
        seen_ids.add(ident)

        is_gp_modifier = ident.startswith('GREASE_PENCIL_')
        if is_gp_modifier != is_gpencil_object:
            continue

        en = entry.name  # исходное (английское) название из RNA, не переведено
        try:
            translated = bpy.app.translations.pgettext_iface(en)
        except Exception:
            translated = en

        if translated and translated != en:
            label = f"{en}  |  {translated}"
        else:
            # Либо перевода для текущего языка нет, либо интерфейс и так на английском.
            label = en

        items.append((ident, label, entry.description or en))

    items.sort(key=lambda x: x[1])
    _enum_items_cache = items
    return _enum_items_cache


class OBJECT_OT_modifier_search_en_ru(bpy.types.Operator):
    """Найти модификатор по названию на английском или русском и добавить его"""
    bl_idname = "object.modifier_search_en_ru"
    bl_label = "Поиск модификатора (EN/RU)"
    bl_description = "Найти модификатор по английскому или русскому названию и добавить его к объекту"
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = "modifier_type"

    modifier_type: bpy.props.EnumProperty(
        name="Модификатор",
        description="Начните вводить название на английском или русском",
        items=get_modifier_enum_items,
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        try:
            bpy.ops.object.modifier_add(type=self.modifier_type)
        except (RuntimeError, TypeError) as exc:
            self.report({'ERROR'}, f"Не удалось добавить модификатор: {exc}")
            return {'CANCELLED'}

        label = next(
            (lbl for ident, lbl, _ in _enum_items_cache if ident == self.modifier_type),
            self.modifier_type,
        )
        self.report({'INFO'}, f"Добавлен модификатор: {label}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}


class OBJECT_OT_modifier_search_en_ru_deferred(bpy.types.Operator):
    """Обёртка для вызова поиска ИЗ уже открытого меню "Добавить модификатор".

    У Blender есть известная особенность: если открыть invoke_search_popup()
    прямо во время обработки клика, которым закрывается родительское меню,
    тот же клик "проваливается" в новый попап и сразу подтверждает пункт
    под курсором (обычно первый по алфавиту). Поэтому здесь запуск реального
    поиска откладывается на следующий тик цикла событий через bpy.app.timers —
    к этому моменту клик, закрывший меню, уже полностью обработан.
    """
    bl_idname = "object.modifier_search_en_ru_deferred"
    bl_label = "Поиск модификатора (EN/RU)"
    bl_description = "Найти модификатор по английскому или русскому названию и добавить его к объекту"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        def _open_search():
            bpy.ops.object.modifier_search_en_ru('INVOKE_DEFAULT')
            return None  # не повторять таймер

        bpy.app.timers.register(_open_search, first_interval=0.0)
        return {'FINISHED'}


def draw_menu_entry(self, context):
    layout = self.layout
    layout.operator(
        OBJECT_OT_modifier_search_en_ru_deferred.bl_idname,
        text="Поиск EN/RU…",
        icon='VIEWZOOM',
    )
    layout.separator()


def draw_panel_button(self, context):
    self.layout.operator(
        OBJECT_OT_modifier_search_en_ru.bl_idname,
        text="Поиск модификатора EN/RU",
        icon='VIEWZOOM',
    )


classes = (
    OBJECT_OT_modifier_search_en_ru,
    OBJECT_OT_modifier_search_en_ru_deferred,
)
addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Пункт в самом верху меню "Добавить модификатор"
    try:
        bpy.types.OBJECT_MT_modifier_add.prepend(draw_menu_entry)
    except Exception as exc:
        print(f"[Modifier Search RU/EN] Не удалось встроиться в OBJECT_MT_modifier_add: {exc}")

    # Кнопка над списком модификаторов на вкладке свойств
    try:
        bpy.types.DATA_PT_modifiers.prepend(draw_panel_button)
    except Exception as exc:
        print(f"[Modifier Search RU/EN] Не удалось встроиться в DATA_PT_modifiers: {exc}")

    # Горячая клавиша Ctrl+F3 в 3D Viewport (режим объекта)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
        kmi = km.keymap_items.new(
            OBJECT_OT_modifier_search_en_ru.bl_idname,
            type='F3', value='PRESS', ctrl=True,
        )
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    try:
        bpy.types.DATA_PT_modifiers.remove(draw_panel_button)
    except Exception:
        pass
    try:
        bpy.types.OBJECT_MT_modifier_add.remove(draw_menu_entry)
    except Exception:
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
