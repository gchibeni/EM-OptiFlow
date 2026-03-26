import re
import json
import urllib.request
import urllib.parse
import socket
import threading
import http.server
import webbrowser
import time
import bpy
import os
import math
from bpy.types import Scene, UILayout
from datetime import date
from bpy.app.handlers import persistent

# region Variables

remove_names =  ["basecolor", "albedo", "diffuse", "base_color", "color", "offset", "uniform", "chiseled", "matte", "grip", "polished"]
basecolor_names = ["basecolor", "albedo", "diffuse", "base_color", "color"]
roughness_names = ["roughness", "rough", "rmap"]
reflect_names = ["reflect", "reflective", "reflection", "specular"]
metallic_names = ["metallic", "metal", "metalness"]
normal_names = ["normal", "nmap"]
fbx_map = {"Bullnose": "MESH_BULLNOSE.fbx", "Covebase": "MESH_COVEBASE.fbx"}

# endregion

# region General

def delete_collection_with_contents(collection):
    """Remove a collection and all objects/child collections it contains."""
    if collection is None:
        return
    for child in list(collection.children):
        delete_collection_with_contents(child)
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)

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
        import_textures(mesh_obj, item.textures_path, item.textures_size, backface_culling=item.item_type == 'TILE/MATERIAL')
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

def start_sku_input():
    if bpy.context and bpy.context.window_manager:
        try:
            bpy.ops.sceneitems.sku_input('INVOKE_DEFAULT')
        except Exception:
            pass
    return None  # don't repeat

@persistent
def load_post_start_sku_input(dummy):
    bpy.app.timers.register(start_sku_input, first_interval=0.1)

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
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
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

def get_temp_path(filepath, max_size, subfolder = ""):
    sub = subfolder.replace("/", "_").replace("\\", "_")
    base = os.path.splitext(os.path.basename(filepath))[0]
    res = f"{int(max_size/1024)}K"
    name = f"{sub}_{base}_{res}" if sub != "" else f"{base}_{res}"
    ext = "jpg"
    temp_dir = bpy.app.tempdir
    temp_path = os.path.join(temp_dir, f"{name}.{ext}")
    # Avoid overwrite → increment
    i = 1
    while os.path.exists(temp_path):
        temp_path = os.path.join(temp_dir, f"{name}_{i:03d}.{ext}")
        i += 1
    return temp_path

def load_and_resize_texture(filepath, max_size, is_color=True, subfolder = ""):
    temp_path = get_temp_path(filepath, max_size, subfolder)
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
    name = clean_name(os.path.splitext(os.path.basename(basecolor_path))[0], remove_names) + " " + subfolder
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
        import_textures(obj, texture_folder, texture_size, basecolor_override, True, subfolder)
    return obj

def import_textures(obj, texture_folder, texture_size, basecolor_override=None, backface_culling=False, subfolder = ""):
    if not obj:
        return None
    texture_folder = bpy.path.abspath(texture_folder)
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
    basecolor_tex = load_and_resize_texture(basecolor_path, max_size, True, subfolder)
    roughness_tex = load_and_resize_texture(roughness_path, max_size, False, subfolder) if roughness_path else None
    reflect_tex = load_and_resize_texture(reflect_path, max_size, False, subfolder) if reflect_path else None
    metallic_tex = load_and_resize_texture(metallic_path, max_size, False, subfolder) if metallic_path else None
    normal_tex = load_and_resize_texture(normal_path, max_size, False, subfolder) if normal_path else None
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
    mat.use_backface_culling = backface_culling
    return obj

def start_tiles_import(texture_folder, texture_size):
    import_tiles(texture_folder, texture_size)
    purge_unused_data()

def import_tiles(texture_folder, texture_size, subfolder="", depth=0):
    if depth >= 5:
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

# region Auto Fill

def _normalize_for_match(s):
    """Lowercase and collapse separators to spaces for fuzzy comparison."""
    return re.sub(r'[._\-\s]+', ' ', s.lower()).strip()

# Tokens that are too generic to be meaningful match signals (dimensions, pure numbers, etc.)
_NOISE_TOKEN_RE = re.compile(r'^\d+x\d+$|^\d+(\.\d+)?$')

# Finish/surface treatment terms used as a dedicated tiebreaker
_FINISH_TERMS = frozenset({
    'matte', 'polished', 'honed', 'glazed', 'grip', 'lappato',
    'satin', 'chiseled', 'chisseled', 'hammered', 'brushed',
    'natural', 'silk', 'offset', 'structured', 'textured',
    'glossy'
})

