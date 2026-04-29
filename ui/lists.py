import bpy
from bpy.types import Operator, UIList
from bpy.props import IntProperty
from ..core.helpers import rebuild_flat_entries, find_flat_idx, get_active_entry
from ..core.constants import EXPORTER_ICONS

# region Flat List Helpers

def _deferred_expand_all(scene):
    """Timer callback to expand all groups for filtered view."""
    for group in scene.optiflow_groups:
        group.expanded = True
    rebuild_flat_entries(scene)
    return None


def _deferred_restore_expanded(scene, saved):
    """Timer callback to restore expanded state after filter clears."""
    groups = scene.optiflow_groups
    for gi, was_expanded in saved.items():
        if gi < len(groups):
            groups[gi].expanded = was_expanded
    rebuild_flat_entries(scene)
    return None

# endregion

# region Item List

class OPT_UL_flat(UIList):
    """Flat hierarchical list showing groups and items."""
    bl_idname = "OPT_UL_flat"

    _saved_expanded    = {}
    _filter_was_active = False

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        """Render a single row in the flat item list."""
        groups    = context.scene.optiflow_groups
        gi        = item.group_index
        ii        = item.item_index
        is_group  = (item.entry_type == 'GROUP')
        is_active = getattr(active_data, active_propname) == index
        if gi < 0 or gi >= len(groups):
            return
        row = layout.row(align=True)
        if is_group:
            self._draw_group_row(row, groups[gi], is_active, index)
        else:
            if ii < 0 or ii >= len(groups[gi].items):
                return
            self._draw_item_row(row, groups[gi].items[ii], item, is_active)
        row.separator(factor=1.0)
        self._draw_active_buttons(row, is_active, is_group)

    def _draw_group_row(self, row, group, is_active, index):
        """Render a group row with expand toggle and inline name."""
        if not is_active and (group.name == "" or len(group.items) <= 0):
            row.alert = True
        expanded = group.expanded
        if len(group.items) <= 0:
            row.label(text="", icon='REMOVE')
        elif is_active:
            op = row.operator(
                "optiflow.toggle_expand", text="",
                icon='DOWNARROW_HLT' if expanded else 'RIGHTARROW',
                emboss=False,
            )
            op.flat_index = index
        else:
            row.label(text="", icon='DOWNARROW_HLT' if expanded else 'RIGHTARROW')
        row.prop(group, "name", text="", emboss=False, placeholder="\u2014\u2014")

    def _draw_item_row(self, row, item_obj, flat_entry, is_active):
        """Render an item row with type icon and inline name."""
        if not is_active and ((item_obj.name == "" or not any(ref.object for ref in item_obj.objects)) or "INVALID" in item_obj.name):
            row.alert = True
        row.separator(factor=3.0)
        icon_name = flat_entry.bl_rna.properties['entry_type'].enum_items[flat_entry.entry_type].description
        row.label(text="", icon=icon_name or 'OBJECT_DATA')
        row.prop(item_obj, "name", text="", emboss=False, placeholder="\u2014\u2014")

    def _draw_active_buttons(self, row, is_active, is_group):
        """Draw edit, duplicate, delete, and drag buttons for the active row."""
        if is_active:
            if not is_group:
                row.operator("optiflow.edit_item", text="", icon='MODIFIER_ON', emboss=False)
            row.operator("optiflow.duplicate", text="", icon='DUPLICATE', emboss=False)
            row.operator("optiflow.delete",    text="", icon='TRASH',     emboss=False)
            row.separator(factor=2.8)
            row.operator("optiflow.item_drag", text="", icon='GRIP', emboss=False)
        else:
            row.label(text="", icon='BLANK1')

    def filter_items(self, context, data, propname):
        """Filter entries by name, auto expanding groups while active."""
        scene      = context.scene
        groups     = scene.optiflow_groups
        has_filter = bool(self.filter_name)

        if has_filter and not self._filter_was_active:
            self.__class__._filter_was_active = True
            for gi, group in enumerate(groups):
                self._saved_expanded[gi] = group.expanded
            bpy.app.timers.register(
                lambda: _deferred_expand_all(scene), first_interval=0.0,
            )
        elif not has_filter and self._filter_was_active:
            self.__class__._filter_was_active = False
            saved = dict(self._saved_expanded)
            self._saved_expanded.clear()
            bpy.app.timers.register(
                lambda: _deferred_restore_expanded(scene, saved), first_interval=0.0,
            )

        entries   = getattr(data, propname)
        flt_flags = []
        for fe in entries:
            gi, ii = fe.group_index, fe.item_index
            if fe.entry_type == 'GROUP':
                name = groups[gi].name if gi < len(groups) else ""
            else:
                name = (
                    groups[gi].items[ii].name
                    if gi < len(groups) and ii < len(groups[gi].items) else ""
                )
            if self.filter_name and self.filter_name.lower() not in name.lower():
                flt_flags.append(0)
            else:
                flt_flags.append(self.bitflag_filter_item)
        return flt_flags, []

    def draw_filter(self, context, layout):
        """Draw the search filter input."""
        row = layout.row()
        row.prop(self, "filter_name", text="")


