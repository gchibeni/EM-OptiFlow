import bpy
import os
from bpy.types import Operator, PropertyGroup, UIList
from bpy.props import StringProperty, EnumProperty, IntProperty, BoolProperty, FloatProperty, CollectionProperty
from ..core import constants, helpers
from ..ui.file_dialogs import dir_input, prop_input, file_input, path_input

# region Textures

_SUPPORTED_TEX_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.webp'})

# Temporary storage while OPT_OT_add_item is open.
# Structure: { group_name: [absolute_path, ...] }
# group_name == "" means the root / flat-file selection.
_tex_groups: dict = {}
_tex_current_group: int = 0
_tex_btn_mouse_pos: tuple = (0, 0)

# Aliases checked in order — ORM must come before Occlusion because
# _occlussionroughnessmetallic starts with _occl.
_TEX_ALIASES = [
    ('Color',        ['_color', '_base', '_diffuse', '-color', '-base', '-diffuse']),
    ('ORM',          ['_occlussionroughnessmetallic', '_orm', '-occlussionroughnessmetallic', '-orm']),
    ('Normal',       ['_norm', '_nrm', '-norm', '-nrm']),
    ('Occlusion',    ['_ao', '_occl', '-ao', '-occl']),
    ('Roughness',    ['_rough', '-rough']),
    ('Metallic',     ['_metal', '-metal']),
    ('Specular',     ['_spec', '-spec']),
    ('Reflection',   ['_refl', '-refl']),
    ('Emission',     ['_emiss', '-emiss']),
    ('Opacity',      ['_opacity', '_alpha', '-opacity', '-alpha']),
    ('Height',       ['_height', '_disp', '-height', '-disp']),
    ('Glossiness',   ['_gloss', '-gloss']),
    ('SSS',          ['_sss', '_subs', '-sss', '-subs']),
    ('Transmission', ['_trans', '-trans']),
    ('Sheen',        ['_sheen', '-sheen']),
    ('Coat',         ['_clearcoat', '_coat', '-clearcoat', '-coat']),
    ('Mask',         ['_mask', '-mask']),
]

_TEX_DISPLAY_ORDER = [
    'Color', 'Roughness', 'Reflection', 'Metallic', 'ORM', 'Occlusion',
    'Specular', 'Glossiness', 'SSS', 'Transmission', 'Sheen', 'Coat',
    'Emission', 'Opacity', 'Height', 'Normal', 'Mask',
]


class TexDisplayItem(PropertyGroup):
    """One row in the texture preview list inside the Add Item dialog."""
    label: StringProperty()  # type: ignore


class OPT_UL_tex_list(UIList):
    """Scrollable read-only texture list for the Add Item dialog."""
    bl_idname = "OPT_UL_tex_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        if ": " in item.label:
            type_part, name_part = item.label.split(": ", 1)
            split = row.split(factor=0.23)
            split.label(text=type_part + ":")
            split.label(text=name_part)
        else:
            row.label(text=item.label)
        if index == getattr(active_data, active_propname, -1):
            op = row.operator("optiflow.remove_texture_map", text="", icon="X", emboss=False)
            op.label = item.label

    def draw_filter(self, context, layout):
        """Draw the search filter input."""
        row = layout.row()
        row.prop(self, "filter_name", text="")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flt_flags = bpy.types.UI_UL_list.filter_items_by_name(
            self.filter_name, self.bitflag_filter_item, items, "label",
        )
        return flt_flags, []


def _rebuild_tex_display(scene):
    """Rebuild scene.optiflow_tex_display from the current _tex_groups entry."""
    if not hasattr(scene, "optiflow_tex_display"):
        return
    col = scene.optiflow_tex_display
    col.clear()
    if not _tex_groups:
        return
    group_keys   = list(_tex_groups.keys())
    group_idx    = max(0, min(_tex_current_group, len(group_keys) - 1))
    current_paths = _tex_groups[group_keys[group_idx]]
    by_type = {}
    for path in current_paths:
        fname = os.path.basename(path)
        t     = _classify_tex(fname)
        if t is not None:
            by_type.setdefault(t, []).append(fname)
    for tex_type in _TEX_DISPLAY_ORDER:
        names = sorted(by_type.get(tex_type, []))
        for i, name in enumerate(names):
            entry = col.add()
            entry.label = (f"{tex_type}: {name}" if len(names) == 1
                           else f"{tex_type} {i + 1}: {name}")


def _classify_tex(filename):
    """Return the texture type label for a given filename, or None if unrecognised."""
    stem = os.path.splitext(filename)[0].lower()
    for tex_type, aliases in _TEX_ALIASES:
        for alias in aliases:
            if alias in stem:
                return tex_type
    return None


