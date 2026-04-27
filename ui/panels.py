import bpy
import os
from bpy.types import Operator, Panel
from .file_dialogs import dir_input, prop_input

# region Header

def optiflow_buttons(self, context):
    """Draw isolate/reveal and options buttons in the viewport header."""
    layout = self.layout
    scene  = context.scene
    isolated = scene.get("optiflow_isolated", False)
    if isolated:
        layout.operator("optiflow.reveal", text="", icon='RESTRICT_VIEW_ON')
    else:
        layout.operator("optiflow.isolate", text="", icon='RESTRICT_VIEW_OFF')
    layout.operator("optiflow.options", text="", icon='GEOMETRY_SET')

# endregion

# region Options

class optiflow_options(Operator):
    """Toggle the OptiFlow side panel visibility."""
    bl_idname  = "optiflow.options"
    bl_label   = "OptiFlow"
    bl_description = "Open main panel for the optimization helper."

    def execute(self, context):
        space     = context.space_data
        ui_region = next((r for r in context.area.regions if r.type == 'UI'), None)
        if ui_region is None:
            return {'CANCELLED'}
        def switch_tab():
            try:
                ui_region.active_panel_category = "OptiFlow"
            except AttributeError:
                pass
            return None
        if not space.show_region_ui:
            space.show_region_ui = True
            bpy.app.timers.register(switch_tab, first_interval=0.01)
        elif ui_region.active_panel_category == "OptiFlow":
            space.show_region_ui = False
        else:
            space.show_region_ui = True
            bpy.app.timers.register(switch_tab, first_interval=0.01)
        return {'FINISHED'}

# endregion

# region Panel

class optiflow_main(Panel):
    """Main OptiFlow panel in the 3D viewport sidebar."""
    bl_label       = "OptiFlow"
    bl_idname      = "OPTIFLOW_PT_main"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "OptiFlow"

    def draw(self, context):
        _draw_main(self.layout, context)


def _draw_main(layout, context):
    """Render the main panel with items, exporters, and export button."""
    scene = context.scene
    layout.separator(type='LINE')
    _draw_items_section(layout, scene)
    layout.separator(type='LINE')
    _draw_exporters_section(layout, scene)
    layout.separator(type='LINE')
    _draw_export_button(layout, scene)
    _draw_import_progress(layout, scene)
    layout.separator(type='LINE')


def _draw_items_section(layout, scene):
    """Draw the collapsible items list with side controls."""
    items_header = layout.row()
    items_header.prop(
        scene, "show_items",
        icon='DOWNARROW_HLT' if scene.show_items else 'RIGHTARROW',
        icon_only=True, emboss=False,
    )
    items_header.label(text="Items")
    if scene.show_items:
        row = layout.row()
        row.template_list(
            "OPT_UL_flat", "optiflow_flat",
            scene, "optiflow_flat_entries",
            scene, "optiflow_flat_index",
            rows=10
        )
        col = row.column(align=True)
        col.menu("OPT_MT_add_menu", text="", icon="ADD")
        col.separator(type='LINE', factor=5.0)
        isolate_icon = 'HIDE_ON' if scene.get("optiflow_item_isolated", False) else 'HIDE_OFF'
        col.operator("optiflow.isolate_items", text="", icon=isolate_icon)
        col.operator("optiflow.auto_fill", text="", icon="SPREADSHEET")


def _draw_exporters_section(layout, scene):
    """Draw the collapsible exporters list with path inputs."""
    exp_header = layout.row()
    exp_header.prop(
        scene, "show_exporters",
        icon='DOWNARROW_HLT' if scene.show_exporters else 'RIGHTARROW',
        icon_only=True, emboss=False,
    )
    exp_header.label(text="Exporters")
    if scene.show_exporters:
        row = layout.row()
        row.template_list(
            "EXPORTERS_UL_list", "",
            scene, "exporters",
            scene, "exporters_index",
            rows=2
        )
        col = row.column(align=True)
        col.menu("EXPORTERS_MT_add_menu", icon='ADD', text="")
        col.separator(type='LINE', factor=5.0)
        dir_input(layout, scene, "Export Path:", "export_path")
        prop_input(layout, scene, "Copyright:", "copyright_text")


def _draw_export_button(layout, scene):
    """Draw the export button, enabled only when exportable items and valid paths exist."""
    has_exportable = any(
        any(ref.object for ref in item.objects)
        for group in scene.optiflow_groups
        for item in group.items
    )
    def _is_valid_path(exp):
        override = exp.override_path.strip()
        if override:
            return os.path.isdir(bpy.path.abspath(override))
        export = scene.export_path.strip()
        if export:
            return os.path.isdir(bpy.path.abspath(export))
        return True
    has_valid_path = (
        any(_is_valid_path(exp) for exp in scene.exporters)
        if scene.exporters else False
    )
    row         = layout.row()
    row.enabled = has_exportable and has_valid_path
    row.operator("optiflow.export_confirm", text="Export", icon="EXPORT")

def _draw_import_progress(layout, scene):
    """Draw a progress bar while textures are being imported in the background."""
    if not scene.optiflow_is_importing:
        return
    factor = scene.optiflow_tex_progress
    layout.separator(factor=0.5)
    layout.progress(
        factor=factor,
        text=f"Importing textures... {int(factor * 100)}%",
    )

# endregion

# region Registration

def register():
    bpy.types.VIEW3D_HT_header.append(optiflow_buttons)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(optiflow_buttons)

# endregion
