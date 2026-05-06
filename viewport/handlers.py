import bpy
import re
from bpy.app.handlers import persistent
from bpy.types import Scene
from bpy.props import StringProperty, BoolProperty, IntProperty, CollectionProperty, FloatProperty
from . import screen


def _sanitize_item_prefix(self, context):
    clean = re.sub(r'[^A-Za-z0-9]', '', self.optiflow_item_prefix).upper()
    if self.optiflow_item_prefix != clean:
        self.optiflow_item_prefix = clean


def _sanitize_item_suffix(self, context):
    clean = re.sub(r'[^A-Za-z0-9]', '', self.optiflow_item_suffix).upper()
    if self.optiflow_item_suffix != clean:
        self.optiflow_item_suffix = clean

# region Timers

def _start_key_listener():
    """Timer callback to start the persistent key listener modal."""
    bpy.ops.optiflow.key_listener('INVOKE_DEFAULT')
    return None


def _sync_isolation_borders():
    """Sync viewport borders with scene isolation flags after file load."""
    from ..operators.isolation import ensure_item_isolate_timer
    scene = bpy.context.scene
    screen.disable_all_borders()
    if scene.get("optiflow_isolated", False):
        screen.enable_border()
    if scene.get("optiflow_item_isolated", False):
        screen.enable_border("#ffcc00", key="item")
        ensure_item_isolate_timer()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None

# endregion

# region Handlers

@persistent
def _on_load_post(dummy):
    """Restart key listener and sync isolation state on file load."""
    from ..operators.items import _template_mesh_cache
    _template_mesh_cache.clear()
    bpy.app.timers.register(_start_key_listener, first_interval=0.15)
    bpy.app.timers.register(_sync_isolation_borders, first_interval=0.15)


@persistent
def _on_depsgraph_update(scene, depsgraph):
    """Clean stale object references when scene objects are deleted."""
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object):
            break
    else:
        return
    if not hasattr(scene, 'optiflow_groups'):
        return
    scene_objects = set(scene.collection.all_objects)
    for group in scene.optiflow_groups:
        for item in group.items:
            i = len(item.objects) - 1
            while i >= 0:
                obj = item.objects[i].object
                if obj is not None and obj not in scene_objects:
                    item.objects.remove(i)
                i -= 1


@persistent
def _on_undo_redo(dummy):
    """Sync isolation borders after undo or redo."""
    from ..operators.isolation import ensure_item_isolate_timer
    from ..operators import tex_import as _tex_import
    scene = bpy.context.scene
    # If undo/redo restored the importing flag but no import is running, clear it.
    # This prevents the progress bar from getting stuck at 0% after redo.
    if scene.optiflow_is_importing and not _tex_import.is_import_active():
        scene.optiflow_is_importing = False
        scene.optiflow_tex_progress = 0.0
    if scene.get("optiflow_isolated", False):
        screen.enable_border()
    else:
        screen.disable_border()
    if scene.get("optiflow_item_isolated", False):
        screen.enable_border("#ffcc00", key="item")
        ensure_item_isolate_timer()
    else:
        screen.disable_border(key="item")


@persistent
def _on_redo(dummy):
    """Re-apply async-created materials to objects that lost them via undo/redo."""
    from ..operators import tex_import as _tex_import
    if _tex_import.is_import_active():
        return
    assignments = _tex_import._last_material_assignments
    if not assignments:
        return
    for obj_name, mat_name in assignments.items():
        obj = bpy.data.objects.get(obj_name)
        mat = bpy.data.materials.get(mat_name)
        if obj and mat and obj.type == 'MESH' and obj.data and len(obj.data.materials) == 0:
            obj.data.materials.append(mat)

# endregion

# region Key Listener

