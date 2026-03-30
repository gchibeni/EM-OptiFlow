import bpy
import os
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, IntProperty
from ..core import constants, helpers

# region Placeholder

class placeholder(Operator):
    """Stub operator for unimplemented features."""
    bl_idname  = "optiflow.placeholder"
    bl_label   = "Placeholder"
    bl_description = "Placeholder"

    def execute(self, context):
        return {'FINISHED'}


class OPT_OT_wip_popup(Operator):
    """Generic work in progress dialog."""
    bl_idname  = "optiflow.wip_popup"
    bl_label   = "Work In Progress"
    bl_description = "\u200b"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=220)

    def draw(self, context):
        self.layout.label(text="Work in progress.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}

# endregion

# region Groups

class OPT_OT_add_group(Operator):
    """Create a new group below the current selection."""
    bl_idname  = "optiflow.add_group"
    bl_label   = "Add Group"
    bl_description = "Add a new group."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene  = context.scene
        groups = scene.optiflow_groups
        existing = {g.name for g in groups}
        n = 1
        while f"NEW_GROUP_{n}" in existing:
            n += 1
        name        = f"New Group {n}"
        g           = groups.add()
        g.name      = name
        g.prev_name = name
        g.expanded  = True
        new_gi = len(groups) - 1
        # Insert below the currently selected group
        fe = helpers.get_active_entry(scene)
        insert_after = (fe.group_index + 1) if fe else new_gi
        if insert_after < new_gi:
            groups.move(new_gi, insert_after)
            new_gi = insert_after
        helpers.rebuild_and_select(scene, new_gi, -1)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}


