import bpy
import time
from bpy.types import Operator
from ..core.helpers import (
    rebuild_flat_entries, find_flat_idx, move_item_between_groups, get_prefix,
)

_SELECT_SKIP = frozenset({'COL', 'PLACER', 'SNAP', 'GUIDE'})

# region Cursor

def _wrap_cursor_y(context, event, state):
    """Wrap cursor vertically at window edges, updating state['last_y']."""
    margin = 30
    h      = context.window.height
    if event.mouse_y <= margin:
        context.window.cursor_warp(event.mouse_x, h - margin - 1)
        state['last_y'] = h - margin - 1
    elif event.mouse_y >= h - margin:
        context.window.cursor_warp(event.mouse_x, margin + 1)
        state['last_y'] = margin + 1
    else:
        state['last_y'] = event.mouse_y

# endregion

# region Item Drag

class OPT_OT_item_drag(Operator):
    """Drag to reorder items and groups in the flat list."""
    bl_idname  = "optiflow.item_drag"
    bl_label   = "Drag"
    bl_description = "Click once, drag up or down to reorder, then click again to confirm.\nDouble-click to select objects"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        scene   = context.scene
        entries = scene.optiflow_flat_entries
        idx     = scene.optiflow_flat_index
        if idx < 0 or idx >= len(entries):
            return {'CANCELLED'}
        fe = entries[idx]
        self._tracked_gi       = fe.group_index
        self._tracked_ii       = fe.item_index
        self._is_group_row     = (fe.entry_type == 'GROUP')
        self._state            = {'last_y': event.mouse_y}
        self._orig_x           = event.mouse_x
        self._orig_y           = event.mouse_y
        self._accum_y          = 0.0
        self._auto_expanded_gi = -1
        self._reordered        = False
        self._invoke_time      = time.time()
        context.window.cursor_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            scene      = context.scene
            row_height = 20 * context.preferences.system.ui_scale
            self._accum_y += self._state['last_y'] - event.mouse_y
            _wrap_cursor_y(context, event, self._state)

            steps = int(self._accum_y / row_height)
            if steps != 0:
                self._accum_y -= steps * row_height
                step_fn = self._step_down if steps > 0 else self._step_up
                for _ in range(abs(steps)):
                    if not step_fn(scene):
                        self._accum_y = 0.0
                        break
                context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            context.window.cursor_warp(self._orig_x, self._orig_y)
            context.window.cursor_set('DEFAULT')
            if not self._reordered and time.time() - self._invoke_time < 0.25:
                return self._select(context)
            # Collapse auto expanded group if item landed elsewhere
            if not self._is_group_row and self._auto_expanded_gi != -1:
                if self._tracked_gi != self._auto_expanded_gi:
                    context.scene.optiflow_groups[self._auto_expanded_gi].expanded = False
                    rebuild_flat_entries(context.scene)
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            context.window.cursor_warp(self._orig_x, self._orig_y)
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _step_down(self, scene):
        """Move the tracked entry one row down."""
        groups = scene.optiflow_groups
        gi, ii = self._tracked_gi, self._tracked_ii
        if self._is_group_row:
            if gi + 1 >= len(groups):
                return False
            groups.move(gi, gi + 1)
            self._tracked_gi = gi + 1
        else:
            group = groups[gi]
            if ii + 1 < len(group.items):
                move_item_between_groups(scene, gi, ii, gi, ii + 1)
                self._tracked_ii = ii + 1
            elif gi + 1 < len(groups):
                self._handle_group_transition(scene, gi, gi + 1)
                move_item_between_groups(scene, gi, ii, gi + 1, 0)
                self._tracked_gi = gi + 1
                self._tracked_ii = 0
            else:
                return False
        rebuild_flat_entries(scene)
        scene.optiflow_flat_index = find_flat_idx(
            scene, self._tracked_gi, self._tracked_ii,
        )
        self._reordered = True
        return True

    def _step_up(self, scene):
        """Move the tracked entry one row up."""
        groups = scene.optiflow_groups
        gi, ii = self._tracked_gi, self._tracked_ii
        if self._is_group_row:
            if gi - 1 < 0:
                return False
            groups.move(gi, gi - 1)
            self._tracked_gi = gi - 1
        else:
            group = groups[gi]
            if ii - 1 >= 0:
                move_item_between_groups(scene, gi, ii, gi, ii - 1)
                self._tracked_ii = ii - 1
            elif gi - 1 >= 0:
                dst_ii = len(groups[gi - 1].items)
                self._handle_group_transition(scene, gi, gi - 1)
                move_item_between_groups(scene, gi, ii, gi - 1, dst_ii)
                self._tracked_gi = gi - 1
                self._tracked_ii = dst_ii
            else:
                return False
        rebuild_flat_entries(scene)
        scene.optiflow_flat_index = find_flat_idx(
            scene, self._tracked_gi, self._tracked_ii,
        )
        self._reordered = True
        return True

    def _handle_group_transition(self, scene, leaving_gi, entering_gi):
        """Auto expand/collapse groups during cross group drag."""
        groups = scene.optiflow_groups
        if self._auto_expanded_gi == leaving_gi:
            groups[leaving_gi].expanded = False
            self._auto_expanded_gi = -1
        if not groups[entering_gi].expanded:
            groups[entering_gi].expanded = True
            self._auto_expanded_gi = entering_gi

    def _select(self, context):
        """Select viewport objects for the double-clicked entry."""
        scene  = context.scene
        groups = scene.optiflow_groups
        gi     = self._tracked_gi
        if gi < 0 or gi >= len(groups):
            return {'CANCELLED'}
        bpy.ops.object.select_all(action='DESELECT')
        first = None
        if self._is_group_row:
            for item in groups[gi].items:
                for ref in item.objects:
                    obj = ref.object
                    if obj and obj.type == 'MESH' and get_prefix(obj) not in _SELECT_SKIP:
                        obj.select_set(True)
                        if first is None:
                            first = obj
        else:
            ii = self._tracked_ii
            if ii < 0 or ii >= len(groups[gi].items):
                return {'CANCELLED'}
            for ref in groups[gi].items[ii].objects:
                obj = ref.object
                if obj and obj.type == 'MESH':
                    obj.select_set(True)
                    if first is None:
                        first = obj
        if first:
            context.view_layer.objects.active = first
        return {'FINISHED'}

    def execute(self, context):
        return {'FINISHED'}

# endregion

# region Exporter Drag

class EXPORTERS_OT_drag(Operator):
    """Drag to reorder exporters in the list."""
    bl_idname  = "exporters.drag"
    bl_label   = "Drag"
    bl_description = "Click once, drag up or down to reorder, then click again to confirm"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        if not context.scene.exporters:
            return {'CANCELLED'}
        self._state   = {'last_y': event.mouse_y}
        self._accum_y = 0.0
        context.window.cursor_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            scene      = context.scene
            row_height = 20 * context.preferences.system.ui_scale
            self._accum_y += self._state['last_y'] - event.mouse_y
            _wrap_cursor_y(context, event, self._state)

            steps = int(self._accum_y / row_height)
            if steps != 0:
                self._accum_y -= steps * row_height
                idx     = scene.exporters_index
                new_idx = max(0, min(idx + steps, len(scene.exporters) - 1))
                if new_idx != idx:
                    scene.exporters.move(idx, new_idx)
                    scene.exporters_index = new_idx
                    for area in context.window.screen.areas:
                        area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type in {'LEFTMOUSE', 'RIGHTMOUSE', 'RET', 'ESC'}:
            context.window.cursor_set('DEFAULT')
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

# endregion