class OPT_OT_key_listener(bpy.types.Operator):
    """Persistent modal that tracks keyboard shortcuts in the OptiFlow panel."""
    bl_idname  = "optiflow.key_listener"
    bl_label   = "Key Listener"
    bl_options = {'INTERNAL'}

    _mouse_x: int = 0
    _mouse_y: int = 0

    def modal(self, context, event):
        self._mouse_x = event.mouse_x
        self._mouse_y = event.mouse_y
        in_panel = _is_mouse_in_optiflow_panel(
            context, self._mouse_x, self._mouse_y,
        )
        if not in_panel:
            return {'PASS_THROUGH'}

        # Ctrl+Arrow for navigation
        if event.type in {'UP_ARROW', 'DOWN_ARROW'} and event.value == 'PRESS' and event.ctrl:
            scene   = context.scene
            entries = scene.optiflow_flat_entries
            idx     = scene.optiflow_flat_index
            if event.type == 'UP_ARROW':
                scene.optiflow_flat_index = max(0, idx - 1)
            else:
                scene.optiflow_flat_index = min(len(entries) - 1, idx + 1)
            for area in context.window.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Ctrl+key shortcuts on release
        if event.value == 'RELEASE' and event.ctrl:
            return self._handle_ctrl_shortcut(context, event)

        return {'PASS_THROUGH'}

    def _handle_ctrl_shortcut(self, context, event):
        """Dispatch Ctrl+key shortcuts within the panel."""
        if event.type == 'DEL':
            bpy.ops.optiflow.delete('EXEC_DEFAULT')
            bpy.ops.ed.undo_push(message="Delete Entry")
            return {'RUNNING_MODAL'}
        if event.type == 'D':
            bpy.ops.optiflow.duplicate('EXEC_DEFAULT')
            bpy.ops.ed.undo_push(message="Duplicate Entry")
            return {'RUNNING_MODAL'}
        if event.type == 'A':
            bpy.ops.optiflow.wip_popup('INVOKE_DEFAULT')
            return {'RUNNING_MODAL'}
        if event.type == 'G':
            bpy.ops.optiflow.add_group('EXEC_DEFAULT')
            bpy.ops.ed.undo_push(message="Add Group")
            return {'RUNNING_MODAL'}
        if event.type == 'E':
            scene   = context.scene
            entries = scene.optiflow_flat_entries
            idx     = scene.optiflow_flat_index
            if 0 <= idx < len(entries) and entries[idx].entry_type != 'GROUP':
                bpy.ops.optiflow.edit_item('INVOKE_DEFAULT')
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

# endregion

# region Helpers

def _is_mouse_in_optiflow_panel(context, mouse_x, mouse_y):
    """Check if the cursor is over the OptiFlow sidebar panel."""
    return any(
        area.type == 'VIEW_3D' and any(
            region.type == 'UI' and
            region.x <= mouse_x <= region.x + region.width and
            region.y <= mouse_y <= region.y + region.height and
            getattr(region, 'active_panel_category', None) == 'OptiFlow'
            for region in area.regions
        )
        for area in context.window.screen.areas
    )

# endregion

# region Registration

