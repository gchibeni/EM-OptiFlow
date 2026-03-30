import bpy
import re
from .constants import KNOWN_PREFIXES

# region Naming

def sanitize_name(name):
    """Strip and uppercase a name, keeping only safe characters."""
    sanitized = name.strip().replace(" ", "_").upper()
    return re.sub(r'[^A-Z0-9.\-_+=~]', '', sanitized)


def sanitize_group_name(name):
    """Strip and uppercase a group name, allowing path separators."""
    sanitized = name.strip().replace(" ", "_").replace("\\", "/").upper()
    sanitized = re.sub(r'[^A-Z0-9.\-_+=~/]', '', sanitized)
    return sanitized.strip("/")


def sanitize_prefix(name):
    """Clean an exporter prefix to only safe characters."""
    sanitized = re.sub(r'[^A-Za-z0-9_\-]', '', name).upper()
    sanitized = re.sub(r'_{2,}', '_', sanitized)
    sanitized = re.sub(r'-{2,}', '-', sanitized)
    return sanitized.strip('_-')


def unique_item_name(desired, group, exclude_item):
    """Generate a unique name among siblings, skipping exclude_item."""
    existing = {it.name for it in group.items
                if it.as_pointer() != exclude_item.as_pointer()}
    if desired not in existing:
        return desired
    m = re.match(r'^(.*?)_(\d+)$', desired)
    base = m.group(1) if m else desired
    n = 1
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def copy_name(base, existing):
    """Generate a copy name with incrementing suffix."""
    m = re.match(r'^(.*?)(?:[_ ]?\(\d+\)|_(\d+))$', base)
    clean = m.group(1) if m else base
    n = 1
    while f"{clean}_{n}" in existing:
        n += 1
    return f"{clean}_{n}"

# endregion

# region Objects

def get_vertex_count(obj):
    """Return the vertex count of a mesh object, or 0."""
    if obj and obj.type == 'MESH' and obj.data:
        return len(obj.data.vertices)
    return 0


def get_prefix(obj):
    """Return the known prefix from an object name, or None."""
    upper = obj.name.upper()
    for p in KNOWN_PREFIXES:
        if upper.startswith(p):
            return p
    return None


def rename_obj(obj, new_name):
    """Set both the object name and its mesh data name."""
    obj.name = new_name
    if obj.type == 'MESH' and obj.data:
        obj.data.name = new_name


def clean_stale_refs(item):
    """Remove ObjectRef entries whose object has been deleted."""
    scene_objects = set(bpy.context.scene.collection.all_objects)
    i = len(item.objects) - 1
    while i >= 0:
        obj = item.objects[i].object
        if obj is None or obj not in scene_objects:
            item.objects.remove(i)
        i -= 1

# endregion

# region Flat Entries

def rebuild_flat_entries(scene):
    """Rebuild the flat display cache from the group hierarchy."""
    entries = scene.optiflow_flat_entries
    entries.clear()
    for gi, group in enumerate(scene.optiflow_groups):
        fe             = entries.add()
        fe.entry_type  = 'GROUP'
        fe.group_index = gi
        fe.item_index  = -1
        if group.expanded:
            for ii, item in enumerate(group.items):
                fe             = entries.add()
                fe.entry_type  = item.item_type
                fe.group_index = gi
                fe.item_index  = ii
                fe.selected    = item.selected
    scene.optiflow_flat_index = min(
        scene.optiflow_flat_index, max(0, len(entries) - 1)
    )


def find_flat_idx(scene, group_index, item_index):
    """Find the flat list index for a given group/item pair."""
    for i, fe in enumerate(scene.optiflow_flat_entries):
        if fe.group_index == group_index and fe.item_index == item_index:
            return i
    return 0


def rebuild_and_select(scene, gi, ii):
    """Rebuild flat entries and select the given group/item."""
    rebuild_flat_entries(scene)
    scene.optiflow_flat_index = find_flat_idx(scene, gi, ii)

# endregion

# region Active Entry

def get_active_entry(scene):
    """Return the active FlatEntry or None if out of bounds."""
    entries = scene.optiflow_flat_entries
    idx     = scene.optiflow_flat_index
    if 0 <= idx < len(entries):
        return entries[idx]
    return None


def get_active_item(scene):
    """Return the currently selected Item or None."""
    fe = get_active_entry(scene)
    if fe is None or fe.item_index < 0:
        return None
    try:
        return scene.optiflow_groups[fe.group_index].items[fe.item_index]
    except (IndexError, KeyError):
        return None

