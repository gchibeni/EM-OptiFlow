import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty, EnumProperty, CollectionProperty,
    PointerProperty, IntProperty, FloatProperty, BoolProperty,
)

from .constants import FLAT_TYPE, ITEM_TYPE, MESH_TYPE, EXPORTER_TYPE, GLTF_IMAGE_TYPE, SUBFOLDER_TYPE
from . import helpers

# region Guards

renaming_guard = False
pending_trailing_slot = None

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
    desired_name = helpers.sanitize_name(self.name)
    if not desired_name:
        if self.prev_name:
            renaming_guard = True
            self.name = self.prev_name
            renaming_guard = False
        return
    scene = context.scene
    group = helpers.find_parent_group(self, scene)
    clean_name = helpers.unique_item_name(desired_name, group, self) if group else desired_name
    if self.name != clean_name:
        renaming_guard = True
        self.name = clean_name
        renaming_guard = False
    self.prev_name = clean_name
    objs = [ref.object for ref in self.objects if ref.object is not None]
    if not objs:
        return
    prefix = getattr(scene, 'optiflow_item_prefix', '')
    suffix = getattr(scene, 'optiflow_item_suffix', '')
    _rename_item_objects(objs, clean_name, desired_name, prefix, suffix)


_INVISIBLE_PREFIXES = {"COL", "PLACER", "SNAP", "GUIDE"}

def _rename_item_objects(objs, clean_name, desired_name, prefix="", suffix=""):
    """Rename objects as PREFIX_name, or PREFIX_name_N when the same prefix appears more than once.
    clean_name is the actual item name (may include a uniqueness suffix like _2).
    desired_name is what the user intended before uniquification — used as the multi-object base
    so that a uniqueness suffix is never confused with part of the real name.
    An optional name prefix/suffix is applied; already-present affixes are not doubled.
    Objects whose prefix is in _INVISIBLE_PREFIXES also get the ColMat invisible material applied.
    """
    from collections import defaultdict

    def _build_effective(name):
        parts = []
        if prefix and not name.startswith(f"{prefix}_"):
            parts.append(prefix)
        parts.append(name)
        if suffix and not name.endswith(f"_{suffix}"):
            parts.append(suffix)
        return "_".join(parts)

    # Single-object: use the full item name (includes any uniqueness suffix)
    effective_name = _build_effective(clean_name)
    # Multi-object base: use the user's intended name so we never mistake a uniqueness
    # suffix (_2 on "TABLE_2") for part of the real name, and explicit names like "123_1"
    # are preserved as-is.
    multi_base = _build_effective(desired_name)

    obj_prefix_groups = defaultdict(list)
    for obj in objs:
        p = helpers.get_prefix(obj) or "MESH"
        obj_prefix_groups[p].append(obj)

    for p, group in obj_prefix_groups.items():
        apply_invisible = p in _INVISIBLE_PREFIXES
        if len(group) == 1:
            helpers.rename_obj(group[0], f"{p}_{effective_name}")
            if apply_invisible:
                helpers.set_invisible_mat(group[0], "ColMat")
        else:
            for i, obj in enumerate(group, start=1):
                helpers.rename_obj(obj, f"{p}_{multi_base}_{i}")
                if apply_invisible:
                    helpers.set_invisible_mat(obj, "ColMat")


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
    prev_name: StringProperty(options={'HIDDEN'})  # type: ignore
    alias:     StringProperty(name="Alias")  # type: ignore
    batch:     StringProperty(name="Batch")  # type: ignore
    selected:  BoolProperty(default=False)  # type: ignore
    item_type: EnumProperty(name="Type", items=ITEM_TYPE)  # type: ignore
    preset: EnumProperty(name="Mesh", items=lambda self, ctx: MESH_TYPE)  # type: ignore
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
    export_subfolder: EnumProperty(
        name="Subfolder", items=SUBFOLDER_TYPE, default='GROUP',
    )  # type: ignore
    override_path: StringProperty(name="Override Path")  # type: ignore
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
    tangents: BoolProperty(
        name="Tangents", default=True,
    )  # type: ignore
    images_type: EnumProperty(
        name="Images Type", items=GLTF_IMAGE_TYPE, default='AUTO',
    )  # type: ignore
    quality: IntProperty(
        name="Quality", default=100, min=50, max=100, subtype='PERCENTAGE',
    )  # type: ignore
    anim_frame_start: IntProperty(
        name="Start", default=1,
    )  # type: ignore
    anim_frame_end: IntProperty(
        name="End", default=250,
    )  # type: ignore

# endregion
