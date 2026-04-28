import bpy
import os
import shutil
from bpy.types import AddonPreferences, Operator, UIList, PropertyGroup
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty
from .. import addon_name


def _get_meshes_dir():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "meshes")


def _scan_presets():
    """Return list of (key, display_name, filename) sorted with TILE first."""
    meshes_dir = _get_meshes_dir()
    entries = []
    if not os.path.isdir(meshes_dir):
        return entries
    for fname in sorted(os.listdir(meshes_dir)):
        if fname.startswith("MESH_") and fname.upper().endswith(".FBX"):
            key   = fname[5:fname.upper().rfind(".FBX")]
            label = key.replace("_", " ").title()
            entries.append((key, label, fname))
    entries.sort(key=lambda e: (e[0] != 'TILE', e[0]))
    return entries


def _unique_dest(meshes_dir, stem):
    """Return a unique MESH_*.fbx path, appending _N for duplicates."""
    path = os.path.join(meshes_dir, f"{stem}.fbx")
    if not os.path.exists(path):
        return path
    n = 2
    while True:
        candidate = os.path.join(meshes_dir, f"{stem}_{n}.fbx")
        if not os.path.exists(candidate):
            return candidate
        n += 1


# region PropertyGroup

_rename_guard = False


def _on_preset_name_update(self, context):
    global _rename_guard
    if _rename_guard or self.is_default:
        return
    meshes_dir = _get_meshes_dir()
    old_path   = os.path.join(meshes_dir, self.filename)
    new_stem   = self.name.strip().upper().replace(" ", "_")
    if not new_stem:
        _revert_name(self)
        return
    if not new_stem.startswith("MESH_"):
        new_stem = f"MESH_{new_stem}"
    new_fname = f"{new_stem}.fbx"
    new_path  = os.path.join(meshes_dir, new_fname)
    if os.path.normcase(new_path) == os.path.normcase(old_path):
        return
    if os.path.exists(new_path):
        _revert_name(self)
        return
    os.rename(old_path, new_path)
    _rename_guard = True
    self.filename = new_fname
    _rename_guard = False
    from ..core.constants import refresh_mesh_type
    refresh_mesh_type()


def _revert_name(entry):
    global _rename_guard
    key = entry.filename[5:entry.filename.upper().rfind(".FBX")]
    _rename_guard = True
    entry.name = key.replace("_", " ").title()
    _rename_guard = False


class PresetEntry(PropertyGroup):
    name:       StringProperty(name="Name", update=_on_preset_name_update)  # type: ignore
    filename:   StringProperty(options={'HIDDEN'})  # type: ignore
    is_default: BoolProperty(default=False, options={'HIDDEN'})  # type: ignore

# endregion

# region UIList

class PREF_UL_presets(UIList):
    bl_idname = "PREF_UL_presets"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if item.is_default:
            row.label(text=item.name)
            row.label(text="", icon='BLANK1')
        else:
            row.prop(item, "name", text="", emboss=False)
            op          = row.operator("optiflow.pref_delete_preset", text="", icon='TRASH')
            op.filename = item.filename

# endregion

# region Operators

class PREF_OT_delete_preset(Operator):
    """Delete a mesh preset file from the meshes folder."""
    bl_idname  = "optiflow.pref_delete_preset"
    bl_label   = "Delete Preset"
    bl_description = "Permanently delete this mesh preset"
    bl_options = {'INTERNAL'}

    filename: StringProperty(options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        from ..core.constants import refresh_mesh_type
        path = os.path.join(_get_meshes_dir(), self.filename)
        if os.path.isfile(path):
            os.remove(path)
            refresh_mesh_type()
        return {'FINISHED'}


class PREF_OT_import_preset(Operator):
    """Browse for an FBX file and copy it into the meshes folder as a preset."""
    bl_idname  = "optiflow.pref_import_preset"
    bl_label   = "Import Preset"
    bl_description = "Import an FBX file as a new mesh preset"
    bl_options = {'INTERNAL'}

    filepath:    StringProperty(subtype='FILE_PATH')  # type: ignore
    filter_glob: StringProperty(default="*.fbx;*.FBX", options={'HIDDEN'})  # type: ignore

    def execute(self, context):
        from ..core.constants import refresh_mesh_type
        src = bpy.path.abspath(self.filepath)
        if not os.path.isfile(src):
            self.report({'ERROR'}, "Invalid file selected")
            return {'CANCELLED'}
        meshes_dir = _get_meshes_dir()
        if os.path.normcase(os.path.abspath(src)).startswith(
            os.path.normcase(os.path.abspath(meshes_dir)) + os.sep
        ):
            self.report({'WARNING'}, "That file is already installed as a preset")
            return {'CANCELLED'}
        stem = os.path.splitext(os.path.basename(src))[0].upper()
        if not stem.startswith("MESH_"):
            stem = f"MESH_{stem}"
        dest = _unique_dest(meshes_dir, stem)
        try:
            shutil.copy2(src, dest)
        except PermissionError as e:
            self.report({'ERROR'}, f"Cannot copy file: {e}")
            return {'CANCELLED'}
        refresh_mesh_type()
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# endregion

# region Preferences

def _sync_preset_entries(prefs):
    """Sync the preset_entries collection from the meshes folder if stale."""
    global _rename_guard
    presets = _scan_presets()
    entries = prefs.preset_entries
    if len(entries) == len(presets) and all(
        entries[i].filename == fname for i, (_, _, fname) in enumerate(presets)
    ):
        return
    entries.clear()
    _rename_guard = True
    for key, label, fname in presets:
        e            = entries.add()
        e.is_default = (key == 'TILE')
        e.filename   = fname
        e.name       = label
    _rename_guard = False
    if prefs.preset_index >= len(entries):
        prefs.preset_index = max(0, len(entries) - 1)


class OPTIFLOW_AddonPreferences(AddonPreferences):
    bl_idname = addon_name

    presets_expanded: BoolProperty(name="Presets", default=False) # type: ignore
    preset_entries:   CollectionProperty(type=PresetEntry) # type: ignore
    preset_index:     IntProperty(default=0, name="Preset") # type: ignore

    def draw(self, context):
        layout = self.layout
        header = layout.row()
        header.prop(
            self, "presets_expanded",
            icon='TRIA_DOWN' if self.presets_expanded else 'TRIA_RIGHT',
            icon_only=True, emboss=False,
        )
        header.label(text="Presets")
        if not self.presets_expanded:
            return
        _sync_preset_entries(self)
        layout.template_list(
            "PREF_UL_presets", "",
            self, "preset_entries",
            self, "preset_index",
            rows=max(3, len(self.preset_entries)),
        )
        layout.operator("optiflow.pref_import_preset", text="Import Preset", icon='IMPORT')

# endregion