def _scan_tex_folder(root):
    """BFS-scan root for images up to depth 4, at most 256 folders total.

    Returns a dict mapping group_name -> [abs_path, ...].
    The root folder itself gets group_name ""; subfolders get their
    POSIX-style path relative to root (e.g. "Sub1/Sub2/Sub3").
    """
    groups = {}
    queue = [(root, 0)]
    folders_scanned = 0
    while queue and folders_scanned < 256:
        dirpath, depth = queue.pop(0)
        folders_scanned += 1
        try:
            entries = list(os.scandir(dirpath))
        except OSError:
            continue
        images = [
            e.path for e in entries
            if e.is_file()
            and os.path.splitext(e.name)[1].lower() in _SUPPORTED_TEX_EXTS
        ]
        if images:
            rel = os.path.relpath(dirpath, root)
            group_name = "" if rel == '.' else rel.replace(os.sep, '/')
            groups[group_name] = images
        if depth < 4:
            subdirs = sorted(
                e.path for e in entries
                if e.is_dir(follow_symlinks=False)
            )
            queue.extend((d, depth + 1) for d in subdirs)
    return groups


class OPT_OT_select_textures(Operator):
    """Open a file browser to pick texture images or a folder."""
    bl_idname  = "optiflow.select_textures"
    bl_label   = "Select Textures/Folder"
    bl_description = "Select texture(s) or a folder containing texture(s)"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory:   StringProperty(subtype='DIR_PATH', options={'HIDDEN'})  # type: ignore
    files:       CollectionProperty(                                       # type: ignore
        type=bpy.types.OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    filter_glob: StringProperty(                                           # type: ignore
        default="*.jpg;*.jpeg;*.png;*.webp",
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        global _tex_btn_mouse_pos
        _tex_btn_mouse_pos = (event.mouse_x, event.mouse_y)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        global _tex_groups, _tex_current_group
        _tex_groups.clear()
        _tex_current_group = 0
        dir_abs = bpy.path.abspath(self.directory)
        file_names = [
            f.name for f in self.files
            if f.name and os.path.isfile(os.path.join(dir_abs, f.name))
            and os.path.splitext(f.name)[1].lower() in _SUPPORTED_TEX_EXTS
        ]
        if file_names:
            paths = [
                os.path.join(dir_abs, n) for n in file_names
                if _classify_tex(n) is not None
            ]
            if paths:
                _tex_groups[""] = paths
        else:
            for group_name, paths in _scan_tex_folder(dir_abs).items():
                filtered = [p for p in paths if _classify_tex(os.path.basename(p)) is not None]
                if filtered:
                    _tex_groups[group_name] = filtered
        _rebuild_tex_display(context.scene)
        helpers.snap_cursor(*_tex_btn_mouse_pos)
        return {'FINISHED'}


class OPT_OT_clear_textures(Operator):
    """Clear all texture groups from the Add Item dialog."""
    bl_idname  = "optiflow.clear_textures"
    bl_label   = "Clear Textures"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _tex_groups, _tex_current_group
        _tex_groups.clear()
        _tex_current_group = 0
        if hasattr(context.scene, "optiflow_tex_display"):
            context.scene.optiflow_tex_display.clear()
        return {'FINISHED'}


class OPT_OT_remove_tex_group(Operator):
    """Remove the current texture group from the list."""
    bl_idname  = "optiflow.remove_tex_group"
    bl_label   = "Remove Texture Group"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _tex_groups, _tex_current_group
        if not _tex_groups:
            return {'CANCELLED'}
        group_keys = list(_tex_groups.keys())
        key = group_keys[max(0, min(_tex_current_group, len(group_keys) - 1))]
        del _tex_groups[key]
        _tex_current_group = max(0, min(_tex_current_group, len(_tex_groups) - 1))
        _rebuild_tex_display(context.scene)
        return {'FINISHED'}


class OPT_OT_remove_texture_map(Operator):
    """Remove this texture from the current group."""
    bl_idname  = "optiflow.remove_texture_map"
    bl_label   = "Remove Texture"
    bl_options = {'INTERNAL'}

    label: StringProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        global _tex_groups, _tex_current_group
        if not _tex_groups:
            return {'CANCELLED'}
        filename = self.label.split(": ", 1)[-1] if ": " in self.label else self.label
        group_keys = list(_tex_groups.keys())
        key = group_keys[max(0, min(_tex_current_group, len(group_keys) - 1))]
        new_paths = [p for p in _tex_groups[key] if os.path.basename(p) != filename]
        if len(new_paths) == len(_tex_groups[key]):
            return {'CANCELLED'}
        if new_paths:
            _tex_groups[key] = new_paths
        else:
            del _tex_groups[key]
            _tex_current_group = max(0, min(_tex_current_group, len(_tex_groups) - 1))
        _rebuild_tex_display(context.scene)
        return {'FINISHED'}


class OPT_OT_tex_group_nav(Operator):
    """Navigate between texture groups in the Add Item dialog."""
    bl_idname  = "optiflow.tex_group_nav"
    bl_label   = "Navigate"
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=[  # type: ignore
        ('FIRST', 'First', ''),
        ('PREV',  'Prev',  ''),
        ('NEXT',  'Next',  ''),
        ('LAST',  'Last',  ''),
    ])

    @classmethod
    def description(cls, context, properties):
        return {
            'FIRST': "Go to first texture group",
            'PREV':  "Go to previous texture group",
            'NEXT':  "Go to next texture group",
            'LAST':  "Go to last texture group",
        }.get(properties.action, "")

    def execute(self, context):
        global _tex_current_group
        n = len(_tex_groups)
        if n == 0:
            return {'CANCELLED'}
        if self.action == 'FIRST':
            _tex_current_group = 0
        elif self.action == 'PREV':
            _tex_current_group = max(0, _tex_current_group - 1)
        elif self.action == 'NEXT':
            _tex_current_group = min(n - 1, _tex_current_group + 1)
        elif self.action == 'LAST':
            _tex_current_group = n - 1
        _rebuild_tex_display(context.scene)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}

