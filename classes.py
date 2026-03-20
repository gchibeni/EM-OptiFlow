import bpy
import os
from .functions import *
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

# region Classes

class SceneItem(PropertyGroup):
    item_type: EnumProperty(
        name="Type",
        items=[
            ('OBJECT', "Object", ""),
            ('TILE/MATERIAL', "Tile/Material", ""),
        ],
        default='OBJECT'
    ) # type: ignore
    collection: PointerProperty(
        name="Collection",
        type=Collection
    )  # type: ignore
    sku: StringProperty(name="SKU")  # type: ignore
    subfolder: StringProperty(name="Subfolder")  # type: ignore
    textures_path: StringProperty(name="Textures")  # type: ignore
    textures_size: EnumProperty(
        name="Texture Size",
        items=[
            ('512', "512", ""),
            ('1024', "1024", ""),
            ('2048', "2048", ""),
            ('4096', "4096", ""),
            ('8192', "8192", "")
        ],
        default='4096'
    ) # type: ignore
    mesh_type: EnumProperty(
        name="Mesh Type",
        items=[
            ('TILES', "Tiles", ""),
            ('BULLNOSE', "Bullnose", ""),
            ('COVEBASE', "Covebase", ""),
        ],
        default='TILES'
    ) # type: ignore


class ExporterItem(PropertyGroup):
    exporter_type: EnumProperty(
        name="Exporter",
        items=[
            ('GLTF', "glTF", ""),
            ('FBX', "FBX", ""),
            ('OBJ', "OBJ", ""),
        ],
        default='GLTF'
    )  # type: ignore
    override_path: StringProperty(name="Override Path") # type: ignore
    prefix: StringProperty(name="Prefix")  # type: ignore
    scale: FloatProperty(
        name="Scale",
        default=1.0,
        min=0.0,
        max=1000.0
    )  # type: ignore
    apply_transforms: bpy.props.BoolProperty(
        name="Apply Transforms",
        default=True
    )  # type: ignore
    embed_materials: bpy.props.BoolProperty(
        name="Embed Materials",
        default=True
    )  # type: ignore
    animations: bpy.props.BoolProperty(
        name="Animations",
        default=True
    )  # type: ignore

# endregion
