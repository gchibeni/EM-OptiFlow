from .functions import *
from .classes import *

import bpy
import os
from bpy.types import (
    Operator,
    Collection,
    Panel,
    Operator,
    PropertyGroup,
    UIList
)
from bpy.props import (
    EnumProperty,
    CollectionProperty,
    PointerProperty,
    IntProperty,
    FloatProperty,
)

# region Lists

class SCENEITEMS_UL_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scene = context.scene
        row = layout.row(align=True)
        uncertain = "?" in item.sku
        if item.sku == "" or not item.collection:
            row.alert = True
        # Left padding
        row.separator(factor=0.5)
        # Type icon
        match item.item_type:
            case 'OBJECT':
                row.label(icon='STRIP_COLOR_01' if uncertain else 'MATSHADERBALL')
            case 'TILE/MATERIAL':
                row.label(icon='STRIP_COLOR_01' if uncertain else 'MESH_GRID')
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
        row = layout.row()
        row.operator("optimization.create", icon='MOD_REMESH')
        row.operator("optimization.import", icon='IMPORT')
        row.operator("optimization.export", icon='EXPORT')
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
        count = len(scene.scene_items)
        row.label(text=f"Items ({count})" if count else "Items")
        if scene.show_items:
            row = layout.row()
            # List
            row.template_list(
                "SCENEITEMS_UL_list",
                "",
                scene,
                "scene_items",
                scene,
                "scene_items_index",
                rows=8
            )
            # Buttons
            col = row.column(align=True)
            col.operator("sceneitems.add", icon='ADD', text="")
            col.operator("sceneitems.remove", icon='REMOVE', text="")
            col.separator()
            col.operator("sceneitems.move_up", icon='TRIA_UP', text="")
            col.operator("sceneitems.move_down", icon='TRIA_DOWN', text="")
            col.separator()
            col.prop(scene, "scene_items_isolate", text="", icon="HIDE_ON" if scene.scene_items_isolate else "HIDE_OFF", toggle=True)
            col.prop(scene, "scene_items_quick_edit", text="", icon="GREASEPENCIL")
            col.separator(factor=4.0, type="LINE")
            col.operator("sceneitems.auto_fill", text="", icon="SPREADSHEET")
            # Active item properties
            if scene.scene_items and scene.scene_items_index >= 0:
                item = scene.scene_items[scene.scene_items_index]
                box = layout.box()
                row = box.row()
                row.prop(item, "item_type")
                row.prop(scene, "code", text="Code", placeholder="EM")
                box.separator(type="LINE")
                box.prop(item, "collection")
                box.prop(item, "sku")
                box.prop(item, "subfolder")
                dir_input(box, item, "Textures:", "textures_path")
                if item.textures_path != "":
                    box.prop(item, "textures_size")
                if item.item_type == 'TILE/MATERIAL':
                    box.prop(item, "mesh_type")
                box.separator(type="LINE")
                row = box.row()
                row.enabled = item.collection is not None and item.sku != "" # Disable if empty
                row.operator("sceneitems.apply")
                layout.separator()
                row = layout.row()
                row.operator("sceneitems.apply_all")
                row.enabled = any(i.collection and i.sku for i in scene.scene_items)
        layout.separator(type='LINE')

# endregion

# region Popups

class IMPORT_OT_popup(Operator):
    bl_idname = "loaders.import_popup"
    bl_label = "Import"
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "import_type")
        layout.separator(type='LINE')
        if scene.import_type == 'OBJECT':
            file_input(layout, scene, "Model:", "import_model", "fbx,obj,glb,gltf")
            file_input(layout, scene, "Collider:", "import_collider", "fbx,obj,glb,gltf")
            dir_input(layout, scene, "Texture Folder:", "import_texture_folder")
        elif scene.import_type == 'TILES/MATERIALS':
            dir_input(layout, scene, "Texture Folder:", "import_texture_folder")
            layout.prop(scene, "import_texture_size")
        layout.separator(type='LINE')

    def execute(self, context):
        scene = context.scene
        match scene.import_type:
            case 'OBJECT':
                if not scene.import_model:
                    self.report({'ERROR'}, "Model file is required for Object import.")
                    return {'CANCELLED'}
                if not scene.import_texture_folder:
                    self.report({'ERROR'}, "Texture folder is required for Object import.")
                    return {'CANCELLED'}
                start_object_import(scene.import_model, scene.import_collider, scene.import_texture_folder, scene.import_texture_size)
                return {'FINISHED'}
            case 'TILES/MATERIALS':
                if not scene.import_texture_folder:
                    self.report({'ERROR'}, "Texture folder is required for Tiles/Materials import.")
                    return {'CANCELLED'}
                start_tiles_import(scene.import_texture_folder, scene.import_texture_size)
                return {'FINISHED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=400,
            confirm_text="Import"
        )

class EXPORT_OT_popup(Operator):
    bl_idname = "loaders.export_popup"
    bl_label = "Export"
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        dir_input(layout, scene, "Export Path:", "export_path")
        layout.prop(scene, "copyright_text")
        layout.separator(type='LINE')
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
            layout.separator(type='LINE')
            row = layout.row()
            row.prop(
                scene,
                "show_exporters",
                icon="TRIA_DOWN" if scene.show_exporters else "TRIA_RIGHT",
                icon_only=True,
                emboss=False
            )
            row.label(text="Settings")
            if scene.show_exporters:
                exporter = scene.exporters[scene.exporters_index]
                box = layout.box()
                box.prop(exporter, "exporter_type")
                dir_input(box, exporter, "Override Path:", "override_path")
                box.prop(exporter, "prefix")
                set_box = layout.box()
                if exporter.exporter_type != 'GLTF':
                    set_box.prop(exporter, "scale")
                    set_box.prop(exporter, "apply_transforms")
                set_box.prop(exporter, "embed_materials")
                if exporter.exporter_type != 'OBJ':
                    set_box.prop(exporter, "animations")
        layout.separator(type='LINE')

    def execute(self, context):
        scene = context.scene
        self.report({'INFO'}, f"Exporting ...")
        was_isolated = scene.scene_items_isolate
        if was_isolated:
            scene.scene_items_isolate = False
        for exporter in scene.exporters:
            for item in scene.scene_items:
                export_item(item, exporter)
        if was_isolated:
            scene.scene_items_isolate = True
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=400,
            confirm_text="Export"
        )

class CREATE_OT_popup(Operator):
    bl_idname = "loaders.create_popup"
    bl_label = "Create"
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text="Work in progress...")

    def execute(self, context):
        self.report({'INFO'}, f"Creating ...")
        # TODO: Implement creation logic.
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=400,
            confirm_text="Create"
        )

# endregion