# endregion

# region Placeholder

class placeholder(Operator):
    """Stub operator for unimplemented features."""
    bl_idname  = "optiflow.placeholder"
    bl_label   = "Placeholder"
    bl_description = "Placeholder"

    def execute(self, context):
        return {'FINISHED'}

class OPT_OT_wip_popup(Operator):
    """Generic work in progress dialog."""
    bl_idname  = "optiflow.wip_popup"
    bl_label   = "Work In Progress"
    bl_description = "\u200b"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=220)

    def draw(self, context):
        self.layout.label(text="Work in progress.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}


# endregion

# region Groups

class OPT_OT_add_group(Operator):
    """Create a new group below the current selection."""
    bl_idname  = "optiflow.add_group"
    bl_label   = "Add Group"
    bl_description = "Add a new group."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene  = context.scene
        groups = scene.optiflow_groups
        existing = {g.name for g in groups}
        n = 1
        while f"NEW_GROUP_{n}" in existing:
            n += 1
        name        = f"NEW_GROUP_{n}"
        g           = groups.add()
        g.name      = name
        g.prev_name = name
        g.expanded  = True
        new_gi = len(groups) - 1
        # Insert below the currently selected group
        fe = helpers.get_active_entry(scene)
        insert_after = (fe.group_index + 1) if fe else new_gi
        if insert_after < new_gi:
            groups.move(new_gi, insert_after)
            new_gi = insert_after
        helpers.rebuild_and_select(scene, new_gi, -1)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}


class OPT_OT_confirm_merge(Operator):
    """Confirm and merge two groups with the same name."""
    bl_idname  = "optiflow.confirm_merge"
    bl_label   = "Merge Groups"
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        scene = context.scene
        if scene.get("_optiflow_merge_gi", -1) < 0:
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(
            self, width=300, confirm_text="Merge",
        )

    def draw(self, context):
        name = context.scene.get("_optiflow_merge_name", "")
        self.layout.label(text=f'A group named "{name}" already exists.')
        self.layout.separator(type='LINE')

    def execute(self, context):
        scene    = context.scene
        merge_gi = scene.get("_optiflow_merge_gi", -1)
        dup_gi   = scene.get("_optiflow_merge_dup_gi", -1)
        if merge_gi < 0 or dup_gi < 0:
            return {'CANCELLED'}
        groups = scene.optiflow_groups
        if merge_gi >= len(groups) or dup_gi >= len(groups):
            return {'CANCELLED'}
        src, dst = groups[merge_gi], groups[dup_gi]
        for item in src.items:
            new_item      = dst.items.add()
            new_item.name = item.name
            helpers.clone_item_props(item, new_item)
            helpers.clone_item_refs(item, new_item)
        groups.remove(merge_gi)
        scene["_optiflow_merge_gi"]    = -1
        scene["_optiflow_merge_dup_gi"] = -1
        helpers.rebuild_flat_entries(scene)
        return {'FINISHED'}

# endregion

# region Add

_3D_IMPORTERS = {
    '.fbx':  lambda fp: bpy.ops.import_scene.fbx(filepath=fp, use_image_search=False),
    '.glb':  lambda fp: bpy.ops.import_scene.gltf(filepath=fp),
    '.gltf': lambda fp: bpy.ops.import_scene.gltf(filepath=fp),
    '.obj':  lambda fp: bpy.ops.wm.obj_import(filepath=fp),
    '.abc':  lambda fp: bpy.ops.wm.alembic_import(filepath=fp),
    '.usd':  lambda fp: bpy.ops.wm.usd_import(filepath=fp),
    '.usda': lambda fp: bpy.ops.wm.usd_import(filepath=fp),
    '.usdc': lambda fp: bpy.ops.wm.usd_import(filepath=fp),
    '.usdz': lambda fp: bpy.ops.wm.usd_import(filepath=fp),
    '.dae':  lambda fp: bpy.ops.wm.collada_import(filepath=fp),
    '.stl':  lambda fp: bpy.ops.wm.stl_import(filepath=fp),
    '.ply':  lambda fp: bpy.ops.wm.ply_import(filepath=fp),
    '.x3d':  lambda fp: bpy.ops.import_scene.x3d(filepath=fp),
}


def _import_3d(filepath):
    """Import a 3D file, return new objects or None on unsupported/failure."""
    fn = _3D_IMPORTERS.get(os.path.splitext(filepath)[1].lower())
    if fn is None:
        return None
    before = set(bpy.data.objects[:])
    try:
        result = fn(filepath)
    except Exception:
        return None
    if isinstance(result, set) and 'CANCELLED' in result:
        return None
    return [o for o in bpy.data.objects if o not in before]


