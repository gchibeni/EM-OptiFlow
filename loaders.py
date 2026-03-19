import bpy
import math
from .functions import file_input, dir_input
import bpy
import os
from bpy_extras.io_utils import ImportHelper
from . import functions
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

# region Popups

class IMPORT_OT_popup(Operator):
    bl_idname = "loaders.import_popup"
    bl_label = "Import"
    bl_options = {'REGISTER', 'UNDO'}

    # Common properties
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "import_type")
        if scene.import_type == 'OBJECT':
            file_input(layout, scene, "Model:", "import_model", "fbx,obj,glb,gltf")
            file_input(layout, scene, "Collider:", "import_collider", "fbx,obj,glb,gltf")
            dir_input(layout, scene, "Texture Folder:", "import_texture_folder")
        elif scene.import_type == 'TILES/MATERIALS':
            dir_input(layout, scene, "Texture Folder:", "import_texture_folder")
            layout.prop(scene, "import_texture_size")

    def execute(self, context):
        scene = context.scene
        self.report({'INFO'}, f"Importing {scene.import_type}")
        # TODO: Implement import logic.
        match scene.import_type:
            case 'OBJECT':
                if not scene.import_model:
                    self.report({'ERROR'}, "Model file is required for Object import.")
                    return {'CANCELLED'}
                if not scene.import_texture_folder:
                    self.report({'ERROR'}, "Texture folder is required for Object import.")
                    return {'CANCELLED'}
                self.report({'INFO'}, f"Model: {scene.import_model}")
                self.report({'INFO'}, f"Collider: {scene.import_collider}")
                self.report({'INFO'}, f"Texture Folder: {scene.import_texture_folder}")
            case 'TILES/MATERIALS':
                if not scene.import_texture_folder:
                    self.report({'ERROR'}, "Texture folder is required for Tiles/Materials import.")
                    return {'CANCELLED'}
                tiles = import_tiles(scene.import_texture_folder, scene.import_texture_size)
                self.report({'INFO'}, f"Texture Folder: {scene.import_texture_folder}")
                self.report({'INFO'}, f"Texture Size: {scene.import_texture_size}")
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
                box.prop(exporter, "prefix")
                box.prop(exporter, "preset")
                if exporter.preset == "":
                    set_box = layout.box()
                    set_box.prop(exporter, "scale")
                    set_box.prop(exporter, "apply_transforms")
                    set_box.prop(exporter, "embed_materials")
                    set_box.prop(exporter, "animations")

    def execute(self, context):
        self.report({'INFO'}, f"Exporting ...")
        # TODO: Implement export logic.
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

# region Functions

def arrange_nodes(node_tree):
    nodes = node_tree.nodes
    tex_x = -800
    util_x = -400
    bsdf_x = 0
    out_x = 300
    y = 0
    y_step = -300
    # Stack texture nodes vertically
    for node in nodes:
        if node.type == 'TEX_IMAGE':
            node.location = (tex_x, y)
            y += y_step
    # Utility nodes
    for node in nodes:
        if node.type == 'NORMAL_MAP':
            node.location = (util_x, -200)

        elif node.type == 'INVERT':
            node.location = (util_x, -400)
    # Core nodes
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            node.location = (bsdf_x, 0)

        elif node.type == 'OUTPUT_MATERIAL':
            node.location = (out_x, 0)

def get_temp_path(filepath, max_size):
    base = os.path.splitext(os.path.basename(filepath))[0]
    res = f"{int(max_size/1024)}K"
    name = f"{base}_{res}"
    ext = "jpg"
    temp_dir = bpy.app.tempdir
    temp_path = os.path.join(temp_dir, f"{name}.{ext}")
    # Avoid overwrite → increment
    i = 1
    while os.path.exists(temp_path):
        temp_path = os.path.join(temp_dir, f"{name}_{i:03d}.{ext}")
        i += 1
    return temp_path

def load_and_resize_texture(filepath, max_size, is_color=True):
    temp_path = get_temp_path(filepath, max_size)
    # Use filename as Blender image name
    image_name = os.path.basename(temp_path)
    # Check if already exists in Blender
    existing = bpy.data.images.get(image_name)
    if existing:
        return existing
    original_img = bpy.data.images.load(filepath)
    original_img.pixels[0]
    needs_resize = max(original_img.size) > max_size
    if needs_resize:
        original_img.scale(max_size, max_size)
        original_img.filepath_raw = temp_path
        original_img.file_format = 'JPEG' if is_color else 'PNG'
        original_img.save()
        # Load resized version
        new_img = bpy.data.images.load(temp_path)
        new_img.name = image_name  # ensure consistent naming
        if not is_color:
            new_img.colorspace_settings.name = 'Non-Color'
        new_img.pack()
        # Remove original image
        if original_img.users == 0:
            bpy.data.images.remove(original_img)
        # Cleanup temp
        try:
            os.remove(temp_path)
        except:
            pass
        return new_img
    else:
        # No resize → reuse original but rename to match system
        original_img.name = image_name
        if not is_color:
            original_img.colorspace_settings.name = 'Non-Color'
        original_img.pack()
        return original_img

