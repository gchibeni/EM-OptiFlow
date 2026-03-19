import bpy
import os
from .functions import file_input, dir_input
from . import loaders
from bpy.types import (
    Operator,
    Collection,
    Panel,
    Operator,
    PropertyGroup,
    UIList
)
from bpy.props import (
    StringProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
    IntProperty,
    FloatProperty,
    BoolProperty
)

# region Classes

class SceneItem(PropertyGroup):
    item_type: EnumProperty(
        name="Type",
        items=[
            ('OBJECT', "Object", ""),
            ('TILE/MATERIAL', "Tile/Material", ""),
        ],
        default='OBJECT'
    ) # type: ignore
    sku: StringProperty(name="SKU")  # type: ignore
    item_name: StringProperty(name="Name")  # type: ignore
    variation: StringProperty(name="Variation")  # type: ignore
    collection: PointerProperty(
        name="Collection",
        type=Collection
    )  # type: ignore

class ExporterItem(PropertyGroup):
    exporter_type: EnumProperty(
        name="Exporter",
        items=[
            ('GLTF', "glTF", ""),
            ('FBX', "FBX", ""),
            ('OBJ', "OBJ", ""),
        ],
        default='GLTF'
    )  # type: ignore

    preset: StringProperty(name="Preset")  # type: ignore

    prefix: StringProperty(name="Prefix")  # type: ignore

    scale: FloatProperty(
        name="Scale",
        default=1.0,
        min=0.0,
        max=1000.0
    )  # type: ignore

    apply_transforms: bpy.props.BoolProperty(
        name="Apply Transforms",
        default=True
    )  # type: ignore

    embed_materials: bpy.props.BoolProperty(
        name="Embed Materials",
        default=True
    )  # type: ignore

    animations: bpy.props.BoolProperty(
        name="Animations",
        default=True
    )  # type: ignore

# endregion

# region Lists

class SCENEITEMS_UL_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scene = context.scene
        row = layout.row(align=True)

        # Left padding
        row.separator(factor=0.5)

        # Type icon (visual clarity)
        match item.item_type:
            case 'OBJECT':
                row.label(icon='MATSHADERBALL')
            case 'TILE/MATERIAL':
                row.label(icon='MESH_GRID')

        # SKU shown but NOT editable (label instead of prop)
        sku_text = "SKU: " + (item.sku if item.sku else "-")

        row.label(text=sku_text)
        layout.prop(item, "item_type", text="", emboss=False)

        # Right padding
        row.separator(factor=0.5)

class EXPORTERS_UL_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        row.separator(factor=0.5)

        # Icon per exporter
        if item.exporter_type == 'GLTF':
            row.label(icon='META_CUBE')
        elif item.exporter_type == 'FBX':
            row.label(icon='MESH_UVSPHERE')
        else:
            row.label(icon='META_CAPSULE')
        split = row.split(factor=0.82)
        split.prop(item, "exporter_type", text="", emboss=False)
        split.alignment = 'RIGHT'
        split.label(text=item.prefix if item.prefix else "-")
        row.separator(factor=0.5)

#endregion

# region Panels

class SCENEITEMS_PT_optimization(Panel):
    bl_label = "Optimization"
    bl_idname = "SCENEITEMS_PT_optimization"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.operator("optimization.create", icon='MOD_REMESH')
        layout.operator("optimization.import", icon='IMPORT')
        layout.operator("optimization.export", icon='EXPORT')
        col = layout.column(align=True)
        split = col.split(factor=0.3)
        split.label(text="Initialism Code:")
        row = split.row(align=True)
        row.prop(scene, "code", text="")

        layout.separator(type='LINE')
        self.build_items_section(layout, scene)
        #self.build_exporters_section(layout, scene)

    def build_items_section(self, layout, scene):
        row = layout.row()
        row.prop(
            scene,
            "show_items",
            icon="TRIA_DOWN" if scene.show_items else "TRIA_RIGHT",
            icon_only=True,
            emboss=False
        )
        row.label(text="Items")
        if scene.show_items:
            row = layout.row()
            # List
            row.template_list(
                "SCENEITEMS_UL_list",
                "",
                scene,
                "scene_items",
                scene,
                "scene_items_index"
            )
            # Buttons
            col = row.column(align=True)
            col.operator("sceneitems.add", icon='ADD', text="")
            col.operator("sceneitems.remove", icon='REMOVE', text="")
            col.separator()
            col.operator("sceneitems.move_up", icon='TRIA_UP', text="")
            col.operator("sceneitems.move_down", icon='TRIA_DOWN', text="")
            # Active item properties
            if scene.scene_items and scene.scene_items_index >= 0:
                item = scene.scene_items[scene.scene_items_index]
                box = layout.box()
                box.prop(item, "sku")
                if item.item_type == 'TILE/MATERIAL':
                    box.prop(item, "item_name")
                    box.prop(item, "variation")
                box.prop(item, "item_type")
                box.prop(item, "collection")

                row = box.row()
                row.enabled = item.collection is not None and item.sku != "" # Disable if empty
                row.operator("sceneitems.apply")

    def build_exporters_section(self, layout, scene):
        layout.separator(type='LINE')
        row = layout.row()
        row.prop(
            scene,
            "show_exporters",
            icon="TRIA_DOWN" if scene.show_exporters else "TRIA_RIGHT",
            icon_only=True,
            emboss=False
        )
        row.label(text="Exporters")
        if scene.show_exporters:
            dir_input(layout, scene, "Export Path:", "export_path")
            # Copyright input
            col = layout.column(align=True)
            split = col.split(factor=0.3)
            split.label(text="Copyright:")
            split.prop(scene, "copyright_text", text="")

            row = layout.row()

            # List
            row.template_list(
                "EXPORTERS_UL_list",
                "",
                scene,
                "exporters",
                scene,
                "exporters_index"
            )

            # Buttons
            col = row.column(align=True)
            col.operator("exporters.add", icon='ADD', text="")
            col.operator("exporters.remove", icon='REMOVE', text="")
            col.separator()
            col.operator("exporters.move_up", icon='TRIA_UP', text="")
            col.operator("exporters.move_down", icon='TRIA_DOWN', text="")

            # Active exporter settings
            if scene.exporters and scene.exporters_index >= 0:
                exporter = scene.exporters[scene.exporters_index]
                box = layout.box()
                box.prop(exporter, "exporter_type")
                box.prop(exporter, "prefix")
                box.prop(exporter, "preset")
                if exporter.preset == "":
                    set_box = layout.box()
                    set_box.prop(exporter, "scale")
                    set_box.prop(exporter, "apply_transforms")
                    set_box.prop(exporter, "embed_materials")
                    set_box.prop(exporter, "animations")

# endregion
