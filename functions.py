import bpy
from bpy.types import Scene, UILayout

# region Preset

def dir_input(layout: UILayout, context, label, target_prop):
    split = layout.split(factor=0.3)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_dirpath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop

def file_input(layout: UILayout, context, label, target_prop, file_types=""):
    split = layout.split(factor=0.3)
    split.label(text=label)
    row = split.row(align=True)
    row.prop(context, target_prop, text="")
    op = row.operator("ui.select_filepath", text="", icon='FILE_FOLDER')
    op.target_prop = target_prop
    op.file_types = file_types

# endregion

# region Functions

def apply_naming(item):
    if not item.collection:
        print("No collection assigned")
        return
    objects = [obj for obj in item.collection.objects if obj.type == 'MESH']
    if not objects:
        print("No mesh objects found in collection")
        return

    code = bpy.context.scene.code.strip()
    sku = item.sku.strip()
    mesh_name = f"MESH_{code}_{sku}"
    col_name = f"COL_{code}_{sku}"
    mesh_obj = None
    col_obj = None
    # 1. Try to find by name
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
        # Assign to all slots
        for i in range(len(obj.material_slots)):
            obj.material_slots[i].material = new_mat
        # If object has no material slots, add one
        if len(obj.material_slots) == 0:
            obj.data.materials.append(new_mat)

# endregion