def _strip_materials(objs):
    for obj in objs:
        if obj.type == 'MESH' and obj.data:
            obj.data.materials.clear()


def _push_actions_to_nla(objs):
    for obj in objs:
        if not (obj.animation_data and obj.animation_data.action):
            continue
        action = obj.animation_data.action
        track  = obj.animation_data.nla_tracks.new()
        track.name = action.name
        track.strips.new(action.name, int(action.frame_range[0]), action)
        obj.animation_data.action = None


def _mark_colliders(objs):
    """Give imported collider objects a COL_ prefix so the rename system picks it up."""
    for i, obj in enumerate(objs):
        tmp = f"COL_tmp_{i}"
        obj.name = tmp
        if obj.type == 'MESH' and obj.data:
            obj.data.name = tmp


def _derive_name_from_color(color_path):
    """Strip recognized color-type suffixes from a texture filename to form an item name."""
    stem = os.path.splitext(os.path.basename(color_path))[0]
    for suffix in ('_basecolor', '-basecolor', '_color', '-color', '_diffuse', '-diffuse'):
        idx = stem.lower().find(suffix)
        if idx != -1:
            stem = stem[:idx]
            break
    return helpers.sanitize_name(stem)


def _next_new_object_name(group):
    existing = {it.name for it in group.items}
    n = 1
    while f"NEW_OBJECT_{n}" in existing:
        n += 1
    return f"NEW_OBJECT_{n}"


def _split_preset_paths(gi, ii_start, ii_end, paths):
    """
    For each preset item created (ii_start..ii_end-1), build a path list that
    contains the item's own color texture plus all non-color shared maps.
    Returns list of (gi, ii, filtered_paths).
    """
    shared   = [p for p in paths if _classify_tex(os.path.basename(p)) != 'Color']
    colors   = [p for p in paths if _classify_tex(os.path.basename(p)) == 'Color']
    result   = []
    n_items  = ii_end - ii_start
    for local_idx in range(n_items):
        color_path = colors[local_idx] if local_idx < len(colors) else (colors[-1] if colors else None)
        item_paths = ([color_path] if color_path else []) + shared
        result.append((gi, ii_start + local_idx, item_paths))
    return result


def _add_item(context, group, item_type, preset, objs, name, alias=""):
    """Create one item in group, link objects (or apply preset mesh), then set name."""
    it           = group.items.add()
    it.item_type = item_type
    it.preset    = preset
    it.alias     = alias
    if item_type == 'PRESET':
        it.name = name             # sanitise + uniqueness; no objects yet → rename is no-op
        _apply_preset(context, it, preset)
    else:
        for obj in objs:
            it.objects.add().object = obj
        it.name = name             # fires rename with all objects already present
    return it


class OPT_OT_add_empty(Operator):
    """Create an empty item in the current group."""
    bl_idname  = "optiflow.add_empty"
    bl_label   = "Add Empty"
    bl_description = "Add a new empty item"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        group, gi = helpers.ensure_default_group(scene)
        existing = {it.name for it in group.items}
        n = 1
        while f"NEW_OBJECT_{n}" in existing:
            n += 1
        it           = group.items.add()
        it.name      = f"NEW_OBJECT_{n}"
        it.item_type = 'OBJECT'
        if not group.expanded:
            group.expanded = True
        new_ii = len(group.items) - 1
        helpers.rebuild_and_select(scene, gi, new_ii)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

