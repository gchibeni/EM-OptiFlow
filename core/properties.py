import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty, EnumProperty, CollectionProperty,
    PointerProperty, IntProperty, FloatProperty, BoolProperty,
)
from .constants import FLAT_TYPE, ITEM_TYPE, MESH_TYPE, EXPORTER_TYPE
from . import helpers

# region Guards

renaming_guard = False
pending_trailing_slot = None
_exporter_prefix_guard = False

# endregion

# region Callbacks

def _do_add_trailing():
    """Timer callback to add a trailing empty slot after object assignment."""
    global pending_trailing_slot
    if pending_trailing_slot is None:
        return None
    gi, ii = pending_trailing_slot
    pending_trailing_slot = None
    try:
        scene = bpy.context.scene
        item  = scene.optiflow_groups[gi].items[ii]
        if item.objects and item.objects[-1].object is not None:
            item.objects.add()
    except Exception:
        pass
    return None


def _on_object_ref_update(self, context):
    """Add a trailing empty slot when the last ObjectRef gets filled."""
    global pending_trailing_slot
    if self.object is None:
        return
    scene = context.scene
    if not hasattr(scene, 'optiflow_groups'):
        return
    for gi, group in enumerate(scene.optiflow_groups):
        for ii, item in enumerate(group.items):
            helpers.clean_stale_refs(item)
            if item.objects and item.objects[-1].as_pointer() == self.as_pointer():
                pending_trailing_slot = (gi, ii)
                bpy.app.timers.register(_do_add_trailing, first_interval=0.0)
                return


def _on_item_name_update(self, context):
    """Sanitize, enforce uniqueness, and auto rename associated objects."""
    global renaming_guard
    if renaming_guard:
        return
    clean_name = helpers.sanitize_name(self.name)
    if not clean_name:
        return
    scene = context.scene
    group = helpers.find_parent_group(self, scene)
    if group:
        clean_name = helpers.unique_item_name(clean_name, group, self)
    if self.name != clean_name:
        renaming_guard = True
        self.name = clean_name
        renaming_guard = False
    objs = [ref.object for ref in self.objects if ref.object is not None]
    if not objs:
        return
    _rename_item_objects(objs, clean_name)


def _rename_item_objects(objs, clean_name):
    """Apply naming convention based on object count and existing prefixes."""
    if len(objs) == 1:
        prefix = helpers.get_prefix(objs[0]) or "MESH"
        helpers.rename_obj(objs[0], f"{prefix}_{clean_name}")

    elif len(objs) == 2:
        prefixes = [(obj, helpers.get_prefix(obj)) for obj in objs]
        col_obj  = next((obj for obj, p in prefixes if p == "COL"), None)
        if col_obj:
            mesh_obj    = next(obj for obj in objs if obj != col_obj)
            mesh_prefix = helpers.get_prefix(mesh_obj)
            if mesh_prefix == "COL":
                mesh_prefix = "MESH"
            helpers.rename_obj(col_obj, f"COL_{clean_name}")
            helpers.rename_obj(mesh_obj, f"{mesh_prefix or 'MESH'}_{clean_name}")
        else:
            sorted_objs = sorted(objs, key=helpers.get_vertex_count)
            low, high   = sorted_objs[0], sorted_objs[1]
            prefix_low  = helpers.get_prefix(low) or "COL"
            prefix_high = helpers.get_prefix(high) or "MESH"
            helpers.rename_obj(low, f"{prefix_low}_{clean_name}")
            helpers.rename_obj(high, f"{prefix_high}_{clean_name}")

    else:
        sorted_objs = sorted(objs, key=helpers.get_vertex_count)
        col_obj = next(
            (obj for obj in sorted_objs if helpers.get_prefix(obj) == "COL"),
            sorted_objs[0],
        )
        helpers.rename_obj(col_obj, f"COL_{clean_name}")
        counter = 1
        for obj in sorted_objs:
            if obj == col_obj:
                continue
            prefix = helpers.get_prefix(obj)
            if prefix == "COL":
                prefix = "MESH"
            prefix = prefix or "MESH"
            helpers.rename_obj(obj, f"{prefix}_{clean_name}_{counter}")
            counter += 1