def _meaningful_tokens(token_set):
    """Remove noise tokens; fall back to full set only if everything is noise."""
    filtered = frozenset(t for t in token_set if not _NOISE_TOKEN_RE.match(t))
    return filtered if filtered else token_set

def _finish_tokens(token_set):
    return frozenset(t for t in token_set if t in _FINISH_TERMS)

def _parse_tsv(text_content):
    """Parse tab-separated content with a header row.
    Returns (headers, rows) where rows is a list of dicts, or None if not TSV.
    """
    lines = [l for l in text_content.splitlines() if l.strip()]
    if not lines or '\t' not in lines[0]:
        return None
    headers = [h.strip() for h in lines[0].split('\t')]
    rows = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split('\t')]
        rows.append(dict(zip(headers, cells)))
    return headers, rows

def _find_sku_column(headers, rows):
    """Return the most likely SKU column name, or None."""
    # 1. Exact or partial name match
    for h in headers:
        if 'sku' in h.lower():
            return h
    # 2. Heuristic: column whose values look like product codes (digits + separators)
    for h in headers:
        sample = [row.get(h, '').strip() for row in rows[:20] if row.get(h, '').strip()]
        if len(sample) >= 3 and sum(1 for v in sample if re.match(r'^\d[\d.\-/]+$', v)) >= len(sample) * 0.5:
            return h
    return None

_FUZZY_MIN_SCORE = 0.3   # below this: no match
_FUZZY_CONFIDENT = 0.6   # below this: append "?" to signal uncertainty

_DIM_RE = re.compile(r'^\d+x\d+')


def _is_row_inactive(row, status_col):
    """Return True if the row should be excluded (inactive/discontinued)."""
    if status_col:
        status = row.get(status_col, '').strip().upper()
        if status and status not in ('ACTIVE', ''):
            return True
    return any('discontinued' in v.lower() for v in row.values() if v)