class OPT_OT_add_item(Operator):
    """Create an item in the current group."""
    bl_idname  = "optiflow.add_item"
    bl_label   = "Add Item"
    bl_description = "Add a new imported item"
    bl_options = {'INTERNAL', 'UNDO'}

    item_alias: StringProperty(name="Alias", description="Descriptive for identification only", default="")  # type: ignore
    item_mode: EnumProperty(
        name="Mode",
        items=constants.ITEM_TYPE,
        default='OBJECT',
    )  # type: ignore
    item_preset: EnumProperty(
        name="Mesh", items=lambda self, ctx: constants.MESH_TYPE,
    )  # type: ignore
    preview_image_name: StringProperty(name="Texture", default="")  # type: ignore

    tex_roughness_enabled: BoolProperty(name="Toggle Roughness", description="Replaces roughness — multiplies values if a map is provided (using a mask if available)", default=False)  # type: ignore
    tex_roughness: FloatProperty(name="Roughness", subtype='PERCENTAGE', min=0.0, max=100.0, default=50.0)  # type: ignore
    tex_metallic_enabled: BoolProperty(name="Toggle Metallic", description="Replaces metallic — multiplies values if a map is provided (using a mask if available)", default=False)  # type: ignore
    tex_metallic: FloatProperty(name="Metallic", subtype='PERCENTAGE', min=0.0, max=100.0, default=50.0)  # type: ignore
    tex_size_enabled: BoolProperty(name="Toggle Resize", default=False)  # type: ignore
    tex_size: EnumProperty(
        name="Size",
        items=constants.TEXTURE_SIZES,
        default='4096',
    )  # type: ignore
    tex_compression_enabled: BoolProperty(name="Toggle Compression", default=False)  # type: ignore
    tex_compression: EnumProperty(
        name="Compression",
        items=[
            ('AUTO', 'Auto', 'Preserve details — Minumum quality'),
            ('SMALLEST', 'Smallest Size', 'Lighter size, Lower quality'),
            ('BALANCED', 'Balanced', 'Moderate size — Medium quality'),
            ('HIGHER', 'Higher Quality', 'Heavier size — Higher quality'),
        ],
        default='AUTO',
    )  # type: ignore
    tex_format_enabled: BoolProperty(name="Toggle Reformat", default=False)  # type: ignore
    tex_format: EnumProperty(
        name="Format",
        items=[
            ('JPG', 'JPG', ''),
            ('PNG', 'PNG', ''),
            ('WEBP', 'WEBP', ''),
        ],
    )  # type: ignore

    def invoke(self, context, event):
        global _tex_groups, _tex_current_group
        _tex_groups.clear()
        _tex_current_group = 0
        if hasattr(context.scene, "optiflow_tex_display"):
            context.scene.optiflow_tex_display.clear()
        context.scene.optiflow_add_obj_path = ""
        context.scene.optiflow_add_col_path = ""
        self.item_alias             = ""
        self.item_preset            = constants.MESH_TYPE[0][0] if constants.MESH_TYPE else 'TILE'
        self.tex_roughness_enabled  = False
        self.tex_roughness          = 50.0
        self.tex_metallic_enabled   = False
        self.tex_metallic           = 50.0
        self.tex_size_enabled       = False
        self.tex_size               = '4096'
        self.tex_compression_enabled = False
        self.tex_compression        = 'AUTO'
        self.tex_format_enabled     = False
        self.tex_format             = 'JPG'
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "item_mode", expand=True)
        layout.separator(type='LINE')
        if self.item_mode == "OBJECT":
            file_input(layout, context.scene, "Object:", "optiflow_add_obj_path",
                       file_types="fbx,obj,glb,gltf,abc,usd,usda,usdc,dae,stl,ply,x3d")
            file_input(layout, context.scene, "Collider:", "optiflow_add_col_path",
                       file_types="fbx,obj,glb,gltf,abc,usd,usda,usdc,dae,stl,ply,x3d")
        elif self.item_mode == "PRESET":
            prop_input(layout, self, "Mesh:", "item_preset")
        prop_input(layout, self, "Alias:", "item_alias")
        layout.separator(type='LINE')
        row = layout.row(align=True)
        row.operator("optiflow.select_textures", text="Add Texture(s)")
        if _tex_groups:
            row.operator("optiflow.clear_textures", text="", icon='X')
        else:
            row.operator("optiflow.select_textures", text="", icon='IMPORT')
        layout.separator(type='LINE')
        if _tex_groups:
            group_keys = list(_tex_groups.keys())
            n_groups   = len(group_keys)
            group_idx  = max(0, min(_tex_current_group, n_groups - 1))

            if n_groups > 1:
                display_name = group_keys[group_idx] if group_keys[group_idx] else "\u2014\u2014"
                count_str    = f"{group_idx + 1:02d}/{n_groups:02d}"
                row = layout.row(align=True)
                sub = row.row(align=True)
                sub.enabled = group_idx > 0
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_LEFT_BAR")
                op.action = 'FIRST'
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_LEFT")
                op.action = 'PREV'
                mid = row.row()
                mid.alignment = 'CENTER'
                mid.label(text=f"{display_name} ({count_str})" if group_keys[group_idx] else f"{display_name}")
                sub = row.row(align=True)
                sub.enabled = group_idx < n_groups - 1
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_RIGHT")
                op.action = 'NEXT'
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_RIGHT_BAR")
                op.action = 'LAST'
                last = row.row(align=True)
                last.operator("optiflow.remove_tex_group", text="", icon='TRASH')

            layout.template_list(
                "OPT_UL_tex_list", "",
                context.scene, "optiflow_tex_display",
                context.scene, "optiflow_tex_display_index",
                rows=6,
            )
            for label, enabled_prop, value_prop, slider in [
                ("Roughness:", "tex_roughness_enabled", "tex_roughness",    True),
                ("Metallic:",  "tex_metallic_enabled",  "tex_metallic",     True),
                ("Size:",      "tex_size_enabled",       "tex_size",         False),
                ("Compression:", "tex_compression_enabled", "tex_compression", False),
                ("Format:",    "tex_format_enabled",    "tex_format",       False),
            ]:
                split = layout.split(factor=0.23)
                split.label(text=label)
                row = split.row(align=True)
                row.prop(self, enabled_prop, text="", icon="DOT", toggle=True)
                sub = row.row(align=True)
                sub.enabled = getattr(self, enabled_prop)
                sub.prop(self, value_prop, text="", slider=slider)

    def execute(self, context):
        scene = context.scene
        # Snapshot all override values NOW as plain Python primitives.
        # operator properties must not be read after any bpy call because
        # Blender may reset the operator state during the UNDO push.
        overrides = {
            'item_mode':           str(self.item_mode),
            'roughness_enabled':   bool(self.tex_roughness_enabled),
            'roughness':           float(self.tex_roughness),
            'metallic_enabled':    bool(self.tex_metallic_enabled),
            'metallic':            float(self.tex_metallic),
            'size_enabled':        bool(self.tex_size_enabled),
            'size':                str(self.tex_size),
            'compression_enabled': bool(self.tex_compression_enabled),
            'compression':         str(self.tex_compression),
            'format_enabled':      bool(self.tex_format_enabled),
            'format':              str(self.tex_format),
        }
        if self.item_mode == 'OBJECT':
            return self._exec_object(context, scene, overrides)
        return self._exec_preset(context, scene, overrides)

    def _exec_object(self, context, scene, overrides):
        obj_path = bpy.path.abspath(scene.optiflow_add_obj_path) if scene.optiflow_add_obj_path else ""
        if not obj_path or not os.path.isfile(obj_path):
            self.report({'ERROR'}, "Invalid object path")
            return {'CANCELLED'}

        obj_objs = _import_3d(obj_path)
        if obj_objs is None:
            self.report({'ERROR'}, f"Unsupported format: {os.path.splitext(obj_path)[1]}")
            return {'CANCELLED'}
        if not obj_objs:
            self.report({'ERROR'}, "No objects imported from the object file")
            return {'CANCELLED'}
        _strip_materials(obj_objs)
        _push_actions_to_nla(obj_objs)

        col_objs = []
        if scene.optiflow_add_col_path:
            col_path = bpy.path.abspath(scene.optiflow_add_col_path)
            if not os.path.isfile(col_path):
                self.report({'WARNING'}, "Collider path is invalid — skipping")
            else:
                imported = _import_3d(col_path)
                if not imported:
                    self.report({'WARNING'}, "No objects imported from collider — skipping")
                else:
                    _strip_materials(imported)
                    _mark_colliders(imported)
                    col_objs = imported

        group, gi = helpers.ensure_default_group(scene)

        name = ""
        tex_paths = []
        if _tex_groups:
            group_keys = list(_tex_groups.keys())
            tex_paths  = _tex_groups[group_keys[max(0, min(_tex_current_group, len(group_keys) - 1))]]
            for p in tex_paths:
                if _classify_tex(os.path.basename(p)) == 'Color':
                    name = _derive_name_from_color(p)
                    break
        if not name:
            name = _next_new_object_name(group)

        ii = len(group.items)
        _add_item(context, group, 'OBJECT', self.item_preset, obj_objs + col_objs, name, self.item_alias)
        helpers.rebuild_and_select(scene, gi, ii)
        helpers.tag_redraw_all(context)

        if tex_paths:
            self._schedule_import(scene, gi, ii, tex_paths, overrides)

        return {'FINISHED'}

    def _schedule_import(self, scene, gi, ii, tex_paths, overrides):
        """Kick off async texture import using the pre-captured overrides snapshot."""
        from .tex_import import schedule_tex_import

        skip = {'COL', 'PLACER', 'SNAP', 'GUIDE'}
        try:
            item = scene.optiflow_groups[gi].items[ii]
        except (IndexError, KeyError):
            return
        mesh_names = [
            ref.object.name for ref in item.objects
            if ref.object and ref.object.type == 'MESH'
            and helpers.get_prefix(ref.object) not in skip
        ]
        if not mesh_names:
            return

        schedule_tex_import(gi, ii, mesh_names, tex_paths, overrides, scene)

    def _exec_preset(self, context, scene, overrides):
        pending = []  # list of (gi, ii, item_paths)
        if len(_tex_groups) <= 1:
            group, gi = helpers.ensure_default_group(scene)
            paths     = list(_tex_groups.values())[0] if _tex_groups else []
            ii_start  = len(group.items)
            self._make_preset_items(context, group, paths)
            ii = max(0, len(group.items) - 1)
            helpers.rebuild_and_select(scene, gi, ii)
            if paths:
                pending.extend(_split_preset_paths(gi, ii_start, len(group.items), paths))
        else:
            last_gi = last_ii = 0
            for gname, paths in _tex_groups.items():
                safe   = helpers.sanitize_group_name(gname) if gname else "GROUP"
                groups = scene.optiflow_groups
                gi     = next((i for i, g in enumerate(groups) if g.name == safe), -1)
                if gi == -1:
                    g           = groups.add()
                    g.name      = safe
                    g.prev_name = safe
                    g.expanded  = True
                    gi          = len(groups) - 1
                group    = groups[gi]
                ii_start = len(group.items)
                self._make_preset_items(context, group, paths)
                if group.items:
                    last_gi, last_ii = gi, len(group.items) - 1
                if paths:
                    pending.extend(_split_preset_paths(gi, ii_start, len(group.items), paths))
            helpers.rebuild_and_select(scene, last_gi, last_ii)

        helpers.tag_redraw_all(context)

        for gi, ii, item_paths in pending:
            self._schedule_import(scene, gi, ii, item_paths, overrides)

        return {'FINISHED'}

    def _make_preset_items(self, context, group, paths):
        colors = [p for p in paths if _classify_tex(os.path.basename(p)) == 'Color']
        if not colors:
            _add_item(context, group, 'PRESET', self.item_preset, [], _next_new_object_name(group), self.item_alias)
            return
        for color_path in colors:
            name = _derive_name_from_color(color_path) or _next_new_object_name(group)
            _add_item(context, group, 'PRESET', self.item_preset, [], name, self.item_alias)

