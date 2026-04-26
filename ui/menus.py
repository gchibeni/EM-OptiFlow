import bpy
import bmesh
import mathutils
import os
import shutil
from bpy.types import Operator, Menu
from bpy.props import StringProperty
from ..core.helpers import (
    get_active_item, ensure_default_group,
    rebuild_and_select, tag_redraw_all, set_invisible_mat,
)

# region Add Menu

class OPT_MT_add_menu(Menu):
    """Menu for adding groups, items, or empty entries."""
    bl_idname = "OPT_MT_add_menu"
    bl_label  = "Add"
    bl_description = "Create a new group, item, or empty entry in the current group"

    def draw(self, context):
        layout = self.layout
        layout.operator("optiflow.add_group", text="Group", icon="COLLECTION_NEW")
        layout.operator("optiflow.add_item", text="Item(s)", icon="FILE_NEW")
        layout.separator(type='LINE')
        layout.operator("optiflow.add_empty", text="Empty", icon="FILE_NEW")

# endregion

# region Exporter Menu

class EXPORTERS_MT_add_menu(Menu):
    """Menu for adding exporters by format type."""
    bl_idname = "EXPORTERS_MT_add_menu"
    bl_label  = "Add"
    bl_description = "Create a new exporter of the specified format"

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
        item.name      = f"NEW_OBJECT_{n}"
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

class OPTIFLOW_OT_unassign_from_selected_item(Operator):
    """Remove selected viewport objects from the current OptiFlow item."""
    bl_idname  = "optiflow.ctx_unassign_from_item"
    bl_label   = "Unassign from Selected Item"
    bl_description = "Remove selected viewport objects from the currently selected OptiFlow item"
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

        selected_ptrs = {obj.as_pointer() for obj in context.selected_objects}
        removed = 0
        i = len(item.objects) - 1
        while i >= 0:
            ref = item.objects[i]
            if ref.object is not None and ref.object.as_pointer() in selected_ptrs:
                item.objects.remove(i)
                removed += 1
            i -= 1

        tag_redraw_all(context)
        self.report({'INFO'}, f"Removed {removed} object(s) from '{item.name}'")
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

class OPTIFLOW_OT_extract_textures(Operator):
    """Extract all textures from selected objects' materials to a folder."""
    bl_idname  = "optiflow.ctx_extract_textures"
    bl_label   = "Extract Textures"
    bl_description = "Save all textures from selected objects to a folder"
    bl_options = {'REGISTER', 'UNDO'}

    # Extension map keyed by Blender's image.file_format
    _FORMAT_EXT = {
        'BMP':                  '.bmp',
        'IRIS':                 '.rgb',
        'PNG':                  '.png',
        'JPEG':                 '.jpg',
        'JPEG2000':             '.jp2',
        'TARGA':                '.tga',
        'TARGA_RAW':            '.tga',
        'CINEON':               '.cin',
        'DPX':                  '.dpx',
        'OPEN_EXR_MULTILAYER':  '.exr',
        'OPEN_EXR':             '.exr',
        'HDR':                  '.hdr',
        'TIFF':                 '.tif',
        'WEBP':                 '.webp',
    }

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def invoke(self, context, event):
        context.scene.optiflow_extract_tex_dir = ""
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text="Extract")

    def draw(self, context):
        from .file_dialogs import dir_input
        layout = self.layout
        dir_input(layout, context.scene, "Output Folder:", "optiflow_extract_tex_dir")
        layout.separator(type="LINE")

    def execute(self, context):
        output_dir = bpy.path.abspath(context.scene.optiflow_extract_tex_dir)
        if not os.path.isdir(output_dir):
            self.report({'ERROR'}, "Please select a valid output folder")
            return {'CANCELLED'}

        # Collect unique image textures from all selected objects
        images = set()
        for obj in context.selected_objects:
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes:
                    continue
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        images.add(node.image)

        if not images:
            self.report({'WARNING'}, "No textures found on selected objects")
            return {'CANCELLED'}

        saved   = 0
        skipped = 0

        for image in images:
            raw_path = image.filepath_raw
            basename = bpy.path.basename(raw_path) if raw_path else ""
            if not basename:
                ext      = self._FORMAT_EXT.get(image.file_format, '.png')
                basename = bpy.path.clean_name(image.name) + ext

            out_path  = os.path.join(output_dir, basename)
            is_packed = bool(image.packed_files)

            # File-based and not packed — copy the source file directly to
            # perfectly preserve the original format and compression.
            if not is_packed and raw_path:
                src = bpy.path.abspath(raw_path)
                if os.path.isfile(src):
                    shutil.copy2(src, out_path)
                    saved += 1
                    continue

            # Packed or generated — write via Blender using the image's own
            # format settings, then restore the original filepath.
            if not image.has_data:
                skipped += 1
                continue

            old_path = image.filepath_raw
            try:
                image.filepath_raw = out_path
                image.save()
                saved += 1
            except Exception as e:
                self.report({'WARNING'}, f"Could not save '{image.name}': {e}")
                skipped += 1
            finally:
                image.filepath_raw = old_path

        msg = f"Extracted {saved} texture(s)"
        if skipped:
            msg += f", skipped {skipped}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

