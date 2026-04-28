import bpy
import os
import uuid
from bpy.types import Operator
from datetime import date

# region Pipeline

def get_copyright():
    """Generate a copyright string from scene settings."""
    scene = bpy.context.scene
    text  = scene.copyright_text.strip()
    if not text:
        return ""
    return f"\u00a9 {date.today().year} {text}"


def _path_root_exists(path):
    """Return True if the drive/root of path is accessible on this OS."""
    if not path:
        return False
    drive, _ = os.path.splitdrive(path)
    if drive:
        return os.path.exists(drive + os.sep)
    # On Windows a path without a drive letter (e.g. /Export) is not rooted.
    if os.name == 'nt':
        return False
    return True


def resolve_export_path(exporter, scene):
    """Determine the base export directory for an exporter."""
    blend_path = bpy.data.filepath
    override   = exporter.override_path.strip()
    raw        = override if override else scene.export_path.strip()
    if raw:
        # Relative paths (//...) require a saved blend file to be meaningful.
        if raw.startswith("//") and not blend_path:
            pass
        else:
            resolved = bpy.path.abspath(raw)
            if _path_root_exists(resolved):
                return resolved
    if blend_path:
        return os.path.dirname(blend_path)
    return os.path.join(os.path.expanduser("~"), "Documents")


def build_item_filename(item_name, prefix, exporter):
    """Build the export filename with extension based on exporter type."""
    name = f"{prefix}_{item_name}" if prefix else item_name
    match exporter.exporter_type:
        case 'GLTF':
            ext = 'glb' if exporter.embed_materials else 'gltf'
        case 'FBX':
            ext = 'fbx'
        case 'OBJ':
            ext = 'obj'
        case _:
            ext = 'glb'
    return f"{name}.{ext}"


def select_item_objects(item):
    """Deselect all, then select mesh objects from item. Returns selected list."""
    bpy.ops.object.select_all(action='DESELECT')
    objs = [
        ref.object for ref in item.objects
        if ref.object is not None and ref.object.type == 'MESH'
    ]
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]
    return objs


def export_file(filepath, exporter):
    """Call the Blender export operator for the given exporter type."""
    match exporter.exporter_type:
        case 'GLTF':
            bpy.ops.export_scene.gltf(
                use_selection=True,
                filepath=filepath,
                export_format='GLB' if exporter.embed_materials else 'GLTF_SEPARATE',
                check_existing=False,
                export_animations=exporter.animations,
                export_animation_mode='NLA_TRACKS',
                export_tangents=exporter.tangents,
                export_image_format=exporter.images_type,
                export_jpeg_quality=exporter.quality,
                export_image_quality=exporter.quality,
                export_materials='EXPORT',
                export_copyright=get_copyright(),
            )
        case 'FBX':
            bpy.ops.export_scene.fbx(
                use_selection=True,
                filepath=filepath,
                check_existing=False,
                global_scale=exporter.scale,
                bake_space_transform=exporter.apply_transforms,
                embed_textures=exporter.embed_materials,
                path_mode='COPY' if exporter.embed_materials else 'AUTO',
                bake_anim=exporter.animations,
                bake_anim_use_all_bones=True,
                bake_anim_use_nla_strips=True,
                bake_anim_use_all_actions=False,
            )
        case 'OBJ':
            bpy.ops.wm.obj_export(
                export_selected_objects=True,
                filepath=filepath,
                check_existing=False,
                global_scale=exporter.scale,
                apply_modifiers=exporter.apply_transforms,
                export_materials=exporter.embed_materials,
                export_animation=exporter.animations,
                start_frame=exporter.anim_frame_start,
                end_frame=exporter.anim_frame_end,
            )


def _temp_mat_name():
    return f"__tmp_{uuid.uuid4().hex[:8]}__"


def _rename_item_materials(item):
    """Before export: rename this item's materials to Mat, Mat_1, Mat_2…
    Any scene material that already holds a target name is moved to a temp name.
    Returns {mat: original_name} for every touched material."""
    item_mats = []
    seen_ids = set()
    for ref in item.objects:
        obj = ref.object
        if obj is None or obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name == 'ColMat' or id(mat) in seen_ids:
                continue
            seen_ids.add(id(mat))
            item_mats.append(mat)

    if not item_mats:
        return {}

    target_names = ['Mat'] + [f'Mat_{i}' for i in range(1, len(item_mats))]
    restore = {}

    # Move scene materials that already hold a target name out of the way.
    for target in target_names:
        existing = bpy.data.materials.get(target)
        if existing is not None and id(existing) not in seen_ids:
            restore[existing] = existing.name
            existing.name = _temp_mat_name()

    # Move item materials to temp names first to free their current names,
    # then assign the sequential target names.
    for mat in item_mats:
        restore[mat] = mat.name
        mat.name = _temp_mat_name()
    for mat, target in zip(item_mats, target_names):
        mat.name = target

    return restore


def _restore_material_names(restore):
    """After export: restore all renamed materials to their original names."""
    if not restore:
        return
    # Two-pass: move everything to unique temps first to avoid cross-conflicts,
    # then restore to originals.
    temps = {}
    for mat in restore:
        t = _temp_mat_name()
        temps[mat] = t
        mat.name = t
    for mat, orig in restore.items():
        mat.name = orig