def _auto_fill_fuzzy(lines, collection_queries, text_content=None, item_meta=None):
    """Match collection names to SKUs using structured or token-overlap scoring.

    collection_queries: {collection_name: query_string}
    item_meta: optional {collection_name: {'series': str, 'subfolder': str}}
      When provided and the source is TSV, uses structured multi-signal scoring:
        - Series tokens (vendor series / collection name)  → 30 %
        - Color tokens (derived from collection name)       → 40 %
        - Shape tokens (from collection name primarily)     → 20 %
        - Finish tokens (from subfolder)                    → 10 %

    - Confident match (score >= 0.6): returns the SKU as-is.
    - Uncertain match (0.3 <= score < 0.6): appends "?" to the SKU.
    """

    tsv = _parse_tsv(text_content) if text_content else None

    if tsv:
        headers, rows = tsv
        sku_col = _find_sku_column(headers, rows)
        if sku_col:
            status_col = next((h for h in headers if h.strip().lower() == 'status'), None)
            match_cols = [h for h in headers if h != sku_col]

            # Pre-filter and pre-tokenise active rows
            active_rows = []
            for row in rows:
                if _is_row_inactive(row, status_col):
                    continue
                sku = row.get(sku_col, '').strip()
                if not sku:
                    continue
                parts = [row.get(c, '').strip() for c in match_cols if row.get(c, '').strip()]
                row_tokens = frozenset(_normalize_for_match(' '.join(parts)).split())
                active_rows.append((sku, row_tokens))

            if not active_rows:
                return {}

            results = {}
            for col_name, query_str in collection_queries.items():
                meta = (item_meta or {}).get(col_name, {})
                series_str = meta.get('series', '').strip()
                subfolder_str = meta.get('subfolder', '').strip()

                series_tokens = frozenset(_normalize_for_match(series_str).split()) if series_str else frozenset()
                subfolder_tokens = frozenset(_normalize_for_match(subfolder_str).split()) if subfolder_str else frozenset()
                coll_tokens = frozenset(_normalize_for_match(col_name).split())

                # Shape: use collection name as primary source, subfolder as fallback
                coll_shape = frozenset(t for t in coll_tokens if _DIM_RE.match(t))
                sub_shape = frozenset(t for t in subfolder_tokens if _DIM_RE.match(t))
                shape_tokens = coll_shape if coll_shape else sub_shape

                # Finish: subfolder is the most reliable source
                finish_tokens = frozenset(t for t in subfolder_tokens if t in _FINISH_TERMS)

                # Color: what's left in the collection name after removing known non-color tokens
                color_tokens = frozenset(
                    t for t in coll_tokens
                    if t not in series_tokens
                    and not _NOISE_TOKEN_RE.match(t)
                    and t not in _FINISH_TERMS
                ) - coll_shape

                use_structured = bool(series_tokens or color_tokens)

                scored = []
                for sku, row_tokens in active_rows:
                    if use_structured:
                        s_score = len(series_tokens & row_tokens) / len(series_tokens) if series_tokens else 0.5
                        sh_score = len(shape_tokens & row_tokens) / len(shape_tokens) if shape_tokens else 0.5
                        row_finish = _finish_tokens(row_tokens)
                        if finish_tokens:
                            fin_match = len(finish_tokens & row_finish)
                            fin_extra = len(row_finish - finish_tokens)
                            fin_score = max(0.0, (fin_match - 0.5 * fin_extra) / len(finish_tokens))
                        else:
                            fin_score = 0.5
                        c_score = len(color_tokens & row_tokens) / len(color_tokens) if color_tokens else 0.0
                        total = 0.30 * s_score + 0.40 * c_score + 0.20 * sh_score + 0.10 * fin_score
                    else:
                        query = frozenset(_normalize_for_match(query_str).split())
                        query_main = _meaningful_tokens(query)
                        cand_main = _meaningful_tokens(row_tokens)
                        total = len(query_main & cand_main) / len(query_main) if query_main else 0.0
                    scored.append((sku, total))

                best_sku, best_score = max(scored, key=lambda x: x[1])
                if best_score < _FUZZY_MIN_SCORE:
                    continue
                results[col_name] = best_sku if best_score >= _FUZZY_CONFIDENT else best_sku + "?"
            return results

        # No SKU column found — flat fallback
        parsed = []
        for line in lines[1:]:
            if any('discontinued' in v.lower() for v in [line] if v):
                continue
            tokens = line.split()
            for i, tok in enumerate(tokens):
                if re.match(r'^\d[\d.\-/]+$', tok):
                    rest = " ".join(tokens[:i] + tokens[i+1:])
                    parsed.append((tok, frozenset(_normalize_for_match(rest).split())))
                    break
            else:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    parsed.append((parts[0].strip(), frozenset(_normalize_for_match(parts[1]).split())))
    else:
        parsed = []
        for line in lines:
            if any('discontinued' in v.lower() for v in [line] if v):
                continue
            tokens = line.split()
            for i, tok in enumerate(tokens):
                if re.match(r'^\d[\d.\-/]+$', tok):
                    rest = " ".join(tokens[:i] + tokens[i+1:])
                    parsed.append((tok, frozenset(_normalize_for_match(rest).split())))
                    break
            else:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    parsed.append((parts[0].strip(), frozenset(_normalize_for_match(parts[1]).split())))

    # Flat token-overlap scoring (non-TSV or no SKU column)
    if not parsed:
        return {}

    results = {}
    for col_name, query_str in collection_queries.items():
        query = frozenset(_normalize_for_match(query_str).split())
        if not query:
            continue
        query_main = _meaningful_tokens(query)
        query_dim = query - query_main
        query_finish = _finish_tokens(query_main)
        scored = []
        for sku, tokens in parsed:
            cand_main = _meaningful_tokens(tokens)
            cand_dim = tokens - cand_main
            cand_finish = _finish_tokens(cand_main)
            main_score = len(query_main & cand_main) / len(query_main) if query_main else 0.0
            dim_score = len(query_dim & cand_dim) / len(query_dim) if query_dim and cand_dim else 1.0
            finish_score = len(query_finish & cand_finish) - len(cand_finish - query_finish)
            scored.append((sku, main_score, dim_score, finish_score))
        best_main = max(m for _, m, _, _ in scored)
        if best_main < _FUZZY_MIN_SCORE:
            continue
        best_sku, best_main_s, _, _ = max(scored, key=lambda x: (x[1], x[2], x[3]))
        results[col_name] = best_sku if best_main_s >= _FUZZY_CONFIDENT else best_sku + "?"
    return results

def auto_fill_skus(text_content, collection_queries, item_meta=None):
    """Match collection names to SKUs from text_content using fuzzy matching.

    collection_queries: {collection_name: query_string}
    item_meta: optional {collection_name: {'series': str, 'subfolder': str}}
      Providing item_meta enables structured multi-signal scoring (series, color,
      shape, finish) which is significantly more accurate than flat token overlap.

    Returns dict {collection_name: sku}.
    """
    lines = [l.strip() for l in text_content.splitlines() if l.strip()]
    if not lines or not collection_queries:
        return {}
    return _auto_fill_fuzzy(lines, collection_queries, text_content, item_meta=item_meta)

