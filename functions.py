import re
import bpy
import os
import math
from bpy.types import Scene, UILayout
from datetime import date

# region Variables

basecolor_names = ["basecolor", "albedo", "diffuse", "base_color", "color"]
roughness_names = ["roughness", "rough", "rmap"]
reflect_names = ["reflect", "reflective", "reflection", "specular"]
metallic_names = ["metallic", "metal", "metalness"]
normal_names = ["normal", "nmap"]
fbx_map = {"Bullnose": "MESH_BULLNOSE.fbx", "Covebase": "MESH_COVEBASE.fbx"}

# endregion

# region General

def purge_unused_data():
    # Images
    for img in bpy.data.images:
        if img.users == 0:
            bpy.data.images.remove(img)
    # Materials
    for mat in bpy.data.materials:
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    # Meshes
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    # Collections
    for col in bpy.data.collections:
        if col.users == 0:
            bpy.data.collections.remove(col)

def dir_input(layout: UILayout, context, label, target_prop):
    split = layout.split(factor=0.3)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_dirpath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop
    try:
        op.data_path = context.path_from_id()
    except (ValueError, AttributeError):
        op.data_path = ""

def file_input(layout: UILayout, context, label, target_prop, file_types=""):
    split = layout.split(factor=0.3)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_filepath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop
    op.file_types = file_types
    try:
        op.data_path = context.path_from_id()
    except (ValueError, AttributeError):
        op.data_path = ""

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

# endregion

# region Items

def get_item_name(item) -> str:
    code = bpy.context.scene.code.strip()
    if not code:
        code = "EM"
    sku = item.sku.strip().replace("-", ".").replace("_", ".")
    if not sku:
        sku = "000.000.000"
    item_name = f"{code}_{sku}".upper().replace(" ", "")
    return item_name

def apply_item_changes(item):
    if not item.collection:
        print("No collection assigned")
        return
    objects = [obj for obj in item.collection.objects if obj.type == 'MESH']
    if not objects:
        print("No mesh objects found in collection")
        return
    code = bpy.context.scene.code.strip()
    if not code:
        code = "EM"
    sku = item.sku.strip()
    mesh_name = f"MESH_{code}_{sku}"
    col_name = f"COL_{code}_{sku}"
    mesh_obj = None
    col_obj = None
    # Try to find by name
    COL_KEYS = ["col", "collider"]
    MESH_KEYS = ["mesh", "3d"]

    for obj in objects:
        name_lower = obj.name.lower()
        if any(k in name_lower for k in MESH_KEYS):
            mesh_obj = obj
        elif any(k in name_lower for k in COL_KEYS):
            col_obj = obj
    # 2. Fallback (vertex count)
    if not mesh_obj or not col_obj:
        sorted_objs = sorted(
            objects,
            key=lambda o: len(o.data.vertices)
        )

        if not col_obj:
            col_obj = sorted_objs[0]  # least verts

        if not mesh_obj:
            mesh_obj = sorted_objs[-1]  # most verts
    # 3. Rename safely
    def rename(obj, new_name):
        if not obj:
            return
        obj.name = new_name
        if obj.data:
            obj.data.name = new_name
    rename(col_obj, col_name.upper())
    rename(mesh_obj, mesh_name.upper())

    rename_material(col_obj, "ColMat")
    rename_material(mesh_obj, "Mat")

    if mesh_obj and item.textures_path:
        import_textures(mesh_obj, item.textures_path, item.textures_size)
    #item.textures_path = ""

    print(f"Renamed Mesh: {mesh_obj.name if mesh_obj else 'None'}")
    print(f"Renamed Col: {col_obj.name if col_obj else 'None'}")

def rename_material(obj, new_name):
    if not obj or obj.type != 'MESH':
        return
    no_mat = False
    for i, slot in enumerate(obj.material_slots):
        mat = slot.material
        if mat:
            mat.name = new_name
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf and new_name == "ColMat":
                bsdf.inputs["Alpha"].default_value = 0
        else:
            no_mat = True
    if len(obj.material_slots) == 0:
        no_mat = True
    if no_mat:
        # Create new material
        new_mat = bpy.data.materials.new(name=new_name)
        new_mat.use_nodes = True
        # Optional: set a default color
        bsdf = new_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
            if new_name == "ColMat":
                bsdf.inputs["Alpha"].default_value = 0
        # Assign to all slots
        for i in range(len(obj.material_slots)):
            obj.material_slots[i].material = new_mat
        # If object has no material slots, add one
        if len(obj.material_slots) == 0:
            obj.data.materials.append(new_mat)