# endregion

# region Edit

class OPT_OT_edit_item(Operator):
    """Edit the selected item properties and object references."""
    bl_idname  = "optiflow.edit_item"
    bl_label   = "Edit Item"
    bl_description = "Edit the selected item."
    bl_options = {'UNDO', 'INTERNAL'}

    edit_name:      StringProperty(name="Name")       # type: ignore
    edit_alias:     StringProperty(name="Alias")       # type: ignore
    edit_item_type: EnumProperty(
        name="Type", items=constants.ITEM_TYPE,
    )  # type: ignore
    edit_preset: EnumProperty(
        name="Mesh", items=lambda self, ctx: constants.MESH_TYPE,
    )  # type: ignore

    def invoke(self, context, event):
        fe = helpers.get_active_entry(context.scene)
        if fe is None or fe.entry_type == 'GROUP':
            return {'CANCELLED'}
        item = context.scene.optiflow_groups[fe.group_index].items[fe.item_index]
        # Snapshot current values into the buffer
        self.edit_name      = item.name
        self.edit_alias     = item.alias
        self.edit_item_type = item.item_type
        self.edit_preset = item.preset
        if not item.objects or item.objects[-1].object is not None:
            item.objects.add()
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        from ..ui.file_dialogs import prop_input
        fe   = helpers.get_active_entry(context.scene)
        item = context.scene.optiflow_groups[fe.group_index].items[fe.item_index]
        layout = self.layout
        prop_input(layout, self, "Name:", "edit_name")
        prop_input(layout, self, "Alias:", "edit_alias")
        prop_input(layout, self, "Type:", "edit_item_type")
        if self.edit_item_type == 'PRESET':
            layout.separator(type='LINE')
            prop_input(layout, self, "Mesh:", "edit_preset")
        layout.separator(type='LINE')
        layout.label(text="Objects:")
        box = layout.box()
        for i, ref in enumerate(item.objects):
            row = box.row(align=True)
            row.prop(ref, "object", text="")
            is_trailing_empty = (ref.object is None and i == len(item.objects) - 1)
            if not is_trailing_empty:
                op           = row.operator("optiflow.edit_item_remove_object", text="", icon='TRASH')
                op.item_gi   = fe.group_index
                op.item_ii   = fe.item_index
                op.ref_index = i
        layout.separator(type='LINE')

    def execute(self, context):
        scene = context.scene
        fe    = helpers.get_active_entry(scene)
        item  = scene.optiflow_groups[fe.group_index].items[fe.item_index]
        item.item_type = self.edit_item_type
        item.preset = self.edit_preset
        item.name      = self.edit_name
        item.alias     = self.edit_alias
        if self.edit_item_type == 'PRESET':
            _apply_preset(context, item, self.edit_preset)
        helpers.rebuild_flat_entries(scene)
        return {'FINISHED'}

