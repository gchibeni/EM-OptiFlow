import bpy
import os
from bpy.types import Operator, UILayout
from bpy.props import StringProperty

# region Variables

_last_dir = ""
_last_mouse_pos = (0, 0)
_direct_targets = {}

# endregion

# region Target Resolution

def _resolve_target(context, data_path):
    """Resolve a data path to the target object, checking direct refs first."""
    if data_path and data_path.startswith("__direct__:"):
        target = _direct_targets.get(data_path)
        if target is not None:
            return target
    if data_path:
        try:
            return context.scene.path_resolve(data_path)
        except (ValueError, AttributeError):
            pass
    return context.scene


def _register_direct_target(target):
    """Store a direct reference for targets not resolvable via scene path."""
    key = f"__direct__:{id(target)}"
    _direct_targets[key] = target
    return key


def _get_start_path(target, target_prop):
    """Determine the initial path for a file browser dialog."""
    current_path = getattr(target, target_prop, "")
    if current_path:
        abs_path = bpy.path.abspath(current_path)
        if os.path.exists(abs_path):
            return abs_path
    if _last_dir and os.path.exists(_last_dir):
        return _last_dir
    blend_path = bpy.data.filepath
    blend_dir  = os.path.dirname(blend_path) if blend_path else ""
    if blend_dir and os.path.exists(blend_dir):
        return blend_dir
    return os.path.expanduser("~/Documents")


def _to_relative_path(path):
    """Convert an absolute path to Blender relative if possible."""
    blend_dir = os.path.dirname(bpy.data.filepath)
    if not blend_dir:
        return path
    try:
        return bpy.path.relpath(path)
    except Exception:
        return path

# endregion

# region Redraw

def _force_redraw(context):
    """Force a full UI redraw including open popups."""
    try:
        context.scene.update_tag()
    except Exception:
        pass
    if context.region:
        context.region.tag_redraw()
        if hasattr(context.region, 'tag_refresh'):
            context.region.tag_refresh()
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
            for region in area.regions:
                region.tag_redraw()
                if hasattr(region, 'tag_refresh'):
                    region.tag_refresh()
    # Cursor nudge to force MOUSEMOVE over popups
    x, y = _last_mouse_pos
    def _nudge():
        try:
            window = bpy.context.window
            window.cursor_warp(x + 1, y)
            window.cursor_warp(x, y)
        except Exception:
            pass
        return None
    bpy.app.timers.register(_nudge, first_interval=0.05)

# endregion

# region Operators

class UI_OT_select_dirpath(Operator):
    """File browser dialog for selecting a directory."""
    bl_idname  = "ui.select_dirpath"
    bl_label   = "Select Directory"
    bl_description = "Specify the target directory path"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory:   StringProperty(options={'HIDDEN'})  # type: ignore
    target_prop: StringProperty(options={'HIDDEN'})  # type: ignore
    data_path:   StringProperty(options={'HIDDEN'})  # type: ignore
    filter_glob: StringProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        global _last_dir
        target = _resolve_target(context, self.data_path)
        path   = bpy.path.abspath(self.directory)
        if not os.path.isdir(path):
            self.report({'ERROR'}, "Selected path is not a valid directory")
            return {'CANCELLED'}
        _last_dir = path
        setattr(target, self.target_prop, _to_relative_path(self.directory))
        _force_redraw(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        global _last_mouse_pos
        _last_mouse_pos = (event.mouse_x, event.mouse_y)
        target     = _resolve_target(context, self.data_path)
        start_path = _get_start_path(target, self.target_prop)
        self.directory = start_path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class UI_OT_select_filepath(Operator):
    """File browser dialog for selecting a file."""
    bl_idname  = "ui.select_filepath"
    bl_label   = "Select File"
    bl_description = "Specify the target file path"
    bl_options = {'REGISTER', 'INTERNAL'}

    filepath:    StringProperty(subtype='FILE_PATH')  # type: ignore
    target_prop: StringProperty(options={'HIDDEN'})  # type: ignore
    data_path:   StringProperty(options={'HIDDEN'})  # type: ignore
    file_types:  StringProperty(default="", options={'HIDDEN'})  # type: ignore
    filter_glob: StringProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        global _last_dir
        target = _resolve_target(context, self.data_path)
        path   = bpy.path.abspath(self.filepath)
        if not os.path.isfile(path):
            self.report({'ERROR'}, "Selected path is not a valid file")
            return {'CANCELLED'}
        _last_dir = os.path.dirname(path)
        setattr(target, self.target_prop, _to_relative_path(self.filepath))
        _force_redraw(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        global _last_mouse_pos
        _last_mouse_pos = (event.mouse_x, event.mouse_y)
        target     = _resolve_target(context, self.data_path)
        start_path = _get_start_path(target, self.target_prop)
        current_path = getattr(target, self.target_prop, "")
        if current_path:
            abs_path = bpy.path.abspath(current_path)
            if os.path.isfile(abs_path):
                start_path = os.path.dirname(abs_path)
        self.filepath = os.path.join(start_path, "")
        if self.file_types:
            types = [f"*.{ext.strip()}" for ext in self.file_types.split(",")]
            self.filter_glob = ";".join(types)
        else:
            self.filter_glob = ""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# endregion

# region Helpers

def prop_input(layout, data, label, prop_name, expand=False):
    """Draw a property input row with consistent label-input split."""
    split = layout.split(factor=0.23)
    split.label(text=label)
    row = split.row(align=True)
    if expand:
        row.prop(data, prop_name, expand=True)
    else:
        row.prop(data, prop_name, text="")
    return row


def dir_input(layout, context, label, target_prop):
    """Draw a directory path input row with browse button."""
    split = layout.split(factor=0.23)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_dirpath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop
    try:
        op.data_path = context.path_from_id()
    except (ValueError, AttributeError):
        op.data_path = _register_direct_target(context)


def file_input(layout, context, label, target_prop, file_types=""):
    """Draw a file path input row with browse button and type filter."""
    split = layout.split(factor=0.23)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_filepath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop
    op.file_types  = file_types
    try:
        op.data_path = context.path_from_id()
    except (ValueError, AttributeError):
        op.data_path = _register_direct_target(context)

# endregion