# endregion

# region Exporter

def get_copyright():
    scene = bpy.context.scene
    copyright = scene.copyright_text.strip()
    if not copyright:
        return ""
    return f"© {date.today().year} {copyright}"

def get_export_path(export_path):
    # If user provided path
    if export_path:
        return bpy.path.abspath(export_path)
    # If .blend is saved -> use its folder
    blend_path = bpy.data.filepath
    if blend_path:
        return os.path.dirname(blend_path)
    # Fallback → Documents folder
    return os.path.join(os.path.expanduser("~"), "Documents")

def export_item(item, exporter):
    if item.sku == "" or not item.collection:
        return
    scene = bpy.context.scene
    export_path = get_export_path(exporter.override_path.strip()) if exporter.override_path.strip() else get_export_path(scene.export_path.strip())
    final_path = os.path.join(export_path, item.subfolder.strip()) if item.subfolder.strip() else export_path
    prefix = f"{exporter.prefix.strip()}_" if exporter.prefix.strip() else ""
    item_name = prefix + get_item_name(item)
    collection = item.collection
    print(f"Exporting {collection.name} = {item_name} | {get_copyright()}")
    bpy.ops.object.select_all(action='DESELECT')
    objs = [obj for obj in collection.all_objects if obj.type == 'MESH']
    if not objs:
        return
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    for exporter in bpy.context.scene.exporters:
        match exporter.exporter_type:
            case 'GLTF':
                bpy.ops.export_scene.gltf(
                    use_selection=True,
                    filepath=os.path.join(final_path, f"{item_name}.glb"),
                    export_format='GLB' if exporter.embed_materials else 'GLTF_SEPARATE',
                    check_existing=True,
                    export_animations=exporter.animations,
                    export_jpeg_quality=70,
                    export_image_format='JPEG',
                    export_materials='EXPORT',
                    export_copyright=get_copyright()
                )
                break
            case 'FBX':
                bpy.ops.export_scene.fbx(
                    use_selection=True,
                    filepath=os.path.join(final_path, f"{item_name}.fbx"),
                    check_existing=True,
                    export_animations=exporter.animations,
                    global_scale=exporter.scale,
                )
                # TODO: Finish FBX export logic
                break
            case 'OBJ':
                bpy.ops.export_scene.obj(
                    use_selection=True,
                    filepath=os.path.join(final_path, f"{item_name}.obj"),
                    check_existing=True,
                    global_scale=exporter.scale,
                )
                # TODO: Finish OBJ export logic
                break

# endregion

# region Importer

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

def find_textures(folder, keywords):
    matches = []
    for f in os.listdir(folder):
        name = f.lower()
        for kw in keywords:
            if kw.lower() in name:
                matches.append(os.path.join(folder, f))
                break
    return matches

def add_tex_node(image, label, nodes, sRGB = True):
    tex_node = nodes.new(type="ShaderNodeTexImage")
    tex_node.image = image
    tex_node.label = label
    tex_node.image.colorspace_settings.name = 'sRGB' if sRGB else 'Non-Color'
    return tex_node

def clean_name(name, keywords):
    name_lower = name.lower()
    # Remove keywords
    for kw in keywords:
        name_lower = name_lower.replace(kw.lower(), "")
    # Remove double separators created by removal
    name_lower = re.sub(r'[-_]{2,}', '-', name_lower)
    # Strip trailing/leading separators
    name_lower = name_lower.strip('-_')
    return name_lower

def create_tile_mesh(texture_folder, texture_size, subfolder = "", basecolor_override = None):
    folder_name = os.path.basename(texture_folder) if subfolder == "" else subfolder
    folder_lower = folder_name.lower()
    basecolor_path = find_texture(texture_folder, basecolor_names) if not basecolor_override else basecolor_override
    name = clean_name(os.path.splitext(os.path.basename(basecolor_path))[0], basecolor_names)
    fbx_key = next((k for k in fbx_map if k.lower() in folder_lower), None)
    if fbx_key:
        name = name + "_" + fbx_key.lower()
    # Reuse existing object if already imported
    obj = bpy.data.objects.get(name)
    if not obj:
        addon_dir = os.path.dirname(os.path.realpath(__file__))
        if fbx_key:
            fbx_path = os.path.join(addon_dir, "Meshes", fbx_map[fbx_key])
            before = set(bpy.data.objects)
            bpy.ops.import_scene.fbx(filepath=fbx_path)
            new_objs = [o for o in bpy.data.objects if o not in before]
            obj = new_objs[0] if new_objs else bpy.context.active_object
        else:
            bpy.ops.mesh.primitive_plane_add(size=1, rotation=(math.radians(90), 0, 0))
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            obj = bpy.context.active_object
        if not obj:
            return None
        obj.name = name
    # Collection setup
    collection = bpy.data.collections.get(name)
    if not collection:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
        for col in obj.users_collection:
            col.objects.unlink(obj)
        collection.objects.link(obj)
    # SceneItem setup
    item = next((i for i in bpy.context.scene.scene_items if i.collection == collection), None)
    if not item:
        item = bpy.context.scene.scene_items.add()
        item.item_type = 'TILE/MATERIAL'
        item.subfolder = subfolder.strip()
        item.collection = collection
        import_textures(obj, texture_folder, texture_size, basecolor_override)
    return obj

