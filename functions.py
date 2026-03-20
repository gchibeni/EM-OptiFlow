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
        if not mesh_obj:
            mesh_obj = sorted_objs[-1]  # most verts
        if not col_obj:
            least_verts_obj = sorted_objs[0]
            if mesh_obj != least_verts_obj:
                col_obj = least_verts_obj # least verts

    # 3. Swap mesh for TILE/MATERIAL based on mesh_type
    if item.item_type == 'TILE/MATERIAL' and mesh_obj:
        fbx_key = item.mesh_type.title()  # 'BULLNOSE' → 'Bullnose', 'TILES' → 'Tiles'
        addon_dir = os.path.dirname(os.path.realpath(__file__))
        if fbx_key in fbx_map:
            fbx_path = os.path.join(addon_dir, "Meshes", fbx_map[fbx_key])
            before = set(bpy.data.objects)
            bpy.ops.import_scene.fbx(filepath=fbx_path)
            new_objs = [o for o in bpy.data.objects if o not in before]
            new_obj = new_objs[0] if new_objs else None
        else:
            # TILES → plane
            bpy.ops.mesh.primitive_plane_add(size=1, rotation=(math.radians(90), 0, 0))
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            new_obj = bpy.context.active_object
        if new_obj and new_obj != mesh_obj:
            # Transfer materials
            new_obj.data.materials.clear()
            for mat in mesh_obj.data.materials:
                new_obj.data.materials.append(mat)
            # Move to item collection
            for col in list(new_obj.users_collection):
                col.objects.unlink(new_obj)
            item.collection.objects.link(new_obj)
            # Remove old object and its mesh data
            old_data = mesh_obj.data
            bpy.data.objects.remove(mesh_obj)
            if old_data.users == 0:
                bpy.data.meshes.remove(old_data)
            mesh_obj = new_obj

    # 4. Rename safely
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
                mat.blend_method = 'BLEND'
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
                new_mat.blend_method = 'BLEND'
        # Assign to all slots
        for i in range(len(obj.material_slots)):
            obj.material_slots[i].material = new_mat
        # If object has no material slots, add one
        if len(obj.material_slots) == 0:
            obj.data.materials.append(new_mat)

def get_layer_collection(layer_coll, collection):
    if layer_coll.collection == collection:
        return layer_coll
    for child in layer_coll.children:
        result = get_layer_collection(child, collection)
        if result:
            return result
    return None

def isolate_items_collection(self, context):
    scene = context.scene
    if not scene.scene_items_isolate:
        for item in scene.scene_items:
            if item.collection:
                lc = get_layer_collection(context.view_layer.layer_collection, item.collection)
                if lc:
                    lc.hide_viewport = False
        return
    if not scene.scene_items or scene.scene_items_index < 0:
        return
    selected = scene.scene_items[scene.scene_items_index]
    for item in scene.scene_items:
        if item.collection:
            lc = get_layer_collection(context.view_layer.layer_collection, item.collection)
            if lc:
                lc.hide_viewport = (item.collection != selected.collection)

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
    os.makedirs(final_path, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    objs = [obj for obj in collection.all_objects if obj.type == 'MESH']
    if not objs:
        return
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
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
        case 'FBX':
            bpy.ops.export_scene.fbx(
                use_selection=True,
                filepath=os.path.join(final_path, f"{item_name}.fbx"),
                check_existing=True,
                global_scale=exporter.scale,
                bake_space_transform=exporter.apply_transforms,
                embed_textures=exporter.embed_materials,
                path_mode='COPY' if exporter.embed_materials else 'AUTO',
                bake_anim=exporter.animations,
            )
        case 'OBJ':
            bpy.ops.wm.obj_export(
                export_selected_objects=True,
                filepath=os.path.join(final_path, f"{item_name}.obj"),
                check_existing=True,
                global_scale=exporter.scale,
                apply_modifiers=exporter.apply_transforms,
                export_materials=exporter.embed_materials,
            )

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
        item.mesh_type = fbx_key.upper() if fbx_key else 'TILES'
        item.collection = collection
        import_textures(obj, texture_folder, texture_size, basecolor_override)
    return obj

def import_textures(obj, texture_folder, texture_size, basecolor_override = None):
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

def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    before = set(bpy.data.objects)
    if ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=filepath)
    else:
        return []
    return [o for o in bpy.data.objects if o not in before]

def join_objects(objs, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    if obj.data:
        obj.data.name = name
    return obj

def start_object_import(model_path, collider_path, texture_folder, texture_size):
    import_object(model_path, collider_path, texture_folder, texture_size)
    purge_unused_data()

def import_object(model_path, collider_path, texture_folder, texture_size):
    model_path = bpy.path.abspath(model_path)
    if not os.path.isfile(model_path):
        return
    model_name = os.path.splitext(os.path.basename(model_path))[0]
    # Import and merge model
    model_objs = import_file(model_path)
    if not model_objs:
        return
    mesh_obj = join_objects(model_objs, model_name)
    # Import and merge collider (optional)
    col_obj = None
    if collider_path:
        collider_path = bpy.path.abspath(collider_path)
        if os.path.isfile(collider_path):
            col_name = os.path.splitext(os.path.basename(collider_path))[0]
            col_objs = import_file(collider_path)
            if col_objs:
                col_obj = join_objects(col_objs, col_name)
    # Collection setup
    collection = bpy.data.collections.get(model_name)
    if not collection:
        collection = bpy.data.collections.new(model_name)
        bpy.context.scene.collection.children.link(collection)
    for obj in [mesh_obj, col_obj]:
        if obj:
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            collection.objects.link(obj)
    # SceneItem setup
    item = next((i for i in bpy.context.scene.scene_items if i.collection == collection), None)
    if not item:
        item = bpy.context.scene.scene_items.add()
        item.item_type = 'OBJECT'
        item.collection = collection
    # Materials
    rename_material(mesh_obj, "Mat")
    if col_obj:
        rename_material(col_obj, "ColMat")
    # Textures
    if texture_folder:
        texture_path = bpy.path.abspath(texture_folder)
        if os.path.isdir(texture_path):
            import_textures(mesh_obj, texture_path, texture_size)
    return mesh_obj

# endregion