def _on_group_name_update(self, context):
    """Sanitize group name and trigger merge dialog on duplicates."""
    global renaming_guard
    if renaming_guard:
        return
    scene = context.scene
    if not hasattr(scene, 'optiflow_groups'):
        return
    clean = helpers.sanitize_group_name(self.name)
    if self.name != clean:
        renaming_guard = True
        self.name = clean
        renaming_guard = False
    groups   = scene.optiflow_groups
    new_name = self.name
    my_gi    = next((i for i, g in enumerate(groups) if g == self), -1)
    if my_gi == -1:
        return
    # Lazily initialize prev_name on first rename
    if not self.prev_name:
        self.prev_name = new_name
        return
    dup_gi = next(
        (i for i, g in enumerate(groups) if i != my_gi and g.name == new_name), -1
    )
    if dup_gi == -1:
        self.prev_name = new_name
        return
    # Duplicate found, revert and schedule merge dialog
    scene["_optiflow_merge_gi"]     = my_gi
    scene["_optiflow_merge_dup_gi"] = dup_gi
    scene["_optiflow_merge_name"]   = new_name
    renaming_guard = True
    self.name = self.prev_name
    renaming_guard = False
    bpy.app.timers.register(_merge_dialog, first_interval=0.05)


def _merge_dialog():
    """Timer callback to invoke the merge confirmation dialog."""
    try:
        bpy.ops.optiflow.confirm_merge('INVOKE_SCREEN')
    except Exception:
        pass
    return None


def _on_exporter_prefix_update(self, context):
    """Sanitize exporter prefix on change."""
    global _exporter_prefix_guard
    if _exporter_prefix_guard:
        return
    clean = helpers.sanitize_prefix(self.prefix)
    if self.prefix != clean:
        _exporter_prefix_guard = True
        self.prefix = clean
        _exporter_prefix_guard = False

# endregion

# region PropertyGroups

class ObjectRef(PropertyGroup):
    """Reference to a scene object within an item."""
    object: PointerProperty(
        name="Object", type=bpy.types.Object,
        update=_on_object_ref_update,
    )  # type: ignore


class Item(PropertyGroup):
    """Named container for objects with type and mesh variant."""
    name:      StringProperty(name="Name", update=_on_item_name_update)  # type: ignore
    alias:     StringProperty(name="Alias")  # type: ignore
    selected:  BoolProperty(default=False)  # type: ignore
    item_type: EnumProperty(name="Type", items=ITEM_TYPE)  # type: ignore
    tile_mesh: EnumProperty(name="Mesh", items=MESH_TYPE)  # type: ignore
    objects:   CollectionProperty(type=ObjectRef)  # type: ignore


class Group(PropertyGroup):
    """Named container for items with expand/collapse state."""
    name:      StringProperty(name="Name", update=_on_group_name_update)  # type: ignore
    prev_name: StringProperty(options={'HIDDEN'})  # type: ignore
    expanded:  BoolProperty(name="Expanded", default=True)  # type: ignore
    items:     CollectionProperty(type=Item)  # type: ignore


class FlatEntry(PropertyGroup):
    """Flat display cache entry, rebuilt from optiflow_groups."""
    entry_type:  EnumProperty(items=FLAT_TYPE, default='GROUP')  # type: ignore
    name:        StringProperty(default="")  # type: ignore
    selected:    BoolProperty(default=False)  # type: ignore
    group_index: IntProperty(default=0)  # type: ignore
    item_index:  IntProperty(default=-1)  # type: ignore


class Exporter(PropertyGroup):
    """Export configuration for a single format target."""
    exporter_type: EnumProperty(
        name="Exporter", items=EXPORTER_TYPE, default='GLTF',
    )  # type: ignore
    override_path: StringProperty(name="Override Path")  # type: ignore
    prefix: StringProperty(
        name="Prefix", update=_on_exporter_prefix_update,
    )  # type: ignore
    scale: FloatProperty(
        name="Scale", default=1.0, min=0.0, max=1000.0,
    )  # type: ignore
    apply_transforms: BoolProperty(
        name="Apply Transforms", default=True,
    )  # type: ignore
    embed_materials: BoolProperty(
        name="Embed Materials", default=True,
    )  # type: ignore
    animations: BoolProperty(
        name="Animations", default=True,
    )  # type: ignore

# endregion
