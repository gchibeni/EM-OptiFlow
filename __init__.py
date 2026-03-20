# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name": "EM-OptiFlow",
    "author": "gchibeni",
    "description": "A workflow optimization add-on designed to automate repetitive tasks across our 3D pipeline—handling PBR texture acquisition, map conversion, resizing, compression, imports, naming standardization, and batch exports.",
    "blender": (5, 0, 0),
    "version": (0, 0, 1),
    "location": "Properties > Scene",
    "category": "Scene",
}

import bpy
from bpy.props import (
    StringProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
    IntProperty,
    FloatProperty,
    BoolProperty
)
from bpy.types import (
    Scene
)
from . import auto_load
from . import panels

auto_load.init()

def register():
    auto_load.register()
    Scene.show_items = BoolProperty(name="Items", default=True)
    Scene.scene_items = CollectionProperty(type=panels.SceneItem)
    Scene.scene_items_index = IntProperty(name="")
    Scene.show_exporters = BoolProperty(name="Exporters", default=False)
    Scene.exporters = CollectionProperty(type=panels.ExporterItem)
    Scene.exporters_index = IntProperty(name="")
    Scene.copyright_text = StringProperty(name="Copyright")
    Scene.export_path = StringProperty(name="Export Path")
    Scene.code = StringProperty(name="Code")
    Scene.import_model = StringProperty(name="Model")
    Scene.import_collider = StringProperty(name="Collider")
    Scene.import_texture_folder = StringProperty(name="Texture folder")
    Scene.import_type = EnumProperty(
        name="Type",
        items=[
            ('OBJECT', "Object", ""),
            ('TILES/MATERIALS', "Tiles/Materials", ""),
        ],
        default='OBJECT'
    ) #type: ignore
    Scene.import_texture_size = EnumProperty(
        name="Texture Size",
        items=[
            ('512', "512", ""),
            ('1024', "1024", ""),
            ('2048', "2048", ""),
            ('4096', "4096", ""),
            ('8192', "8192", "")
        ],
        default='4096'
    ) #type: ignore

def unregister():
    auto_load.unregister()
    del Scene.show_items
    del Scene.scene_items
    del Scene.scene_items_index
    del Scene.show_exporters
    del Scene.exporters
    del Scene.exporters_index
    del Scene.copyright_text
    del Scene.export_path
    del Scene.code
    del Scene.import_model
    del Scene.import_collider
    del Scene.import_texture_folder
    del Scene.import_type
    del Scene.import_texture_size

