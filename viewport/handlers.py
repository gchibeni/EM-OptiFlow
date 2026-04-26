import bpy
from bpy.app.handlers import persistent
from bpy.types import Scene
from bpy.props import StringProperty, BoolProperty, IntProperty, CollectionProperty
from . import screen

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
    scene = bpy.context.scene
    if scene.get("optiflow_isolated", False):
        screen.enable_border()
    else:
        screen.disable_border()
    if scene.get("optiflow_item_isolated", False):
        screen.enable_border("#ffcc00", key="item")
        ensure_item_isolate_timer()
    else:
        screen.disable_border(key="item")

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
    from ..operators.items import TexDisplayItem
    Scene.show_items            = BoolProperty(name="Items", default=True)
    Scene.optiflow_tex_display       = CollectionProperty(type=TexDisplayItem, options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_tex_display_index = IntProperty(name="", default=0, options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_add_obj_path      = StringProperty(name="Object",        default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
    Scene.optiflow_add_col_path      = StringProperty(name="Collider",      default="", options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore
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
    bpy.types.WindowManager.optiflow_ctrl_held = BoolProperty(
        default=False, options={'HIDDEN', 'SKIP_SAVE'},
    )
    bpy.app.timers.register(_start_key_listener, first_interval=0.15)
    bpy.app.handlers.load_post.append(_on_load_post)
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    bpy.app.handlers.undo_post.append(_on_undo_redo)
    bpy.app.handlers.redo_post.append(_on_undo_redo)


def unregister():
    """Unregister scene properties and handlers."""
    for handler_list in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo in handler_list:
            handler_list.remove(_on_undo_redo)
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for attr in (
        "show_items", "optiflow_groups", "optiflow_flat_entries", "optiflow_flat_index",
        "export_path", "copyright_text", "exporters", "exporters_index", "show_exporters",
        "optiflow_origin_wip", "optiflow_tex_display", "optiflow_tex_display_index",
        "optiflow_add_obj_path", "optiflow_add_col_path",
        "optiflow_edit_override_path", "optiflow_extract_tex_dir",
    ):
        if hasattr(Scene, attr):
            delattr(Scene, attr)
    if hasattr(bpy.types.WindowManager, "optiflow_ctrl_held"):
        del bpy.types.WindowManager.optiflow_ctrl_held

# endregion