def import_textures(obj, texture_folder, texture_size, basecolor_override):
    if not obj:
        return None
    max_size = int(texture_size)
    # Find textures
    basecolor_path = find_texture(texture_folder, basecolor_names) if not basecolor_override else basecolor_override
    roughness_path = find_texture(texture_folder, roughness_names)
    reflect_path = find_texture(texture_folder, reflect_names)
    metallic_path = find_texture(texture_folder, metallic_names)
    normal_path = find_texture(texture_folder, normal_names)
    if not basecolor_path:
        return obj
    # Material setup — reuse existing or create new
    if obj.data.materials:
        mat = obj.data.materials[0]
    else:
        mat = bpy.data.materials.new("Mat")
        mat.use_nodes = True
        obj.data.materials.append(mat)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    # Core nodes
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    # Load textures
    basecolor_tex = load_and_resize_texture(basecolor_path, max_size, True)
    roughness_tex = load_and_resize_texture(roughness_path, max_size, False) if roughness_path else None
    reflect_tex = load_and_resize_texture(reflect_path, max_size, False) if reflect_path else None
    metallic_tex = load_and_resize_texture(metallic_path, max_size, False) if metallic_path else None
    normal_tex = load_and_resize_texture(normal_path, max_size, False) if normal_path else None
    # Wire nodes
    def get_or_create_tex(label, image, sRGB=True):
        for n in nodes:
            if n.type == 'TEX_IMAGE' and n.label == label:
                return n
        return add_tex_node(image, label, nodes, sRGB=sRGB)
    if basecolor_tex:
        node = get_or_create_tex("BaseColor", basecolor_tex, True)
        links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    if roughness_tex:
        node = get_or_create_tex("Roughness", roughness_tex, False)
        links.new(node.outputs['Color'], bsdf.inputs['Roughness'])
    if reflect_tex:
        refl_node = get_or_create_tex("Reflect", reflect_tex, False)
        invert_node = next((n for n in nodes if n.type == 'INVERT'), None)
        if not invert_node:
            invert_node = nodes.new(type="ShaderNodeInvert")
        links.new(refl_node.outputs['Color'], invert_node.inputs['Color'])
        links.new(invert_node.outputs['Color'], bsdf.inputs['Roughness'])
    if metallic_tex:
        node = get_or_create_tex("Metallic", metallic_tex, False)
        links.new(node.outputs['Color'], bsdf.inputs['Metallic'])
    if normal_tex:
        norm_node = get_or_create_tex("Normal", normal_tex, False)
        norm_map = next((n for n in nodes if n.type == 'NORMAL_MAP'), None)
        if not norm_map:
            norm_map = nodes.new(type="ShaderNodeNormalMap")
        links.new(norm_node.outputs['Color'], norm_map.inputs['Color'])
        links.new(norm_map.outputs['Normal'], bsdf.inputs['Normal'])
    arrange_nodes(mat.node_tree)
    return obj

def start_tiles_import(texture_folder, texture_size):
    import_tiles(texture_folder, texture_size)
    purge_unused_data()

def import_tiles(texture_folder, texture_size, subfolder="", depth=0):
    if depth >= 4:
        return
    path = bpy.path.abspath(texture_folder)
    # Check if there's tiles in folder
    for basecolor in find_textures(path, basecolor_names):
            create_tile_mesh(path, texture_size, subfolder, basecolor)
    # Check if there's subfolders
    subfolders = [e for e in os.scandir(path) if e.is_dir()]
    if subfolders:
        for entry in subfolders:
            subfolder_name = entry.name if subfolder == "" else os.path.join(subfolder, entry.name)
            subfolder_path = entry.path
            import_tiles(subfolder_path, texture_size, subfolder_name, depth + 1)

def start_object_import():
    pass

def import_object():
    pass

# endregion
