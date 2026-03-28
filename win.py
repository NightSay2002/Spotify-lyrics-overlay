import ctypes
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

import mac


if platform.system() != "Windows":
    raise SystemExit("win.py is only for Windows.")


SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FONT_FILE_NAME = "arheiuhk_bd.ttf"
ICON_FILE_NAME = "icon.png"


def resolve_node_bin_windows():
    runtime_root = mac.get_runtime_root()
    repo_root = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        mac.safe_strip(os.getenv("NODE_BIN")),
        os.path.join(runtime_root, "node.exe"),
        os.path.join(runtime_root, "node-runtime.exe"),
        os.path.join(runtime_root, "node-runtime", "node.exe"),
        os.path.join(runtime_root, "node-runtime", "node-runtime.exe"),
        os.path.join(repo_root, "node.exe"),
        os.path.join(repo_root, "node-runtime.exe"),
        os.path.join(repo_root, "node-runtime", "node.exe"),
        os.path.join(repo_root, "node-runtime", "node-runtime.exe"),
        mac.safe_strip(shutil.which("node.exe")),
        mac.safe_strip(shutil.which("node")),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def resolve_font_path():
    candidates = [
        os.path.join(mac.get_runtime_root(), FONT_FILE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), FONT_FILE_NAME),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def resolve_icon_path():
    candidates = [
        os.path.join(mac.get_runtime_root(), ICON_FILE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", ICON_FILE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILE_NAME),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def load_application_font():
    font_path = resolve_font_path()
    if not font_path:
        mac.log_warning(f"Bundled font not found: {FONT_FILE_NAME}")
        return ""

    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id < 0:
        mac.log_warning(f"Failed to load bundled font: {font_path}")
        return ""

    families = QFontDatabase.applicationFontFamilies(font_id)
    return families[0] if families else ""


def apply_overlay_font(overlay, font_family):
    if not font_family:
        return

    overlay.song_label.setFont(QFont(font_family, 14, QFont.Weight.DemiBold))


def apply_app_icon(app, overlay):
    icon_path = resolve_icon_path()
    if not icon_path:
        return

    icon = QIcon(icon_path)
    if icon.isNull():
        return

    app.setWindowIcon(icon)
    overlay.setWindowIcon(icon)
    overlay.control_window.setWindowIcon(icon)
    overlay.settings_window.setWindowIcon(icon)
    overlay.translation_window.setWindowIcon(icon)


def start_netease_api_if_needed_windows():
    if mac.is_netease_api_running():
        return

    if mac._NETEASE_API_PROCESS is not None and mac._NETEASE_API_PROCESS.poll() is None:
        return

    api_dir = mac.resolve_netease_api_dir()
    if not api_dir:
        mac.log_warning("api-enhanced directory not found. Netease fallback will stay disabled.")
        return

    node_bin = resolve_node_bin_windows()
    if not node_bin:
        mac.log_warning("Node.js runtime not found. api-enhanced could not be started.")
        return

    app_js_path = os.path.join(api_dir, "app.js")
    if not os.path.isfile(app_js_path):
        mac.log_warning("api-enhanced app.js not found. Netease fallback will stay disabled.")
        return

    try:
        api_url = urlparse(mac.DEFAULT_NETEASE_API_BASE_URL)
        api_port = str(api_url.port or 8998)
        process_env = os.environ.copy()
        process_env["PORT"] = api_port
        mac._NETEASE_API_LOG_FILE = open(mac.NETEASE_API_LOG_PATH, "a", encoding="utf-8")
        mac._NETEASE_API_PROCESS = subprocess.Popen(
            [node_bin, "app.js"],
            cwd=api_dir,
            stdout=mac._NETEASE_API_LOG_FILE,
            stderr=subprocess.STDOUT,
            env=process_env,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        mac.log_warning("Failed to start api-enhanced.", exc)
        mac._NETEASE_API_PROCESS = None
        if mac._NETEASE_API_LOG_FILE is not None:
            mac._NETEASE_API_LOG_FILE.close()
            mac._NETEASE_API_LOG_FILE = None
        return

    for _ in range(20):
        if mac.is_netease_api_running():
            return
        if mac._NETEASE_API_PROCESS.poll() is not None:
            break
        time.sleep(0.25)

    mac.log_warning("api-enhanced did not become ready in time. Check api-enhanced.log for details.")


def _set_window_topmost(widget, force_front=False):
    if widget is None or not widget.isVisible():
        return

    try:
        hwnd = int(widget.winId())
    except Exception:
        return

    user32 = ctypes.windll.user32
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOOWNERZORDER | SWP_NOACTIVATE
    if force_front:
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        flags |= SWP_SHOWWINDOW
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)


def _ensure_on_top_windows(self, force_front=False):
    _set_window_topmost(self, force_front=force_front)
    if self.control_window.isVisible():
        _set_window_topmost(self.control_window, force_front=force_front)
    if self.settings_window.isVisible():
        _set_window_topmost(self.settings_window, force_front=force_front)
    if self.translation_window.isVisible():
        _set_window_topmost(self.translation_window, force_front=force_front)


def _set_windows_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SpotifyFloatingOverlay.Win")
    except Exception:
        pass


mac.resolve_node_bin = resolve_node_bin_windows
mac.start_netease_api_if_needed = start_netease_api_if_needed_windows
mac.LyricsOverlay._ensure_on_top = _ensure_on_top_windows


def main():
    _set_windows_app_id()
    app = QApplication(sys.argv)
    font_family = load_application_font()
    if font_family:
        app.setFont(QFont(font_family, 10))
    app.setQuitOnLastWindowClosed(True)

    overlay = mac.LyricsOverlay()
    apply_overlay_font(overlay, font_family)
    apply_app_icon(app, overlay)
    overlay.show()
    overlay._ensure_on_top(force_front=True)
    QTimer.singleShot(
        0,
        lambda: threading.Thread(
            target=start_netease_api_if_needed_windows,
            name="netease-api-start",
            daemon=True,
        ).start(),
    )

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