# endregion

# region Google Sheets

def _google_addon_dir():
    return os.path.dirname(os.path.realpath(__file__))

def google_load_credentials():
    path = os.path.join(_google_addon_dir(), "credentials.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get("installed") or data.get("web")

def google_load_token():
    path = os.path.join(_google_addon_dir(), "token.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def google_save_token(token):
    with open(os.path.join(_google_addon_dir(), "token.json"), 'w') as f:
        json.dump(token, f)

def google_clear_token():
    path = os.path.join(_google_addon_dir(), "token.json")
    if os.path.exists(path):
        os.remove(path)

def google_is_authenticated():
    return google_load_token() is not None

def _google_refresh(token):
    creds = google_load_credentials()
    payload = urllib.parse.urlencode({
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'refresh_token': token['refresh_token'],
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request(
        creds['token_uri'],
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        new_data = json.loads(resp.read())
    token['access_token'] = new_data['access_token']
    if 'refresh_token' in new_data:
        token['refresh_token'] = new_data['refresh_token']
    token['expires_at'] = time.time() + new_data.get('expires_in', 3600)
    google_save_token(token)
    return token

def google_get_valid_token():
    """Return a valid token dict, refreshing if expired. None if not authenticated."""
    token = google_load_token()
    if not token:
        return None
    if time.time() >= token.get('expires_at', 0) - 60:
        try:
            token = _google_refresh(token)
        except Exception as e:
            print(f"[OptiFlow] Token refresh failed: {e}")
            return None
    return token

def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def google_start_auth_flow():
    """Open browser for OAuth2. Returns (auth_event, result_dict).
    auth_event is set when the callback is received.
    result_dict has 'code', 'error', and 'port' keys."""
    creds = google_load_credentials()
    if not creds:
        raise ValueError("credentials.json not found or invalid")

    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}"
    auth_event = threading.Event()
    result = {'code': None, 'error': None, 'port': port}

    _auth_html_path = os.path.join(_google_addon_dir(), "auth.html")

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in qs:
                result['code'] = qs['code'][0]
                success = True
            else:
                result['error'] = qs.get('error', ['unknown'])[0]
                success = False
            try:
                with open(_auth_html_path, 'rb') as f:
                    html = f.read()
                # Inject success flag before </head>
                flag = b'true' if success else b'false'
                html = html.replace(b'</head>', b'<script>var AUTH_SUCCESS=' + flag + b';</script></head>', 1)
                body = html
            except Exception:
                body = b'<h1>Done. You can close this tab.</h1>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            auth_event.set()

        def log_message(self, *a):
            pass

    def _serve():
        srv = http.server.HTTPServer(('localhost', port), _Handler)
        srv.handle_request()  # block until one request, then exit

    threading.Thread(target=_serve, daemon=True).start()

    params = urllib.parse.urlencode({
        'client_id': creds['client_id'],
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/spreadsheets.readonly',
        'access_type': 'offline',
        'prompt': 'consent',
    })
    webbrowser.open(f"{creds['auth_uri']}?{params}")
    return auth_event, result

def google_exchange_code(code, port):
    """Exchange auth code for tokens and save to disk."""
    creds = google_load_credentials()
    payload = urllib.parse.urlencode({
        'code': code,
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'redirect_uri': f"http://localhost:{port}",
        'grant_type': 'authorization_code',
    }).encode()
    req = urllib.request.Request(
        creds['token_uri'],
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read())
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    google_save_token(token)
    return token

def _google_api_get(access_token, url):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def google_parse_spreadsheet_id(url_or_id):
    """Extract spreadsheet ID from a URL or return the value as-is if it looks like an ID."""
    # Handle full URLs: .../spreadsheets/d/SPREADSHEET_ID/...
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)
    # Assume it's already a bare ID
    return url_or_id.strip()

def google_get_spreadsheet_sheets(access_token, spreadsheet_id):
    """Returns list of sheet tab titles."""
    data = _google_api_get(access_token, f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields=sheets.properties.title")
    return [s['properties']['title'] for s in data.get('sheets', [])]

def google_get_sheet_as_tsv(access_token, spreadsheet_id, sheet_title):
    """Returns sheet data as a TSV string."""
    range_param = urllib.parse.quote(sheet_title)
    data = _google_api_get(access_token, f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_param}")
    rows = data.get('values', [])
    return '\n'.join('\t'.join(str(c) for c in row) for row in rows)

# endregion