def find_texture(folder, keywords):
    for f in os.listdir(folder):
        name = f.lower()
        for kw in keywords:
            if kw.lower() in name:
                return os.path.join(folder, f)
    return None

def add_tex_node(image, label, nodes, sRGB = True):
    tex_node = nodes.new(type="ShaderNodeTexImage")
    tex_node.image = image
    tex_node.label = label
    tex_node.image.colorspace_settings.name = 'sRGB' if sRGB else 'Non-Color'
    return tex_node

def import_tile_mesh(texture_folder, texture_size):
    max_size = int(texture_size)
    # Find textures
    basecolor_path = find_texture(texture_folder, ["basecolor", "albedo", "diffuse"])
    roughness_path = find_texture(texture_folder, ["roughness", "rough", "rmap"])
    reflect_path = find_texture(texture_folder, ["reflect", "reflective", "reflection", "specular"])
    metallic_path = find_texture(texture_folder, ["metallic", "metal", "metalness"])
    normal_path = find_texture(texture_folder, ["normal", "nmap"])
    if not basecolor_path:
        return None
    # Name based on basecolor
    name = os.path.splitext(os.path.basename(basecolor_path))[0]
    # Object setup
    plane = bpy.data.objects.get(name)
    if plane:
        # Reuse existing object
        bpy.context.view_layer.objects.active = plane
    else:
        bpy.ops.mesh.primitive_plane_add(size=1, rotation=(math.radians(-90), 0, 0))
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        plane = bpy.context.active_object
        plane.name = name
    # Material setup
    if plane.data.materials:
        mat = plane.data.materials[0]
    else:
        mat = bpy.data.materials.new("Mat")
        mat.use_nodes = True
        plane.data.materials.append(mat)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    # If material is empty or you want to rebuild
    # if len(nodes) <= 2:
    nodes.clear()
    # Core nodes
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    # else:
    #     # Try to find existing nodes
    #     bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    #     output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
    #     if not bsdf:
    #         bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    #     if not output:
    #         output = nodes.new(type="ShaderNodeOutputMaterial")
    #         links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    # Textures
    basecolor_tex = load_and_resize_texture(basecolor_path, max_size, True)
    roughness_tex = load_and_resize_texture(roughness_path, max_size, False) if roughness_path else None
    reflect_tex = load_and_resize_texture(reflect_path, max_size, False) if reflect_path else None
    metallic_tex = load_and_resize_texture(metallic_path, max_size, False) if metallic_path else None
    normal_tex = load_and_resize_texture(normal_path, max_size, False) if normal_path else None

    # Apply nodes
    def get_or_create_tex(label, image, sRGB=True):
        for n in nodes:
            if n.type == 'TEX_IMAGE' and n.label == label:
                return n
        node = add_tex_node(image, label, nodes, sRGB=sRGB)
        return node
    # Basecolor
    if basecolor_tex:
        node = get_or_create_tex("BaseColor", basecolor_tex, True)
        links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    # Roughness
    if roughness_tex:
        node = get_or_create_tex("Roughness", roughness_tex, False)
        links.new(node.outputs['Color'], bsdf.inputs['Roughness'])
    # Reflect → invert → roughness
    if reflect_tex:
        refl_node = get_or_create_tex("Reflect", reflect_tex, False)
        invert_node = next((n for n in nodes if n.type == 'INVERT'), None)
        if not invert_node:
            invert_node = nodes.new(type="ShaderNodeInvert")
        links.new(refl_node.outputs['Color'], invert_node.inputs['Color'])
        links.new(invert_node.outputs['Color'], bsdf.inputs['Roughness'])
    # Metallic
    if metallic_tex:
        node = get_or_create_tex("Metallic", metallic_tex, False)
        links.new(node.outputs['Color'], bsdf.inputs['Metallic'])
    # Normal
    if normal_tex:
        norm_node = get_or_create_tex("Normal", normal_tex, False)
        norm_map = next((n for n in nodes if n.type == 'NORMAL_MAP'), None)
        if not norm_map:
            norm_map = nodes.new(type="ShaderNodeNormalMap")
        links.new(norm_node.outputs['Color'], norm_map.inputs['Color'])
        links.new(norm_map.outputs['Normal'], bsdf.inputs['Normal'])
    arrange_nodes(mat.node_tree)
    return plane

def import_tiles(texture_folder, texture_size):
    path = bpy.path.abspath(texture_folder)
    import_tile_mesh(path, texture_size)

# endregion