class OPTIFLOW_OT_check_materials(Operator):
    """Apply invisible material to collider/guide objects and reload all textures."""
    bl_idname  = "optiflow.ctx_check_materials"
    bl_label   = "Check Materials"
    bl_description = "Apply ColMat to colliders/guides and reload textures on selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    INVISIBLE_PREFIXES = ("COL", "PLACER", "SNAP", "GUIDE")

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        mat_applied = 0
        images_reloaded = 0
        images_seen = set()

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            upper = obj.name.upper()
            if any(upper.startswith(p) for p in self.INVISIBLE_PREFIXES):
                set_invisible_mat(obj, "ColMat")
                mat_applied += 1
                continue

            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes:
                    continue
                for node in mat.node_tree.nodes:
                    if node.type != 'TEX_IMAGE' or not node.image:
                        continue
                    img = node.image
                    if img.as_pointer() in images_seen:
                        continue
                    images_seen.add(img.as_pointer())
                    if img.source == 'FILE' and img.filepath_raw:
                        img.reload()
                        images_reloaded += 1

        parts = []
        if mat_applied:
            parts.append(f"ColMat applied to {mat_applied} object(s)")
        if images_reloaded:
            parts.append(f"{images_reloaded} texture(s) reloaded")
        self.report({'INFO'}, ", ".join(parts) if parts else "Nothing to update")
        return {'FINISHED'}

class OPTIFLOW_OT_create_collider(Operator):
    """Create a box collider that wraps the bounds of the selected objects."""
    bl_idname  = "optiflow.ctx_create_collider"
    bl_label   = "Create Box Collider"
    bl_description = "Create a box collider that wraps the selected objects' bounds"
    bl_options = {'REGISTER', 'UNDO'}

    GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        selected = [o for o in context.selected_objects if o.type in self.GEOMETRY_TYPES]
        if not selected:
            self.report({'WARNING'}, "No geometry objects selected")
            return {'CANCELLED'}

        INF = float('inf')
        min_co = mathutils.Vector(( INF,  INF,  INF))
        max_co = mathutils.Vector((-INF, -INF, -INF))

        for obj in selected:
            for local_corner in obj.bound_box:
                world_corner = obj.matrix_world @ mathutils.Vector(local_corner)
                min_co.x = min(min_co.x, world_corner.x)
                min_co.y = min(min_co.y, world_corner.y)
                min_co.z = min(min_co.z, world_corner.z)
                max_co.x = max(max_co.x, world_corner.x)
                max_co.y = max(max_co.y, world_corner.y)
                max_co.z = max(max_co.z, world_corner.z)

        center = (min_co + max_co) / 2
        size   = max_co - min_co

        # primitive_cube_add creates a 2x2x2 cube, so half-extents = 1
        bpy.ops.mesh.primitive_cube_add(location=center)
        collider = context.active_object
        collider.scale = (size.x / 2, size.y / 2, size.z / 2)
        collider.name = "COL"

        # Bake scale into mesh data
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Move origin to the first selected object's world origin
        saved_cursor = context.scene.cursor.location.copy()
        context.scene.cursor.location = selected[0].matrix_world.translation.copy()
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
        context.scene.cursor.location = saved_cursor

        set_invisible_mat(collider, "ColMat")

        self.report({'INFO'}, f"Created box collider '{collider.name}'")
        return {'FINISHED'}

