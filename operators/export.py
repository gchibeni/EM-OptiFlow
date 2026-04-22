import bpy
import os
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


def resolve_export_path(exporter, scene):
    """Determine the base export directory for an exporter."""
    override = exporter.override_path.strip()
    path = override if override else scene.export_path.strip()
    if path:
        return bpy.path.abspath(path)
    blend_path = bpy.data.filepath
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


def export_item(item, exporter, export_dir):
    """Export a single item as one file into export_dir."""
    objs = select_item_objects(item)
    if not objs:
        return
    prefix   = exporter.prefix.strip()
    filename = build_item_filename(item.name, prefix, exporter)
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, filename)
    export_file(filepath, exporter)


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

    def invoke(self, context, event):
        scene = context.scene
        self._files, self._exporters_info = collect_export_files(scene)
        self._overwrite = [f for f, exists in self._files if exists]
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
        layout.separator(type='LINE')

    def execute(self, context):
        scene        = context.scene
        was_isolated = scene.get("optiflow_item_isolated", False)
        if was_isolated:
            scene["optiflow_item_isolated"] = False
        export_all(scene)
        if was_isolated:
            scene["optiflow_item_isolated"] = True
        self.report({'INFO'}, "Export complete")
        return {'FINISHED'}

# endregion
