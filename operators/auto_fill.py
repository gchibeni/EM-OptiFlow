import bpy
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty

# region Text Editor

class OPT_OT_open_autofill_text(Operator):
    """Open the Auto-Fill text block in a small text editor window."""
    bl_idname  = "optiflow.open_autofill_text"
    bl_label   = "Open Editor"
    bl_description = "Open the Auto-Fill text block in a text editor window"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        text_name = "Auto-Fill"
        text_block = bpy.data.texts.get(text_name)
        if text_block is None:
            text_block = bpy.data.texts.new(text_name)
        bpy.ops.wm.window_new()
        window = context.window_manager.windows[-1]
        area = window.screen.areas[0]
        area.type = 'TEXT_EDITOR'
        area.spaces[0].text = text_block
        return {'FINISHED'}

# endregion

# region Auto Fill

class optiflow_auto_fill(Operator):
    """Rename items automatically from an external data source."""
    bl_idname  = "optiflow.auto_fill"
    bl_label   = "Auto Fill"
    bl_description = "Automatically rename items based on a providede list"
    bl_options = {'UNDO'}

    source: EnumProperty(
        name="Source",
        items=[
            ('GOOGLE_SHEETS', "Google Sheets", "Fill based on a Google Spreadsheet"),
            ('FILE', "File", "Fill based on a given  CSV or TSV file"),
            ('TEXT_EDITOR', "Text Editor", "Fill based on text written or pasted by the user."),
        ],
        default='GOOGLE_SHEETS',
    )  # type: ignore

    method: EnumProperty(
        name="Method",
        items=[
            ('FUZZY', "Fuzzy", "Fill based on fuzzy matching"),
            ('AI', "AI/Semantic", "Fill based on AI-assisted matching (requires internet connection)"),
        ],
        default='FUZZY',
    )  # type: ignore

    key_name:  StringProperty(name="Key")  # type: ignore
    file_path: StringProperty(name="File Path")  # type: ignore
    sheet_url: StringProperty(name="Spreadsheet URL or ID")  # type: ignore
    sheet_tab: EnumProperty(
        name="Sheet",
        items=[
            ('SHEET_1', "Placeholder 1", "First placeholder sheet"),
            ('SHEET_2', "Placeholder 2", "Second placeholder sheet"),
        ],
    )  # type: ignore

    def draw(self, context):
        from ..ui.file_dialogs import file_input, prop_input
        layout = self.layout
        prop_input(layout, self, "Source:", "source", expand=True)
        layout.separator(type='LINE')
        prop_input(layout, self, "Key:", "key_name")
        _google_login = 'ONLINE'
        if self.source == 'TEXT_EDITOR':
            split = layout.split(factor=0.23)
            split.label(text="Text:")
            row = split.row(align=True)
            row.operator("optiflow.open_autofill_text")
            row.operator("optiflow.open_autofill_text", text="", icon='TEXT')
        elif self.source == 'FILE':
            file_input(layout, self, "File:", "file_path", "csv,tsv,txt")
        elif self.source == 'GOOGLE_SHEETS':
            if _google_login == 'PENDING':
                layout.operator(
                    "optiflow.placeholder",
                    text="Waiting for browser authentication...",
                    icon='INTERNET_OFFLINE',
                )
            elif not _google_login == 'ONLINE':
                layout.operator(
                    "optiflow.placeholder",
                    text="Connect to Google",
                    icon='URL',
                )
            else:
                row = prop_input(layout, self, "URL / ID:", "sheet_url")
                row.operator("optiflow.placeholder", text="", icon='INTERNET_OFFLINE')
                row = prop_input(layout, self, "Sheet:", "sheet_tab")
                row.operator("optiflow.placeholder", text="", icon='FILE_REFRESH')
        layout.separator(type='LINE')
        row = prop_input(layout, self, "Method:", "method", expand=True)
        row.operator("optiflow.placeholder", text="", icon='UNLINKED')
        layout.separator(type='LINE')
        row = layout.row()
        row.enabled = False

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self, width=400, confirm_text="Fill",
        )

# endregion
