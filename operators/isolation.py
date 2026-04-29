import bpy
import bmesh
from bpy.types import Operator
from ..viewport import screen

# region Variables

_item_isolate_timer_running   = False
_isolation_mode_timer_running = False

# endregion

# region Isolate

class optiflow_isolate(Operator):
    """Hide all objects or geometry except the current selection."""
    bl_idname  = "optiflow.isolate"
    bl_label   = "Isolate"
    bl_description = "Hide all objects or geometry, except selection."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        mode  = context.mode
        if not scene.get("optiflow_isolated", False):
            self._isolate(context, mode, scene)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

    def _isolate(self, context, mode, scene):
        """Apply isolation based on current mode."""
        if scene.get("optiflow_item_isolated", False):
            disable_item_isolation(context, scene)
        screen.enable_border()
        if mode == 'OBJECT':
            selected = set(context.selected_objects)
            for obj in context.view_layer.objects:
                obj.hide_viewport = obj not in selected
        elif mode == 'EDIT_MESH':
            bpy.ops.mesh.hide(unselected=True)
            for obj in context.view_layer.objects:
                if obj.mode != 'EDIT':
                    obj.hide_viewport = True
            ensure_isolation_mode_timer()
        scene["optiflow_isolated"]      = True
        scene["optiflow_isolated_mode"] = mode

# endregion

# region Reveal

class optiflow_reveal(Operator):
    """Unhide all objects and geometry."""
    bl_idname  = "optiflow.reveal"
    bl_label   = "Reveal"
    bl_description = "Shows all objects or geometry that have been isolated."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if scene.get("optiflow_isolated", False):
            self.reveal(context, scene)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

    def reveal(self, context, scene):
        """Remove isolation and restore all visibility."""
        screen.disable_border()
        isolated_mode = scene.get("optiflow_isolated_mode", context.mode)
        if isolated_mode == 'EDIT_MESH':
            for obj in context.view_layer.objects:
                if obj.type != 'MESH':
                    continue
                if obj.mode == 'EDIT':
                    bm = bmesh.from_edit_mesh(obj.data)
                    for elem in (*bm.verts, *bm.edges, *bm.faces):
                        elem.hide = False
                    bmesh.update_edit_mesh(obj.data)
                else:
                    bm = bmesh.new()
                    bm.from_mesh(obj.data)
                    for elem in (*bm.verts, *bm.edges, *bm.faces):
                        elem.hide = False
                    bm.to_mesh(obj.data)
                    bm.free()
        for obj in context.view_layer.objects:
            obj.hide_viewport = False
        scene["optiflow_isolated"]      = False
        scene["optiflow_isolated_mode"] = ""

# endregion

# region Item Isolation

class optiflow_isolate_items(Operator):
    """Toggle visibility to show only the selected item's objects."""
    bl_idname  = "optiflow.isolate_items"
    bl_label   = "Isolate"
    bl_description = "Display only selected items in the viewport"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if scene.get("optiflow_item_isolated", False):
            disable_item_isolation(context, scene)
        else:
            # Disable regular isolation first
            if scene.get("optiflow_isolated", False):
                optiflow_reveal.reveal(optiflow_reveal, context, scene)
            screen.enable_border("#ffcc00", key="item")
            scene["optiflow_item_isolated"]          = True
            scene["optiflow_item_isolated_last_idx"] = scene.optiflow_flat_index
            apply_item_isolation(context, scene)
            ensure_item_isolate_timer()
        for area in context.window.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def apply_item_isolation(context, scene):
    """Show only objects belonging to the currently selected item or group."""
    entries = scene.optiflow_flat_entries
    idx     = scene.optiflow_flat_index
    groups  = scene.optiflow_groups
    visible_ptrs = set()
    if 0 <= idx < len(entries):
        fe = entries[idx]
        try:
            group = groups[fe.group_index]
            items_to_show = [group.items[fe.item_index]] if fe.item_index >= 0 else list(group.items)
            for item in items_to_show:
                for ref in item.objects:
                    if ref.object is not None:
                        visible_ptrs.add(ref.object.as_pointer())
        except (IndexError, KeyError):
            pass
    for obj in context.view_layer.objects:
        obj.hide_viewport = obj.as_pointer() not in visible_ptrs


def disable_item_isolation(context, scene):
    """Turn off item isolation and restore all objects."""
    screen.disable_border(key="item")
    for obj in context.view_layer.objects:
        obj.hide_viewport = False
    scene["optiflow_item_isolated"]          = False
    scene["optiflow_item_isolated_last_idx"] = -1

# endregion

# region Timer

def ensure_isolation_mode_timer():
    """Start the edit-mode watch timer if not already running."""
    global _isolation_mode_timer_running
    if not _isolation_mode_timer_running:
        _isolation_mode_timer_running = True
        bpy.app.timers.register(_isolation_mode_poll, first_interval=0.1)


def _isolation_mode_poll():
    """Auto-reveal if the user leaves edit mode while isolated."""
    global _isolation_mode_timer_running
    try:
        context = bpy.context
        scene   = context.scene
    except Exception:
        _isolation_mode_timer_running = False
        return None
    if not scene.get("optiflow_isolated", False):
        _isolation_mode_timer_running = False
        return None
    if scene.get("optiflow_isolated_mode", "") == 'EDIT_MESH' and context.mode != 'EDIT_MESH':
        optiflow_reveal.reveal(optiflow_reveal, context, scene)
        for area in context.window.screen.areas:
            area.tag_redraw()
        _isolation_mode_timer_running = False
        return None
    return 0.1


def ensure_item_isolate_timer():
    """Start the polling timer if not already running."""
    global _item_isolate_timer_running
    if not _item_isolate_timer_running:
        _item_isolate_timer_running = True
        bpy.app.timers.register(_item_isolate_poll, first_interval=0.1)


def _item_isolate_poll():
    """Re apply item isolation when the selected item changes."""
    global _item_isolate_timer_running
    try:
        scene = bpy.context.scene
    except Exception:
        _item_isolate_timer_running = False
        return None
    if not scene.get("optiflow_item_isolated", False):
        _item_isolate_timer_running = False
        return None
    last_idx    = scene.get("optiflow_item_isolated_last_idx", -1)
    current_idx = scene.optiflow_flat_index
    if current_idx != last_idx:
        scene["optiflow_item_isolated_last_idx"] = current_idx
        apply_item_isolation(bpy.context, scene)
        for area in bpy.context.window.screen.areas:
            area.tag_redraw()
    return 0.1

# endregion