class OPT_OT_toggle_expand(Operator):
    """Toggle a group's expanded/collapsed state."""
    bl_idname  = "optiflow.toggle_expand"
    bl_label   = "Toggle Group"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    flat_index: IntProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        scene   = context.scene
        entries = scene.optiflow_flat_entries
        if self.flat_index < 0 or self.flat_index >= len(entries):
            return {'CANCELLED'}
        fe = entries[self.flat_index]
        if fe.entry_type != 'GROUP':
            return {'CANCELLED'}
        gi    = fe.group_index
        group = scene.optiflow_groups[gi]
        group.expanded = not group.expanded
        rebuild_flat_entries(scene)
        scene.optiflow_flat_index = find_flat_idx(scene, gi, -1)
        return {'FINISHED'}

# endregion

# region Exporter List

class EXPORTERS_UL_list(UIList):
    """List showing configured exporters with action controls."""
    bl_idname = "EXPORTERS_UL_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        """Render a single exporter row."""
        is_active = getattr(active_data, active_property) == index
        row       = layout.row(align=True)
        type_icon = EXPORTER_ICONS.get(item.exporter_type, 'EXPORT')
        row.label(text="", icon=type_icon)
        label = item.exporter_type
        if item.prefix:
            label += f"  [{item.prefix}]"
        row.label(text=label)
        row.separator(factor=1.0)
        if is_active:
            self._draw_active_buttons(row, item, context.scene)
        else:
            row.label(text="", icon='BLANK1')

    def _draw_active_buttons(self, row, item, scene):
        """Draw action buttons for the active exporter row."""
        row.operator("exporters.open_folder", text="", icon='FOLDER_REDIRECT', emboss=False)
        row.separator(factor=2.8)
        row.operator("exporters.edit",      text="", icon='MODIFIER_ON', emboss=False)
        row.operator("exporters.duplicate", text="", icon='DUPLICATE',   emboss=False)
        row.operator("exporters.remove",    text="", icon='TRASH',       emboss=False)
        row.separator(factor=2.8)
        row.operator("exporters.drag", text="", icon='GRIP', emboss=False)

    def draw_filter(self, context, layout):
        """Draw the search filter input."""
        row = layout.row()
        row.prop(self, "filter_name", text="")

    def filter_items(self, context, data, propname):
        """Filter exporters by type and prefix."""
        exporters = getattr(data, propname)
        flt_flags = []
        if self.filter_name:
            query = self.filter_name.upper()
            for exp in exporters:
                searchable = exp.exporter_type + " " + exp.prefix
                if query in searchable.upper():
                    flt_flags.append(self.bitflag_filter_item)
                else:
                    flt_flags.append(0)
        else:
            flt_flags = [self.bitflag_filter_item] * len(exporters)
        return flt_flags, []

# endregion
