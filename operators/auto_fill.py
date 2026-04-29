import bpy
import os
import re
import csv
import io
import json
import time
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import http.server
import webbrowser
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, IntProperty
from ..ui.file_dialogs import file_input, prop_input

_AUTO_FILL_TEXT = "Auto-Fill"

# ── Google auth state ──────────────────────────────────────────────────────────

_google_auth_pending     = False
_google_auth_event_ref   = None
_google_auth_result_ref  = None
_google_sheet_tabs: list = []


_url_last_change           = 0.0
_url_load_timer_registered = False

# region Fuzzy Matching

def _normalize_for_match(s):
    """Lowercase and collapse separators (including / ) to single spaces."""
    return re.sub(r'[._\-\s/]+', ' ', s.lower()).strip()


_NOISE_TOKEN_RE = re.compile(r'^\d+x\d+$|^\d+(\.\d+)?$')
_DIM_RE         = re.compile(r'^\d+x\d+')

# Layout/pattern words that appear in group names but carry no semantic signal.
# Finish and type terms are NOT listed here — they are learned dynamically from
# whatever is left in the group name after size, shape, and these noise words are removed.
_GROUP_NOISE_TOKENS = frozenset({'offset', 'uniform'})

# Detects the shape/format column in the sheet by header name.
# Values from this column are used to classify group tokens as shape signals
# (e.g. COVEBASE, BULLNOSE) distinct from finish tokens.
_SHAPE_COL_RE = re.compile(r'\bshape\b|\bformat\b|\bprofile\b', re.I)

_INVALID_KEY_VALUES = frozenset({'n/a', 'none', '-', 'na'})

_FUZZY_MIN_SCORE = 0.25

# Relative importance of each signal; normalised per-item by active weight sum.
_SIGNAL_WEIGHTS = {
    'group_finish': 0.25,  # finish/type from group name (dynamic — no hardcoded terms)
    'group_size':   0.25,  # NxM dimension tokens from group name
    'group_shape':  0.20,  # shape/format tokens matched against the sheet (e.g. COVEBASE)
    'item_color':   0.20,  # item name is the color
    'alias':        0.10,  # alias is the collection
}


def _parse_tsv(text_content, header_row=1):
    """Parse tab-separated content. Returns (headers, rows) or None.

    header_row: 1-based index of the line to treat as column headers.
    Lines before the header row are ignored.
    """
    lines = [l for l in text_content.splitlines() if l.strip()]
    hi = header_row - 1  # convert to 0-based
    if hi >= len(lines) or '\t' not in lines[hi]:
        return None
    headers = [h.strip() for h in lines[hi].split('\t')]
    rows    = []
    for line in lines[hi + 1:]:
        cells = [c.strip() for c in line.split('\t')]
        rows.append(dict(zip(headers, cells)))
    return headers, rows


def _is_row_inactive(row, status_col):
    """Return True if the row should be excluded."""
    if status_col:
        status = row.get(status_col, '').strip().upper()
        return bool(status and status not in ('ACTIVE', ''))
    return any('discontinued' in v.lower() for v in row.values() if v)


def _find_key_column(headers, key_name):
    """Find column header by exact then case-insensitive match."""
    if key_name in headers:
        return key_name
    kl = key_name.lower()
    for h in headers:
        if h.lower() == kl:
            return h
    return None


