import bpy
import bmesh
import mathutils
import os
import shutil
from bpy.types import Operator, Menu
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty
from ..core import constants
from ..core.helpers import (
    get_active_item, ensure_default_group,
    rebuild_and_select, tag_redraw_all, set_invisible_mat,
)
from .file_dialogs import prop_input

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
    bl_options = {'UNDO'}

    item_mode: EnumProperty(
        name="Mode",
        items=[
            ('SINGLE',   'Single',   'All selected objects into one item'),
            ('MULTIPLE', 'Multiple', 'One item per selected object'),
        ],
        default='SINGLE',
    )  # type: ignore

    def invoke(self, context, event):
        if len(context.selected_objects) <= 1:
            self.item_mode = 'SINGLE'
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        prop_input(self.layout, self, "Mode:", "item_mode", expand=True)
        self.layout.separator(type='LINE')

    def execute(self, context):
        scene    = context.scene
        selected = list(context.selected_objects)
        if not selected:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        group, gi = ensure_default_group(scene)

        if self.item_mode == 'MULTIPLE':
            for obj in selected:
                existing = {it.name for it in group.items}
                n = 1
                while f"NEW_OBJECT_{n}" in existing:
                    n += 1
                item           = group.items.add()
                item.name      = f"NEW_OBJECT_{n}"
                item.item_type = 'OBJECT'
                item.objects.add().object = obj
            if not group.expanded:
                group.expanded = True
            rebuild_and_select(scene, gi, len(group.items) - 1)
            tag_redraw_all(context)
            self.report({'INFO'}, f"Created {len(selected)} item(s)")
        else:
            existing = {it.name for it in group.items}
            n = 1
            while f"NEW_OBJECT_{n}" in existing:
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