def register():
    """Register scene properties, handlers, and key listener timer."""
    from ..core.properties import FlatEntry, Group, Exporter
    from ..operators.items import TexDisplayItem, _on_tex_index_changed
    from ..operators.auto_fill import _on_autofill_url_change
    Scene.show_items            = BoolProperty(name="Items", default=True)
    Scene.optiflow_tex_display       = CollectionProperty(type=TexDisplayItem, options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_tex_display_index = IntProperty(name="", default=0, options={'HIDDEN', 'SKIP_SAVE'}, update=_on_tex_index_changed)  # type: ignore
    Scene.optiflow_add_obj_path      = StringProperty(name="Object",        default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_add_col_path      = StringProperty(name="Collider",      default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_change_obj_path   = StringProperty(name="Object",        default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_edit_override_path = StringProperty(name="Override Path", default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_extract_tex_dir   = StringProperty(name="Output Folder",  default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_groups       = CollectionProperty(name="", type=Group, options={'HIDDEN'})
    Scene.optiflow_flat_entries = CollectionProperty(name="", type=FlatEntry, options={'HIDDEN'})
    Scene.optiflow_flat_index   = IntProperty(name="", default=0, options={'HIDDEN', 'SKIP_SAVE'})
    Scene.export_path           = StringProperty(name="Export Path", options={'HIDDEN'})
    Scene.copyright_text        = StringProperty(name="Copyright", options={'HIDDEN'})
    Scene.exporters             = CollectionProperty(type=Exporter, options={'HIDDEN'})
    Scene.exporters_index       = IntProperty(name="", default=0, options={'HIDDEN', 'SKIP_SAVE'})
    Scene.show_exporters        = BoolProperty(name="Show Exporters", default=False)
    Scene.optiflow_origin_wip   = BoolProperty(name="", default=False, options={'HIDDEN', 'SKIP_SAVE'})
    Scene.optiflow_is_importing  = BoolProperty(name="", default=False, options={'HIDDEN', 'SKIP_SAVE'})
    Scene.optiflow_tex_progress = FloatProperty(name="", default=0.0, min=0.0, max=1.0, options={'HIDDEN', 'SKIP_SAVE'})
    Scene.optiflow_autofill_url        = StringProperty(name="Spreadsheet URL or ID", options={'HIDDEN'}, update=_on_autofill_url_change)  # type: ignore
    Scene.optiflow_autofill_file       = StringProperty(name="File Path", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_autofill_tab        = StringProperty(name="Last Sheet Tab", options={'HIDDEN'})  # type: ignore
    Scene.optiflow_autofill_source     = StringProperty(name="Last Source",     default='GOOGLE_SHEETS', options={'HIDDEN'})  # type: ignore
    Scene.optiflow_autofill_key_name   = StringProperty(name="Last Key Column",  default='',             options={'HIDDEN'})  # type: ignore
    Scene.optiflow_autofill_header_row = StringProperty(name="Last Header Row",  default='1',            options={'HIDDEN'})  # type: ignore
    Scene.optiflow_item_prefix = StringProperty(name="Prefix", default='', options={'HIDDEN'}, update=_sanitize_item_prefix)  # type: ignore
    Scene.optiflow_item_suffix = StringProperty(name="Suffix", default='', options={'HIDDEN'}, update=_sanitize_item_suffix)  # type: ignore
    bpy.types.WindowManager.optiflow_ctrl_held = BoolProperty(
        default=False, options={'HIDDEN', 'SKIP_SAVE'},
    )
    bpy.app.timers.register(_start_key_listener, first_interval=0.15)
    bpy.app.handlers.load_post.append(_on_load_post)
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    bpy.app.handlers.undo_post.append(_on_undo_redo)
    bpy.app.handlers.redo_post.append(_on_undo_redo)
    bpy.app.handlers.redo_post.append(_on_redo)


def unregister():
    """Unregister scene properties and handlers."""
    from ..operators.tex_import import cancel_all
    from ..operators.items import _clear_template_mesh_cache
    cancel_all()
    _clear_template_mesh_cache()
    for handler_list in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo in handler_list:
            handler_list.remove(_on_undo_redo)
    if _on_redo in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(_on_redo)
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for attr in (
        "show_items", "optiflow_groups", "optiflow_flat_entries", "optiflow_flat_index",
        "export_path", "copyright_text", "exporters", "exporters_index", "show_exporters",
        "optiflow_origin_wip", "optiflow_tex_display", "optiflow_tex_display_index",
        "optiflow_add_obj_path", "optiflow_add_col_path", "optiflow_change_obj_path",
        "optiflow_edit_override_path", "optiflow_extract_tex_dir",
        "optiflow_is_importing", "optiflow_tex_progress",
        "optiflow_autofill_url", "optiflow_autofill_file", "optiflow_autofill_tab",
        "optiflow_autofill_source", "optiflow_autofill_key_name", "optiflow_autofill_header_row",
        "optiflow_item_prefix", "optiflow_item_suffix",
    ):
        if hasattr(Scene, attr):
            delattr(Scene, attr)
    if hasattr(bpy.types.WindowManager, "optiflow_ctrl_held"):
        del bpy.types.WindowManager.optiflow_ctrl_held

# endregion
