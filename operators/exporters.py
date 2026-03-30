import bpy
import os
import sys
import subprocess
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty
from ..core import constants

# region Helpers

def _copy_exporter_props(src, dst):
    """Copy all properties from one exporter to another."""
    dst.exporter_type   = src.exporter_type
    dst.override_path   = src.override_path
    dst.prefix          = src.prefix
    dst.scale           = src.scale
    dst.apply_transforms = src.apply_transforms
    dst.embed_materials = src.embed_materials
    dst.animations      = src.animations

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
    edit_override_path:   StringProperty(name="Override Path")  # type: ignore
    edit_prefix:          StringProperty(name="Prefix")  # type: ignore
    edit_embed_materials: BoolProperty(name="Embed Materials", default=True)  # type: ignore
    edit_animations:      BoolProperty(name="Animations", default=True)  # type: ignore

    def invoke(self, context, event):
        scene = context.scene
        if not scene.exporters or scene.exporters_index < 0:
            return {'CANCELLED'}
        src = scene.exporters[scene.exporters_index]
        self.edit_exporter_type   = src.exporter_type
        self.edit_override_path   = src.override_path
        self.edit_prefix          = src.prefix
        self.edit_embed_materials = src.embed_materials
        self.edit_animations      = src.animations
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        from ..ui.file_dialogs import dir_input, prop_input
        layout = self.layout
        prop_input(layout, self, "Exporter:", "edit_exporter_type")
        dir_input(layout, self, "Override Path:", "edit_override_path")
        prop_input(layout, self, "Prefix:", "edit_prefix")
        layout.separator(type='LINE')
        prop_input(layout, self, "Embed Materials:", "edit_embed_materials")
        if self.edit_exporter_type != 'OBJ':
            prop_input(layout, self, "Animations:", "edit_animations")
        layout.separator(type='LINE')

    def execute(self, context):
        scene    = context.scene
        exporter = scene.exporters[scene.exporters_index]
        exporter.exporter_type   = self.edit_exporter_type
        exporter.override_path   = self.edit_override_path
        exporter.prefix          = self.edit_prefix
        exporter.embed_materials = self.edit_embed_materials
        exporter.animations      = self.edit_animations
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
        scene = context.scene
        if not scene.exporters or scene.exporters_index < 0:
            return {'CANCELLED'}
        exporter = scene.exporters[scene.exporters_index]
        override = exporter.override_path.strip()
        if override:
            path = bpy.path.abspath(override)
        else:
            raw = scene.export_path.strip()
            path = bpy.path.abspath(raw) if raw else ""
        if not path or not os.path.isdir(path):
            self.report({'ERROR'}, "Invalid path")
            return {'CANCELLED'}
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return {'FINISHED'}

# endregion