class OPT_OT_edit_item_remove_object(Operator):
    """Unassign an object reference from an item."""
    bl_idname  = "optiflow.edit_item_remove_object"
    bl_label   = "Remove Object"
    bl_description = "Unassign object from the item"
    bl_options = {'UNDO', 'INTERNAL'}

    item_gi:   IntProperty(options={'HIDDEN'})  # type: ignore
    item_ii:   IntProperty(options={'HIDDEN'})  # type: ignore
    ref_index: IntProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        item = context.scene.optiflow_groups[self.item_gi].items[self.item_ii]
        item.objects.remove(self.ref_index)
        return {'FINISHED'}

# endregion

# region Duplicate

class OPT_OT_duplicate(Operator):
    """Duplicate the selected group or item with all objects."""
    bl_idname  = "optiflow.duplicate"
    bl_label   = "Duplicate"
    bl_description = "Duplicate the selected item.\nIncluding all object references."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        fe = helpers.get_active_entry(scene)
        if fe is None:
            return {'CANCELLED'}
        groups     = scene.optiflow_groups
        gi         = fe.group_index
        collection = context.collection or context.scene.collection
        if fe.entry_type == 'GROUP':
            self._duplicate_group(scene, groups, gi, collection)
        else:
            self._duplicate_item(scene, groups, gi, fe.item_index, collection)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

    def _duplicate_group(self, scene, groups, gi, collection):
        """Clone a group including all items and their scene objects."""
        src      = groups[gi]
        new_name = helpers.copy_name(src.name, {g.name for g in groups})
        dst          = groups.add()
        dst.name     = new_name
        dst.prev_name = new_name
        dst.expanded = src.expanded
        for item in src.items:
            ni      = dst.items.add()
            ni.name = item.name
            helpers.clone_item_props(item, ni)
            helpers.clone_item_objects(item, ni, collection)
        groups.move(len(groups) - 1, gi + 1)
        helpers.rebuild_and_select(scene, gi + 1, -1)

    def _duplicate_item(self, scene, groups, gi, ii, collection):
        """Clone an item with deep copied objects within the same group."""
        group    = groups[gi]
        src      = group.items[ii]
        new_name = helpers.copy_name(src.name, {it.name for it in group.items})
        dst      = group.items.add()
        dst.name = new_name
        helpers.clone_item_props(src, dst)
        helpers.clone_item_objects(src, dst, collection)
        new_ii = len(group.items) - 1
        group.items.move(new_ii, ii + 1)
        helpers.rebuild_and_select(scene, gi, ii + 1)

