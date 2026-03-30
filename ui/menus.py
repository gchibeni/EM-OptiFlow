import bpy
from bpy.types import Operator, Menu
from ..core.helpers import (
    get_active_item, ensure_default_group,
    rebuild_and_select, tag_redraw_all,
)

# region Add Menu

class OPT_MT_add_menu(Menu):
    """Menu for adding groups, items, or empty entries."""
    bl_idname = "OPT_MT_add_menu"
    bl_label  = "Add"
    bl_description = "Shows extra item options"

    def draw(self, context):
        layout = self.layout
        layout.operator("optiflow.add_group", text="Group", icon="COLLECTION_NEW")
        layout.operator("optiflow.wip_popup", text="Item(s)", icon="FILE_NEW")
        layout.separator(type='LINE')
        layout.operator("optiflow.add_empty", text="Empty", icon="FILE_NEW")

# endregion

# region Exporter Menu

class EXPORTERS_MT_add_menu(Menu):
    """Menu for adding exporters by format type."""
    bl_idname = "EXPORTERS_MT_add_menu"
    bl_label  = "Add Exporter"

    def draw(self, context):
        layout = self.layout
        for etype, label, icon in [
            ('GLTF', "glTF", 'META_CUBE'),
            ('FBX', "FBX", 'MESH_UVSPHERE'),
            ('OBJ', "OBJ", 'META_CAPSULE'),
        ]:
            op = layout.operator("exporters.add", text=label, icon=icon)
            op.exporter_type = etype

# endregion

# region Context Menu

class OPTIFLOW_OT_create_object_item(Operator):
    """Create an Object item from selected viewport objects."""
    bl_idname  = "optiflow.ctx_create_object_item"
    bl_label   = "Create Object Item"
    bl_description = "Create an Object item from the selected viewport objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene    = context.scene
        selected = list(context.selected_objects)
        if not selected:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        group, gi = ensure_default_group(scene)
        existing  = {it.name for it in group.items}
        n = 1
        while f"New Object {n}" in existing:
            n += 1
        item           = group.items.add()
        item.name      = f"New Object {n}"
        item.item_type = 'OBJECT'
        for obj in selected:
            item.objects.add().object = obj
        if not group.expanded:
            group.expanded = True
        rebuild_and_select(scene, gi, len(group.items) - 1)
        tag_redraw_all(context)
        self.report({'INFO'}, f"Created item '{item.name}' with {len(selected)} object(s)")
        return {'FINISHED'}


class OPTIFLOW_OT_assign_to_selected_item(Operator):
    """Assign selected viewport objects to the current OptiFlow item."""
    bl_idname  = "optiflow.ctx_assign_to_item"
    bl_label   = "Assign to Selected Item"
    bl_description = "Assign selected viewport objects to the currently selected OptiFlow item"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            get_active_item(context.scene) is not None
            and len(context.selected_objects) > 0
        )

    def execute(self, context):
        scene = context.scene
        item  = get_active_item(scene)
        if item is None:
            self.report({'WARNING'}, "No item selected in OptiFlow")
            return {'CANCELLED'}
        selected      = context.selected_objects
        existing_ptrs = {
            ref.object.as_pointer()
            for ref in item.objects if ref.object is not None
        }
        # Remove trailing empty slot
        if len(item.objects) > 0 and item.objects[-1].object is None:
            item.objects.remove(len(item.objects) - 1)
        added = 0
        for obj in selected:
            if obj.as_pointer() not in existing_ptrs:
                item.objects.add().object = obj
                added += 1
        item.objects.add()  # trailing empty slot
        tag_redraw_all(context)
        self.report({'INFO'}, f"Assigned {len(selected)} object(s) to '{item.name}'")
        return {'FINISHED'}


class OPTIFLOW_OT_replace_selected_item(Operator):
    """Replace item objects with the currently selected viewport objects."""
    bl_idname  = "optiflow.ctx_replace_item"
    bl_label   = "Replace from Selected Item"
    bl_description = "Replace the selected OptiFlow item's objects with the selected viewport objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            get_active_item(context.scene) is not None
            and len(context.selected_objects) > 0
        )

    def execute(self, context):
        scene = context.scene
        item  = get_active_item(scene)
        if item is None:
            self.report({'WARNING'}, "No item selected in OptiFlow")
            return {'CANCELLED'}
        selected = context.selected_objects
        item.objects.clear()
        for obj in selected:
            item.objects.add().object = obj
        item.objects.add()  # trailing empty slot
        tag_redraw_all(context)
        self.report({'INFO'}, f"Replaced objects in '{item.name}' with {len(selected)} object(s)")
        return {'FINISHED'}


class OPTIFLOW_OT_change_texture(Operator):
    """Placeholder for texture change feature."""
    bl_idname  = "optiflow.ctx_change_texture"
    bl_label   = "Change Texture"
    bl_description = "Change texture of the selected objects (WIP)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return context.window_manager.invoke_popup(self, width=300)

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Change Texture \u2014 Work in Progress", icon='IMAGE_DATA')
        layout.separator()
        layout.label(text="This feature is not yet implemented.")


class OPTIFLOW_MT_context_menu(Menu):
    """OptiFlow submenu in the viewport right click context menu."""
    bl_idname = "OPTIFLOW_MT_context_menu"
    bl_label  = "OptiFlow"

    def draw(self, context):
        if not context.selected_objects:
            return
        layout = self.layout
        layout.operator("optiflow.ctx_create_object_item", icon='ADD')
        layout.operator("optiflow.ctx_assign_to_item", icon='LINKED')
        layout.operator("optiflow.ctx_replace_item", icon='FILE_REFRESH')
        layout.operator("optiflow.ctx_change_texture", icon='IMAGE_DATA')


def _draw_optiflow_context_menu(self, context):
    """Prepend OptiFlow submenu to the object context menu."""
    try:
        if not context.selected_objects:
            return
        layout = self.layout
        layout.menu("OPTIFLOW_MT_context_menu", icon="FORCE_VORTEX")
        layout.separator()
    except Exception:
        pass

# endregion

# region Registration

def register():
    bpy.types.VIEW3D_MT_object_context_menu.prepend(_draw_optiflow_context_menu)


def unregister():
    bpy.types.VIEW3D_MT_object_context_menu.remove(_draw_optiflow_context_menu)

# endregion
