import bpy
import os
import sys
import subprocess
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty, IntProperty
from ..core import constants
from ..ui.file_dialogs import dir_input, prop_input

# region Helpers

def _copy_exporter_props(src, dst):
    """Copy all properties from one exporter to another."""
    dst.exporter_type    = src.exporter_type
    dst.override_path    = src.override_path
    dst.prefix           = src.prefix
    dst.scale            = src.scale
    dst.apply_transforms = src.apply_transforms
    dst.embed_materials  = src.embed_materials
    dst.animations       = src.animations
    dst.tangents          = src.tangents
    dst.images_type       = src.images_type
    dst.quality           = src.quality
    dst.anim_frame_start  = src.anim_frame_start
    dst.anim_frame_end    = src.anim_frame_end

# endregion

# region Add

class EXPORTERS_OT_add(Operator):
    """Add a new exporter configuration."""
    bl_idname  = "exporters.add"
    bl_label   = "Add"
    bl_options = {'UNDO'}

    exporter_type: EnumProperty(
        name="Type", items=constants.EXPORTER_TYPE,
    )  # type: ignore

    def execute(self, context):
        scene = context.scene
        exp = scene.exporters.add()
        exp.exporter_type = self.exporter_type
        scene.exporters_index = len(scene.exporters) - 1
        return {'FINISHED'}

# endregion

# region Remove

class EXPORTERS_OT_remove(Operator):
    """Remove the selected exporter."""
    bl_idname  = "exporters.remove"
    bl_label   = "Remove"
    bl_description = "Remove the selected exporter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.exporters) > 0

    def execute(self, context):
        scene = context.scene
        scene.exporters.remove(scene.exporters_index)
        scene.exporters_index = min(
            scene.exporters_index, len(scene.exporters) - 1,
        )
        return {'FINISHED'}

# endregion

# region Duplicate

class EXPORTERS_OT_duplicate(Operator):
    """Duplicate the selected exporter with all settings."""
    bl_idname  = "exporters.duplicate"
    bl_label   = "Duplicate"
    bl_description = "Duplicate the selected exporter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return scene.exporters and scene.exporters_index >= 0

    def execute(self, context):
        scene  = context.scene
        src    = scene.exporters[scene.exporters_index]
        dst    = scene.exporters.add()
        _copy_exporter_props(src, dst)
        new_idx = len(scene.exporters) - 1
        target  = scene.exporters_index + 1
        scene.exporters.move(new_idx, target)
        scene.exporters_index = target
        return {'FINISHED'}

# endregion

# region Edit

class EXPORTERS_OT_edit(Operator):
    """Edit exporter settings in a dialog."""
    bl_idname  = "exporters.edit"
    bl_label   = "Edit"
    bl_description = "Edit exporter settings"
    bl_options = {'UNDO', 'INTERNAL'}

    edit_exporter_type:   EnumProperty(name="Exporter", items=constants.EXPORTER_TYPE)  # type: ignore
    edit_prefix:          StringProperty(name="Prefix")  # type: ignore
    edit_embed_materials: BoolProperty(name="Embed Materials", default=True)  # type: ignore
    edit_animations:      BoolProperty(name="Animations", default=True)  # type: ignore
    edit_tangents:          BoolProperty(name="Tangents", default=True)  # type: ignore
    edit_images_type:       EnumProperty(name="Images Type", items=constants.GLTF_IMAGE_TYPE, default='AUTO')  # type: ignore
    edit_quality:           IntProperty(name="Quality", default=100, min=50, max=100, subtype='PERCENTAGE')  # type: ignore
    edit_anim_frame_start:  IntProperty(name="Start", default=1)  # type: ignore
    edit_anim_frame_end:    IntProperty(name="End", default=250)  # type: ignore

    def invoke(self, context, event):
        scene = context.scene
        if not scene.exporters or scene.exporters_index < 0:
            return {'CANCELLED'}
        src = scene.exporters[scene.exporters_index]
        self.edit_exporter_type   = src.exporter_type
        context.scene.optiflow_edit_override_path = src.override_path
        self.edit_prefix          = src.prefix
        self.edit_embed_materials = src.embed_materials
        self.edit_animations      = src.animations
        self.edit_tangents         = src.tangents
        self.edit_images_type      = src.images_type
        self.edit_quality          = src.quality
        self.edit_anim_frame_start = src.anim_frame_start
        self.edit_anim_frame_end   = src.anim_frame_end
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        prop_input(layout, self, "Exporter:", "edit_exporter_type")
        dir_input(layout, context.scene, "Override Path:", "optiflow_edit_override_path")
        prop_input(layout, self, "Prefix:", "edit_prefix")
        layout.separator(type='LINE')
        split = layout.split(factor=0.23)
        split.label(text="Data:")
        row = split.row(align=True)
        row.prop(self, "edit_embed_materials", text="Embed Materials", toggle=True)
        row.prop(self, "edit_animations", text="Animations", toggle=True)
        if self.edit_exporter_type == 'OBJ' and self.edit_animations:
            split = layout.split(factor=0.23)
            split.label(text="Frame Range:")
            row = split.row(align=True)
            row.prop(self, "edit_anim_frame_start", text="Start")
            row.prop(self, "edit_anim_frame_end", text="End")
        if self.edit_exporter_type == 'GLTF':
            row.prop(self, "edit_tangents", text="Tangents", toggle=True)
            split = layout.split(factor=0.23)
            split.label(text="Images:")
            row = split.row(align=True)
            row.prop(self, "edit_images_type", expand=True)
            split = layout.split(factor=0.23)
            split.label(text="Quality:")
            split.prop(self, "edit_quality", text="", slider=True)
        layout.separator(type='LINE')

    def execute(self, context):
        scene    = context.scene
        exporter = scene.exporters[scene.exporters_index]
        exporter.exporter_type   = self.edit_exporter_type
        exporter.override_path   = context.scene.optiflow_edit_override_path
        exporter.prefix          = self.edit_prefix
        exporter.embed_materials = self.edit_embed_materials
        exporter.animations      = self.edit_animations
        exporter.tangents          = self.edit_tangents
        exporter.images_type       = self.edit_images_type
        exporter.quality           = self.edit_quality
        exporter.anim_frame_start  = self.edit_anim_frame_start
        exporter.anim_frame_end    = self.edit_anim_frame_end
        return {'FINISHED'}

# endregion

# region Open Folder

class EXPORTERS_OT_open_folder(Operator):
    """Open the export folder in the system file explorer."""
    bl_idname  = "exporters.open_folder"
    bl_label   = "Open Export Folder"
    bl_description = "Open the export folder in the file explorer"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from .export import resolve_export_path
        scene = context.scene
        if not scene.exporters or scene.exporters_index < 0:
            return {'CANCELLED'}
        exporter = scene.exporters[scene.exporters_index]
        path = resolve_export_path(exporter, scene)
        if not path:
            path = os.path.expanduser("~/Documents")
        os.makedirs(path, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return {'FINISHED'}

# endregion