def export_item(item, exporter, export_dir):
    """Export a single item as one file into export_dir."""
    objs = select_item_objects(item)
    if not objs:
        return
    prefix   = exporter.prefix.strip()
    filename = build_item_filename(item.name, prefix, exporter)
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, filename)
    restore = _rename_item_materials(item)
    try:
        export_file(filepath, exporter)
    finally:
        _restore_material_names(restore)


def export_group(group, exporter, scene):
    """Export all items in a group to a subfolder."""
    base_path  = resolve_export_path(exporter, scene)
    group_name = group.name.strip()
    export_dir = os.path.join(base_path, group_name) if group_name else base_path
    for item in group.items:
        export_item(item, exporter, export_dir)


def collect_export_files(scene):
    """Collect all files to be exported. Returns (files, exporters_info)."""
    files          = []
    exporters_info = []
    for exporter in scene.exporters:
        base_path = resolve_export_path(exporter, scene)
        prefix    = exporter.prefix.strip()
        exporters_info.append((exporter.exporter_type, prefix, base_path))
        for group in scene.optiflow_groups:
            group_name = group.name.strip()
            export_dir = os.path.join(base_path, group_name) if group_name else base_path
            for item in group.items:
                objs = [
                    ref.object for ref in item.objects
                    if ref.object is not None and ref.object.type == 'MESH'
                ]
                if not objs:
                    continue
                filename = build_item_filename(item.name, prefix, exporter)
                filepath = os.path.join(export_dir, filename)
                files.append((filepath, os.path.isfile(filepath)))
    return files, exporters_info


def export_all(scene):
    """Export all groups with all configured exporters."""
    for exporter in scene.exporters:
        for group in scene.optiflow_groups:
            export_group(group, exporter, scene)


def has_ngons(scene):
    """Return True if any mesh object in any item has a face with 5+ vertices."""
    for group in scene.optiflow_groups:
        for item in group.items:
            for ref in item.objects:
                if ref.object is None or ref.object.type != 'MESH':
                    continue
                for poly in ref.object.data.polygons:
                    if poly.loop_total > 4:
                        return True
    return False

# endregion

# region Confirm

class OPT_OT_export_confirm(Operator):
    """Show export confirmation dialog with file summary."""
    bl_idname  = "optiflow.export_confirm"
    bl_label   = "Export"
    bl_description = "Export items using configured exporters."
    bl_options = {'INTERNAL'}

    _files          = []
    _overwrite      = []
    _exporters_info = []
    _ngons_found    = False

    def invoke(self, context, event):
        scene = context.scene
        self._files, self._exporters_info = collect_export_files(scene)
        self._overwrite  = [f for f, exists in self._files if exists]
        self._ngons_found = has_ngons(scene)
        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout   = self.layout
        total    = len(self._files)
        replaced = len(self._overwrite)
        layout.label(text=f"{total} file(s) will be exported to:", icon='INFO')
        for exp_type, prefix, path in self._exporters_info:
            tag = f"[{exp_type}]"
            if prefix:
                tag += f" [{prefix}]"
            split = layout.split(factor=0.20)
            box = split.box()
            box.label(text=tag)
            box = split.box()
            box.label(text=path)
        if replaced > 0:
            layout.separator(type='LINE')
            row       = layout.row()
            row.alert = True
            row.label(text=f"{replaced} existing file(s) will be replaced.")
        if self._ngons_found:
            layout.separator(type='LINE')
            row       = layout.row()
            row.alert = True
            row.label(
                text="Meshes contain N-gons, which may lead to export issues or visual artifacts.",
                icon='ERROR',
            )
        layout.separator(type='LINE')

    def execute(self, context):
        from .isolation import (
            disable_item_isolation, ensure_item_isolate_timer, optiflow_reveal,
        )
        from ..viewport import screen

        scene = context.scene

        was_item_isolated = bool(scene.get("optiflow_item_isolated", False))
        was_isolated      = bool(scene.get("optiflow_isolated", False))
        isolated_mode     = scene.get("optiflow_isolated_mode", "")

        # Snapshot per-object visibility before lifting isolation so we can
        # restore the exact hidden state after export without recomputing it.
        hidden_before = {}
        if was_item_isolated or was_isolated:
            for obj in context.view_layer.objects:
                hidden_before[obj.name] = obj.hide_viewport

        if was_item_isolated:
            disable_item_isolation(context, scene)
        if was_isolated:
            optiflow_reveal.reveal(optiflow_reveal, context, scene)

        export_all(scene)

        # Restore per-object visibility
        for name, was_hidden in hidden_before.items():
            obj = context.view_layer.objects.get(name)
            if obj:
                obj.hide_viewport = was_hidden

        # Re-enable item isolation (border + flag + timer)
        if was_item_isolated:
            screen.enable_border("#ffcc00", key="item")
            scene["optiflow_item_isolated"]          = True
            scene["optiflow_item_isolated_last_idx"] = scene.optiflow_flat_index
            ensure_item_isolate_timer()

        # Re-enable regular isolation (border + flag)
        if was_isolated:
            screen.enable_border()
            scene["optiflow_isolated"]      = True
            scene["optiflow_isolated_mode"] = isolated_mode

        self.report({'INFO'}, "Export complete")
        return {'FINISHED'}

# endregion