# endregion

# region Groups

def find_parent_group(item, scene):
    """Return the Group that owns this Item, or None."""
    item_ptr = item.as_pointer()
    for group in scene.optiflow_groups:
        for it in group.items:
            if it.as_pointer() == item_ptr:
                return group
    return None


def ensure_default_group(scene):
    """Create a default group if none exist. Returns (group, gi)."""
    groups = scene.optiflow_groups
    if len(groups) == 0:
        g           = groups.add()
        g.name      = ""
        g.prev_name = ""
        g.expanded  = True
        rebuild_flat_entries(scene)
    fe = get_active_entry(scene)
    gi = fe.group_index if fe else 0
    return groups[gi], gi


def move_item_between_groups(scene, src_gi, src_ii, dst_gi, dst_ii):
    """Move an item within or between groups."""
    groups    = scene.optiflow_groups
    src_group = groups[src_gi]
    dst_group = groups[dst_gi]
    src_item  = src_group.items[src_ii]
    if src_gi == dst_gi:
        src_group.items.move(src_ii, dst_ii)
        return
    new_item      = dst_group.items.add()
    new_item.name = src_item.name
    clone_item_props(src_item, new_item)
    clone_item_refs(src_item, new_item)
    src_group.items.remove(src_ii)
    end_idx = len(dst_group.items) - 1
    if dst_ii != end_idx:
        dst_group.items.move(end_idx, dst_ii)

# endregion

# region Cloning

def clone_item_props(src, dst):
    """Copy item properties from src to dst (excluding name and objects)."""
    dst.item_type = src.item_type
    dst.tile_mesh = src.tile_mesh
    dst.alias     = src.alias
    dst.selected  = src.selected


def clone_item_refs(src, dst):
    """Copy object references from src to dst (shared, not duplicated)."""
    for ref in src.objects:
        if ref.object is not None:
            dst.objects.add().object = ref.object


def clone_item_objects(src, dst, collection):
    """Deep copy objects into scene and assign to dst item."""
    for ref in src.objects:
        if ref.object is None:
            continue
        new_obj = ref.object.copy()
        if ref.object.data is not None:
            new_obj.data = ref.object.data.copy()
        collection.objects.link(new_obj)
        dst.objects.add().object = new_obj

# endregion

# region Deletion

def collect_referenced_ptrs(groups, skip_gi=None, skip_item_ptr=None):
    """Collect object pointers referenced by items, optionally skipping a group or item."""
    referenced = set()
    for g_idx, g in enumerate(groups):
        if skip_gi is not None and g_idx == skip_gi:
            continue
        for it in g.items:
            if skip_item_ptr is not None and it.as_pointer() == skip_item_ptr:
                continue
            for ref in it.objects:
                if ref.object is not None:
                    referenced.add(ref.object.as_pointer())
    return referenced


def delete_unreferenced(to_delete, referenced):
    """Delete scene objects not present in the referenced set."""
    for ptr, obj in to_delete.items():
        if ptr not in referenced:
            bpy.data.objects.remove(obj, do_unlink=True)

# endregion

# region UI

def tag_redraw_all(context):
    """Tag all areas for redraw."""
    for area in context.window.screen.areas:
        area.tag_redraw()

# endregion

# region Data

def purge_unused_data():
    """Remove unused images, materials, meshes, and collections."""
    for img in bpy.data.images:
        if img.users == 0:
            bpy.data.images.remove(img)
    for mat in bpy.data.materials:
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for col in bpy.data.collections:
        if col.users == 0:
            bpy.data.collections.remove(col)


def arrange_nodes(node_tree):
    """Auto arrange shader nodes by type into columnar layout."""
    nodes = node_tree.nodes
    tex_x, util_x, bsdf_x, out_x = -800, -400, 0, 300
    y, y_step = 0, -300
    for node in nodes:
        if node.type == 'TEX_IMAGE':
            node.location = (tex_x, y)
            y += y_step
    for node in nodes:
        if node.type == 'NORMAL_MAP':
            node.location = (util_x, -200)
        elif node.type == 'INVERT':
            node.location = (util_x, -400)
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            node.location = (bsdf_x, 0)
        elif node.type == 'OUTPUT_MATERIAL':
            node.location = (out_x, 0)

# endregion
