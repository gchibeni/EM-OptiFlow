from .functions import *
from .classes import *

import bpy
import os
from bpy_extras.io_utils import ImportHelper
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

# region General

_last_dir = ""

class PROPERTIES_OT_dirpath(Operator):
    bl_idname = "ui.select_dirpath"
    bl_label = "Select Path"

    directory: StringProperty(options={'HIDDEN'}) #type: ignore # Stores the final path
    target_prop: StringProperty(options={'HIDDEN'})  #type: ignore # Property to set
    data_path: StringProperty(options={'HIDDEN'})  #type: ignore # Path to resolve target object
    filter_glob: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore

    def execute(self, context):
        global _last_dir
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        path = bpy.path.abspath(self.directory)
        # Show error if not a file
        if not os.path.isdir(path):
            self.report({'ERROR'}, "Selected path is not a valid directory")
            return {'CANCELLED'}
        _last_dir = path
        # Convert to relative path if possible
        blend_dir = os.path.dirname(bpy.data.filepath)
        if not blend_dir:
            setattr(target, self.target_prop, self.directory)
            return {'FINISHED'}
        try:
            rel_path = bpy.path.relpath(self.directory)
            setattr(target, self.target_prop, rel_path)
        except Exception:
            setattr(target, self.target_prop, self.directory)
        return {'FINISHED'}

    def invoke(self, context, event):
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        current_path = getattr(target, self.target_prop, "")
        # Determine starting path
        if current_path:
            abs_path = bpy.path.abspath(current_path)
        else:
            abs_path = ""
        if abs_path and os.path.exists(abs_path):
            start_path = abs_path
        elif _last_dir and os.path.exists(_last_dir):
            start_path = _last_dir
        else:
            blend_path = bpy.data.filepath
            blend_dir = os.path.dirname(blend_path) if blend_path else ""
            start_path = blend_dir if blend_dir and os.path.exists(blend_dir) else os.path.expanduser("~/Documents")
        self.directory = start_path
        #self.filter_glob = "DIR_PATH"  # Force directory selection
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class PROPERTIES_OT_filepath(Operator):
    bl_idname = "ui.select_filepath"
    bl_label = "Select File"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH") #type: ignore
    target_prop: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore
    data_path: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore # Path to resolve target object
    file_types: bpy.props.StringProperty(default="", options={'HIDDEN'}) #type: ignore
    filter_glob: bpy.props.StringProperty(options={'HIDDEN'}) #type: ignore

    def execute(self, context):
        global _last_dir
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        # Resolve full path
        path = bpy.path.abspath(self.filepath)
        # Show error if not a file
        if not os.path.isfile(path):
            self.report({'ERROR'}, "Selected path is not a valid file")
            return {'CANCELLED'}
        _last_dir = os.path.dirname(path)
        # Convert to relative path if possible
        blend_dir = os.path.dirname(bpy.data.filepath)
        if not blend_dir:
            setattr(target, self.target_prop, self.filepath)
            return {'FINISHED'}
        try:
            rel_path = bpy.path.relpath(self.filepath)
            setattr(target, self.target_prop, rel_path)
        except Exception:
            setattr(target, self.target_prop, self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        target = context.scene.path_resolve(self.data_path) if self.data_path else context.scene
        current_path = getattr(target, self.target_prop, "")
        # Determine starting path
        if current_path:
            abs_path = bpy.path.abspath(current_path)
            abs_path = os.path.dirname(abs_path) if os.path.isfile(abs_path) else abs_path
        else:
            abs_path = ""
        if abs_path and os.path.exists(abs_path):
            start_path = abs_path
        elif _last_dir and os.path.exists(_last_dir):
            start_path = _last_dir
        else:
            blend_path = bpy.data.filepath
            blend_dir = os.path.dirname(blend_path) if blend_path else ""
            start_path = blend_dir if blend_dir and os.path.exists(blend_dir) else os.path.expanduser("~/Documents")
        self.filepath = os.path.join(start_path, "")
        if self.file_types:
            types = [f"*.{ext.strip()}" for ext in self.file_types.split(",")]
            self.filter_glob = ";".join(types)
        else:
            self.filter_glob = ""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# endregion

# region SceneItems

class SCENEITEMS_OT_add(Operator):
    bl_idname = "sceneitems.add"
    bl_label = "Add"
    bl_description = "Add new item to the list"

    def execute(self, context):
        scene = context.scene
        item = scene.scene_items.add()
        item.name = f"Item {len(scene.scene_items)}"
        scene.scene_items_index = len(scene.scene_items) - 1
        return {'FINISHED'}

class SCENEITEMS_OT_remove(Operator):
    bl_idname = "sceneitems.remove"
    bl_label = "Remove"
    bl_description = "Remove selected item from the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if scene.scene_items:
            scene.scene_items.remove(index)
            scene.scene_items_index = max(0, index - 1)

        return {'FINISHED'}

class SCENEITEMS_OT_move_up(Operator):
    bl_idname = "sceneitems.move_up"
    bl_label = "Up"
    bl_description = "Move item up in the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if index > 0:
            scene.scene_items.move(index, index - 1)
            scene.scene_items_index -= 1

        return {'FINISHED'}

class SCENEITEMS_OT_move_down(Operator):
    bl_idname = "sceneitems.move_down"
    bl_label = "Down"
    bl_description = "Move item down in the list"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index

        if index < len(scene.scene_items) - 1:
            scene.scene_items.move(index, index + 1)
            scene.scene_items_index += 1

        return {'FINISHED'}

class SCENEITEMS_OT_apply(Operator):
    bl_idname = "sceneitems.apply"
    bl_label = "Apply"
    bl_description = "Apply item changes to Collection"

    def execute(self, context):
        scene = context.scene
        index = scene.scene_items_index
        # Get selected item
        if index < 0 or index >= len(scene.scene_items):
            self.report({'WARNING'}, "No item selected")
            return {'CANCELLED'}
        item = scene.scene_items[index]
        apply_item_changes(item)
        self.report({'INFO'},"Applying changes...")
        return {'FINISHED'}

class SCENEITEMS_OT_apply_all(Operator):
    bl_idname = "sceneitems.apply_all"
    bl_label = "Apply All"
    bl_description = "Apply all Items changes to all Collections"

    def execute(self, context):
        scene = context.scene
        for item in scene.scene_items:
            if item.sku != "" and item.collection is not None:
                apply_item_changes(item)
        self.report({'INFO'},"Applying changes...")
        return {'FINISHED'}

# endregion

# region Optimizations

class OPTIMIZATION_OT_create(Operator):
    bl_idname = "optimization.create"
    bl_label = "Create"
    bl_description = "Open creation window"

    def execute(self, context):
        bpy.ops.loaders.create_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Creating...")
        print("=== CREATE ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

class OPTIMIZATION_OT_export(Operator):
    bl_idname = "optimization.export"
    bl_label = "Export"
    bl_description = "Export optimized items using the configured exporters and settings"

    def execute(self, context):
        bpy.ops.loaders.export_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Exporting...")
        print("=== EXPORT ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

class OPTIMIZATION_OT_import(Operator):
    bl_idname = "optimization.import"
    bl_label = "Import"
    bl_description = "Import Furnitures, Tiles and Textures to be optimized"

    def execute(self, context):
        bpy.ops.loaders.import_popup('INVOKE_DEFAULT')
        scene = context.scene
        self.report({'INFO'},"Importing...")
        print("=== IMPORT ===")
        for item in scene.scene_items:
            print(f"Type: {item.item_type}")
            print(f"SKU: {item.sku}")
        return {'FINISHED'}

# endregion

# region Exporters

class EXPORTERS_OT_add(Operator):
    bl_idname = "exporters.add"
    bl_label = "Add"
    bl_description = "Add new exporter to the list"

    def execute(self, context):
        scene = context.scene
        exporter = scene.exporters.add()
        exporter.name = f"Exporter {len(scene.exporters)}"
        scene.exporters_index = len(scene.exporters) - 1
        return {'FINISHED'}

class EXPORTERS_OT_remove(Operator):
    bl_idname = "exporters.remove"
    bl_label = "Remove"
    bl_description = "Remove selected exporter from the list"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if scene.exporters:
            scene.exporters.remove(index)
            scene.exporters_index = max(0, index - 1)

        return {'FINISHED'}

class EXPORTERS_OT_move_up(Operator):
    bl_idname = "exporters.move_up"
    bl_label = "Up"
    bl_description = "Move exporter up in the list (higher priority)"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if index > 0:
            scene.exporters.move(index, index - 1)
            scene.exporters_index -= 1

        return {'FINISHED'}

class EXPORTERS_OT_move_down(Operator):
    bl_idname = "exporters.move_down"
    bl_label = "Down"
    bl_description = "Move exporter down in the list (lower priority)"

    def execute(self, context):
        scene = context.scene
        index = scene.exporters_index

        if index < len(scene.exporters) - 1:
            scene.exporters.move(index, index + 1)
            scene.exporters_index += 1

        return {'FINISHED'}

# endregion

# region Auto-fill

_AUTO_FILL_TEXT = "auto-fill-text"

# Google auth state
_google_auth_pending = False
_google_auth_event_ref = None
_google_auth_result_ref = None
_google_sheet_tabs = []     # [title, ...]

# URL auto-load debounce
_url_last_change = 0.0
_url_load_timer_registered = False


def _load_tabs_deferred():
    global _google_sheet_tabs, _url_load_timer_registered, _url_last_change
    if time.time() - _url_last_change < 0.7:
        return 0.8  # still typing, wait longer
    _url_load_timer_registered = False
    if not bpy.context or not bpy.context.scene:
        return None
    url = bpy.context.scene.auto_fill_spreadsheet_url.strip()
    if not url or not google_is_authenticated():
        return None
    token = google_get_valid_token()
    if not token:
        return None
    try:
        spreadsheet_id = google_parse_spreadsheet_id(url)
        _google_sheet_tabs = google_get_spreadsheet_sheets(token['access_token'], spreadsheet_id)
    except Exception as e:
        print(f"[OptiFlow] Auto-load sheet tabs failed: {e}")
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def _on_spreadsheet_url_change(self, context):
    global _google_sheet_tabs, _url_load_timer_registered, _url_last_change
    _google_sheet_tabs = []
    _url_last_change = time.time()
    if not self.auto_fill_spreadsheet_url.strip() or not google_is_authenticated():
        return
    if not _url_load_timer_registered:
        _url_load_timer_registered = True
        bpy.app.timers.register(_load_tabs_deferred, first_interval=0.8)

def _poll_google_auth():
    global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
    if not _google_auth_event_ref or not _google_auth_event_ref.is_set():
        return 1.0  # check again in 1s
    result = _google_auth_result_ref
    _google_auth_pending = False
    _google_auth_event_ref = None
    _google_auth_result_ref = None
    if result and result.get('code'):
        try:
            google_exchange_code(result['code'], result['port'])
        except Exception as e:
            print(f"[OptiFlow] Token exchange failed: {e}")
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def _sheet_tab_items(self, context):
    if not _google_sheet_tabs:
        return [('NONE', '— Load tabs first —', '')]
    return [(t, t, '') for t in _google_sheet_tabs]


class SCENEITEMS_OT_sku_input(Operator):
    """Persistent modal: typing while mouse is over Properties fills selected item SKU"""
    bl_idname = "sceneitems.sku_input"
    bl_label = "SKU Input"
    bl_options = {'INTERNAL'}

    _mouse_x: int = 0
    _mouse_y: int = 0

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._mouse_x = event.mouse_x
            self._mouse_y = event.mouse_y
            return {'PASS_THROUGH'}

        if event.value != 'PRESS':
            return {'PASS_THROUGH'}

        # Only act when mouse is over a Properties area
        over_properties = any(
            area.type == 'PROPERTIES' and
            area.x <= self._mouse_x <= area.x + area.width and
            area.y <= self._mouse_y <= area.y + area.height
            for area in context.window.screen.areas
        )

        if not over_properties:
            return {'PASS_THROUGH'}

        scene = context.scene
        if not scene.scene_items_quick_edit:
            return {'PASS_THROUGH'}

        if not scene.scene_items or scene.scene_items_index < 0:
            return {'PASS_THROUGH'}

        item = scene.scene_items[scene.scene_items_index]

        if event.type == 'TAB':
            if "?" in item.sku:
                item.sku = item.sku.replace("?", "")
            else:
                item.sku += '?'
            for area in context.window.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'BACK_SPACE':
            if item.sku:
                item.sku = item.sku[:-1]
                for area in context.window.screen.areas:
                    area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'DEL':
            if event.ctrl:
                for i in scene.scene_items:
                    i.sku = ""
            else:
                item.sku = ""
            for area in context.window.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.ascii and event.ascii.isprintable():
            item.sku += event.ascii
            for area in context.window.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class SCENEITEMS_OT_open_text_editor(Operator):
    """Open the auto-fill text block in a new floating Text Editor window"""
    bl_idname = "sceneitems.open_text_editor"
    bl_label = "Open in Text Editor"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        text = SCENEITEMS_OT_auto_fill._get_text()
        existing = set(context.window_manager.windows[:])
        bpy.ops.wm.window_new()
        new_wins = [w for w in context.window_manager.windows if w not in existing]
        if not new_wins:
            self.report({'WARNING'}, "Could not open new window.")
            return {'CANCELLED'}
        area = new_wins[0].screen.areas[0]
        area.type = 'TEXT_EDITOR'
        area.spaces[0].text = text
        return {'FINISHED'}

class SCENEITEMS_OT_google_auth(Operator):
    """Open browser to authenticate with Google"""
    bl_idname = "sceneitems.google_auth"
    bl_label = "Connect to Google"
    bl_description = "Sign in with Google to access your Sheets"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
        try:
            event, result = google_start_auth_flow()
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        _google_auth_pending = True
        _google_auth_event_ref = event
        _google_auth_result_ref = result
        bpy.app.timers.register(_poll_google_auth, first_interval=1.0)
        return {'FINISHED'}

class SCENEITEMS_OT_google_auth_cancel(Operator):
    """Cancel the pending Google authentication"""
    bl_idname = "sceneitems.google_auth_cancel"
    bl_label = "Cancel"
    bl_description = "Cancel the pending Google authentication"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
        _google_auth_pending = False
        _google_auth_event_ref = None
        _google_auth_result_ref = None
        try:
            bpy.app.timers.unregister(_poll_google_auth)
        except Exception:
            pass
        return {'FINISHED'}

class SCENEITEMS_OT_google_disconnect(Operator):
    """Clear saved Google token"""
    bl_idname = "sceneitems.google_disconnect"
    bl_label = "Disconnect"
    bl_description = "Disconnect Google account and clear saved token"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_sheet_tabs
        google_clear_token()
        _google_sheet_tabs = []
        return {'FINISHED'}

class SCENEITEMS_OT_google_load_tabs(Operator):
    """Load sheet tabs for the entered spreadsheet URL or ID"""
    bl_idname = "sceneitems.google_load_tabs"
    bl_label = "Load Sheet Tabs"
    bl_description = "Fetch the sheet tabs from the entered spreadsheet"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_sheet_tabs
        url = context.scene.auto_fill_spreadsheet_url.strip()
        if not url:
            self.report({'ERROR'}, "Enter a spreadsheet URL or ID first.")
            return {'CANCELLED'}
        spreadsheet_id = google_parse_spreadsheet_id(url)
        token = google_get_valid_token()
        if not token:
            self.report({'ERROR'}, "Not authenticated with Google.")
            return {'CANCELLED'}
        try:
            _google_sheet_tabs = google_get_spreadsheet_sheets(token['access_token'], spreadsheet_id)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load sheet tabs: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class SCENEITEMS_OT_auto_fill(Operator):
    """Auto-fill SKUs by matching collection names against a SKU list"""
    bl_idname = "sceneitems.auto_fill"
    bl_label = "Auto Fill SKUs"
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(
        name="Source",
        items=[
            ('GOOGLE_SHEETS', "Google Sheets", "Import from a Google Spreadsheet"),
            ('FILE', "File", "Load from a CSV or TSV file"),
            ('TEXT_EDITOR', "Text Editor", "Paste data in Blender's Text Editor"),
        ],
        default='GOOGLE_SHEETS',
    )  # type: ignore

    sheet_tab: EnumProperty(
        name="Sheet",
        items=_sheet_tab_items,
    )  # type: ignore

    @staticmethod
    def _get_text():
        text = bpy.data.texts.get(_AUTO_FILL_TEXT)
        if not text:
            text = bpy.data.texts.new(_AUTO_FILL_TEXT)
        return text

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        row.prop(self, "source", expand=True)
        layout.separator(type='LINE')

        if self.source == 'TEXT_EDITOR':
            layout.operator("sceneitems.open_text_editor", icon='TEXT')
            text = self._get_text()
            if text.as_string().strip():
                layout.label(text=f"{len(text.lines)} line(s) loaded.", icon='CHECKMARK')
            else:
                layout.label(text="No list loaded yet. Open the Text Editor to paste.", icon='INFO')

        elif self.source == 'FILE':
            file_input(layout, scene, "File:", "auto_fill_file_path", "csv,tsv,txt")
            path = bpy.path.abspath(scene.auto_fill_file_path) if scene.auto_fill_file_path else ""
            if path and os.path.isfile(path):
                layout.label(text=f"Ready: {os.path.basename(path)}", icon='CHECKMARK')
            else:
                layout.label(text="Select a CSV or TSV file.", icon='INFO')

        elif self.source == 'GOOGLE_SHEETS':
            if _google_auth_pending:
                row = layout.row(align=True)
                row.label(text="Waiting for browser authentication...", icon='TIME')
                row.operator("sceneitems.google_auth_cancel", text="", icon='X')
            elif not google_is_authenticated():
                layout.operator("sceneitems.google_auth", text="Connect to Google", icon='URL')
            else:
                layout.prop(scene, "auto_fill_spreadsheet_url", text="URL / ID")
                if _google_sheet_tabs:
                    layout.prop(self, "sheet_tab")
                row = layout.row()
                row.operator("sceneitems.google_load_tabs", text="Refresh", icon='FILE_REFRESH')
                row.operator("sceneitems.google_disconnect", text="", icon='X')
        layout.separator(type='LINE')


    def execute(self, context):
        scene = context.scene

        if self.source == 'TEXT_EDITOR':
            text = bpy.data.texts.get(_AUTO_FILL_TEXT)
            if not text or not text.as_string().strip():
                self.report({'ERROR'}, "The SKU list is empty.")
                return {'CANCELLED'}
            content = text.as_string()

        elif self.source == 'FILE':
            path = bpy.path.abspath(scene.auto_fill_file_path) if scene.auto_fill_file_path else ""
            if not path or not os.path.isfile(path):
                self.report({'ERROR'}, "Select a valid file.")
                return {'CANCELLED'}
            with open(path, encoding='utf-8', errors='replace') as f:
                raw = f.read()
            if os.path.splitext(path)[1].lower() == '.csv':
                import csv, io
                content = '\n'.join('\t'.join(row) for row in csv.reader(io.StringIO(raw)))
            else:
                content = raw

        elif self.source == 'GOOGLE_SHEETS':
            url = context.scene.auto_fill_spreadsheet_url.strip()
            if not url:
                self.report({'ERROR'}, "Enter a spreadsheet URL or ID.")
                return {'CANCELLED'}
            if not self.sheet_tab or self.sheet_tab == 'NONE':
                self.report({'ERROR'}, "No sheet selected. Enter a valid spreadsheet URL.")
                return {'CANCELLED'}
            token = google_get_valid_token()
            if not token:
                self.report({'ERROR'}, "Not authenticated with Google.")
                return {'CANCELLED'}
            spreadsheet_id = google_parse_spreadsheet_id(url)
            try:
                content = google_get_sheet_as_tsv(token['access_token'], spreadsheet_id, self.sheet_tab)
                context.scene.auto_fill_sheet_tab = self.sheet_tab
            except Exception as e:
                self.report({'ERROR'}, f"Failed to fetch sheet: {e}")
                return {'CANCELLED'}

        else:
            return {'CANCELLED'}

        unmatched = [i for i in scene.scene_items if i.collection and not i.sku]
        if not unmatched:
            self.report({'INFO'}, "All items already have SKUs.")
            return {'CANCELLED'}

        collection_queries = {
            i.collection.name: " ".join(filter(None, [i.collection.name, i.subfolder.strip()]))
            for i in unmatched
        }
        results = auto_fill_skus(content, collection_queries)

        if not results:
            self.report({'WARNING'}, "No matches found.")
            return {'CANCELLED'}

        count = 0
        for item in unmatched:
            if item.collection.name in results:
                sku = results[item.collection.name]
                if not sku:
                    continue
                if 'offset' in item.subfolder.lower():
                    sku += '.OFFSET'
                if 'chiseled' in item.subfolder.lower():
                    sku += '.CHISELED'
                item.sku = sku
                count += 1
        self.report({'INFO'}, f"Filled {count} / {len(unmatched)} SKUs.")
        return {'FINISHED'}

    def invoke(self, context, event):
        self._get_text()
        remembered = context.scene.auto_fill_sheet_tab
        if remembered and remembered in _google_sheet_tabs:
            self.sheet_tab = remembered
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text="Auto Fill")

# endregion
