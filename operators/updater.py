import bpy
import urllib.request
import json
import threading
import os
import tempfile
from bpy.types import Operator

GITHUB_REPO  = "gchibeni/OptiFlow"
GITHUB_URL   = f"https://github.com/{GITHUB_REPO}"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

_state = {
    "checked": False,
    "checking": False,
    "available": False,
    "latest_version": "",
    "latest_tag": "",
    "manual_pending": False,
    "download_url": "",
    "downloading": False,
    "download_error": "",
}

_startup_check_done = False


def get_update_state():
    return _state


def _get_current_version():
    from .. import bl_info
    return bl_info["version"]


def _parse_version(tag):
    tag = tag.lstrip("vV")
    try:
        return tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _redraw_view3d():
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    return None


def _fetch_update():
    global _state
    manual = _state.get("manual_pending", False)
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": "OptiFlow-Blender-Addon"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        latest = _parse_version(tag)
        current = _get_current_version()
        assets = data.get("assets", [])
        download_url = next(
            (a.get("browser_download_url", "") for a in assets if a.get("name", "").endswith(".zip")),
            data.get("zipball_url", ""),
        )
        _state = {
            "checked": True,
            "checking": False,
            "available": latest > current,
            "latest_version": ".".join(str(x) for x in latest),
            "latest_tag": tag,
            "manual_pending": False,
            "download_url": download_url,
            "downloading": False,
            "download_error": "",
        }
    except Exception:
        _state = {
            "checked": True,
            "checking": False,
            "available": False,
            "latest_version": "",
            "latest_tag": "",
            "manual_pending": False,
            "download_url": "",
            "downloading": False,
            "download_error": "",
        }

    def _on_done():
        _redraw_view3d()
        if manual and _state.get("available"):
            bpy.ops.optiflow.confirm_update('INVOKE_DEFAULT')
        return None

    bpy.app.timers.register(_on_done, first_interval=0.0)


def check_for_updates_async():
    _state["checking"] = True
    threading.Thread(target=_fetch_update, daemon=True).start()


def _download_and_install(download_url):
    """Download the release zip from GitHub and install it as a Blender extension."""
    global _state
    try:
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "OptiFlow-Blender-Addon"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            zip_data = resp.read()

        fd, temp_path = tempfile.mkstemp(suffix='.zip', prefix='optiflow_update_')
        try:
            os.write(fd, zip_data)
        finally:
            os.close(fd)

        def _install_on_main():
            global _state
            error = None
            try:
                bpy.ops.extensions.package_install_files(
                    filepath=temp_path,
                    enable_on_install=True,
                )
            except Exception as e:
                error = str(e)
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            _state["downloading"] = False
            if error:
                _state["download_error"] = error
                def _show_err(self_menu, context):
                    self_menu.layout.label(text="Update failed:", icon='ERROR')
                    self_menu.layout.label(text=error[:80])
                bpy.context.window_manager.popup_menu(_show_err, title="OptiFlow Update")
            else:
                def _show_ok(self_menu, context):
                    self_menu.layout.label(text="OptiFlow updated successfully!")
                    self_menu.layout.label(text="Restart Blender to apply the changes.")
                bpy.context.window_manager.popup_menu(_show_ok, title="OptiFlow Update")
            _redraw_view3d()
            return None

        bpy.app.timers.register(_install_on_main, first_interval=0.0)

    except Exception as e:
        _state["downloading"] = False
        _state["download_error"] = str(e)
        bpy.app.timers.register(_redraw_view3d, first_interval=0.0)


@bpy.app.handlers.persistent
def _on_load_post(filepath):
    global _startup_check_done
    if not _startup_check_done:
        _startup_check_done = True
        check_for_updates_async()


# region Operators

class OPTIFLOW_OT_open_github(Operator):
    bl_idname = "optiflow.open_github"
    bl_label = "GitHub"
    bl_description = "Open the OptiFlow GitHub repository in your browser"

    def execute(self, context):
        bpy.ops.wm.url_open(url=GITHUB_URL)
        return {'FINISHED'}


class OPTIFLOW_OT_open_preferences(Operator):
    bl_idname = "optiflow.open_preferences"
    bl_label = "Settings"
    bl_description = "Open OptiFlow add-on settings"

    def execute(self, context):
        from .. import addon_name
        bpy.ops.preferences.addon_show(module=addon_name)
        return {'FINISHED'}


class OPTIFLOW_OT_confirm_update(Operator):
    """Downloads and installs the latest OptiFlow release."""
    bl_idname = "optiflow.confirm_update"
    bl_label = "Update Available"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        download_url = _state.get("download_url", "")
        if not download_url:
            bpy.ops.wm.url_open(url=RELEASES_URL)
            return {'FINISHED'}
        _state["downloading"] = True
        _state["download_error"] = ""
        threading.Thread(target=_download_and_install, args=(download_url,), daemon=True).start()
        self.report({'INFO'}, "Downloading OptiFlow update...")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self, width=360, confirm_text="Update"
        )

    def draw(self, context):
        layout = self.layout
        ver = _state.get("latest_version", "unknown")
        layout.separator(factor=0.3)
        col = layout.column(align=True)
        col.label(text=f"A new version ({ver}) was found in the repositories.")
        col.label(text="Do you want to download and install it now?")
        layout.separator(factor=0.3)


class OPTIFLOW_OT_check_updates(Operator):
    bl_idname = "optiflow.check_updates"
    bl_label = "Check for Updates"

    @classmethod
    def description(cls, context, properties):
        if _state.get("available"):
            ver = _state.get("latest_version", "")
            return f"Version {ver} is available — click to update"
        return "Check for a new OptiFlow release on GitHub"

    def execute(self, context):
        global _state
        _state["manual_pending"] = True
        check_for_updates_async()
        self.report({'INFO'}, "Checking for updates...")
        return {'FINISHED'}

# endregion

# region Registration

def register():
    bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    global _startup_check_done
    _startup_check_done = False
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

# endregion