class OPT_OT_confirm_merge(Operator):
    """Confirm and merge two groups with the same name."""
    bl_idname  = "optiflow.confirm_merge"
    bl_label   = "Merge Groups"
    bl_options = {'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        scene = context.scene
        if scene.get("_optiflow_merge_gi", -1) < 0:
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(
            self, width=300, confirm_text="Merge",
        )

    def draw(self, context):
        name = context.scene.get("_optiflow_merge_name", "")
        self.layout.label(text=f'A group named "{name}" already exists.')
        self.layout.separator(type='LINE')

    def execute(self, context):
        scene    = context.scene
        merge_gi = scene.get("_optiflow_merge_gi", -1)
        dup_gi   = scene.get("_optiflow_merge_dup_gi", -1)
        if merge_gi < 0 or dup_gi < 0:
            return {'CANCELLED'}
        groups = scene.optiflow_groups
        if merge_gi >= len(groups) or dup_gi >= len(groups):
            return {'CANCELLED'}
        src, dst = groups[merge_gi], groups[dup_gi]
        for item in src.items:
            new_item      = dst.items.add()
            new_item.name = item.name
            helpers.clone_item_props(item, new_item)
            helpers.clone_item_refs(item, new_item)
        groups.remove(merge_gi)
        scene["_optiflow_merge_gi"]    = -1
        scene["_optiflow_merge_dup_gi"] = -1
        helpers.rebuild_flat_entries(scene)
        return {'FINISHED'}

# endregion

# region Add

class OPT_OT_add_empty(Operator):
    """Create an empty item in the current group."""
    bl_idname  = "optiflow.add_empty"
    bl_label   = "Add Empty"
    bl_description = "Add a new empty item"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        group, gi = helpers.ensure_default_group(scene)
        existing = {it.name for it in group.items}
        n = 1
        while f"New Object {n}" in existing:
            n += 1
        it           = group.items.add()
        it.name      = f"New Object {n}"
        it.item_type = 'OBJECT'
        if not group.expanded:
            group.expanded = True
        new_ii = len(group.items) - 1
        helpers.rebuild_and_select(scene, gi, new_ii)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

# endregion

# region Edit

class OPT_OT_edit_item(Operator):
    """Edit the selected item properties and object references."""
    bl_idname  = "optiflow.edit_item"
    bl_label   = "Edit Item"
    bl_description = "Edit the selected item."
    bl_options = {'UNDO', 'INTERNAL'}

    edit_name:      StringProperty(name="Name")       # type: ignore
    edit_alias:     StringProperty(name="Alias")       # type: ignore
    edit_item_type: EnumProperty(
        name="Type", items=constants.ITEM_TYPE,
    )  # type: ignore
    edit_tile_mesh: EnumProperty(
        name="Mesh", items=constants.MESH_TYPE,
    )  # type: ignore

    def invoke(self, context, event):
        fe = helpers.get_active_entry(context.scene)
        if fe is None or fe.entry_type == 'GROUP':
            return {'CANCELLED'}
        item = context.scene.optiflow_groups[fe.group_index].items[fe.item_index]
        # Snapshot current values into the buffer
        self.edit_name      = item.name
        self.edit_alias     = item.alias
        self.edit_item_type = item.item_type
        self.edit_tile_mesh = item.tile_mesh
        if not item.objects or item.objects[-1].object is not None:
            item.objects.add()
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        from ..ui.file_dialogs import prop_input
        fe   = helpers.get_active_entry(context.scene)
        item = context.scene.optiflow_groups[fe.group_index].items[fe.item_index]
        layout = self.layout
        prop_input(layout, self, "Name:", "edit_name")
        prop_input(layout, self, "Alias:", "edit_alias")
        prop_input(layout, self, "Type:", "edit_item_type")
        if self.edit_item_type == 'TILE/MATERIAL':
            layout.separator(type='LINE')
            prop_input(layout, self, "Mesh:", "edit_tile_mesh")
        layout.separator(type='LINE')
        layout.label(text="Objects:")
        box = layout.box()
        for i, ref in enumerate(item.objects):
            row = box.row(align=True)
            row.prop(ref, "object", text="")
            is_trailing_empty = (ref.object is None and i == len(item.objects) - 1)
            if not is_trailing_empty:
                op           = row.operator("optiflow.edit_item_remove_object", text="", icon='TRASH')
                op.item_gi   = fe.group_index
                op.item_ii   = fe.item_index
                op.ref_index = i
        layout.separator(type='LINE')

    def execute(self, context):
        scene = context.scene
        fe    = helpers.get_active_entry(scene)
        item  = scene.optiflow_groups[fe.group_index].items[fe.item_index]
        item.item_type = self.edit_item_type
        item.tile_mesh = self.edit_tile_mesh
        item.name      = self.edit_name
        item.alias     = self.edit_alias
        if self.edit_item_type == 'TILE/MATERIAL':
            _apply_tile_mesh(context, item, self.edit_tile_mesh)
        helpers.rebuild_flat_entries(scene)
        return {'FINISHED'}


class OPT_OT_edit_item_remove_object(Operator):
    """Unassign an object reference from an item."""
    bl_idname  = "optiflow.edit_item_remove_object"
    bl_label   = "Remove Object"
    bl_description = "Unassign object from the item"
    bl_options = {'UNDO', 'INTERNAL'}

    item_gi:   IntProperty(options={'HIDDEN'})  # type: ignore
    item_ii:   IntProperty(options={'HIDDEN'})  # type: ignore
    ref_index: IntProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        item = context.scene.optiflow_groups[self.item_gi].items[self.item_ii]
        item.objects.remove(self.ref_index)
        return {'FINISHED'}

# endregion

# region Duplicate

class OPT_OT_duplicate(Operator):
    """Duplicate the selected group or item with all objects."""
    bl_idname  = "optiflow.duplicate"
    bl_label   = "Duplicate"
    bl_description = "Duplicate the selected item.\nIncluding all object references."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        fe = helpers.get_active_entry(scene)
        if fe is None:
            return {'CANCELLED'}
        groups     = scene.optiflow_groups
        gi         = fe.group_index
        collection = context.collection or context.scene.collection
        if fe.entry_type == 'GROUP':
            self._duplicate_group(scene, groups, gi, collection)
        else:
            self._duplicate_item(scene, groups, gi, fe.item_index, collection)
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

    def _duplicate_group(self, scene, groups, gi, collection):
        """Clone a group including all items and their scene objects."""
        src      = groups[gi]
        new_name = helpers.copy_name(src.name, {g.name for g in groups})
        dst          = groups.add()
        dst.name     = new_name
        dst.prev_name = new_name
        dst.expanded = src.expanded
        for item in src.items:
            ni      = dst.items.add()
            ni.name = item.name
            helpers.clone_item_props(item, ni)
            helpers.clone_item_objects(item, ni, collection)
        groups.move(len(groups) - 1, gi + 1)
        helpers.rebuild_and_select(scene, gi + 1, -1)

    def _duplicate_item(self, scene, groups, gi, ii, collection):
        """Clone an item with deep copied objects within the same group."""
        group    = groups[gi]
        src      = group.items[ii]
        new_name = helpers.copy_name(src.name, {it.name for it in group.items})
        dst      = group.items.add()
        dst.name = new_name
        helpers.clone_item_props(src, dst)
        helpers.clone_item_objects(src, dst, collection)
        new_ii = len(group.items) - 1
        group.items.move(new_ii, ii + 1)
        helpers.rebuild_and_select(scene, gi, ii + 1)

# endregion

# region Delete

class OPT_OT_delete(Operator):
    """Delete the selected group or item and its exclusive objects."""
    bl_idname  = "optiflow.delete"
    bl_label   = "Delete"
    bl_description = "Delete the selected item.\nExclusive referenced objects will also be deleted."
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        idx   = scene.optiflow_flat_index
        fe    = helpers.get_active_entry(scene)
        if fe is None:
            return {'CANCELLED'}
        groups = scene.optiflow_groups
        gi     = fe.group_index
        if fe.entry_type == 'GROUP':
            self._delete_group(groups, gi)
        else:
            self._delete_item(groups, gi, fe.item_index)
        helpers.rebuild_flat_entries(scene)
        scene.optiflow_flat_index = max(
            0, min(idx, len(scene.optiflow_flat_entries) - 1),
        )
        helpers.tag_redraw_all(context)
        return {'FINISHED'}

    def _delete_group(self, groups, gi):
        """Remove a group and delete its exclusive scene objects."""
        src = groups[gi]
        to_delete = {}
        for item in src.items:
            for ref in item.objects:
                if ref.object is not None:
                    to_delete[ref.object.as_pointer()] = ref.object
        referenced = helpers.collect_referenced_ptrs(groups, skip_gi=gi)
        groups.remove(gi)
        helpers.delete_unreferenced(to_delete, referenced)

    def _delete_item(self, groups, gi, ii):
        """Remove an item and delete its exclusive scene objects."""
        item = groups[gi].items[ii]
        to_delete = {
            ref.object.as_pointer(): ref.object
            for ref in item.objects if ref.object is not None
        }
        referenced = helpers.collect_referenced_ptrs(
            groups, skip_item_ptr=item.as_pointer(),
        )
        groups[gi].items.remove(ii)
        helpers.delete_unreferenced(to_delete, referenced)

# endregion

# region Mesh Templates

def _import_template_mesh(tile_mesh_type):
    """Import the FBX template for a mesh type, return the Mesh datablock."""
    mesh_filename = f"MESH_{tile_mesh_type}.fbx"
    addon_dir     = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    mesh_path     = os.path.join(addon_dir, "meshes", mesh_filename)
    if not os.path.isfile(mesh_path):
        return None
    before = set(bpy.data.objects[:])
    bpy.ops.import_scene.fbx(filepath=mesh_path)
    imported = [o for o in bpy.data.objects if o not in before]
    if not imported:
        return None
    template_obj = next((o for o in imported if o.type == 'MESH'), None)
    if template_obj is None:
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        return None
    template_mesh = template_obj.data
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return template_mesh


def _apply_tile_mesh(context, item, tile_mesh_type):
    """Swap mesh data for item objects to match the selected mesh type."""
    template_mesh = _import_template_mesh(tile_mesh_type)
    if template_mesh is None:
        return
    mesh_refs = [
        (ref, ref.object) for ref in item.objects
        if ref.object is not None and ref.object.type == 'MESH'
    ]
    if not mesh_refs:
        # No objects yet, create one from the template
        new_mesh = template_mesh.copy()
        new_mesh.name = f"MESH_{item.name}"
        new_obj = bpy.data.objects.new(f"MESH_{item.name}", new_mesh)
        collection = context.collection or context.scene.collection
        collection.objects.link(new_obj)
        if item.objects and item.objects[-1].object is None:
            item.objects.remove(len(item.objects) - 1)
        item.objects.add().object = new_obj
    else:
        # Replace mesh data preserving materials
        for ref, obj in mesh_refs:
            old_materials = [slot.material for slot in obj.material_slots]
            old_mesh      = obj.data
            new_mesh      = template_mesh.copy()
            new_mesh.name = obj.name
            obj.data      = new_mesh
            obj.data.materials.clear()
            for mat in old_materials:
                obj.data.materials.append(mat)
            if old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
    # Clean up template if unused
    if template_mesh.users == 0:
        bpy.data.meshes.remove(template_mesh)

# endregion