def _extract_signals(group_name, item_name, alias, shape_vocab=frozenset()):
    """Decompose item fields into typed token signals for weighted scoring.

    group_name  → group_size   (NxM dimension tokens)
                  group_shape  (tokens matched against sheet shape vocab, e.g. COVEBASE)
                  group_finish (everything else minus size, shape, and noise words)
    item_name   → item_color   (the item name is the color)
    alias       → alias        (the alias is the collection)

    shape_vocab: collapsed shape values learned from the sheet (passed in from
                 auto_fill_names_multi so no hardcoding is needed here).
    """
    def _toks(s):
        return frozenset(_normalize_for_match(s).split()) if s else frozenset()

    group_toks = _toks(group_name)
    item_toks  = _toks(item_name)
    alias_toks = _toks(alias)

    group_size   = frozenset(t for t in group_toks if _DIM_RE.match(t))
    group_shape  = frozenset(t for t in group_toks if t in shape_vocab) - group_size
    group_finish = group_toks - group_size - group_shape - _GROUP_NOISE_TOKENS

    item_color   = frozenset(t for t in item_toks if not _NOISE_TOKEN_RE.match(t))

    return {
        'group_finish': group_finish,
        'group_size':   group_size,
        'group_shape':  group_shape,
        'item_color':   item_color,
        'alias':        alias_toks,
    }


def _score_row(row_tokens, signals):
    """Weighted signal-match score, normalised by sum of active signal weights."""
    score = weights = 0.0
    for key, weight in _SIGNAL_WEIGHTS.items():
        s = signals.get(key)
        if not s:
            continue
        score   += weight * (len(s & row_tokens) / len(s))
        weights += weight
    return score / weights if weights else 0.0


def _format_result(key_val, prefix, suffix):
    """Join non-empty parts with underscores → PREFIX_KEYVALUE_SUFFIX."""
    return '_'.join(p for p in (prefix, key_val, suffix) if p)


def auto_fill_names_multi(content, items_data, key_col, header_row=1):
    """Match items to sheet rows via per-field multi-signal scoring.

    items_data : list of {'group_name': str, 'item_name': str, 'alias': str}
    key_col    : column name whose value to return as the match result
    header_row : 1-based row number that contains column headers

    Returns (results, error_msg):
      results   — list[str] parallel to items_data;
                  non-empty str = matched key value, '' = no match above threshold
      error_msg — non-empty string on fatal error (key column not found, etc.)
    """
    tsv = _parse_tsv(content, header_row)
    if not tsv:
        return [''] * len(items_data), "Source data is not tab-separated."

    headers, rows  = tsv
    actual_key_col = _find_key_column(headers, key_col)
    if not actual_key_col:
        avail = ', '.join(headers[:10]) + ('…' if len(headers) > 10 else '')
        return [''] * len(items_data), f"Column '{key_col}' not found. Available: {avail}"

    status_col = next((h for h in headers if h.strip().lower() == 'status'), None)
    match_hdrs = [h for h in headers if h != actual_key_col]

    # Detect shape/format column and build a collapsed vocab.
    # Sheet values like "Cove Base" are stored collapsed ("covebase") so they match
    # single-token group names like COVEBASE regardless of word-boundary differences.
    shape_col   = next((h for h in match_hdrs if _SHAPE_COL_RE.search(h)), None)
    shape_vocab = frozenset(
        re.sub(r'\s+', '', _normalize_for_match(row.get(shape_col, '')))
        for row in rows
        if shape_col and row.get(shape_col, '').strip()
    )

    active_rows = []
    for row in rows:
        if _is_row_inactive(row, status_col):
            continue
        key_val = row.get(actual_key_col, '').strip()
        if not key_val or key_val.lower() in _INVALID_KEY_VALUES:
            continue
        parts      = [row.get(h, '').strip() for h in match_hdrs if row.get(h, '').strip()]
        row_tokens = frozenset(_normalize_for_match(' '.join(parts)).split())
        if shape_col:
            raw_shape = row.get(shape_col, '').strip()
            if raw_shape:
                # Add collapsed form so "Cove Base" is reachable as "covebase"
                row_tokens = row_tokens | {re.sub(r'\s+', '', _normalize_for_match(raw_shape))}
        active_rows.append((key_val, row_tokens))

    if not active_rows:
        return [''] * len(items_data), "No usable rows found in sheet after filtering."

    # Corpus: every token that appears in at least one active row.
    # Used to strip item_color tokens that have no counterpart in the sheet
    # (noise words from item names that would never match any row).
    corpus_toks = frozenset(t for _, rt in active_rows for t in rt)

    results = []
    for item_data in items_data:
        signals = _extract_signals(
            item_data.get('group_name', ''),
            item_data.get('item_name', ''),
            item_data.get('alias', ''),
            shape_vocab,
        )
        if not any(signals.values()):
            results.append('')
            continue

        # Keep only item_color tokens that actually appear somewhere in the sheet.
        ic = signals.get('item_color', frozenset())
        discriminating_ic = ic & corpus_toks
        signals['item_color'] = discriminating_ic

        # Pre-filter candidates to rows that contain at least one color token.
        # This guarantees color discrimination takes priority over finish/size ties:
        # ROMAN can never be returned for a TITANIUM item even if both score the
        # same on finish/size, because ROMAN simply isn't in the candidate pool.
        if discriminating_ic:
            candidates = [(kv, rt) for kv, rt in active_rows if discriminating_ic & rt]
            if not candidates:
                results.append('')
                continue
        else:
            candidates = active_rows

        best_key, best_score, _ = max(
            ((kv, _score_row(rt, signals), rt) for kv, rt in candidates),
            key=lambda x: x[1],
        )
        if best_score < _FUZZY_MIN_SCORE:
            results.append('')
            continue
        results.append(best_key)

    return results, ''