class OPTIFLOW_OT_apply_transforms(Operator):
    """Apply all transforms to selected objects, auto-making shared data single-user."""
    bl_idname  = "optiflow.ctx_apply_transforms"
    bl_label   = "Apply Transforms"
    bl_description = "Apply all selected objects transforms, making shared data single-user automatically"
    bl_options = {'REGISTER', 'UNDO'}

    GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        original_active   = context.view_layer.objects.active
        original_selected = list(context.selected_objects)

        for obj in original_selected:
            if obj.type not in self.GEOMETRY_TYPES:
                continue

            # Make data single-user silently if it is shared
            if obj.data is not None and obj.data.users > 1:
                obj.data = obj.data.copy()

            # Isolate object so transform_apply only acts on it
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        # Restore original selection
        for obj in original_selected:
            obj.select_set(True)
        context.view_layer.objects.active = original_active

        return {'FINISHED'}

class OPTIFLOW_OT_apply_deltas(Operator):
    """Apply rotation & scale to mesh data, then freeze all transforms to delta."""
    bl_idname  = "optiflow.ctx_apply_deltas"
    bl_label   = "Freeze Transforms"
    bl_description = "Apply rotation & scale, then move all transforms to delta"
    bl_options = {'REGISTER', 'UNDO'}

    GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        original_active   = context.view_layer.objects.active
        original_selected = list(context.selected_objects)

        for obj in original_selected:
            if obj.type not in self.GEOMETRY_TYPES:
                continue

            if obj.data is not None and obj.data.users > 1:
                obj.data = obj.data.copy()

            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

        for obj in original_selected:
            obj.select_set(True)
        context.view_layer.objects.active = original_active

        bpy.ops.object.transforms_to_deltas(mode='ALL')
        return {'FINISHED'}

class OPTIFLOW_OT_center_objects(Operator):
    """Move all selected objects to world origin (0, 0, 0)."""
    bl_idname  = "optiflow.ctx_center_objects"
    bl_label   = "Center to World"
    bl_description = "Move selected objects to world center"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        zero = (0.0, 0.0, 0.0)
        for obj in context.selected_objects:
            obj.location       = zero
            obj.delta_location = zero
        return {'FINISHED'}

class OPTIFLOW_OT_triangulate_ngons(Operator):
    """Triangulate only N-gon faces (5+ verts) on all selected mesh objects."""
    bl_idname  = "optiflow.ctx_triangulate_ngons"
    bl_label   = "Triangulate N-gons"
    bl_description = "Triangulate only N-gon faces on selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        total = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            ngons = [f for f in bm.faces if len(f.verts) > 4]
            if ngons:
                bmesh.ops.triangulate(bm, faces=ngons)
                total += len(ngons)
            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()
        self.report({'INFO'}, f"Triangulated {total} N-gon(s)")
        return {'FINISHED'}

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
        layout.operator("optiflow.ctx_unassign_from_item", icon='UNLINKED')
        layout.operator("optiflow.ctx_replace_item", icon='FILE_REFRESH')
        layout.separator(type="LINE")
        layout.operator("optiflow.ctx_change_texture", icon='IMAGE_DATA')
        layout.operator("optiflow.ctx_extract_textures", icon='FORCE_TEXTURE')
        layout.operator("optiflow.ctx_check_materials", icon='MATERIAL')
        layout.separator(type="LINE")
        layout.operator("optiflow.ctx_create_collider", icon='FILE_VOLUME')
        layout.operator("optiflow.ctx_apply_transforms", icon='OBJECT_ORIGIN')
        layout.operator("optiflow.ctx_apply_deltas", icon='FREEZE')
        layout.operator("optiflow.ctx_center_objects", icon='SNAP_FACE_CENTER')
        layout.separator(type="LINE")
        layout.operator("optiflow.ctx_triangulate_ngons", icon='MOD_SIMPLIFY')

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