# endregion

# region Delete

class OPT_OT_delete(Operator):
    """Delete the selected group or item and its exclusive objects."""
    bl_idname  = "optiflow.delete"
    bl_label   = "Delete"
    bl_description = "Delete the selected item.\nExclusive referenced objects will also be deleted.\n\nCtrl+Click: delete item only, keep objects in scene."
    bl_options = {'UNDO'}

    keep_objects: BoolProperty(default=False, options={'SKIP_SAVE'})  # type: ignore

    def invoke(self, context, event):
        self.keep_objects = event.ctrl
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        idx   = scene.optiflow_flat_index
        fe    = helpers.get_active_entry(scene)
        if fe is None:
            return {'CANCELLED'}
        groups = scene.optiflow_groups
        gi     = fe.group_index
        if fe.entry_type == 'GROUP':
            self._delete_group(groups, gi)
        else:
            self._delete_item(groups, gi, fe.item_index)
        helpers.rebuild_flat_entries(scene)
        scene.optiflow_flat_index = max(
            0, min(idx, len(scene.optiflow_flat_entries) - 1),
        )
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

    def _delete_group(self, groups, gi):
        """Remove a group and optionally delete its exclusive scene objects."""
        src = groups[gi]
        to_delete = {}
        if not self.keep_objects:
            for item in src.items:
                for ref in item.objects:
                    if ref.object is not None:
                        to_delete[ref.object.as_pointer()] = ref.object
        referenced = helpers.collect_referenced_ptrs(groups, skip_gi=gi)
        groups.remove(gi)
        if not self.keep_objects:
            helpers.delete_unreferenced(to_delete, referenced)

    def _delete_item(self, groups, gi, ii):
        """Remove an item and optionally delete its exclusive scene objects."""
        item = groups[gi].items[ii]
        to_delete = {}
        if not self.keep_objects:
            to_delete = {
                ref.object.as_pointer(): ref.object
                for ref in item.objects if ref.object is not None
            }
        referenced = helpers.collect_referenced_ptrs(
            groups, skip_item_ptr=item.as_pointer(),
        )
        groups[gi].items.remove(ii)
        if not self.keep_objects:
            helpers.delete_unreferenced(to_delete, referenced)

# endregion

# region Mesh Templates

def _import_template_mesh(preset_type):
    """Import the FBX template for a mesh type, return the Mesh datablock."""
    mesh_filename = f"MESH_{preset_type}.fbx"
    addon_dir     = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    mesh_path     = os.path.join(addon_dir, "meshes", mesh_filename)
    if not os.path.isfile(mesh_path):
        return None
    before = set(bpy.data.objects[:])
    bpy.ops.import_scene.fbx(filepath=mesh_path)
    imported = [o for o in bpy.data.objects if o not in before]
    if not imported:
        return None
    template_obj = next((o for o in imported if o.type == 'MESH'), None)
    if template_obj is None:
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        return None
    template_mesh = template_obj.data
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return template_mesh


def _apply_preset(context, item, preset_type):
    """Swap mesh data for item objects to match the selected mesh type."""
    template_mesh = _import_template_mesh(preset_type)
    if template_mesh is None:
        return
    mesh_refs = [
        (ref, ref.object) for ref in item.objects
        if ref.object is not None and ref.object.type == 'MESH'
    ]
    if not mesh_refs:
        # No objects yet, create one from the template
        new_mesh = template_mesh.copy()
        new_mesh.name = f"MESH_{item.name}"
        new_obj = bpy.data.objects.new(f"MESH_{item.name}", new_mesh)
        collection = context.collection or context.scene.collection
        collection.objects.link(new_obj)
        if item.objects and item.objects[-1].object is None:
            item.objects.remove(len(item.objects) - 1)
        item.objects.add().object = new_obj
    else:
        # Replace mesh data preserving materials
        for ref, obj in mesh_refs:
            old_materials = [slot.material for slot in obj.material_slots]
            old_mesh      = obj.data
            new_mesh      = template_mesh.copy()
            new_mesh.name = obj.name
            obj.data      = new_mesh
            obj.data.materials.clear()
            for mat in old_materials:
                obj.data.materials.append(mat)
            if old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
    # Clean up template if unused
    if template_mesh.users == 0:
        bpy.data.meshes.remove(template_mesh)

# endregion