class OPTIFLOW_OT_change_textures(Operator):
    """Change textures of the selected scene objects."""
    bl_idname  = "optiflow.ctx_change_textures"
    bl_label   = "Change Textures"
    bl_description = "Change textures of the selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    tex_roughness_enabled: BoolProperty(name="Toggle Roughness", description="Replaces roughness \u2014 multiplies values if a map is provided (using a mask if available)", default=False)  # type: ignore
    tex_roughness: FloatProperty(name="Roughness", subtype='PERCENTAGE', min=0.0, max=100.0, default=50.0)  # type: ignore
    tex_metallic_enabled: BoolProperty(name="Toggle Metallic", description="Replaces metallic \u2014 multiplies values if a map is provided (using a mask if available)", default=False)  # type: ignore
    tex_metallic: FloatProperty(name="Metallic", subtype='PERCENTAGE', min=0.0, max=100.0, default=50.0)  # type: ignore
    tex_size_enabled: BoolProperty(name="Toggle Resize", default=False)  # type: ignore
    tex_size: EnumProperty(name="Size", items=constants.TEXTURE_SIZES, default='4096')  # type: ignore
    tex_compression_enabled: BoolProperty(name="Toggle Compression", default=False)  # type: ignore
    tex_compression: EnumProperty(
        name="Compression",
        items=[
            ('AUTO',     'Auto',           'Preserve details \u2014 Minimum quality'),
            ('SMALLEST', 'Smallest Size',  'Lighter size, Lower quality'),
            ('BALANCED', 'Balanced',       'Moderate size \u2014 Medium quality'),
            ('HIGHER',   'Higher Quality', 'Heavier size \u2014 Higher quality'),
        ],
        default='AUTO',
    )  # type: ignore
    tex_format_enabled: BoolProperty(name="Toggle Reformat", default=False)  # type: ignore
    tex_format: EnumProperty(
        name="Format",
        items=[
            ('AUTO', 'Auto', ''),
            ('JPG',  'JPG',  ''),
            ('PNG',  'PNG',  ''),
            ('WEBP', 'WEBP', ''),
        ],
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def invoke(self, context, event):
        from ..operators import items as _items_mod
        _items_mod._tex_groups.clear()
        _items_mod._tex_current_group = 0
        if hasattr(context.scene, "optiflow_tex_display"):
            context.scene.optiflow_tex_display.clear()
        self.tex_roughness_enabled   = False
        self.tex_roughness           = 50.0
        self.tex_metallic_enabled    = False
        self.tex_metallic            = 50.0
        self.tex_size_enabled        = False
        self.tex_size                = '4096'
        self.tex_compression_enabled = False
        self.tex_compression         = 'AUTO'
        self.tex_format_enabled      = False
        self.tex_format              = 'JPG'
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        from ..operators import items as _items_mod
        _tex_groups        = _items_mod._tex_groups
        _tex_current_group = _items_mod._tex_current_group

        layout = self.layout
        row = layout.row(align=True)
        row.operator("optiflow.select_textures", text="Select Texture(s)")
        if _tex_groups:
            row.operator("optiflow.clear_textures", text="", icon='X')
        else:
            row.operator("optiflow.select_textures", text="", icon='IMPORT')
        layout.separator(type='LINE')
        if _tex_groups:
            group_keys = list(_tex_groups.keys())
            n_groups   = len(group_keys)
            group_idx  = max(0, min(_tex_current_group, n_groups - 1))

            if n_groups > 1:
                display_name = group_keys[group_idx] if group_keys[group_idx] else "\u2014\u2014"
                count_str    = f"{group_idx + 1:02d}/{n_groups:02d}"
                row = layout.row(align=True)
                sub = row.row(align=True)
                sub.enabled = group_idx > 0
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_LEFT_BAR")
                op.action = 'FIRST'
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_LEFT")
                op.action = 'PREV'
                mid = row.row()
                mid.alignment = 'CENTER'
                mid.label(text=f"{display_name} ({count_str})" if group_keys[group_idx] else f"{display_name}")
                sub = row.row(align=True)
                sub.enabled = group_idx < n_groups - 1
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_RIGHT")
                op.action = 'NEXT'
                op = sub.operator("optiflow.tex_group_nav", text="", icon="TRIA_RIGHT_BAR")
                op.action = 'LAST'
                last = row.row(align=True)
                last.operator("optiflow.remove_tex_group", text="", icon='TRASH')

            layout.template_list(
                "OPT_UL_tex_list", "",
                context.scene, "optiflow_tex_display",
                context.scene, "optiflow_tex_display_index",
                rows=6,
            )
            for label, enabled_prop, value_prop, slider in [
                ("Roughness:", "tex_roughness_enabled", "tex_roughness",       True),
                ("Metallic:",  "tex_metallic_enabled",  "tex_metallic",        True),
                ("Size:",      "tex_size_enabled",      "tex_size",            False),
                ("Compression:", "tex_compression_enabled", "tex_compression", False),
                ("Format:",    "tex_format_enabled",    "tex_format",          False),
            ]:
                split = layout.split(factor=0.23)
                split.label(text=label)
                row = split.row(align=True)
                row.prop(self, enabled_prop, text="", icon="DOT", toggle=True)
                sub = row.row(align=True)
                sub.enabled = getattr(self, enabled_prop)
                sub.prop(self, value_prop, text="", slider=slider)

    def execute(self, context):
        from ..operators import items as _items_mod
        from ..operators.tex_import import schedule_tex_import
        from ..core.helpers import get_prefix

        _tex_groups        = _items_mod._tex_groups
        _tex_current_group = _items_mod._tex_current_group
        _classify_tex      = _items_mod._classify_tex

        scene = context.scene
        overrides = {
            'roughness_enabled':   bool(self.tex_roughness_enabled),
            'roughness':           float(self.tex_roughness),
            'metallic_enabled':    bool(self.tex_metallic_enabled),
            'metallic':            float(self.tex_metallic),
            'size_enabled':        bool(self.tex_size_enabled),
            'size':                str(self.tex_size),
            'compression_enabled': bool(self.tex_compression_enabled),
            'compression':         str(self.tex_compression),
            'format_enabled':      bool(self.tex_format_enabled),
            'format':              str(self.tex_format),
        }

        _SKIP = frozenset({'COL', 'PLACER', 'SNAP', 'GUIDE'})
        mesh_objs = [
            obj for obj in context.selected_objects
            if obj.type == 'MESH' and get_prefix(obj) not in _SKIP
        ]
        if not mesh_objs:
            self.report({'ERROR'}, "No valid mesh objects selected")
            return {'CANCELLED'}
        if not _tex_groups:
            self.report({'ERROR'}, "No textures selected")
            return {'CANCELLED'}

        old_mat_names   = set()
        old_image_names = set()
        for obj in mesh_objs:
            if obj.data:
                for mat in obj.data.materials:
                    if mat:
                        old_mat_names.add(mat.name)
                        if mat.use_nodes and mat.node_tree:
                            for node in mat.node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and node.image:
                                    old_image_names.add(node.image.name)
                obj.data.materials.clear()

        overrides['old_mat_names']   = list(old_mat_names)
        overrides['old_image_names'] = list(old_image_names)

        group_keys  = list(_tex_groups.keys())
        n_groups    = len(group_keys)
        n_objs      = len(mesh_objs)
        group_idx   = max(0, min(_tex_current_group, n_groups - 1))
        group_paths = _tex_groups[group_keys[group_idx]]

        if n_objs > 1:
            # Multiple objects: per-object color assignment if more than 1 color available
            colors = [p for p in group_paths if _classify_tex(os.path.basename(p)) == 'Color']
            if len(colors) > 1:
                overrides_mc = {**overrides, 'change_tex': True}
                schedule_tex_import(-1, -1, [o.name for o in mesh_objs], group_paths, overrides_mc, scene)
            else:
                schedule_tex_import(-1, -1, [o.name for o in mesh_objs], group_paths, overrides, scene)
        else:
            # Single object: use current navigation group, Color 1 only
            colors     = [p for p in group_paths if _classify_tex(os.path.basename(p)) == 'Color']
            shared     = [p for p in group_paths if _classify_tex(os.path.basename(p)) != 'Color']
            color_path = colors[0] if colors else None
            tex_paths  = ([color_path] if color_path else []) + shared
            schedule_tex_import(-1, -1, [mesh_objs[0].name], tex_paths, overrides, scene)

        tag_redraw_all(context)
        return {'FINISHED'}

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
    bl_options = {'UNDO'}

    GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}

    collider_mode: EnumProperty(
        name="Mode",
        items=[
            ('SINGLE',   'Single',   'One collider wrapping all selected objects'),
            ('MULTIPLE', 'Multiple', 'One collider per selected object'),
        ],
        default='SINGLE',
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def invoke(self, context, event):
        if len(context.selected_objects) <= 1:
            self.collider_mode = 'SINGLE'
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        prop_input(layout, self, "Mode:", "collider_mode", expand=True)
        layout.separator(type='LINE')

    def execute(self, context):
        selected = [o for o in context.selected_objects if o.type in self.GEOMETRY_TYPES]
        if not selected:
            self.report({'WARNING'}, "No geometry objects selected")
            return {'CANCELLED'}

        if self.collider_mode == 'MULTIPLE':
            for obj in selected:
                collider = self._make_collider(context, [obj])
                self._assign_to_item(context, collider, [obj])
            self.report({'INFO'}, f"Created {len(selected)} box collider(s)")
        else:
            collider = self._make_collider(context, selected)
            self._assign_to_item(context, collider, selected)
            self.report({'INFO'}, f"Created box collider '{collider.name}'")
        return {'FINISHED'}

    def _make_collider(self, context, objs):
        """Create and return a box collider wrapping the bounds of objs."""
        INF    = float('inf')
        min_co = mathutils.Vector(( INF,  INF,  INF))
        max_co = mathutils.Vector((-INF, -INF, -INF))
        for obj in objs:
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

        bpy.ops.mesh.primitive_cube_add(location=center)
        collider        = context.active_object
        collider.scale  = (size.x / 2, size.y / 2, size.z / 2)
        collider.name   = "COL"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        saved_cursor = context.scene.cursor.location.copy()
        context.scene.cursor.location = objs[0].matrix_world.translation.copy()
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
        context.scene.cursor.location = saved_cursor

        set_invisible_mat(collider, "ColMat")
        return collider

    def _assign_to_item(self, context, collider, source_objs):
        """Add collider to the OptiFlow item that owns any of source_objs, if found."""
        source_ptrs = {o.as_pointer() for o in source_objs}
        owner_item  = None
        for group in context.scene.optiflow_groups:
            for it in group.items:
                for ref in it.objects:
                    if ref.object is not None and ref.object.as_pointer() in source_ptrs:
                        owner_item = it
                        break
                if owner_item:
                    break
            if owner_item:
                break
        if owner_item is None:
            return
        if owner_item.objects and owner_item.objects[-1].object is None:
            owner_item.objects.remove(len(owner_item.objects) - 1)
        owner_item.objects.add().object = collider
        owner_item.objects.add()  # trailing empty slot
        tag_redraw_all(context)

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
        layout.operator("optiflow.set_preset", icon='MATSHADERBALL')
        layout.separator(type="LINE")
        layout.operator("optiflow.ctx_change_textures", icon='IMAGE_DATA')
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
