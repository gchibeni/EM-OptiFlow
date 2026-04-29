# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gabriel R. Chibeni

bl_info = {
    "name": "OptiFlow",
    "author": "gchibeni",
    "description": "A workflow optimization add-on designed to automate/help on repetitive tasks across the 3D pipeline for optimizations—handling PBR texture acquisition, conversion, compression, standardization, batch imports/exports.",
    "blender": (5, 0, 0),
    "version": (1, 0, 2),
    "location": "",
    "warning": "",
    "category": "Optimization",
    "website": "https://github.com/gchibeni/OptiFlow"
}

from . import auto_load

addon_name = __name__

auto_load.init()


def register():
    auto_load.register()


def unregister():
    auto_load.unregister()
