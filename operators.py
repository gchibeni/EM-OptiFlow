from .functions import *
from .classes import *

import bpy
import os
from bpy_extras.io_utils import ImportHelper
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

# region General

_last_dir = ""

class PROPERTIES_OT_dirpath(Operator):
    bl_idname = "ui.select_dirpath"
    bl_label = "Select Path"

    directory: StringProperty(options={'HIDDEN'}) #type: ignore # Stores the final path
    target_prop: StringProperty(options={'HIDDEN'})  #type: ignore # Property to set
    data_path: StringProperty(options={'HIDDEN'})  #type: ignore # Path to resolve target object
    filter_glob: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore

    def execute(self, context):
        global _last_dir
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        path = bpy.path.abspath(self.directory)
        # Show error if not a file
        if not os.path.isdir(path):
            self.report({'ERROR'}, "Selected path is not a valid directory")
            return {'CANCELLED'}
        _last_dir = path
        # Convert to relative path if possible
        blend_dir = os.path.dirname(bpy.data.filepath)
        if not blend_dir:
            setattr(target, self.target_prop, self.directory)
            return {'FINISHED'}
        try:
            rel_path = bpy.path.relpath(self.directory)
            setattr(target, self.target_prop, rel_path)
        except Exception:
            setattr(target, self.target_prop, self.directory)
        return {'FINISHED'}

    def invoke(self, context, event):
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        current_path = getattr(target, self.target_prop, "")
        # Determine starting path
        if current_path:
            abs_path = bpy.path.abspath(current_path)
        else:
            abs_path = ""
        if abs_path and os.path.exists(abs_path):
            start_path = abs_path
        elif _last_dir and os.path.exists(_last_dir):
            start_path = _last_dir
        else:
            blend_path = bpy.data.filepath
            blend_dir = os.path.dirname(blend_path) if blend_path else ""
            start_path = blend_dir if blend_dir and os.path.exists(blend_dir) else os.path.expanduser("~/Documents")
        self.directory = start_path
        #self.filter_glob = "DIR_PATH"  # Force directory selection
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class PROPERTIES_OT_filepath(Operator):
    bl_idname = "ui.select_filepath"
    bl_label = "Select File"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH") #type: ignore
    target_prop: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore
    data_path: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore # Path to resolve target object
    file_types: bpy.props.StringProperty(default="", options={'HIDDEN'}) #type: ignore
    filter_glob: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore

    def execute(self, context):
        global _last_dir
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        # Resolve full path
        path = bpy.path.abspath(self.filepath)
        # Show error if not a file
        if not os.path.isfile(path):
            self.report({'ERROR'}, "Selected path is not a valid file")
            return {'CANCELLED'}
        _last_dir = os.path.dirname(path)
        # Convert to relative path if possible
        blend_dir = os.path.dirname(bpy.data.filepath)
        if not blend_dir:
            setattr(target, self.target_prop, self.filepath)
            return {'FINISHED'}
        try:
            rel_path = bpy.path.relpath(self.filepath)
            setattr(target, self.target_prop, rel_path)
        except Exception:
            setattr(target, self.target_prop, self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        current_path = getattr(target, self.target_prop, "")
        # Determine starting path
        if current_path:
            abs_path = bpy.path.abspath(current_path)
            abs_path = os.path.dirname(abs_path) if os.path.isfile(abs_path) else abs_path
        else:
            abs_path = ""
        if abs_path and os.path.exists(abs_path):
            start_path = abs_path
        elif _last_dir and os.path.exists(_last_dir):
            start_path = _last_dir
        else:
            blend_path = bpy.data.filepath
            blend_dir = os.path.dirname(blend_path) if blend_path else ""
            start_path = blend_dir if blend_dir and os.path.exists(blend_dir) else os.path.expanduser("~/Documents")
        self.filepath = os.path.join(start_path, "")
        if self.file_types:
            types = [f"*.{ext.strip()}" for ext in self.file_types.split(",")]
            self.filter_glob = ";".join(types)
        else:
            self.filter_glob = ""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# endregion

# region SceneItems

class SCENEITEMS_OT_add(Operator):
    bl_idname = "sceneitems.add"
    bl_label = "Add"
    bl_description = "Add new item to the list"

    def execute(self, context):
        scene = context.scene
        item = scene.scene_items.add()
        item.name = f"Item {len(scene.scene_items)}"
        scene.scene_items_index = len(scene.scene_items) - 1
        return {'FINISHED'}

class SCENEITEMS_OT_remove(Operator):
    bl_idname = "sceneitems.remove"
    bl_label = "Remove"
    bl_description = "Remove selected item from the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if scene.scene_items:
            scene.scene_items.remove(index)
            scene.scene_items_index = max(0, index - 1)

        return {'FINISHED'}

class SCENEITEMS_OT_move_up(Operator):
    bl_idname = "sceneitems.move_up"
    bl_label = "Up"
    bl_description = "Move item up in the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if index > 0:
            scene.scene_items.move(index, index - 1)
            scene.scene_items_index -= 1

        return {'FINISHED'}

class SCENEITEMS_OT_move_down(Operator):
    bl_idname = "sceneitems.move_down"
    bl_label = "Down"
    bl_description = "Move item down in the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if index < len(scene.scene_items) - 1:
            scene.scene_items.move(index, index + 1)
            scene.scene_items_index += 1

        return {'FINISHED'}

class SCENEITEMS_OT_apply(Operator):
    bl_idname = "sceneitems.apply"
    bl_label = "Apply"
    bl_description = "Apply item changes to Collection"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index
        # Get selected item
        if index < 0 or index >= len(scene.scene_items):
            self.report({'WARNING'}, "No item selected")
            return {'CANCELLED'}
        item = scene.scene_items[index]
        apply_item_changes(item)
        self.report({'INFO'},"Applying changes...")
        return {'FINISHED'}

class SCENEITEMS_OT_apply_all(Operator):
    bl_idname = "sceneitems.apply_all"
    bl_label = "Apply All"
    bl_description = "Apply all Items changes to all Collections"

    def execute(self, context):
        scene = context.scene
        for item in scene.scene_items:
            if item.sku != "" and item.collection is not None:
                apply_item_changes(item)
        self.report({'INFO'},"Applying changes...")
        return {'FINISHED'}

# endregion

# region Optimizations

class OPTIMIZATION_OT_create(Operator):
    bl_idname = "optimization.create"
    bl_label = "Create"
    bl_description = "Open creation window"

    def execute(self, context):
        bpy.ops.loaders.create_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Creating...")
        print("=== CREATE ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

class OPTIMIZATION_OT_export(Operator):
    bl_idname = "optimization.export"
    bl_label = "Export"
    bl_description = "Export optimized items using the configured exporters and settings"

    def execute(self, context):
        bpy.ops.loaders.export_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Exporting...")
        print("=== EXPORT ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

class OPTIMIZATION_OT_import(Operator):
    bl_idname = "optimization.import"
    bl_label = "Import"
    bl_description = "Import Furnitures, Tiles and Textures to be optimized"

    def execute(self, context):
        bpy.ops.loaders.import_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Importing...")
        print("=== IMPORT ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

# endregion

# region Exporters

class EXPORTERS_OT_add(Operator):
    bl_idname = "exporters.add"
    bl_label = "Add"
    bl_description = "Add new exporter to the list"

    def execute(self, context):
        scene = context.scene
        exporter = scene.exporters.add()
        exporter.name = f"Exporter {len(scene.exporters)}"
        scene.exporters_index = len(scene.exporters) - 1
        return {'FINISHED'}

class EXPORTERS_OT_remove(Operator):
    bl_idname = "exporters.remove"
    bl_label = "Remove"
    bl_description = "Remove selected exporter from the list"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if scene.exporters:
            scene.exporters.remove(index)
            scene.exporters_index = max(0, index - 1)

        return {'FINISHED'}

class EXPORTERS_OT_move_up(Operator):
    bl_idname = "exporters.move_up"
    bl_label = "Up"
    bl_description = "Move exporter up in the list (higher priority)"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if index > 0:
            scene.exporters.move(index, index - 1)
            scene.exporters_index -= 1

        return {'FINISHED'}

class EXPORTERS_OT_move_down(Operator):
    bl_idname = "exporters.move_down"
    bl_label = "Down"
    bl_description = "Move exporter down in the list (lower priority)"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if index < len(scene.exporters) - 1:
            scene.exporters.move(index, index + 1)
            scene.exporters_index += 1

        return {'FINISHED'}

# endregion