# endregion

# region Google Sheets

def _google_addon_dir():
    """Return the addon root directory (one level above operators/)."""
    return os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))


def google_load_credentials():
    path = os.path.join(_google_addon_dir(), 'credentials.json')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get('installed') or data.get('web')


def google_load_token():
    path = os.path.join(_google_addon_dir(), 'token.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def google_save_token(token):
    with open(os.path.join(_google_addon_dir(), 'token.json'), 'w') as f:
        json.dump(token, f)


def google_clear_token():
    path = os.path.join(_google_addon_dir(), 'token.json')
    if os.path.exists(path):
        os.remove(path)


def google_is_authenticated():
    return google_load_token() is not None


def _google_refresh(token):
    creds   = google_load_credentials()
    payload = urllib.parse.urlencode({
        'client_id':     creds['client_id'],
        'client_secret': creds['client_secret'],
        'refresh_token': token['refresh_token'],
        'grant_type':    'refresh_token',
    }).encode()
    req = urllib.request.Request(
        creds['token_uri'], data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        new_data = json.loads(resp.read())
    token['access_token'] = new_data['access_token']
    if 'refresh_token' in new_data:
        token['refresh_token'] = new_data['refresh_token']
    token['expires_at'] = time.time() + new_data.get('expires_in', 3600)
    google_save_token(token)
    return token


def google_get_valid_token():
    """Return a valid token dict, refreshing if expired. None if not authenticated."""
    token = google_load_token()
    if not token:
        return None
    if time.time() >= token.get('expires_at', 0) - 60:
        try:
            token = _google_refresh(token)
        except Exception as e:
            print(f"[OptiFlow] Token refresh failed: {e}")
            return None
    return token


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def google_start_auth_flow():
    """Open browser for OAuth2. Returns (auth_event, result_dict)."""
    creds = google_load_credentials()
    if not creds:
        raise ValueError("credentials.json not found in addon folder")
    port         = _find_free_port()
    redirect_uri = f"http://localhost:{port}"
    auth_event   = threading.Event()
    result       = {'code': None, 'error': None, 'port': port}
    _auth_html   = os.path.join(_google_addon_dir(), 'auth.html')

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in qs:
                result['code'] = qs['code'][0]
                success = True
            else:
                result['error'] = qs.get('error', ['unknown'])[0]
                success = False
            try:
                with open(_auth_html, 'rb') as f:
                    html = f.read()
                flag = b'true' if success else b'false'
                html = html.replace(
                    b'</head>',
                    b'<script>var AUTH_SUCCESS=' + flag + b';</script></head>',
                    1,
                )
                body = html
            except Exception:
                body = b'<h1>Done. You can close this tab.</h1>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            auth_event.set()

        def log_message(self, *a):
            pass

    def _serve():
        srv = http.server.HTTPServer(('localhost', port), _Handler)
        srv.handle_request()

    threading.Thread(target=_serve, daemon=True).start()

    params = urllib.parse.urlencode({
        'client_id':     creds['client_id'],
        'redirect_uri':  redirect_uri,
        'response_type': 'code',
        'scope':         'https://www.googleapis.com/auth/spreadsheets.readonly',
        'access_type':   'offline',
        'prompt':        'consent',
    })
    webbrowser.open(f"{creds['auth_uri']}?{params}")
    return auth_event, result


def google_exchange_code(code, port):
    """Exchange auth code for tokens and save to disk."""
    creds   = google_load_credentials()
    payload = urllib.parse.urlencode({
        'code':          code,
        'client_id':     creds['client_id'],
        'client_secret': creds['client_secret'],
        'redirect_uri':  f"http://localhost:{port}",
        'grant_type':    'authorization_code',
    }).encode()
    req = urllib.request.Request(
        creds['token_uri'], data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read())
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    google_save_token(token)
    return token


def _google_api_get(access_token, url):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def google_parse_spreadsheet_id(url_or_id):
    """Extract spreadsheet ID from a URL, or return the value as-is."""
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if m:
        return m.group(1)
    return url_or_id.strip()


def google_get_spreadsheet_sheets(access_token, spreadsheet_id):
    """Return a list of sheet tab titles."""
    data = _google_api_get(
        access_token,
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        f"?fields=sheets.properties.title",
    )
    return [s['properties']['title'] for s in data.get('sheets', [])]


def google_get_sheet_as_tsv(access_token, spreadsheet_id, sheet_title):
    """Return sheet data as a TSV string."""
    range_param = urllib.parse.quote(sheet_title)
    data = _google_api_get(
        access_token,
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        f"/values/{range_param}",
    )
    rows = data.get('values', [])
    return '\n'.join('\t'.join(str(c) for c in row) for row in rows)

# endregion

# region Callbacks

def _on_autofill_url_change(self, context):
    global _google_sheet_tabs, _url_load_timer_registered, _url_last_change
    _google_sheet_tabs = []
    _url_last_change   = time.time()
    if not self.optiflow_autofill_url.strip() or not google_is_authenticated():
        return
    if not _url_load_timer_registered:
        _url_load_timer_registered = True
        bpy.app.timers.register(_load_tabs_deferred, first_interval=0.8)


def _load_tabs_deferred():
    global _google_sheet_tabs, _url_load_timer_registered, _url_last_change
    if time.time() - _url_last_change < 0.7:
        return 0.8
    _url_load_timer_registered = False
    if not bpy.context or not bpy.context.scene:
        return None
    url = bpy.context.scene.optiflow_autofill_url.strip()
    if not url or not google_is_authenticated():
        return None
    token = google_get_valid_token()
    if not token:
        return None
    try:
        spreadsheet_id     = google_parse_spreadsheet_id(url)
        _google_sheet_tabs = google_get_spreadsheet_sheets(token['access_token'], spreadsheet_id)
    except Exception as e:
        print(f"[OptiFlow] Auto-load sheet tabs failed: {e}")
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def _poll_google_auth():
    global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
    if not _google_auth_event_ref or not _google_auth_event_ref.is_set():
        return 1.0
    result                  = _google_auth_result_ref
    _google_auth_pending    = False
    _google_auth_event_ref  = None
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
        label = 'Loading…' if _url_load_timer_registered else '— Load tabs first —'
        return [('NONE', label, '')]
    return [(t, t, '') for t in _google_sheet_tabs]


# endregion

# region Text Editor Operator

class OPT_OT_open_autofill_text(Operator):
    """Open the Auto-Fill text block in a text editor window."""
    bl_idname  = "optiflow.open_autofill_text"
    bl_label   = "Open Editor"
    bl_description = "Open the Auto-Fill text block in a text editor window"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        text_block = bpy.data.texts.get(_AUTO_FILL_TEXT) or bpy.data.texts.new(_AUTO_FILL_TEXT)
        existing   = set(context.window_manager.windows[:])
        bpy.ops.wm.window_new()
        new_wins = [w for w in context.window_manager.windows if w not in existing]
        if not new_wins:
            self.report({'WARNING'}, "Could not open new window.")
            return {'CANCELLED'}
        area = new_wins[0].screen.areas[0]
        area.type           = 'TEXT_EDITOR'
        area.spaces[0].text = text_block
        return {'FINISHED'}

# endregion

# region Google Auth Operators

class OPT_OT_google_auth(Operator):
    """Open browser to authenticate with Google."""
    bl_idname  = "optiflow.google_auth"
    bl_label   = "Connect to Google"
    bl_description = "Sign in with Google to access your Sheets"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
        try:
            event, result = google_start_auth_flow()
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        _google_auth_pending    = True
        _google_auth_event_ref  = event
        _google_auth_result_ref = result
        bpy.app.timers.register(_poll_google_auth, first_interval=1.0)
        return {'FINISHED'}


class OPT_OT_google_auth_cancel(Operator):
    """Cancel the pending Google authentication."""
    bl_idname  = "optiflow.google_auth_cancel"
    bl_label   = "Cancel"
    bl_description = "Cancel the pending Google authentication"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_auth_pending, _google_auth_event_ref, _google_auth_result_ref
        _google_auth_pending    = False
        _google_auth_event_ref  = None
        _google_auth_result_ref = None
        try:
            bpy.app.timers.unregister(_poll_google_auth)
        except Exception:
            pass
        return {'FINISHED'}


class OPT_OT_google_disconnect(Operator):
    """Clear saved Google token."""
    bl_idname  = "optiflow.google_disconnect"
    bl_label   = "Disconnect"
    bl_description = "Disconnect Google account and clear saved token"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_sheet_tabs
        google_clear_token()
        _google_sheet_tabs = []
        return {'FINISHED'}


class OPT_OT_google_load_tabs(Operator):
    """Fetch sheet tab names from the entered spreadsheet."""
    bl_idname  = "optiflow.google_load_tabs"
    bl_label   = "Load Sheet Tabs"
    bl_description = "Fetch the sheet tabs from the entered spreadsheet"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _google_sheet_tabs
        url = context.scene.optiflow_autofill_url.strip()
        if not url:
            self.report({'ERROR'}, "Enter a spreadsheet URL or ID first.")
            return {'CANCELLED'}
        token = google_get_valid_token()
        if not token:
            self.report({'ERROR'}, "Not authenticated with Google.")
            return {'CANCELLED'}
        try:
            spreadsheet_id     = google_parse_spreadsheet_id(url)
            _google_sheet_tabs = google_get_spreadsheet_sheets(token['access_token'], spreadsheet_id)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load sheet tabs: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

# endregion

# region Auto Fill Operator

class optiflow_auto_fill(Operator):
    """Rename items automatically from an external data source."""
    bl_idname  = "optiflow.auto_fill"
    bl_label   = "Auto Fill"
    bl_description = "Automatically rename items based on a provided list"
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(
        name="Source",
        items=[
            ('GOOGLE_SHEETS', "Google Sheets", "Fill based on a Google Spreadsheet"),
            ('FILE',          "File",          "Fill based on a CSV or TSV file"),
            ('TEXT_EDITOR',   "Text Editor",   "Fill based on text written or pasted by the user"),
        ],
        default='GOOGLE_SHEETS',
    )  # type: ignore

    key_name:   StringProperty(name="Key",        description="Column name in the sheet to use as the result (e.g. 'SKU')")  # type: ignore
    header_row: IntProperty(name="Row", default=1, min=1, description="Row number that contains the column headers")  # type: ignore
    prefix:     StringProperty(name="Prefix",   description="Optional prefix added before the key value (PREFIX_VALUE)")  # type: ignore
    suffix:     StringProperty(name="Suffix",   description="Optional suffix added after the key value (VALUE_SUFFIX)")   # type: ignore

    sheet_tab: EnumProperty(
        name="Sheet",
        items=_sheet_tab_items,
    )  # type: ignore

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        prop_input(layout, self, "Source:", "source", expand=True)
        layout.separator(type='LINE')

        if self.source == 'TEXT_EDITOR':
            split = layout.split(factor=0.23)
            split.label(text="Text:")
            row = split.row(align=True)
            row.operator("optiflow.open_autofill_text", text="Open")
            row.operator("optiflow.open_autofill_text", text="", icon='TEXT')
            text = bpy.data.texts.get(_AUTO_FILL_TEXT)
            split = layout.split(factor=0.23)
            split.label(text="")
            if text and text.as_string().strip():
                split.label(text=f"{len(text.lines)} line(s) loaded.")
            else:
                split.label(text="No list loaded yet. Open the editor to paste.")

        elif self.source == 'FILE':
            file_input(layout, scene, "File:", "optiflow_autofill_file", "csv,tsv,txt")
            path = bpy.path.abspath(scene.optiflow_autofill_file) if scene.optiflow_autofill_file else ""
            split = layout.split(factor=0.23)
            split.label(text="")
            if path and os.path.isfile(path):
                split.label(text=f"Ready: {os.path.basename(path)}")
            else:
                split.label(text="Select a CSV or TSV file.")

        elif self.source == 'GOOGLE_SHEETS':
            if _google_auth_pending:
                row = layout.row(align=True)
                row.label(text="Waiting for browser authentication...", icon='TIME')
                row.operator("optiflow.google_auth_cancel", text="", icon='X')
            elif not google_is_authenticated():
                layout.operator("optiflow.google_auth", text="Connect to Google", icon='INTERNET')
            else:
                split = layout.split(factor=0.23)
                split.label(text="Url / Id:")
                row = split.row(align=True)
                row.prop(scene, "optiflow_autofill_url", text="")
                row.operator("optiflow.google_load_tabs", text="", icon='FILE_REFRESH')
                row.separator()
                row.operator("optiflow.google_disconnect", text="", icon='INTERNET_OFFLINE')
                if scene.optiflow_autofill_url.strip():
                    split = layout.split(factor=0.23)
                    split.label(text="Sheet:")
                    row = split.row()
                    row.enabled = bool(_google_sheet_tabs)
                    row.prop(self, "sheet_tab", text="")

        layout.separator(type='LINE')
        split = layout.split(factor=0.23)
        split.label(text="Key:")
        row = split.row(align=True)
        row.prop(self, "key_name", text="")
        row.prop(self, "header_row")
        row = layout.row(align=True)
        split = layout.split(factor=0.23)
        split.label(text="Prefix / Suffix:")
        row = split.row(align=True)
        row.prop(self, "prefix", text="")
        row.prop(self, "suffix", text="")
        layout.separator(type='LINE')

    def execute(self, context):
        scene   = context.scene
        self._save_settings(scene)
        key_col = self.key_name.strip()
        prefix  = re.sub(r'[^A-Za-z0-9]', '', self.prefix)
        suffix  = re.sub(r'[^A-Za-z0-9]', '', self.suffix)

        if not key_col:
            self.report({'ERROR'}, "Enter the key column name (e.g. 'SKU').")
            return {'CANCELLED'}

        # ── Fetch content ─────────────────────────────────────────────────────
        if self.source == 'TEXT_EDITOR':
            text = bpy.data.texts.get(_AUTO_FILL_TEXT)
            if not text or not text.as_string().strip():
                self.report({'ERROR'}, "The list is empty.")
                return {'CANCELLED'}
            content = text.as_string()

        elif self.source == 'FILE':
            path = bpy.path.abspath(scene.optiflow_autofill_file) if scene.optiflow_autofill_file else ""
            if not path or not os.path.isfile(path):
                self.report({'ERROR'}, "Select a valid file.")
                return {'CANCELLED'}
            with open(path, encoding='utf-8', errors='replace') as f:
                raw = f.read()
            if os.path.splitext(path)[1].lower() == '.csv':
                content = '\n'.join('\t'.join(row) for row in csv.reader(io.StringIO(raw)))
            else:
                content = raw

        elif self.source == 'GOOGLE_SHEETS':
            url = scene.optiflow_autofill_url.strip()
            if not url:
                self.report({'ERROR'}, "Enter a spreadsheet URL or ID.")
                return {'CANCELLED'}
            if not self.sheet_tab or self.sheet_tab == 'NONE':
                self.report({'ERROR'}, "No sheet selected.")
                return {'CANCELLED'}
            token = google_get_valid_token()
            if not token:
                self.report({'ERROR'}, "Not authenticated with Google.")
                return {'CANCELLED'}
            try:
                spreadsheet_id = google_parse_spreadsheet_id(url)
                content = google_get_sheet_as_tsv(token['access_token'], spreadsheet_id, self.sheet_tab)
                scene.optiflow_autofill_tab = self.sheet_tab
            except Exception as e:
                self.report({'ERROR'}, f"Failed to fetch sheet: {e}")
                return {'CANCELLED'}
        else:
            return {'CANCELLED'}

        # ── Collect all items ─────────────────────────────────────────────────
        all_items  = []   # [(gi, ii), ...]
        items_data = []   # parallel list of signal dicts
        for gi, group in enumerate(scene.optiflow_groups):
            for ii, item in enumerate(group.items):
                all_items.append((gi, ii))
                items_data.append({
                    'group_name': group.name.strip(),
                    'item_name':  item.name.strip(),
                    'alias':      item.alias.strip(),
                })

        if not all_items:
            self.report({'INFO'}, "No items to fill.")
            return {'CANCELLED'}

        # ── Match ──────────────────────────────────────────────────────────────
        matches, error = auto_fill_names_multi(content, items_data, key_col, self.header_row)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        # ── Apply results ─────────────────────────────────────────────────────
        count_matched = count_invalid = 0
        for (gi, ii), match_val in zip(all_items, matches):
            if match_val:
                scene.optiflow_groups[gi].items[ii].name = _format_result(match_val, prefix, suffix)
                count_matched += 1
            else:
                scene.optiflow_groups[gi].items[ii].name = _format_result('INVALID', prefix, suffix)
                count_invalid += 1

        self.report(
            {'INFO'},
            f"Matched {count_matched}, INVALID {count_invalid} of {len(all_items)}.",
        )
        return {'FINISHED'}

    def invoke(self, context, event):
        scene = context.scene
        if scene.optiflow_autofill_source in ('GOOGLE_SHEETS', 'FILE', 'TEXT_EDITOR'):
            self.source = scene.optiflow_autofill_source
        self.key_name = scene.optiflow_autofill_key_name
        self.prefix   = scene.optiflow_autofill_prefix
        self.suffix   = scene.optiflow_autofill_suffix
        try:
            self.header_row = int(scene.optiflow_autofill_header_row)
        except ValueError:
            pass
        remembered = scene.optiflow_autofill_tab
        if remembered and remembered in _google_sheet_tabs:
            self.sheet_tab = remembered
        return context.window_manager.invoke_props_dialog(
            self, width=420, confirm_text="Fill"
        )

    def _save_settings(self, scene):
        scene.optiflow_autofill_source     = self.source
        scene.optiflow_autofill_key_name   = self.key_name
        scene.optiflow_autofill_header_row = str(self.header_row)
        scene.optiflow_autofill_prefix     = self.prefix
        scene.optiflow_autofill_suffix     = self.suffix

# endregion
