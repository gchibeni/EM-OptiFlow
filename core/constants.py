import os

# region Prefixes

KNOWN_PREFIXES = ("MESH", "COL", "PLACER", "SNAP", "GUIDE")

# endregion

# region Enums

FLAT_TYPE = [
    ('GROUP',         "Group",         "GROUP"),
    ('OBJECT',        "Object",        "META_CUBE"),
    ('PRESET', "Preset", "MESH_GRID"),
]

ITEM_TYPE = [
    ('OBJECT', "Object", ""),
    ('PRESET', "Preset", ""),
]

def _build_mesh_type():
    meshes_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "meshes")
    if not os.path.isdir(meshes_dir):
        return [('TILE', "Tile", "")]
    entries = []
    for fname in sorted(os.listdir(meshes_dir)):
        if fname.startswith("MESH_") and fname.upper().endswith(".FBX"):
            key   = fname[5:fname.upper().rfind(".FBX")]
            label = key.replace("_", " ").title()
            entries.append((key, label, ""))
    entries.sort(key=lambda e: (e[0] != 'TILE', e[0]))
    return entries

MESH_TYPE = _build_mesh_type()

def refresh_mesh_type():
    MESH_TYPE[:] = _build_mesh_type()

EXPORTER_TYPE = [
    ('GLTF', "glTF", ""),
    ('FBX', "FBX", ""),
    ('OBJ', "OBJ", ""),
]

SUBFOLDER_TYPE = [
    ('GROUP', "Group", ""),
    ('NONE',  "None",  ""),
]

GLTF_IMAGE_TYPE = [
    ('AUTO', "Automatic", ""),
    ('JPEG', "Jpeg",      ""),
    ('WEBP', "Webp",      ""),
]

TEXTURE_SIZES = [
    ('32', '32', ''), ('64', '64', ''), ('128', '128', ''),
    ('256', '256', ''), ('512', '512', ''), ('1024', '1024', ''),
    ('2048', '2048', ''), ('4096', '4096', ''), ('8192', '8192', ''),
]

# endregion

# region Icons

EXPORTER_ICONS = {
    'GLTF': 'META_CUBE',
    'FBX':  'MESH_UVSPHERE',
    'OBJ':  'META_CAPSULE',
}

# endregion
