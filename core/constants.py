# region Prefixes

KNOWN_PREFIXES = ("MESH", "COL", "PLACER", "SNAP")

# endregion

# region Enums

FLAT_TYPE = [
    ('GROUP',         "Group",         "GROUP"),
    ('OBJECT',        "Object",        "META_CUBE"),
    ('TILE/MATERIAL', "Tile/Material", "MESH_GRID"),
]

ITEM_TYPE = [
    ('OBJECT',        "Object",        ""),
    ('TILE/MATERIAL', "Tile/Material", ""),
]

MESH_TYPE = [
    ('TILE', "Tile", ""),
    ('BULLNOSE', "Bullnose", ""),
    ('COVEBASE', "Covebase", ""),
]

EXPORTER_TYPE = [
    ('GLTF', "glTF", ""),
    ('FBX', "FBX", ""),
    ('OBJ', "OBJ", ""),
]

TEXTURE_SIZES = [
    ('512', "512", ""),
    ('1024', "1024", ""),
    ('2048', "2048", ""),
    ('4096', "4096", ""),
    ('8192', "8192", ""),
]

# endregion

# region Icons

EXPORTER_ICONS = {
    'GLTF': 'META_CUBE',
    'FBX':  'MESH_UVSPHERE',
    'OBJ':  'META_CAPSULE',
}

# endregion
