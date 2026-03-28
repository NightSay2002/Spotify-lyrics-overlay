import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import requests
import spotipy
from bs4 import BeautifulSoup
from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyOauthError

if platform.system() == "Darwin":
    from ctypes import c_void_p

    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSStatusWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorIgnoresCycle,
        NSWindowCollectionBehaviorStationary,
        NSWindowStyleMaskNonactivatingPanel,
    )

DEFAULT_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
DEFAULT_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
DEFAULT_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
DEFAULT_NETEASE_API_BASE_URL = os.getenv("NETEASE_API_BASE_URL", "http://localhost:8998")
SCOPE = "user-read-currently-playing"
APP_NAME = "Spotify Floating Overlay"

POLL_INTERVAL_MS = 1000
ANIMATION_INTERVAL_MS = 16
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Spotify Floating Overlay)"}
WINDOW_TRANSPARENT_FOR_INPUT = getattr(
    Qt.WindowType, "WindowTransparentForInput", Qt.WindowType(0)
)
MOJIGECI_QUERY_ALIASES = {
    ("bldama", "hachi"): ["ビー玉 HACHI", "ビー玉"],
}
UI_STRINGS = {
    "zh": {
        "settings_window_title": "字幕設定",
        "translation_window_title": "翻譯字幕",
        "button_move": "移動",
        "button_lock": "鎖定",
        "button_settings": "設定",
        "button_translation": "翻譯",
        "button_close": "關閉",
        "button_apply": "套用",
        "button_clear": "清除",
        "button_load": "讀取",
        "button_save_spotify": "儲存 Spotify Key",
        "button_clear_spotify": "清除 Spotify Key",
        "button_language": "English",
        "button_offset_reset": "重設",
        "field_text_color": "字色",
        "field_end_color": "終點色",
        "field_button_color": "按鈕色",
        "field_main_size": "主字幕",
        "field_main_translation_size": "主翻譯",
        "field_subtitle_size": "副字幕",
        "field_subtitle_translation_size": "副翻譯",
        "field_gap_song": "歌名距離",
        "field_gap_primary": "行距 1",
        "field_gap_middle": "行距 2",
        "field_gap_subtitle": "行距 3",
        "field_show_song": "顯示歌名",
        "field_show_main": "顯示主歌詞",
        "field_show_subtitle": "顯示副歌詞",
        "field_show_translation": "顯示翻譯",
        "field_client_id": "Client ID",
        "field_client_secret": "Client Secret",
        "field_redirect_uri": "Redirect URI",
        "field_timing_song": "校正歌曲",
        "field_lyric_offset": "歌詞偏移(ms)",
        "field_track_name": "歌名",
        "field_artist_name": "歌手",
        "translation_hint": "每兩行一組：原文 / 翻譯。開頭重複歌名會自動略過。",
        "dialog_pick_text_color": "選擇字幕顏色",
        "dialog_pick_end_color": "選擇主字幕終點色",
        "dialog_pick_button_color": "選擇按鈕顏色",
        "spotify_key_empty": "Spotify key 不可留空。",
        "spotify_key_prompt": "請填入 Spotify Client ID、Client Secret 和 Redirect URI。",
        "spotify_key_saved": "Spotify key 已儲存，之後會一直保留。",
        "spotify_key_cleared": "Spotify key 已清除。",
        "spotify_save_failed": "儲存失敗：{error}",
        "lyric_offset_saved": "已儲存這首歌的歌詞偏移：{offset} ms",
        "translation_enter_song_name": "請先輸入歌名。",
        "translation_loaded": "已載入已儲存的翻譯。",
        "translation_not_found": "這首歌目前沒有已儲存的翻譯。",
        "translation_cleared_current": "已清空這首歌的手動翻譯。",
        "translation_format_invalid": "格式不對，請用原文 / 翻譯成對貼上。",
        "translation_saved_applied": "已儲存並套用 {count} 行翻譯。",
        "translation_saved_json": "已儲存到 JSON，播放到這首歌時會自動套用。",
        "translation_deleted_json": "已刪除這首歌的 JSON 翻譯。",
        "spotify_unconfigured_title": "Spotify 未設定",
        "spotify_unconfigured_message": "打開設定並填入 Spotify Client ID / Secret",
        "spotify_paused_title": "Spotify 已暫停",
        "spotify_waiting_message": "等待 Spotify 播放中...",
        "spotify_unable_title": "Spotify",
        "spotify_unable_message": "無法讀取目前歌曲。",
        "spotify_key_error_title": "Spotify Key Error",
        "spotify_key_error_message": "請到設定填入 Spotify Client ID / Secret / Redirect URI",
        "spotify_error_title": "Spotify Error",
        "spotify_error_message": "錯誤：{error}",
        "no_synced_lyrics_found": "♫純音樂♫",
    },
    "en": {
        "settings_window_title": "Subtitle Settings",
        "translation_window_title": "Translation Subtitles",
        "button_move": "Move",
        "button_lock": "Lock",
        "button_settings": "Settings",
        "button_translation": "Translate",
        "button_close": "Quit",
        "button_apply": "Apply",
        "button_clear": "Clear",
        "button_load": "Load",
        "button_save_spotify": "Save Spotify Key",
        "button_clear_spotify": "Clear Spotify Key",
        "button_language": "中文",
        "button_offset_reset": "Reset",
        "field_text_color": "Text Color",
        "field_end_color": "End Color",
        "field_button_color": "Button Color",
        "field_main_size": "Main Lyric",
        "field_main_translation_size": "Main Translation",
        "field_subtitle_size": "Next Lyric",
        "field_subtitle_translation_size": "Next Translation",
        "field_gap_song": "Title Gap",
        "field_gap_primary": "Gap 1",
        "field_gap_middle": "Gap 2",
        "field_gap_subtitle": "Gap 3",
        "field_show_song": "Show Title",
        "field_show_main": "Show Main Lyric",
        "field_show_subtitle": "Show Next Lyric",
        "field_show_translation": "Show Translation",
        "field_client_id": "Client ID",
        "field_client_secret": "Client Secret",
        "field_redirect_uri": "Redirect URI",
        "field_timing_song": "Timing Track",
        "field_lyric_offset": "Lyric Offset (ms)",
        "field_track_name": "Track",
        "field_artist_name": "Artist",
        "translation_hint": "Use pairs of lines: original / translation. A repeated title at the top will be ignored.",
        "dialog_pick_text_color": "Pick Text Color",
        "dialog_pick_end_color": "Pick Main Lyric End Color",
        "dialog_pick_button_color": "Pick Button Color",
        "spotify_key_empty": "Spotify key cannot be empty.",
        "spotify_key_prompt": "Please fill in Spotify Client ID, Client Secret, and Redirect URI.",
        "spotify_key_saved": "Spotify key saved and will be kept locally.",
        "spotify_key_cleared": "Spotify key cleared.",
        "spotify_save_failed": "Save failed: {error}",
        "lyric_offset_saved": "Saved lyric offset for this song: {offset} ms",
        "translation_enter_song_name": "Please enter a track name first.",
        "translation_loaded": "Saved translation loaded.",
        "translation_not_found": "No saved translation was found for this song.",
        "translation_cleared_current": "Manual translation for this song has been cleared.",
        "translation_format_invalid": "Invalid format. Paste original / translation in pairs.",
        "translation_saved_applied": "Saved and applied {count} translated lines.",
        "translation_saved_json": "Saved to JSON and will auto-apply when this song plays.",
        "translation_deleted_json": "Deleted this song's JSON translation.",
        "spotify_unconfigured_title": "Spotify Not Configured",
        "spotify_unconfigured_message": "Open Settings and add Spotify Client ID / Secret",
        "spotify_paused_title": "Spotify Paused",
        "spotify_waiting_message": "Waiting for Spotify playback...",
        "spotify_unable_title": "Spotify",
        "spotify_unable_message": "Unable to read current track.",
        "spotify_key_error_title": "Spotify Key Error",
        "spotify_key_error_message": "Open Settings and fill Spotify Client ID / Secret / Redirect URI",
        "spotify_error_title": "Spotify Error",
        "spotify_error_message": "Error: {error}",
        "no_synced_lyrics_found": "♫Instrumental♫",
    },
}

if platform.system() == "Darwin":
    MACOS_PANEL_BEHAVIOR = (
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorIgnoresCycle
    )


def _macos_native_window(widget):
    if platform.system() != "Darwin":
        return None

    try:
        ns_view = objc.objc_object(c_void_p=int(widget.winId()))
        return ns_view.window()
    except Exception:
        return None


def _configure_macos_app():
    if platform.system() != "Darwin":
        return

    try:
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        return


def _configure_macos_panel(widget, accepts_input=True, force_front=False):
    ns_window = _macos_native_window(widget)
    if ns_window is None:
        return

    try:
        style_mask = int(ns_window.styleMask())
        if not style_mask & NSWindowStyleMaskNonactivatingPanel:
            ns_window.setStyleMask_(style_mask | NSWindowStyleMaskNonactivatingPanel)
    except Exception:
        pass

    try:
        ns_window.setHidesOnDeactivate_(False)
    except Exception:
        pass

    try:
        ns_window.setIgnoresMouseEvents_(not accepts_input)
    except Exception:
        pass

    for selector_name, value in (
        ("setFloatingPanel_", True),
        ("setBecomesKeyOnlyIfNeeded_", True),
        ("setWorksWhenModal_", True),
        ("setHasShadow_", False),
        ("setExcludedFromWindowsMenu_", True),
    ):
        if not hasattr(ns_window, selector_name):
            continue
        try:
            getattr(ns_window, selector_name)(value)
        except Exception:
            continue

    try:
        ns_window.setCollectionBehavior_(int(MACOS_PANEL_BEHAVIOR))
    except Exception:
        pass

    try:
        ns_window.setLevel_(NSStatusWindowLevel)
    except Exception:
        pass

    if force_front and widget.isVisible():
        try:
            ns_window.orderFrontRegardless()
        except Exception:
            pass
        try:
            ns_window.setCollectionBehavior_(int(MACOS_PANEL_BEHAVIOR))
        except Exception:
            pass
        try:
            ns_window.setLevel_(NSStatusWindowLevel)
        except Exception:
            pass


def _clamp_rect_to_screen(x, y, width, height):
    app = QApplication.instance()
    if app is None:
        return x, y

    target_screen = app.screenAt(QPoint(x + width // 2, y + height // 2))
    if target_screen is None:
        target_screen = app.primaryScreen()
    if target_screen is None:
        return x, y

    available = target_screen.availableGeometry()
    clamped_x = min(max(x, available.left()), available.right() - width + 1)
    clamped_y = min(max(y, available.top()), available.bottom() - height + 1)
    return clamped_x, clamped_y


def get_app_data_dir():
    if platform.system() == "Darwin":
        base_dir = os.path.expanduser("~/Library/Application Support")
    elif platform.system() == "Windows":
        base_dir = os.getenv("APPDATA") or os.path.expanduser("~/AppData/Roaming")
    else:
        base_dir = os.path.expanduser("~/.config")

    app_data_dir = os.path.join(base_dir, APP_NAME)
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir


APP_DATA_DIR = get_app_data_dir()
MANUAL_TRANSLATIONS_PATH = os.path.join(APP_DATA_DIR, "manual_translations.json")
APP_SETTINGS_PATH = os.path.join(APP_DATA_DIR, "app_settings.json")
LEGACY_MANUAL_TRANSLATIONS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "manual_translations.json"
)
SPOTIFY_CACHE_PATH = os.path.join(APP_DATA_DIR, ".spotify_token_cache")
NETEASE_API_LOG_PATH = os.path.join(APP_DATA_DIR, "api-enhanced.log")
NETEASE_API_ARCHIVE_NAME = "api-enhanced.tar.gz"
NETEASE_API_RUNTIME_DIR = os.path.join(APP_DATA_DIR, "api-enhanced-runtime")
NODE_RUNTIME_NAME = "node-runtime"
_NETEASE_API_PROCESS = None
_NETEASE_API_LOG_FILE = None


def load_app_settings():
    if not os.path.exists(APP_SETTINGS_PATH):
        return {}

    try:
        with open(APP_SETTINGS_PATH, "r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return settings if isinstance(settings, dict) else {}


def save_app_settings(settings):
    with open(APP_SETTINGS_PATH, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)


def get_runtime_root():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _extract_netease_api_archive(archive_path):
    if not archive_path or not os.path.isfile(archive_path):
        return ""

    stamp = f"{os.path.getsize(archive_path)}:{int(os.path.getmtime(archive_path))}"
    stamp_path = os.path.join(NETEASE_API_RUNTIME_DIR, ".bundle_stamp")
    extracted_dir = os.path.join(NETEASE_API_RUNTIME_DIR, "api-enhanced")

    if os.path.isfile(os.path.join(extracted_dir, "app.js")) and os.path.exists(stamp_path):
        try:
            with open(stamp_path, "r", encoding="utf-8") as file:
                if safe_strip(file.read()) == stamp:
                    return extracted_dir
        except OSError:
            pass

    shutil.rmtree(NETEASE_API_RUNTIME_DIR, ignore_errors=True)
    os.makedirs(NETEASE_API_RUNTIME_DIR, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(NETEASE_API_RUNTIME_DIR)
        for current_root, dir_names, file_names in os.walk(NETEASE_API_RUNTIME_DIR):
            for dir_name in list(dir_names):
                if dir_name.startswith("._"):
                    shutil.rmtree(os.path.join(current_root, dir_name), ignore_errors=True)
                    dir_names.remove(dir_name)
            for file_name in file_names:
                if file_name.startswith("._"):
                    try:
                        os.remove(os.path.join(current_root, file_name))
                    except OSError:
                        pass
        with open(stamp_path, "w", encoding="utf-8") as file:
            file.write(stamp)
    except (OSError, tarfile.TarError) as exc:
        log_warning("Failed to extract bundled api-enhanced.", exc)
        shutil.rmtree(NETEASE_API_RUNTIME_DIR, ignore_errors=True)
        return ""

    if os.path.isfile(os.path.join(extracted_dir, "app.js")):
        return extracted_dir
    return ""


def resolve_netease_api_dir():
    candidates = [
        safe_strip(os.getenv("API_ENHANCED_DIR")),
        os.path.join(get_runtime_root(), "api-enhanced"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "api-enhanced"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "app.js")):
            return candidate

    archive_candidates = [
        os.path.join(get_runtime_root(), NETEASE_API_ARCHIVE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), NETEASE_API_ARCHIVE_NAME),
    ]
    for archive_path in archive_candidates:
        extracted_dir = _extract_netease_api_archive(archive_path)
        if extracted_dir:
            return extracted_dir
    return ""


def resolve_node_bin():
    candidates = [
        safe_strip(os.getenv("NODE_BIN")),
        os.path.join(get_runtime_root(), NODE_RUNTIME_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), NODE_RUNTIME_NAME),
        safe_strip(shutil.which("node")),
    ]
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            if not os.access(candidate, os.X_OK):
                os.chmod(candidate, 0o755)
        except OSError:
            pass
        if os.access(candidate, os.X_OK):
            return candidate
    return ""


def is_netease_api_running():
    try:
        requests.get(DEFAULT_NETEASE_API_BASE_URL, timeout=1, headers=REQUEST_HEADERS)
        return True
    except requests.RequestException:
        return False


def start_netease_api_if_needed():
    global _NETEASE_API_PROCESS, _NETEASE_API_LOG_FILE

    if is_netease_api_running():
        return

    if _NETEASE_API_PROCESS is not None and _NETEASE_API_PROCESS.poll() is None:
        return

    api_dir = resolve_netease_api_dir()
    if not api_dir:
        log_warning("api-enhanced directory not found. Netease fallback will stay disabled.")
        return

    node_bin = resolve_node_bin()
    if not node_bin:
        log_warning("Node.js runtime not found. api-enhanced could not be started.")
        return

    app_js_path = os.path.join(api_dir, "app.js")
    if not os.path.isfile(app_js_path):
        log_warning("api-enhanced app.js not found. Netease fallback will stay disabled.")
        return

    try:
        api_url = urlparse(DEFAULT_NETEASE_API_BASE_URL)
        api_port = str(api_url.port or 8998)
        process_env = os.environ.copy()
        process_env["PORT"] = api_port
        _NETEASE_API_LOG_FILE = open(NETEASE_API_LOG_PATH, "a", encoding="utf-8")
        _NETEASE_API_PROCESS = subprocess.Popen(
            [node_bin, "app.js"],
            cwd=api_dir,
            stdout=_NETEASE_API_LOG_FILE,
            stderr=subprocess.STDOUT,
            env=process_env,
        )
    except Exception as exc:
        log_warning("Failed to start api-enhanced.", exc)
        _NETEASE_API_PROCESS = None
        if _NETEASE_API_LOG_FILE is not None:
            _NETEASE_API_LOG_FILE.close()
            _NETEASE_API_LOG_FILE = None
        return

    for _ in range(20):
        if is_netease_api_running():
            return
        if _NETEASE_API_PROCESS.poll() is not None:
            break
        time.sleep(0.25)

    log_warning("api-enhanced did not become ready in time. Check api-enhanced.log for details.")


def stop_netease_api_if_needed():
    global _NETEASE_API_PROCESS, _NETEASE_API_LOG_FILE

    if _NETEASE_API_PROCESS is not None and _NETEASE_API_PROCESS.poll() is None:
        _NETEASE_API_PROCESS.terminate()
        try:
            _NETEASE_API_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _NETEASE_API_PROCESS.kill()

    _NETEASE_API_PROCESS = None
    if _NETEASE_API_LOG_FILE is not None:
        _NETEASE_API_LOG_FILE.close()
        _NETEASE_API_LOG_FILE = None


def resolve_spotify_settings(settings=None):
    settings = settings or {}
    return {
        "client_id": str(
            settings.get("client_id")
            or settings.get("spotify_client_id")
            or DEFAULT_CLIENT_ID
        ).strip(),
        "client_secret": str(
            settings.get("client_secret")
            or settings.get("spotify_client_secret")
            or DEFAULT_CLIENT_SECRET
        ).strip(),
        "redirect_uri": str(
            settings.get("redirect_uri")
            or settings.get("spotify_redirect_uri")
            or DEFAULT_REDIRECT_URI
        ).strip(),
    }


def has_spotify_credentials(settings=None):
    spotify_settings = resolve_spotify_settings(settings)
    return bool(
        spotify_settings["client_id"]
        and spotify_settings["client_secret"]
        and spotify_settings["redirect_uri"]
    )


def create_spotify_client(settings=None):
    spotify_settings = resolve_spotify_settings(settings)
    if not has_spotify_credentials(spotify_settings):
        return None
    auth_manager = SpotifyOAuth(
        client_id=spotify_settings["client_id"],
        client_secret=spotify_settings["client_secret"],
        redirect_uri=spotify_settings["redirect_uri"],
        scope=SCOPE,
        cache_path=SPOTIFY_CACHE_PATH,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def parse_lrc(lrc_content):
    if not lrc_content:
        return []

    lyrics_data = []
    pattern = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")

    for raw_line in lrc_content.splitlines():
        matches = pattern.findall(raw_line)
        if not matches:
            continue

        text = pattern.sub("", raw_line).strip()
        for minutes, seconds in matches:
            timestamp = int((int(minutes) * 60 + float(seconds)) * 1000)
            lyrics_data.append({"time": timestamp, "text": text})

    lyrics_data.sort(key=lambda line: line["time"])
    return lyrics_data


def get_lyrics(track_name, artist_name, duration_seconds=0):
    url = "https://lrclib.net/api/get"
    params = {"artist_name": artist_name, "track_name": track_name}
    if duration_seconds > 0:
        params["duration"] = duration_seconds
    try:
        response = requests.get(
            url,
            params=params,
            timeout=10,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        return response.json().get("syncedLyrics", "")
    except requests.RequestException:
        return ""


def search_lyrics(track_name, artist_name, duration_ms=0):
    try:
        response = requests.get(
            "https://lrclib.net/api/search",
            params={"artist_name": artist_name, "track_name": track_name},
            timeout=10,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError):
        return ""

    if not isinstance(results, list):
        return ""

    target_duration_seconds = duration_ms / 1000 if duration_ms > 0 else 0
    candidates = []

    for result in results:
        synced_lyrics = (result or {}).get("syncedLyrics") or ""
        if not synced_lyrics.strip():
            continue

        result_duration = float((result or {}).get("duration") or 0)
        duration_gap = abs(result_duration - target_duration_seconds) if target_duration_seconds > 0 else 0
        if target_duration_seconds > 0 and duration_gap > 2.0:
            continue

        candidates.append((duration_gap, synced_lyrics))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def get_best_synced_lyrics(track_name, artist_name, duration_ms=0):
    duration_seconds = int(round(duration_ms / 1000)) if duration_ms > 0 else 0
    duration_candidates = []
    if duration_seconds > 0:
        duration_candidates = [
            duration_seconds,
            duration_seconds - 1,
            duration_seconds + 1,
            duration_seconds - 2,
            duration_seconds + 2,
        ]

    for duration in duration_candidates:
        if duration <= 0:
            continue
        synced_lyrics = get_lyrics(track_name, artist_name, duration)
        if synced_lyrics.strip():
            return synced_lyrics

    synced_lyrics = get_lyrics(track_name, artist_name)
    if synced_lyrics.strip():
        return synced_lyrics

    return search_lyrics(track_name, artist_name, duration_ms)


def normalize_text(text):
    normalized = unicodedata.normalize("NFKC", text or "").lower().strip()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", "", normalized)
    return normalized


def safe_strip(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def log_warning(message, exc=None):
    print(f"[Spotify Floating Overlay] {message}", file=sys.stderr)
    if exc is not None:
        print(f"[Spotify Floating Overlay] {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()


def log_debug(message):
    print(f"[Spotify Floating Overlay][DEBUG] {message}", file=sys.stderr)


def merge_saved_text_style(saved_text_style):
    default_text_style = {
        "text_color": "#FFFFFF",
        "accent_color": "#60A5FA",
        "button_color": "#0F172A",
        "main_size": 30,
        "main_translation_size": 15,
        "subtitle_size": 20,
        "subtitle_translation_size": 10,
        "gap_song": 0,
        "gap_primary": 2,
        "gap_middle": 4,
        "gap_subtitle": 2,
        "show_song": True,
        "show_main": True,
        "show_subtitle": True,
        "show_translation": True,
    }
    if not isinstance(saved_text_style, dict):
        return default_text_style

    merged = dict(default_text_style)
    color_keys = {"text_color", "accent_color", "button_color"}
    bool_keys = {"show_song", "show_main", "show_subtitle", "show_translation"}

    for key, default_value in default_text_style.items():
        value = saved_text_style.get(key, default_value)
        if key in color_keys:
            normalized = safe_strip(value).upper()
            if re.fullmatch(r"#[0-9A-F]{6}", normalized):
                merged[key] = normalized
        elif key in bool_keys:
            merged[key] = bool(value)
        else:
            merged[key] = safe_int(value, default_value)

    return merged


def similarity_score(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def build_translation_block(translation_pairs):
    lines = []
    for pair in translation_pairs:
        original_text = safe_strip((pair or {}).get("original"))
        translation_text = safe_strip((pair or {}).get("translation"))
        if not original_text or not translation_text:
            continue
        lines.extend((original_text, translation_text))
    return "\n".join(lines)


def align_translation_lrc_by_time(original_lrc, translated_lrc):
    original_lines = parse_lrc(original_lrc)
    translated_lines = parse_lrc(translated_lrc)
    if not original_lines or not translated_lines:
        return []

    translated_by_time = {
        line["time"]: safe_strip(line.get("text"))
        for line in translated_lines
        if safe_strip(line.get("text"))
    }
    translation_pairs = []
    for line in original_lines:
        original_text = safe_strip(line.get("text"))
        translation_text = translated_by_time.get(line["time"], "")
        if not original_text or not translation_text:
            continue
        translation_pairs.append(
            {
                "original": original_text,
                "normalized_original": normalize_text(original_text),
                "translation": translation_text,
            }
        )
    return translation_pairs


def split_netease_merged_lrc(merged_lrc):
    if not merged_lrc:
        return "", []

    line_pattern = re.compile(r"\[\d+:\d+(?:\.\d+)?\]")
    original_lines = []
    translation_pairs = []

    for raw_line in merged_lrc.splitlines():
        timestamps = line_pattern.findall(raw_line)
        if not timestamps:
            continue

        merged_text = safe_strip(line_pattern.sub("", raw_line))
        original_text = merged_text
        translation_text = ""
        if " / " in merged_text:
            original_text, translation_text = [
                safe_strip(part) for part in merged_text.split(" / ", 1)
            ]

        original_lines.append("".join(timestamps) + original_text)
        if original_text and translation_text:
            translation_pairs.append(
                {
                    "original": original_text,
                    "normalized_original": normalize_text(original_text),
                    "translation": translation_text,
                }
            )

    return "\n".join(original_lines), translation_pairs


def generate_title_search_variants(track_name):
    base_title = safe_strip(track_name)
    if not base_title:
        return []

    variants = []
    seen = set()

    def add_variant(text):
        candidate = safe_strip(text)
        dedupe_key = unicodedata.normalize("NFKC", candidate).lower()
        if not candidate or dedupe_key in seen:
            return
        seen.add(dedupe_key)
        variants.append(candidate)

    add_variant(base_title)

    bracket_stripped = safe_strip(re.sub(r"\s*[\(\[（【].*?[\)\]）】]\s*", " ", base_title))
    add_variant(bracket_stripped)

    no_ellipsis = safe_strip(re.sub(r"[.…・]+$", "", safe_strip(base_title)))
    add_variant(no_ellipsis)
    add_variant(safe_strip(re.sub(r"[.…・]+$", "", bracket_stripped)))

    for variant in list(variants):
        simplified = re.split(r"\s*[-:|/]\s*", variant, maxsplit=1)[0]
        add_variant(simplified)

    return variants


def _netease_song_score(song, track_name, artist_name, duration_ms=0):
    song_name = safe_strip(song.get("name"))
    artists = song.get("ar") or song.get("artists") or []
    artist_names = [
        safe_strip(artist.get("name"))
        for artist in artists
        if isinstance(artist, dict) and safe_strip(artist.get("name"))
    ]
    song_artist = ", ".join(artist_names)

    target_title = normalize_text(track_name)
    target_artist = normalize_text(artist_name)
    song_title = normalize_text(song_name)
    song_artist_norm = normalize_text(song_artist)

    score = similarity_score(target_title, song_title) * 3
    score += similarity_score(target_artist, song_artist_norm) * 2

    if target_title and target_title == song_title:
        score += 2
    elif target_title and target_title in song_title:
        score += 1

    if target_artist and target_artist == song_artist_norm:
        score += 1.5
    elif target_artist and target_artist in song_artist_norm:
        score += 0.8

    song_duration_ms = int(song.get("dt") or song.get("duration") or 0)
    if duration_ms > 0 and song_duration_ms > 0:
        duration_gap = abs(song_duration_ms - duration_ms)
        if duration_gap <= 2000:
            score += 1.5
        elif duration_gap <= 5000:
            score += 0.5
        else:
            score -= min(duration_gap / 10000, 2.0)

    return score


def search_netease_song_id(track_name, artist_name, duration_ms=0):
    if not safe_strip(track_name):
        return None

    best_song = None
    best_score = 0.0
    title_variants = generate_title_search_variants(track_name) or [safe_strip(track_name)]

    for title_variant in title_variants:
        keywords = safe_strip(f"{title_variant} {artist_name}") or title_variant
        for endpoint in ("cloudsearch", "search"):
            try:
                response = requests.get(
                    f"{DEFAULT_NETEASE_API_BASE_URL}/{endpoint}",
                    params={"keywords": keywords, "type": 1, "limit": 10},
                    timeout=5,
                    headers=REQUEST_HEADERS,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                continue

            songs = ((payload or {}).get("result") or {}).get("songs") or []
            for song in songs:
                if not isinstance(song, dict):
                    continue

                score = _netease_song_score(song, title_variant, artist_name, duration_ms)
                score = max(score, _netease_song_score(song, track_name, artist_name, duration_ms))
                if title_variant != track_name:
                    score += 0.2
                if score > best_score:
                    best_score = score
                    best_song = song

            if best_song and best_score >= 3.5:
                break
        if best_song and best_score >= 3.5:
            break

    if not best_song or best_score < 3.0:
        return None

    return best_song.get("id")


def get_netease_lyrics_bundle(track_name, artist_name, duration_ms=0):
    song_id = search_netease_song_id(track_name, artist_name, duration_ms)
    if not song_id:
        return {"synced_lyrics": "", "translation_pairs": []}

    try:
        response = requests.get(
            f"{DEFAULT_NETEASE_API_BASE_URL}/lyric",
            params={"id": song_id, "conver": 3},
            timeout=5,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {"synced_lyrics": "", "translation_pairs": []}

    merged_lrc = safe_strip(((payload or {}).get("lrc") or {}).get("lyric"))
    translated_lrc = safe_strip(((payload or {}).get("tlyric") or {}).get("lyric"))
    synced_lyrics, translation_pairs = split_netease_merged_lrc(merged_lrc)

    if not synced_lyrics:
        synced_lyrics = merged_lrc

    if not translation_pairs and translated_lrc:
        translation_pairs = align_translation_lrc_by_time(synced_lyrics, translated_lrc)

    return {
        "synced_lyrics": synced_lyrics,
        "translation_pairs": translation_pairs,
    }


def translation_match_score(left, right):
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0

    if left_normalized == right_normalized:
        return 1.0

    base_score = similarity_score(left_normalized, right_normalized)
    shorter, longer = sorted(
        (left_normalized, right_normalized), key=len
    )

    if len(shorter) >= 4 and shorter in longer:
        gap_penalty = min(max(len(longer) - len(shorter), 0), 12) * 0.01
        base_score = max(base_score, 0.96 - gap_penalty)

    if left_normalized.startswith(right_normalized) or right_normalized.startswith(left_normalized):
        base_score = max(base_score, 0.9)

    return base_score


def search_mojigeci(track_name, artist_name):
    queries = [f"{track_name} {artist_name}".strip(), track_name]
    alias_key = (normalize_text(track_name), normalize_text(artist_name))
    queries.extend(MOJIGECI_QUERY_ALIASES.get(alias_key, []))

    best_candidate = None
    best_score = 0.0

    for query in queries:
        if not query:
            continue

        try:
            response = requests.get(
                "https://mojigeci.com/",
                params={"search": query},
                timeout=15,
                headers=REQUEST_HEADERS,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        seen_urls = set()

        for link in soup.select('a[href^="/lyrics/"]'):
            href = urljoin("https://mojigeci.com", link.get("href", ""))
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            title_node = link.find(["h1", "h2", "h3"])
            title = title_node.get_text(" ", strip=True) if title_node else ""

            artist = ""
            for paragraph in link.find_all("p"):
                text = paragraph.get_text(" ", strip=True)
                if text and text != title:
                    artist = text
                    break

            if not title:
                continue

            title_norm = normalize_text(title)
            artist_norm = normalize_text(artist)
            target_title = normalize_text(track_name)
            target_artist = normalize_text(artist_name)

            score = similarity_score(target_title, title_norm) * 3
            score += similarity_score(target_artist, artist_norm) * 2

            if target_title and target_title in title_norm:
                score += 2
            if target_artist and target_artist in artist_norm:
                score += 1

            if score > best_score:
                best_score = score
                best_candidate = href

        if best_score >= 6.0:
            break

    return best_candidate if best_score >= 6.0 else None


def fetch_mojigeci_translations(track_name, artist_name):
    lyric_url = search_mojigeci(track_name, artist_name)
    if not lyric_url:
        return []

    try:
        response = requests.get(lyric_url, timeout=15, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    translation_pairs = []

    for group in soup.select("div.lyrics-line-group"):
        original_node = group.select_one(".original-text")
        translation_node = group.select_one(".translation-text")

        if not original_node or not translation_node:
            continue

        original_text = original_node.get_text(" ", strip=True)
        translation_text = translation_node.get_text(" ", strip=True)
        if not original_text or not translation_text:
            continue

        translation_pairs.append(
            {
                "original": original_text,
                "normalized_original": normalize_text(original_text),
                "translation": translation_text,
            }
        )

    return translation_pairs


def _combined_lyric_text(lyrics_data, start_index, span_length):
    combined_parts = []
    end_index = min(start_index + span_length, len(lyrics_data))
    for index in range(start_index, end_index):
        text = safe_strip((lyrics_data[index] or {}).get("text"))
        if text:
            combined_parts.append(text)
    return "".join(combined_parts)


def align_translations_to_lyrics(lyrics_data, translation_pairs):
    if not lyrics_data:
        return []

    aligned_lyrics = [dict(lyric, translation="", translation_offset_ms=0) for lyric in lyrics_data]
    if not translation_pairs:
        return aligned_lyrics

    pair_index = 0
    window_size = 20

    lyric_index = 0

    while lyric_index < len(aligned_lyrics):
        lyric = aligned_lyrics[lyric_index]
        lyric_text = safe_strip(lyric.get("text"))
        normalized_lyric = normalize_text(lyric_text)
        if not normalized_lyric:
            lyric_index += 1
            continue

        best_match_index = None
        best_match_score = 0.0
        best_span_length = 1
        search_end = min(pair_index + window_size, len(translation_pairs))

        def consider_matches(start_index, end_index):
            nonlocal best_match_index, best_match_score, best_span_length
            for index in range(start_index, end_index):
                candidate = translation_pairs[index]
                candidate_original = candidate["normalized_original"]
                if not candidate_original:
                    continue
                for span_length in range(1, 4):
                    combined_text = _combined_lyric_text(aligned_lyrics, lyric_index, span_length)
                    if not combined_text:
                        continue
                    score = translation_match_score(combined_text, candidate_original)
                    if score > best_match_score or (
                        abs(score - best_match_score) < 1e-6 and span_length > best_span_length
                    ):
                        best_match_index = index
                        best_match_score = score
                        best_span_length = span_length

        consider_matches(pair_index, search_end)
        if best_match_index is None or best_match_score < 0.72:
            consider_matches(pair_index, len(translation_pairs))

        if best_match_index is None or best_match_score < 0.62:
            lyric_index += 1
            continue

        translation_text = translation_pairs[best_match_index]["translation"]
        translation_offset_ms = safe_int(
            translation_pairs[best_match_index].get("translation_offset_ms"), 0
        )
        span_end = min(lyric_index + best_span_length, len(aligned_lyrics))
        for index in range(lyric_index, span_end):
            aligned_lyrics[index]["translation"] = translation_text
            aligned_lyrics[index]["translation_offset_ms"] = translation_offset_ms
        pair_index = best_match_index + 1
        lyric_index = span_end

    return aligned_lyrics


def parse_manual_translation_block(raw_text, track_label=""):
    lines = [safe_strip(line) for line in raw_text.splitlines() if safe_strip(line)]
    if len(lines) < 2:
        return []

    track_norm = normalize_text(track_label)
    if len(lines) >= 2 and normalize_text(lines[0]) == normalize_text(lines[1]):
        lines = lines[2:]
    elif track_norm and similarity_score(track_norm, normalize_text(lines[0])) >= 0.72:
        lines = lines[1:]

    if len(lines) < 2:
        return []

    if len(lines) % 2 == 1:
        lines = lines[1:]

    translation_pairs = []
    for index in range(0, len(lines) - 1, 2):
        original_text = lines[index]
        translation_text = lines[index + 1]
        if not original_text or not translation_text:
            continue
        translation_pairs.append(
            {
                "original": original_text,
                "normalized_original": normalize_text(original_text),
                "translation": translation_text,
                "translation_offset_ms": 0,
            }
        )

    return translation_pairs


def normalize_translation_entries(entries):
    normalized_entries = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        original_text = safe_strip(entry.get("original"))
        translation_text = safe_strip(entry.get("translation"))
        if not original_text or not translation_text:
            continue
        normalized_entries.append(
            {
                "original": original_text,
                "normalized_original": normalize_text(original_text),
                "translation": translation_text,
                "translation_offset_ms": safe_int(entry.get("translation_offset_ms"), 0),
            }
        )
    return normalized_entries


def load_manual_translation_inputs():
    source_path = None
    for candidate in (MANUAL_TRANSLATIONS_PATH, LEGACY_MANUAL_TRANSLATIONS_PATH):
        if os.path.exists(candidate):
            source_path = candidate
            break

    if source_path is None:
        return {}

    try:
        with open(source_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    normalized_data = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        track_name = safe_strip(value.get("track_name"))
        artist_name = safe_strip(value.get("artist_name"))
        content = safe_strip(value.get("content"))
        synced_lyrics = safe_strip(value.get("synced_lyrics"))
        lyric_offset_ms = safe_int(value.get("lyric_offset_ms"), 0)
        translation_entries = normalize_translation_entries(value.get("translation_entries"))
        if not track_name or (
            not content and not synced_lyrics and lyric_offset_ms == 0 and not translation_entries
        ):
            continue
        normalized_key = key or build_translation_key(track_name, artist_name)
        normalized_data[normalized_key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": content,
            "synced_lyrics": synced_lyrics,
            "lyric_offset_ms": lyric_offset_ms,
            "translation_entries": translation_entries,
        }

    return normalized_data


def save_manual_translation_inputs(manual_translation_inputs):
    payload = {}
    for key, value in manual_translation_inputs.items():
        if not isinstance(value, dict):
            continue
        track_name = safe_strip(value.get("track_name"))
        artist_name = safe_strip(value.get("artist_name"))
        content = safe_strip(value.get("content"))
        synced_lyrics = safe_strip(value.get("synced_lyrics"))
        lyric_offset_ms = safe_int(value.get("lyric_offset_ms"), 0)
        translation_entries = normalize_translation_entries(value.get("translation_entries"))
        if not track_name or (
            not content and not synced_lyrics and lyric_offset_ms == 0 and not translation_entries
        ):
            continue
        payload[key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": content,
            "synced_lyrics": synced_lyrics,
            "lyric_offset_ms": lyric_offset_ms,
            "translation_entries": translation_entries,
        }

    with open(MANUAL_TRANSLATIONS_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def build_translation_key(track_name, artist_name):
    normalized_track = normalize_text(track_name)
    normalized_artist = normalize_text(artist_name)
    return f"{normalized_track}::{normalized_artist}"


def detect_chinese_song(lyrics_data):
    sample_text = "".join(
        safe_strip(lyric.get("text")) for lyric in lyrics_data if safe_strip(lyric.get("text"))
    )[:500]
    if not sample_text:
        return False

    has_japanese = bool(re.search(r"[\u3040-\u30ff]", sample_text))
    has_korean = bool(re.search(r"[\uac00-\ud7af]", sample_text))
    if has_japanese or has_korean:
        return False

    han_count = len(re.findall(r"[\u4e00-\u9fff]", sample_text))
    latin_count = len(re.findall(r"[A-Za-z]", sample_text))
    return han_count >= 8 and han_count >= latin_count * 2


class OverlayControl(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        button_style = """
            QPushButton {
                background: rgba(15, 23, 42, 0.78);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: rgba(30, 41, 59, 0.9);
            }
            """
        self.drag_button = QPushButton("移動")
        self.drag_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drag_button.setFixedHeight(24)
        self.drag_button.clicked.connect(self.overlay.toggle_drag_mode)
        self.drag_button.setStyleSheet(button_style)

        self.settings_button = QPushButton("設定")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setFixedHeight(24)
        self.settings_button.clicked.connect(self.overlay.toggle_settings_window)
        self.settings_button.setStyleSheet(button_style)

        self.translation_button = QPushButton("翻譯")
        self.translation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translation_button.setFixedHeight(24)
        self.translation_button.clicked.connect(self.overlay.toggle_translation_window)
        self.translation_button.setStyleSheet(button_style)

        self.close_button = QPushButton("關閉")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedHeight(24)
        self.close_button.clicked.connect(self.overlay.quit_app)
        self.close_button.setStyleSheet(button_style)

        layout.addWidget(self.drag_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.translation_button)
        layout.addWidget(self.close_button)
        self.apply_button_style("#0F172A")
        self.update_ui_texts()

    def sync_position(self):
        anchor_widget = self.overlay.control_anchor_widget()
        if anchor_widget is None:
            target_x = self.overlay.x() + self.overlay.width() - self.width() - 12
            target_y = self.overlay.y() + 12
        else:
            anchor_rect = anchor_widget.geometry()
            target_y = self.overlay.y() + anchor_rect.y() + int((anchor_rect.height() - self.height()) / 2)

        if anchor_widget is self.overlay.song_label and self.overlay.song_label.isVisible():
            available_width = max(self.overlay.width() - 48, 120)
            text = self.overlay.song_label.text()
            text_width = min(
                self.overlay.song_label.fontMetrics().horizontalAdvance(text), available_width
            )
            centered_text_left = self.overlay.x() + int((self.overlay.width() - text_width) / 2)
            target_x = centered_text_left + text_width + 8
            target_x = min(target_x, self.overlay.x() + self.overlay.width() - self.width() - 12)
            target_x = max(target_x, self.overlay.x() + 12)
        elif anchor_widget is not None:
            target_x = self.overlay.x() + self.overlay.width() - self.width() - 12

        target_x, target_y = _clamp_rect_to_screen(target_x, target_y, self.width(), self.height())
        self.move(target_x, target_y)
        return QRect(target_x, target_y, self.width(), self.height())

    def set_drag_enabled(self, enabled):
        self.drag_button.setText(
            self.overlay.tr("button_lock") if enabled else self.overlay.tr("button_move")
        )

    def update_ui_texts(self):
        self.set_drag_enabled(self.overlay.drag_enabled)
        self.settings_button.setText(self.overlay.tr("button_settings"))
        self.translation_button.setText(self.overlay.tr("button_translation"))
        self.close_button.setText(self.overlay.tr("button_close"))
        self._update_button_widths()

    def _update_button_widths(self):
        for button in (
            self.drag_button,
            self.settings_button,
            self.translation_button,
            self.close_button,
        ):
            target_width = max(button.fontMetrics().horizontalAdvance(button.text()) + 20, 56)
            button.setFixedWidth(target_width)

    def apply_button_style(self, color_hex):
        color = QColor(color_hex)
        foreground = "black" if color.lightness() > 150 else "white"
        hover = color.darker(115).name()
        style = f"""
            QPushButton {{
                background: {color_hex};
                color: {foreground};
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """
        self.drag_button.setStyleSheet(style)
        self.settings_button.setStyleSheet(style)
        self.translation_button.setStyleSheet(style)
        self.close_button.setStyleSheet(style)


class OverlaySettingsWindow(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("字幕設定")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(360, 520)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.color_label = QLabel()
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.overlay.pick_text_color)
        form.addRow(self.color_label, self.color_button)

        self.end_color_label = QLabel()
        self.end_color_button = QPushButton()
        self.end_color_button.clicked.connect(self.overlay.pick_end_text_color)
        form.addRow(self.end_color_label, self.end_color_button)

        self.button_color_label = QLabel()
        self.button_color_button = QPushButton()
        self.button_color_button.clicked.connect(self.overlay.pick_button_color)
        form.addRow(self.button_color_label, self.button_color_button)

        self.main_size = self._build_spinbox(14, 72, self.overlay.update_text_style)
        self.main_translation_size = self._build_spinbox(8, 40, self.overlay.update_text_style)
        self.subtitle_size = self._build_spinbox(10, 48, self.overlay.update_text_style)
        self.subtitle_translation_size = self._build_spinbox(8, 24, self.overlay.update_text_style)
        self.gap_song = self._build_spinbox(-20, 20, self.overlay.update_text_style)
        self.gap_primary = self._build_spinbox(-20, 20, self.overlay.update_text_style)
        self.gap_middle = self._build_spinbox(-24, 24, self.overlay.update_text_style)
        self.gap_subtitle = self._build_spinbox(-20, 20, self.overlay.update_text_style)

        self.show_song = self._build_checkbox("顯示歌名", self.overlay.update_text_style)
        self.show_main = self._build_checkbox("顯示主歌詞", self.overlay.update_text_style)
        self.show_subtitle = self._build_checkbox("顯示副歌詞", self.overlay.update_text_style)
        self.show_translation = self._build_checkbox("顯示翻譯", self.overlay.update_text_style)

        self.main_size_label = QLabel()
        self.main_translation_size_label = QLabel()
        self.subtitle_size_label = QLabel()
        self.subtitle_translation_size_label = QLabel()
        self.gap_song_label = QLabel()
        self.gap_primary_label = QLabel()
        self.gap_middle_label = QLabel()
        self.gap_subtitle_label = QLabel()

        form.addRow(self.main_size_label, self.main_size)
        form.addRow(self.main_translation_size_label, self.main_translation_size)
        form.addRow(self.subtitle_size_label, self.subtitle_size)
        form.addRow(self.subtitle_translation_size_label, self.subtitle_translation_size)
        form.addRow(self.gap_song_label, self.gap_song)
        form.addRow(self.gap_primary_label, self.gap_primary)
        form.addRow(self.gap_middle_label, self.gap_middle)
        form.addRow(self.gap_subtitle_label, self.gap_subtitle)
        form.addRow("", self.show_song)
        form.addRow("", self.show_main)
        form.addRow("", self.show_subtitle)
        form.addRow("", self.show_translation)
        layout.addLayout(form)

        spotify_form = QFormLayout()
        spotify_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        spotify_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        spotify_form.setHorizontalSpacing(10)
        spotify_form.setVerticalSpacing(8)

        self.spotify_client_id_label = QLabel()
        self.spotify_client_secret_label = QLabel()
        self.spotify_redirect_uri_label = QLabel()

        self.spotify_client_id = QLineEdit()
        self.spotify_client_secret = QLineEdit()
        self.spotify_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.spotify_redirect_uri = QLineEdit()

        spotify_form.addRow(self.spotify_client_id_label, self.spotify_client_id)
        spotify_form.addRow(self.spotify_client_secret_label, self.spotify_client_secret)
        spotify_form.addRow(self.spotify_redirect_uri_label, self.spotify_redirect_uri)
        layout.addLayout(spotify_form)

        self.language_button = QPushButton()
        self.language_button.clicked.connect(self.overlay.toggle_language)
        self.language_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        language_row = QHBoxLayout()
        language_row.setContentsMargins(0, 0, 0, 0)
        language_row.addWidget(self.language_button)
        language_row.addStretch(1)
        layout.addLayout(language_row)

        self.spotify_save_button = QPushButton("儲存 Spotify Key")
        self.spotify_save_button.clicked.connect(self.overlay.save_spotify_settings)
        layout.addWidget(self.spotify_save_button)

        self.spotify_clear_button = QPushButton("清除 Spotify Key")
        self.spotify_clear_button.clicked.connect(self.overlay.clear_spotify_settings)
        layout.addWidget(self.spotify_clear_button)

        self.spotify_status_label = QLabel("")
        self.spotify_status_label.setWordWrap(True)
        self.spotify_status_label.setStyleSheet("color: rgba(148, 163, 184, 0.9); font-size: 12px;")
        layout.addWidget(self.spotify_status_label)
        self.update_ui_texts()

    def _build_spinbox(self, minimum, maximum, on_change):
        spinbox = QSpinBox()
        spinbox.setRange(minimum, maximum)
        spinbox.valueChanged.connect(on_change)
        return spinbox

    def _build_checkbox(self, label, on_change):
        checkbox = QCheckBox(label)
        checkbox.setChecked(True)
        checkbox.stateChanged.connect(on_change)
        return checkbox

    def sync_position(self):
        target_x = self.overlay.control_window.x() - self.width() - 12
        target_y = self.overlay.control_window.y()
        target_x, target_y = _clamp_rect_to_screen(target_x, target_y, self.width(), self.height())
        self.move(target_x, target_y)

    def sync_from_overlay(self):
        config = self.overlay.text_style
        self.main_size.blockSignals(True)
        self.main_translation_size.blockSignals(True)
        self.subtitle_size.blockSignals(True)
        self.subtitle_translation_size.blockSignals(True)
        self.gap_song.blockSignals(True)
        self.gap_primary.blockSignals(True)
        self.gap_middle.blockSignals(True)
        self.gap_subtitle.blockSignals(True)
        self.show_song.blockSignals(True)
        self.show_main.blockSignals(True)
        self.show_subtitle.blockSignals(True)
        self.show_translation.blockSignals(True)

        self.main_size.setValue(config["main_size"])
        self.main_translation_size.setValue(config["main_translation_size"])
        self.subtitle_size.setValue(config["subtitle_size"])
        self.subtitle_translation_size.setValue(config["subtitle_translation_size"])
        self.gap_song.setValue(config["gap_song"])
        self.gap_primary.setValue(config["gap_primary"])
        self.gap_middle.setValue(config["gap_middle"])
        self.gap_subtitle.setValue(config["gap_subtitle"])
        self.show_song.setChecked(config["show_song"])
        self.show_main.setChecked(config["show_main"])
        self.show_subtitle.setChecked(config["show_subtitle"])
        self.show_translation.setChecked(config["show_translation"])
        spotify_settings = self.overlay.spotify_settings
        self.spotify_client_id.setText(spotify_settings["client_id"])
        self.spotify_client_secret.setText(spotify_settings["client_secret"])
        self.spotify_redirect_uri.setText(spotify_settings["redirect_uri"])

        self.main_size.blockSignals(False)
        self.main_translation_size.blockSignals(False)
        self.subtitle_size.blockSignals(False)
        self.subtitle_translation_size.blockSignals(False)
        self.gap_song.blockSignals(False)
        self.gap_primary.blockSignals(False)
        self.gap_middle.blockSignals(False)
        self.gap_subtitle.blockSignals(False)
        self.show_song.blockSignals(False)
        self.show_main.blockSignals(False)
        self.show_subtitle.blockSignals(False)
        self.show_translation.blockSignals(False)
        self.set_color_preview(config["text_color"])
        self.set_end_color_preview(config["accent_color"])
        self.set_button_color_preview(config["button_color"])

    def set_spotify_status(self, message, error=False):
        color = "rgba(248, 113, 113, 0.95)" if error else "rgba(148, 163, 184, 0.9)"
        self.spotify_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.spotify_status_label.setText(message)

    def update_ui_texts(self):
        self.setWindowTitle(self.overlay.tr("settings_window_title"))
        self.color_label.setText(self.overlay.tr("field_text_color"))
        self.end_color_label.setText(self.overlay.tr("field_end_color"))
        self.button_color_label.setText(self.overlay.tr("field_button_color"))
        self.main_size_label.setText(self.overlay.tr("field_main_size"))
        self.main_translation_size_label.setText(self.overlay.tr("field_main_translation_size"))
        self.subtitle_size_label.setText(self.overlay.tr("field_subtitle_size"))
        self.subtitle_translation_size_label.setText(self.overlay.tr("field_subtitle_translation_size"))
        self.gap_song_label.setText(self.overlay.tr("field_gap_song"))
        self.gap_primary_label.setText(self.overlay.tr("field_gap_primary"))
        self.gap_middle_label.setText(self.overlay.tr("field_gap_middle"))
        self.gap_subtitle_label.setText(self.overlay.tr("field_gap_subtitle"))
        self.show_song.setText(self.overlay.tr("field_show_song"))
        self.show_main.setText(self.overlay.tr("field_show_main"))
        self.show_subtitle.setText(self.overlay.tr("field_show_subtitle"))
        self.show_translation.setText(self.overlay.tr("field_show_translation"))
        self.spotify_client_id_label.setText(self.overlay.tr("field_client_id"))
        self.spotify_client_secret_label.setText(self.overlay.tr("field_client_secret"))
        self.spotify_redirect_uri_label.setText(self.overlay.tr("field_redirect_uri"))
        self.language_button.setText(self.overlay.tr("button_language"))
        language_width = self.language_button.fontMetrics().horizontalAdvance(
            self.language_button.text()
        )
        target_width = language_width + 32
        self.language_button.setMinimumWidth(target_width)
        self.language_button.setMaximumWidth(target_width)
        self.spotify_save_button.setText(self.overlay.tr("button_save_spotify"))
        self.spotify_clear_button.setText(self.overlay.tr("button_clear_spotify"))

    def set_color_preview(self, color_hex):
        self._apply_preview_style(self.color_button, color_hex)

    def set_end_color_preview(self, color_hex):
        self._apply_preview_style(self.end_color_button, color_hex)

    def set_button_color_preview(self, color_hex):
        self._apply_preview_style(self.button_color_button, color_hex)

    def _apply_preview_style(self, button, color_hex):
        button.setText(color_hex.upper())
        button.setStyleSheet(
            f"""
            QPushButton {{
                background: {color_hex};
                color: {'black' if QColor(color_hex).lightness() > 150 else 'white'};
                border: 1px solid rgba(15, 23, 42, 0.2);
                border-radius: 8px;
                padding: 5px 8px;
                font-weight: 600;
            }}
            """
        )


class OverlayTranslationWindow(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("翻譯字幕")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(420, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.track_name_label = QLabel()
        self.artist_name_label = QLabel()
        self.track_name_input = QLineEdit()
        self.artist_name_input = QLineEdit()
        form.addRow(self.track_name_label, self.track_name_input)
        form.addRow(self.artist_name_label, self.artist_name_input)

        self.hint_label = QLabel("每兩行一組：原文 / 翻譯。開頭重複歌名會自動略過。")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: rgba(226, 232, 240, 0.82); font-size: 12px;")

        offset_form = QFormLayout()
        offset_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        offset_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        offset_form.setHorizontalSpacing(10)
        offset_form.setVerticalSpacing(8)

        self.timing_song_label = QLabel()
        self.timing_song_value = QLabel("")
        self.timing_song_value.setWordWrap(True)
        self.timing_song_value.setStyleSheet("color: rgba(226, 232, 240, 0.82);")

        self.lyric_offset_label = QLabel()
        self.lyric_offset = QSpinBox()
        self.lyric_offset.setRange(-5000, 5000)
        self.lyric_offset.setSingleStep(10)
        self.lyric_offset.valueChanged.connect(self.overlay.update_current_track_lyric_offset)

        offset_button_row = QHBoxLayout()
        offset_button_row.setContentsMargins(0, 0, 0, 0)
        offset_button_row.setSpacing(6)

        self.offset_minus_large = QPushButton("-100")
        self.offset_minus_small = QPushButton("-10")
        self.offset_reset_button = QPushButton("0")
        self.offset_plus_small = QPushButton("+10")
        self.offset_plus_large = QPushButton("+100")

        self.offset_minus_large.clicked.connect(lambda: self.overlay.adjust_current_track_lyric_offset(-100))
        self.offset_minus_small.clicked.connect(lambda: self.overlay.adjust_current_track_lyric_offset(-10))
        self.offset_reset_button.clicked.connect(self.overlay.reset_current_track_lyric_offset)
        self.offset_plus_small.clicked.connect(lambda: self.overlay.adjust_current_track_lyric_offset(10))
        self.offset_plus_large.clicked.connect(lambda: self.overlay.adjust_current_track_lyric_offset(100))

        offset_button_row.addWidget(self.offset_minus_large)
        offset_button_row.addWidget(self.offset_minus_small)
        offset_button_row.addWidget(self.offset_reset_button)
        offset_button_row.addWidget(self.offset_plus_small)
        offset_button_row.addWidget(self.offset_plus_large)

        offset_value_row = QHBoxLayout()
        offset_value_row.setContentsMargins(0, 0, 0, 0)
        offset_value_row.setSpacing(8)
        offset_value_row.addWidget(self.lyric_offset)
        offset_value_row.addLayout(offset_button_row)
        offset_value_row.addStretch(1)

        offset_form.addRow(self.timing_song_label, self.timing_song_value)
        offset_form.addRow(self.lyric_offset_label, offset_value_row)

        self.line_editor_hint = QLabel("逐句翻譯與偏移")
        self.line_editor_hint.setStyleSheet("color: rgba(226, 232, 240, 0.82); font-size: 12px;")

        self.line_scroll = QScrollArea()
        self.line_scroll.setWidgetResizable(True)
        self.line_scroll.setMinimumHeight(220)
        self.line_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 8px; }"
        )
        self.line_scroll_content = QWidget()
        self.line_scroll_layout = QVBoxLayout(self.line_scroll_content)
        self.line_scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.line_scroll_layout.setSpacing(10)
        self.line_scroll.setWidget(self.line_scroll_content)
        self.line_rows = []

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "刀馬 刀馬 (DJ卡點版) - 布卡萬\n刀馬 刀馬 (DJ卡點版) - 布卡萬\nOlha só minha ponto 30\n看看我這30口徑"
        )

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: rgba(148, 163, 184, 0.9); font-size: 12px;")

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.apply_button = QPushButton("套用")
        self.apply_button.clicked.connect(self.overlay.apply_manual_translations)
        self.clear_button = QPushButton("清除")
        self.clear_button.clicked.connect(self.overlay.clear_manual_translations)

        self.load_button = QPushButton("讀取")
        self.load_button.clicked.connect(self.overlay.load_translation_for_inputs)

        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.load_button)

        layout.addLayout(form)
        layout.addWidget(self.hint_label)
        layout.addLayout(offset_form)
        layout.addWidget(self.line_editor_hint)
        layout.addWidget(self.line_scroll)
        layout.addWidget(self.editor)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)
        self.update_ui_texts()

    def sync_position(self):
        target_x = self.overlay.control_window.x() - self.width() - 12
        target_y = self.overlay.control_window.y() + self.overlay.control_window.height() + 12
        target_x, target_y = _clamp_rect_to_screen(target_x, target_y, self.width(), self.height())
        self.move(target_x, target_y)

    def set_status(self, message, error=False):
        color = "rgba(248, 113, 113, 0.95)" if error else "rgba(148, 163, 184, 0.9)"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_label.setText(message)

    def sync_from_overlay(self):
        self.lyric_offset.blockSignals(True)
        self.lyric_offset.setValue(self.overlay.current_track_lyric_offset_ms)
        self.lyric_offset.blockSignals(False)
        self.timing_song_value.setText(self.overlay.current_track_display_name())
        self.track_name_input.setText(self.overlay.current_track_name)
        self.artist_name_input.setText(self.overlay.current_track_artist)
        self.set_line_entries(self.overlay.current_song_translation_editor_entries())
        self.editor.blockSignals(True)
        self.editor.setPlainText(
            self.overlay.translation_content_for_key(self.overlay.current_track_key)
        )
        self.editor.blockSignals(False)

    def update_ui_texts(self):
        self.setWindowTitle(self.overlay.tr("translation_window_title"))
        self.track_name_label.setText(self.overlay.tr("field_track_name"))
        self.artist_name_label.setText(self.overlay.tr("field_artist_name"))
        self.timing_song_label.setText(self.overlay.tr("field_timing_song"))
        self.lyric_offset_label.setText(self.overlay.tr("field_lyric_offset"))
        self.timing_song_value.setText(self.overlay.current_track_display_name())
        self.line_editor_hint.setText(self.overlay.tr("translation_window_title"))
        self.hint_label.setText(self.overlay.tr("translation_hint"))
        self.apply_button.setText(self.overlay.tr("button_apply"))
        self.clear_button.setText(self.overlay.tr("button_clear"))
        self.load_button.setText(self.overlay.tr("button_load"))

    def clear_line_entries(self):
        while self.line_scroll_layout.count():
            item = self.line_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.line_rows = []

    def set_line_entries(self, entries):
        self.clear_line_entries()
        for entry in entries or []:
            self._append_line_entry(entry)
        self.line_scroll_layout.addStretch(1)

    def line_entries(self):
        entries = []
        for row in self.line_rows:
            translation_text = safe_strip(row["translation_input"].text())
            if not translation_text:
                continue
            entries.append(
                {
                    "original": row["original_text"],
                    "normalized_original": normalize_text(row["original_text"]),
                    "translation": translation_text,
                    "translation_offset_ms": row["offset_spinbox"].value(),
                }
            )
        return entries

    def _append_line_entry(self, entry):
        row_frame = QFrame()
        row_frame.setFrameShape(QFrame.Shape.StyledPanel)
        row_frame.setStyleSheet(
            "QFrame { border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 8px; background: rgba(15, 23, 42, 0.12); }"
        )
        row_layout = QVBoxLayout(row_frame)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setSpacing(8)

        original_label = QLabel(safe_strip(entry.get("original")))
        original_label.setWordWrap(True)
        original_label.setStyleSheet("font-weight: 600; color: rgba(248, 250, 252, 0.95);")

        offset_row = QHBoxLayout()
        offset_row.setContentsMargins(0, 0, 0, 0)
        offset_row.setSpacing(6)
        offset_label = QLabel("ms")
        offset_spinbox = QSpinBox()
        offset_spinbox.setRange(-5000, 5000)
        offset_spinbox.setSingleStep(10)
        offset_spinbox.setValue(safe_int(entry.get("translation_offset_ms"), 0))
        minus_large = QPushButton("-100")
        minus_small = QPushButton("-10")
        reset_button = QPushButton("0")
        plus_small = QPushButton("+10")
        plus_large = QPushButton("+100")

        minus_large.clicked.connect(lambda _=False, box=offset_spinbox: box.setValue(box.value() - 100))
        minus_small.clicked.connect(lambda _=False, box=offset_spinbox: box.setValue(box.value() - 10))
        reset_button.clicked.connect(lambda _=False, box=offset_spinbox: box.setValue(0))
        plus_small.clicked.connect(lambda _=False, box=offset_spinbox: box.setValue(box.value() + 10))
        plus_large.clicked.connect(lambda _=False, box=offset_spinbox: box.setValue(box.value() + 100))

        offset_row.addWidget(offset_label)
        offset_row.addWidget(offset_spinbox)
        offset_row.addWidget(minus_large)
        offset_row.addWidget(minus_small)
        offset_row.addWidget(reset_button)
        offset_row.addWidget(plus_small)
        offset_row.addWidget(plus_large)
        offset_row.addStretch(1)

        translation_input = QLineEdit()
        translation_input.setText(safe_strip(entry.get("translation")))

        row_layout.addWidget(original_label)
        row_layout.addLayout(offset_row)
        row_layout.addWidget(translation_input)

        self.line_scroll_layout.addWidget(row_frame)
        self.line_rows.append(
            {
                "original_text": safe_strip(entry.get("original")),
                "translation_input": translation_input,
                "offset_spinbox": offset_spinbox,
            }
        )


class LyricsOverlay(QWidget):

    def __init__(self):
        super().__init__()
        self.app_settings = load_app_settings()
        self.ui_language = str(self.app_settings.get("ui_language", "zh")).strip().lower()
        if self.ui_language not in UI_STRINGS:
            self.ui_language = "zh"
        self.spotify_settings = resolve_spotify_settings(self.app_settings)
        self.spotify = create_spotify_client(self.spotify_settings)
        self.current_track_id = None
        self.current_track_key = None
        self.current_track_artist = ""
        self.current_track_name = ""
        self.base_lyrics = []
        self.cached_lyrics = []
        self.manual_translation_inputs = load_manual_translation_inputs()
        self.drag_position = QPoint()
        self.drag_enabled = False
        self.current_main_text = ""
        self.is_playing = False
        self.last_track_name = "Spotify Floating Overlay"
        self.last_progress_ms = 0
        self.last_progress_timestamp = time.monotonic()
        self.current_track_lyric_offset_ms = 0
        self.text_style = merge_saved_text_style(self.app_settings.get("text_style"))
        self.current_line_progress = 0.0

        self.setWindowTitle("Spotify Floating Overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(960, 280)

        self._build_ui()
        self._bind_drag_targets()
        self.control_window = OverlayControl(self)
        self.settings_window = OverlaySettingsWindow(self)
        self.translation_window = OverlayTranslationWindow(self)
        self.settings_window.sync_from_overlay()
        self.update_ui_texts()
        self.update_text_style()
        self._apply_window_mode()

        QShortcut(QKeySequence("Escape"), self, activated=self.close)

        self.spotify_timer = QTimer(self)
        self.spotify_timer.timeout.connect(self.refresh)
        self.spotify_timer.start(POLL_INTERVAL_MS)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.animate_current_line)
        self.animation_timer.start(ANIMATION_INTERVAL_MS)

        self.control_hover_timer = QTimer(self)
        self.control_hover_timer.timeout.connect(self.update_control_visibility)
        self.control_hover_timer.start(120)

    def _base_window_flags(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if not self.drag_enabled:
            flags |= WINDOW_TRANSPARENT_FOR_INPUT
        return flags

    def _apply_window_mode(self):
        current_position = self.pos()
        self.setWindowFlags(self._base_window_flags())
        self.show()
        self.move(current_position)
        self.control_window.set_drag_enabled(self.drag_enabled)
        self.control_window.sync_position()
        self.update_control_visibility()
        self._ensure_on_top(force_front=True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(0)

        self.song_label = QLabel("Spotify Floating Overlay")
        self.song_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.song_label.setFont(QFont("Helvetica", 14, QFont.Weight.DemiBold))
        self.song_label.setStyleSheet("color: rgba(199, 210, 254, 0.92);")
        self.song_label.setContentsMargins(0, 0, 0, 0)

        self.current_lyric_label = QLabel(self.tr("spotify_waiting_message"))
        self.current_lyric_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_lyric_label.setTextFormat(Qt.TextFormat.RichText)
        self.current_lyric_label.setWordWrap(True)
        self.current_lyric_label.setContentsMargins(0, 0, 0, 0)

        self.current_translation_label = QLabel("")
        self.current_translation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_translation_label.setTextFormat(Qt.TextFormat.RichText)
        self.current_translation_label.setWordWrap(True)
        self.current_translation_label.setContentsMargins(0, 0, 0, 0)

        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setContentsMargins(0, 0, 0, 0)

        self.subtitle_translation_label = QLabel("")
        self.subtitle_translation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_translation_label.setWordWrap(True)
        self.subtitle_translation_label.setContentsMargins(0, 0, 0, 0)

        self.primary_gap = QWidget()
        self.middle_gap = QWidget()
        self.subtitle_gap = QWidget()
        self.song_gap = QWidget()

        layout.addWidget(self.song_label)
        layout.addWidget(self.song_gap)
        layout.addWidget(self.current_lyric_label)
        layout.addWidget(self.primary_gap)
        layout.addWidget(self.current_translation_label)
        layout.addWidget(self.middle_gap)
        layout.addWidget(self.subtitle_label)
        layout.addWidget(self.subtitle_gap)
        layout.addWidget(self.subtitle_translation_label)
        layout.addStretch(1)

    def _bind_drag_targets(self):
        for widget in (
            self,
            self.song_label,
            self.current_lyric_label,
            self.current_translation_label,
            self.subtitle_label,
            self.subtitle_translation_label,
        ):
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if not self.drag_enabled:
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            return True

        if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            return True

        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        width = max(self.width() - 48, 320)
        self.song_label.setMaximumWidth(width)
        self.current_lyric_label.setMaximumWidth(width)
        self.current_translation_label.setMaximumWidth(width)
        self.subtitle_label.setMaximumWidth(width)
        self.subtitle_translation_label.setMaximumWidth(width)
        if hasattr(self, "control_window"):
            self.control_window.sync_position()
            self.update_control_visibility()
        if hasattr(self, "settings_window") and self.settings_window.isVisible():
            self.settings_window.sync_position()
        if hasattr(self, "translation_window") and self.translation_window.isVisible():
            self.translation_window.sync_position()
        super().resizeEvent(event)

    def moveEvent(self, event):
        if hasattr(self, "control_window"):
            self.control_window.sync_position()
            self.update_control_visibility()
        if hasattr(self, "settings_window") and self.settings_window.isVisible():
            self.settings_window.sync_position()
        if hasattr(self, "translation_window") and self.translation_window.isVisible():
            self.translation_window.sync_position()
        super().moveEvent(event)

    def _find_active_lines(self, progress_ms):
        if not self.cached_lyrics:
            return self.tr("no_synced_lyrics_found"), "", "", "", 0.0

        current_line = "..."
        current_translation = ""
        next_line = ""
        next_translation = ""
        current_progress = 0.0

        for index, lyric in enumerate(self.cached_lyrics):
            start_time = max(lyric["time"] + self.current_track_lyric_offset_ms, 0)
            if progress_ms >= start_time:
                current_line = lyric["text"] or "..."
                end_time = (
                    max(self.cached_lyrics[index + 1]["time"] + self.current_track_lyric_offset_ms, 0)
                    if index + 1 < len(self.cached_lyrics)
                    else start_time + 4000
                )
                duration = max(end_time - start_time, 1)
                current_progress = min(max((progress_ms - start_time) / duration, 0.0), 1.0)
                translation_start = start_time + safe_int(lyric.get("translation_offset_ms"), 0)
                if progress_ms >= translation_start:
                    current_translation = lyric.get("translation", "")
                else:
                    current_translation = ""
                if index + 1 < len(self.cached_lyrics):
                    next_line = self.cached_lyrics[index + 1]["text"] or ""
                    next_line_start = max(
                        self.cached_lyrics[index + 1]["time"] + self.current_track_lyric_offset_ms, 0
                    )
                    next_translation_start = next_line_start + safe_int(
                        self.cached_lyrics[index + 1].get("translation_offset_ms"), 0
                    )
                    if progress_ms >= next_translation_start:
                        next_translation = self.cached_lyrics[index + 1].get("translation", "")
                    else:
                        next_translation = ""
            else:
                if current_line == "...":
                    next_line = lyric.get("text", "")
                    translation_start = start_time + safe_int(lyric.get("translation_offset_ms"), 0)
                    if progress_ms >= translation_start:
                        next_translation = lyric.get("translation", "")
                    else:
                        next_translation = ""
                break

        return current_line, current_translation, next_line, next_translation, current_progress

    def _estimated_progress_ms(self):
        if not self.is_playing:
            return max(self.last_progress_ms, 0)

        elapsed_ms = int((time.monotonic() - self.last_progress_timestamp) * 1000)
        return max(self.last_progress_ms + elapsed_ms, 0)

    def _log_terminal_debug(self, progress_ms, current_line, next_line):
        if not self.current_track_name:
            return

        offset_ms = self.current_track_lyric_offset_ms
        active_index = None
        current_start = None
        next_start = None

        for index, lyric in enumerate(self.cached_lyrics):
            lyric_start = max(lyric["time"] + offset_ms, 0)
            if progress_ms >= lyric_start:
                active_index = index
                current_start = lyric_start
                if index + 1 < len(self.cached_lyrics):
                    next_start = max(self.cached_lyrics[index + 1]["time"] + offset_ms, 0)
            else:
                if current_start is None:
                    next_start = lyric_start
                break

        current_base = self.cached_lyrics[active_index]["time"] if active_index is not None else None
        next_base = (
            self.cached_lyrics[active_index + 1]["time"]
            if active_index is not None and active_index + 1 < len(self.cached_lyrics)
            else None
        )
        log_debug(
            'track="{track}" artist="{artist}" spotify_ms={spotify_ms} est_ms={est_ms} '
            'global_offset_ms={offset_ms} current_idx={current_idx} current_base_ms={current_base} '
            'current_effective_ms={current_effective} next_base_ms={next_base} '
            'next_effective_ms={next_effective} current_line="{current_line}" next_line="{next_line}"'.format(
                track=self.current_track_name,
                artist=self.current_track_artist,
                spotify_ms=self.last_progress_ms,
                est_ms=progress_ms,
                offset_ms=offset_ms,
                current_idx=active_index,
                current_base=current_base,
                current_effective=current_start,
                next_base=next_base,
                next_effective=next_start,
                current_line=safe_strip(current_line),
                next_line=safe_strip(next_line),
            )
        )

    def _ensure_on_top(self, force_front=False):
        _configure_macos_panel(self, accepts_input=self.drag_enabled, force_front=force_front)
        if self.control_window.isVisible():
            _configure_macos_panel(self.control_window, accepts_input=True, force_front=force_front)
        if self.settings_window.isVisible():
            _configure_macos_panel(self.settings_window, accepts_input=True, force_front=force_front)
        if self.translation_window.isVisible():
            _configure_macos_panel(self.translation_window, accepts_input=True, force_front=force_front)

    def control_anchor_widget(self):
        candidates = (
            (self.song_label, safe_strip(self.song_label.text())),
            (self.current_lyric_label, safe_strip(self.current_main_text)),
            (
                self.current_translation_label,
                safe_strip(self.current_translation_label.property("plain_text")),
            ),
            (self.subtitle_label, safe_strip(self.subtitle_label.text())),
            (self.subtitle_translation_label, safe_strip(self.subtitle_translation_label.text())),
        )
        for widget, content in candidates:
            if widget.isVisible() and content:
                return widget
        return None

    def toggle_drag_mode(self):
        self.drag_enabled = not self.drag_enabled
        self._apply_window_mode()

    def quit_app(self):
        app = QApplication.instance()
        if app is not None:
            app.quit()
            return
        self.close()

    def tr(self, key, **kwargs):
        template = UI_STRINGS.get(self.ui_language, UI_STRINGS["zh"]).get(
            key, UI_STRINGS["zh"].get(key, key)
        )
        return template.format(**kwargs) if kwargs else template

    def toggle_language(self):
        self.ui_language = "en" if self.ui_language == "zh" else "zh"
        self.app_settings["ui_language"] = self.ui_language
        save_app_settings(self.app_settings)
        self.update_ui_texts()

    def update_ui_texts(self):
        self.control_window.update_ui_texts()
        self.settings_window.update_ui_texts()
        self.translation_window.update_ui_texts()

        if self.spotify is None:
            self._set_labels(
                self.tr("spotify_unconfigured_title"),
                self.tr("spotify_unconfigured_message"),
                "",
                "",
                "",
                0.0,
            )
        elif not self.is_playing and not self.current_track_id:
            self._set_labels(
                self.tr("spotify_paused_title"),
                self.tr("spotify_waiting_message"),
                "",
                "",
                "",
                0.0,
            )

    def save_spotify_settings(self):
        client_id = self.settings_window.spotify_client_id.text().strip()
        client_secret = self.settings_window.spotify_client_secret.text().strip()
        redirect_uri = self.settings_window.spotify_redirect_uri.text().strip()
        if not client_id or not client_secret or not redirect_uri:
            self.settings_window.set_spotify_status(self.tr("spotify_key_empty"), error=True)
            return

        previous_settings = dict(self.spotify_settings)
        self.spotify_settings = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        self.app_settings["spotify_client_id"] = client_id
        self.app_settings["spotify_client_secret"] = client_secret
        self.app_settings["spotify_redirect_uri"] = redirect_uri

        try:
            if previous_settings != self.spotify_settings and os.path.exists(SPOTIFY_CACHE_PATH):
                os.remove(SPOTIFY_CACHE_PATH)
            save_app_settings(self.app_settings)
            self.spotify = create_spotify_client(self.spotify_settings)
            if self.spotify is None:
                self.settings_window.set_spotify_status(
                    self.tr("spotify_key_prompt"),
                    error=True,
                )
                return
            self.current_track_id = None
            self.settings_window.set_spotify_status(self.tr("spotify_key_saved"))
        except Exception as exc:
            self.spotify = None
            self.settings_window.set_spotify_status(
                self.tr("spotify_save_failed", error=exc), error=True
            )

    def clear_spotify_settings(self):
        self.app_settings.pop("spotify_client_id", None)
        self.app_settings.pop("spotify_client_secret", None)
        self.app_settings.pop("spotify_redirect_uri", None)
        self.spotify_settings = resolve_spotify_settings(self.app_settings)
        self.spotify = None
        self.current_track_id = None

        if os.path.exists(APP_SETTINGS_PATH):
            save_app_settings(self.app_settings)
        if os.path.exists(SPOTIFY_CACHE_PATH):
            os.remove(SPOTIFY_CACHE_PATH)

        self.settings_window.spotify_client_id.clear()
        self.settings_window.spotify_client_secret.clear()
        self.settings_window.spotify_redirect_uri.setText(DEFAULT_REDIRECT_URI)
        self.settings_window.set_spotify_status(self.tr("spotify_key_cleared"))
        self.update_ui_texts()

    def toggle_settings_window(self):
        if self.settings_window.isVisible():
            self.settings_window.hide()
            self.update_control_visibility()
            return

        self.settings_window.sync_from_overlay()
        self.settings_window.set_spotify_status("")
        self.settings_window.show()
        self.settings_window.sync_position()
        self._ensure_on_top(force_front=True)
        self.update_control_visibility()

    def toggle_translation_window(self):
        if self.translation_window.isVisible():
            self.translation_window.hide()
            self.update_control_visibility()
            return

        self.translation_window.sync_from_overlay()
        self.translation_window.set_status("")
        self.translation_window.show()
        self.translation_window.sync_position()
        self._ensure_on_top(force_front=True)
        self.update_control_visibility()

    def update_control_visibility(self):
        if not hasattr(self, "control_window"):
            return

        target_rect = self.control_window.sync_position()
        cursor_pos = QCursor.pos()
        hover_rect = QRect(
            target_rect.x() - 8,
            target_rect.y() - 6,
            target_rect.width() + 16,
            target_rect.height() + 12,
        )

        should_show = hover_rect.contains(cursor_pos)
        should_show = should_show or self.control_window.geometry().contains(cursor_pos)
        should_show = should_show or self.settings_window.isVisible()
        should_show = should_show or self.translation_window.isVisible()

        if should_show:
            if not self.control_window.isVisible():
                self.control_window.show()
            self._ensure_on_top(force_front=True)
            return

        self.control_window.hide()

    def pick_text_color(self):
        selected_color = QColorDialog.getColor(
            QColor(self.text_style["text_color"]),
            self.settings_window,
            self.tr("dialog_pick_text_color"),
        )
        if not selected_color.isValid():
            return

        self.text_style["text_color"] = selected_color.name().upper()
        self.update_text_style()
        self.settings_window.set_color_preview(self.text_style["text_color"])

    def pick_end_text_color(self):
        selected_color = QColorDialog.getColor(
            QColor(self.text_style["accent_color"]),
            self.settings_window,
            self.tr("dialog_pick_end_color"),
        )
        if not selected_color.isValid():
            return

        self.text_style["accent_color"] = selected_color.name().upper()
        self.update_text_style()
        self.settings_window.set_end_color_preview(self.text_style["accent_color"])

    def pick_button_color(self):
        selected_color = QColorDialog.getColor(
            QColor(self.text_style["button_color"]),
            self.settings_window,
            self.tr("dialog_pick_button_color"),
        )
        if not selected_color.isValid():
            return

        self.text_style["button_color"] = selected_color.name().upper()
        self.control_window.apply_button_style(self.text_style["button_color"])
        self.settings_window.set_button_color_preview(self.text_style["button_color"])
        self._save_text_style_settings()

    def update_text_style(self):
        if hasattr(self, "settings_window"):
            self.text_style["main_size"] = self.settings_window.main_size.value()
            self.text_style["main_translation_size"] = self.settings_window.main_translation_size.value()
            self.text_style["subtitle_size"] = self.settings_window.subtitle_size.value()
            self.text_style["subtitle_translation_size"] = self.settings_window.subtitle_translation_size.value()
            self.text_style["gap_song"] = self.settings_window.gap_song.value()
            self.text_style["gap_primary"] = self.settings_window.gap_primary.value()
            self.text_style["gap_middle"] = self.settings_window.gap_middle.value()
            self.text_style["gap_subtitle"] = self.settings_window.gap_subtitle.value()
            self.text_style["show_song"] = self.settings_window.show_song.isChecked()
            self.text_style["show_main"] = self.settings_window.show_main.isChecked()
            self.text_style["show_subtitle"] = self.settings_window.show_subtitle.isChecked()
            self.text_style["show_translation"] = self.settings_window.show_translation.isChecked()

        color = QColor(self.text_style["text_color"])
        rgb = f"{color.red()}, {color.green()}, {color.blue()}"
        self.current_translation_label.setStyleSheet(
            f"font-size: {self.text_style['main_translation_size']}px; font-weight: 500;"
        )
        self.subtitle_label.setStyleSheet(
            f"color: rgba({rgb}, 0.82); font-size: {self.text_style['subtitle_size']}px; font-weight: 600;"
        )
        self.subtitle_translation_label.setStyleSheet(
            f"color: rgba({rgb}, 0.68); font-size: {self.text_style['subtitle_translation_size']}px; font-weight: 500;"
        )
        self.song_gap.setFixedHeight(max(self.text_style["gap_song"], 0))
        self.primary_gap.setFixedHeight(max(self.text_style["gap_primary"], 0))
        self.middle_gap.setFixedHeight(max(self.text_style["gap_middle"], 0))
        self.subtitle_gap.setFixedHeight(max(self.text_style["gap_subtitle"], 0))
        self.song_label.setContentsMargins(0, 0, 0, min(self.text_style["gap_song"], 0))
        self.current_lyric_label.setContentsMargins(0, min(self.text_style["gap_song"], 0), 0, 0)
        self.current_translation_label.setContentsMargins(0, min(self.text_style["gap_primary"], 0), 0, 0)
        self.subtitle_label.setContentsMargins(0, min(self.text_style["gap_middle"], 0), 0, 0)
        self.subtitle_translation_label.setContentsMargins(0, min(self.text_style["gap_subtitle"], 0), 0, 0)
        self._apply_line_visibility()
        if hasattr(self, "control_window"):
            self.control_window.apply_button_style(self.text_style["button_color"])
        self._apply_main_lyric_color(self.current_line_progress)
        self._save_text_style_settings()

    def _save_text_style_settings(self):
        self.app_settings["text_style"] = dict(self.text_style)
        save_app_settings(self.app_settings)

    def _apply_line_visibility(self):
        show_song = self.text_style["show_song"]
        show_main = self.text_style["show_main"]
        show_translation = self.text_style["show_translation"]
        show_subtitle = self.text_style["show_subtitle"]

        show_main_translation = show_translation
        show_subtitle_translation = show_translation and show_subtitle

        self.song_label.setVisible(show_song)
        self.current_lyric_label.setVisible(show_main)
        self.current_translation_label.setVisible(show_main_translation)
        self.subtitle_label.setVisible(show_subtitle)
        self.subtitle_translation_label.setVisible(show_subtitle_translation)

        self.song_gap.setVisible(show_song and any(
            (show_main, show_main_translation, show_subtitle, show_subtitle_translation)
        ))
        self.primary_gap.setVisible(show_main and show_main_translation)
        self.middle_gap.setVisible((show_main or show_main_translation) and show_subtitle)
        self.subtitle_gap.setVisible(show_subtitle and show_subtitle_translation)

        if hasattr(self, "control_window"):
            self.control_window.sync_position()

    def _mix_colors(self, start_color, end_color, ratio):
        ratio = min(max(ratio, 0.0), 1.0)
        red = round(start_color.red() + (end_color.red() - start_color.red()) * ratio)
        green = round(start_color.green() + (end_color.green() - start_color.green()) * ratio)
        blue = round(start_color.blue() + (end_color.blue() - start_color.blue()) * ratio)
        return QColor(red, green, blue)

    def _render_progressive_text(self, text, progress_ratio):
        if not text:
            return ""

        start_color = QColor(self.text_style["text_color"])
        end_color = QColor(self.text_style["accent_color"])
        color_steps = sum(1 for char in text if not char.isspace())
        if color_steps <= 0:
            return html.escape(text)

        total_progress = min(max(progress_ratio, 0.0), 1.0) * color_steps
        colored_index = 0
        rendered_parts = []

        for char in text:
            if char == "\n":
                rendered_parts.append("<br/>")
                continue

            if char.isspace():
                rendered_parts.append("&nbsp;")
                continue

            local_progress = min(max(total_progress - colored_index, 0.0), 1.0)
            mixed_color = self._mix_colors(start_color, end_color, local_progress)
            rendered_parts.append(
                f'<span style="color: {mixed_color.name()};">{html.escape(char)}</span>'
            )
            colored_index += 1

        return "".join(rendered_parts)

    def _apply_main_lyric_color(self, progress_ratio):
        self.current_line_progress = progress_ratio
        self.current_lyric_label.setStyleSheet(
            f"font-size: {self.text_style['main_size']}px; font-weight: 700;"
        )
        self.current_lyric_label.setText(
            self._render_progressive_text(self.current_main_text, progress_ratio)
        )
        self.current_translation_label.setText(
            self._render_progressive_text(
                self.current_translation_label.property("plain_text") or "",
                progress_ratio,
            )
        )

    def _build_track_key(self, track_id, track_name, artist_name):
        return build_translation_key(track_name, artist_name)

    def translation_content_for_key(self, storage_key):
        entry = self.manual_translation_inputs.get(storage_key) or {}
        return entry.get("content", "")

    def translation_entries_for_key(self, storage_key):
        entry = self.manual_translation_inputs.get(storage_key) or {}
        return normalize_translation_entries(entry.get("translation_entries"))

    def synced_lyrics_for_key(self, storage_key):
        entry = self.manual_translation_inputs.get(storage_key) or {}
        return safe_strip(entry.get("synced_lyrics"))

    def lyric_offset_for_key(self, storage_key):
        entry = self.manual_translation_inputs.get(storage_key) or {}
        return safe_int(entry.get("lyric_offset_ms"), 0)

    def current_track_display_name(self):
        if self.current_track_name and self.current_track_artist:
            return f"{self.current_track_name} - {self.current_track_artist}"
        if self.current_track_name:
            return self.current_track_name
        return "-"

    def current_song_translation_editor_entries(self):
        if not self.base_lyrics:
            return []

        stored_entries = self.translation_entries_for_key(self.current_track_key)
        if stored_entries:
            aligned_lyrics = align_translations_to_lyrics(self.base_lyrics, stored_entries)
        else:
            raw_text = self.translation_content_for_key(self.current_track_key)
            parsed_pairs = parse_manual_translation_block(
                raw_text, f"{self.current_track_name} - {self.current_track_artist}"
            )
            aligned_lyrics = align_translations_to_lyrics(self.base_lyrics, parsed_pairs)

        entries = []
        for lyric in aligned_lyrics:
            original_text = safe_strip(lyric.get("text"))
            if not original_text:
                continue
            entries.append(
                {
                    "original": original_text,
                    "translation": safe_strip(lyric.get("translation")),
                    "translation_offset_ms": safe_int(lyric.get("translation_offset_ms"), 0),
                }
            )
        return entries

    def _sync_track_timing_controls(self):
        if not hasattr(self, "translation_window"):
            return
        self.translation_window.lyric_offset.blockSignals(True)
        self.translation_window.lyric_offset.setValue(self.current_track_lyric_offset_ms)
        self.translation_window.lyric_offset.blockSignals(False)
        self.translation_window.timing_song_value.setText(self.current_track_display_name())

    def update_current_track_lyric_offset(self):
        if not hasattr(self, "translation_window"):
            return

        offset_ms = self.translation_window.lyric_offset.value()
        self.current_track_lyric_offset_ms = offset_ms
        self._sync_track_timing_controls()

        if not self.current_track_key or not self.current_track_name:
            return

        existing_entry = dict(self.manual_translation_inputs.get(self.current_track_key) or {})
        updated_entry = {
            "track_name": self.current_track_name,
            "artist_name": self.current_track_artist,
            "content": safe_strip(existing_entry.get("content")),
            "synced_lyrics": safe_strip(existing_entry.get("synced_lyrics")),
            "lyric_offset_ms": offset_ms,
            "translation_entries": normalize_translation_entries(existing_entry.get("translation_entries")),
        }

        if (
            not updated_entry["content"]
            and not updated_entry["synced_lyrics"]
            and offset_ms == 0
            and not updated_entry["translation_entries"]
        ):
            self.manual_translation_inputs.pop(self.current_track_key, None)
        else:
            self.manual_translation_inputs[self.current_track_key] = updated_entry

        save_manual_translation_inputs(self.manual_translation_inputs)
        self.translation_window.set_status(self.tr("lyric_offset_saved", offset=offset_ms))
        if self.cached_lyrics:
            self.animate_current_line()

    def adjust_current_track_lyric_offset(self, delta_ms):
        if not hasattr(self, "translation_window"):
            return
        self.translation_window.lyric_offset.setValue(
            self.translation_window.lyric_offset.value() + delta_ms
        )

    def reset_current_track_lyric_offset(self):
        if not hasattr(self, "translation_window"):
            return
        self.translation_window.lyric_offset.setValue(0)

    def cache_netease_lyrics_bundle(self, track_name, artist_name, synced_lyrics, translation_pairs):
        storage_key = build_translation_key(track_name, artist_name)
        existing_entry = dict(self.manual_translation_inputs.get(storage_key) or {})
        updated_entry = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": safe_strip(existing_entry.get("content")),
            "synced_lyrics": safe_strip(synced_lyrics),
            "lyric_offset_ms": safe_int(existing_entry.get("lyric_offset_ms"), 0),
            "translation_entries": normalize_translation_entries(existing_entry.get("translation_entries")),
        }

        if not updated_entry["content"] and translation_pairs:
            updated_entry["content"] = build_translation_block(translation_pairs)
        if not updated_entry["translation_entries"] and translation_pairs:
            updated_entry["translation_entries"] = normalize_translation_entries(translation_pairs)

        if (
            existing_entry.get("track_name") == updated_entry["track_name"]
            and existing_entry.get("artist_name") == updated_entry["artist_name"]
            and safe_strip(existing_entry.get("content")) == updated_entry["content"]
            and safe_strip(existing_entry.get("synced_lyrics")) == updated_entry["synced_lyrics"]
        ):
            return

        self.manual_translation_inputs[storage_key] = updated_entry
        save_manual_translation_inputs(self.manual_translation_inputs)

    def _manual_translation_pairs_for_current(self):
        stored_entries = self.translation_entries_for_key(self.current_track_key)
        if stored_entries:
            return stored_entries

        raw_text = self.translation_content_for_key(self.current_track_key)
        if not raw_text:
            return []

        return parse_manual_translation_block(
            raw_text, f"{self.current_track_name} - {self.current_track_artist}"
        )

    def has_manual_translation_for_key(self, storage_key):
        return bool(
            safe_strip(self.translation_content_for_key(storage_key))
            or self.translation_entries_for_key(storage_key)
        )

    def _build_cached_lyrics(self, lyrics_data):
        if not lyrics_data:
            return []

        translation_pairs = self._manual_translation_pairs_for_current()
        return align_translations_to_lyrics(lyrics_data, translation_pairs)

    def _maybe_cache_netease_translation(self, track_name, artist_name, duration_ms, lyrics_data):
        if not lyrics_data or detect_chinese_song(lyrics_data):
            return

        storage_key = build_translation_key(track_name, artist_name)
        if self.has_manual_translation_for_key(storage_key):
            return

        existing_synced_lyrics = self.synced_lyrics_for_key(storage_key)
        if existing_synced_lyrics:
            return

        try:
            netease_bundle = get_netease_lyrics_bundle(track_name, artist_name, duration_ms)
            synced_lyrics = safe_strip(netease_bundle.get("synced_lyrics"))
            translation_pairs = netease_bundle.get("translation_pairs") or []
            if translation_pairs or synced_lyrics:
                self.cache_netease_lyrics_bundle(
                    track_name,
                    artist_name,
                    synced_lyrics or existing_synced_lyrics,
                    translation_pairs,
                )
        except Exception as exc:
            log_warning(
                f"Failed to load Netease translation cache for '{track_name}' by '{artist_name}'.",
                exc,
            )

    def _load_track_lyrics(self, track_name, artist_name, duration_ms):
        storage_key = build_translation_key(track_name, artist_name)
        try:
            netease_bundle = get_netease_lyrics_bundle(track_name, artist_name, duration_ms)
            synced_lyrics = safe_strip(netease_bundle.get("synced_lyrics"))
            translation_pairs = netease_bundle.get("translation_pairs") or []
            if synced_lyrics:
                self.cache_netease_lyrics_bundle(
                    track_name,
                    artist_name,
                    synced_lyrics,
                    translation_pairs,
                )
                lyrics_data = parse_lrc(synced_lyrics)
                if lyrics_data:
                    return lyrics_data, self._build_cached_lyrics(lyrics_data)
        except Exception as exc:
            log_warning(
                f"Failed to load Netease primary lyrics for '{track_name}' by '{artist_name}'. Falling back to LRCLIB.",
                exc,
            )

        try:
            synced_text = get_best_synced_lyrics(track_name, artist_name, duration_ms)
            if synced_text:
                lyrics_data = parse_lrc(synced_text)
                if lyrics_data:
                    self._maybe_cache_netease_translation(
                        track_name,
                        artist_name,
                        duration_ms,
                        lyrics_data,
                    )
                    return lyrics_data, self._build_cached_lyrics(lyrics_data)
        except Exception as exc:
            log_warning(
                f"Failed to load LRCLIB fallback lyrics for '{track_name}' by '{artist_name}'.",
                exc,
            )

        cached_synced_lyrics = self.synced_lyrics_for_key(storage_key)
        if cached_synced_lyrics:
            lyrics_data = parse_lrc(cached_synced_lyrics)
            if lyrics_data:
                return lyrics_data, self._build_cached_lyrics(lyrics_data)
        return [], []

    def _translation_inputs_to_key(self):
        track_name = safe_strip(self.translation_window.track_name_input.text())
        artist_name = safe_strip(self.translation_window.artist_name_input.text())
        if not track_name:
            return "", "", ""
        return build_translation_key(track_name, artist_name), track_name, artist_name

    def load_translation_for_inputs(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        if not storage_key:
            self.translation_window.set_status(self.tr("translation_enter_song_name"), error=True)
            return

        content = self.translation_content_for_key(storage_key)
        translation_entries = self.translation_entries_for_key(storage_key)
        self.translation_window.editor.setPlainText(content)
        if storage_key == self.current_track_key and self.base_lyrics:
            self.translation_window.set_line_entries(self.current_song_translation_editor_entries())
        if content:
            self.translation_window.set_status(self.tr("translation_loaded"))
        elif translation_entries:
            self.translation_window.set_status(self.tr("translation_loaded"))
        else:
            self.translation_window.set_status(self.tr("translation_not_found"))

    def apply_manual_translations(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        raw_text = safe_strip(self.translation_window.editor.toPlainText())
        if not storage_key:
            self.translation_window.set_status(self.tr("translation_enter_song_name"), error=True)
            return

        line_entries = []
        if storage_key == self.current_track_key and self.base_lyrics:
            line_entries = normalize_translation_entries(self.translation_window.line_entries())

        if not raw_text and not line_entries:
            existing_entry = dict(self.manual_translation_inputs.get(storage_key) or {})
            cached_synced_lyrics = safe_strip(existing_entry.get("synced_lyrics"))
            lyric_offset_ms = safe_int(existing_entry.get("lyric_offset_ms"), 0)
            translation_entries = normalize_translation_entries(existing_entry.get("translation_entries"))
            if cached_synced_lyrics:
                self.manual_translation_inputs[storage_key] = {
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "content": "",
                    "synced_lyrics": cached_synced_lyrics,
                    "lyric_offset_ms": lyric_offset_ms,
                    "translation_entries": translation_entries,
                }
            elif lyric_offset_ms != 0 or translation_entries:
                self.manual_translation_inputs[storage_key] = {
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "content": "",
                    "synced_lyrics": "",
                    "lyric_offset_ms": lyric_offset_ms,
                    "translation_entries": translation_entries,
                }
            else:
                self.manual_translation_inputs.pop(storage_key, None)
            save_manual_translation_inputs(self.manual_translation_inputs)
            if storage_key == self.current_track_key:
                self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
                self.animate_current_line()
            self.translation_window.set_status(self.tr("translation_cleared_current"))
            return

        translation_pairs = line_entries
        generated_content = build_translation_block(line_entries)
        if raw_text and not line_entries:
            translation_pairs = parse_manual_translation_block(
                raw_text, f"{track_name} - {artist_name}"
            )
            generated_content = raw_text
        if not translation_pairs:
            self.translation_window.set_status(self.tr("translation_format_invalid"), error=True)
            return

        existing_entry = dict(self.manual_translation_inputs.get(storage_key) or {})
        self.manual_translation_inputs[storage_key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": generated_content,
            "synced_lyrics": safe_strip(existing_entry.get("synced_lyrics")),
            "lyric_offset_ms": safe_int(existing_entry.get("lyric_offset_ms"), 0),
            "translation_entries": normalize_translation_entries(translation_pairs),
        }
        save_manual_translation_inputs(self.manual_translation_inputs)

        if storage_key == self.current_track_key:
            self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
            if self.base_lyrics:
                self.translation_window.set_line_entries(self.current_song_translation_editor_entries())
            matched_count = sum(1 for lyric in self.cached_lyrics if lyric.get("translation"))
            self.translation_window.set_status(
                self.tr("translation_saved_applied", count=matched_count)
            )
            self.animate_current_line()
            return

        self.translation_window.set_status(self.tr("translation_saved_json"))

    def clear_manual_translations(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        if not storage_key:
            self.translation_window.set_status(self.tr("translation_enter_song_name"), error=True)
            return

        existing_entry = dict(self.manual_translation_inputs.get(storage_key) or {})
        cached_synced_lyrics = safe_strip(existing_entry.get("synced_lyrics"))
        lyric_offset_ms = safe_int(existing_entry.get("lyric_offset_ms"), 0)
        translation_entries = normalize_translation_entries(existing_entry.get("translation_entries"))
        if cached_synced_lyrics:
            self.manual_translation_inputs[storage_key] = {
                "track_name": track_name,
                "artist_name": artist_name,
                "content": "",
                "synced_lyrics": cached_synced_lyrics,
                "lyric_offset_ms": lyric_offset_ms,
                "translation_entries": translation_entries,
            }
        elif lyric_offset_ms != 0 or translation_entries:
            self.manual_translation_inputs[storage_key] = {
                "track_name": track_name,
                "artist_name": artist_name,
                "content": "",
                "synced_lyrics": "",
                "lyric_offset_ms": lyric_offset_ms,
                "translation_entries": translation_entries,
            }
        else:
            self.manual_translation_inputs.pop(storage_key, None)
        save_manual_translation_inputs(self.manual_translation_inputs)
        self.translation_window.editor.clear()
        if storage_key == self.current_track_key and self.base_lyrics:
            self.translation_window.set_line_entries(self.current_song_translation_editor_entries())
        if storage_key == self.current_track_key:
            self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
            self.animate_current_line()
        self.translation_window.set_status(self.tr("translation_deleted_json"))

    def _set_labels(
        self,
        title,
        current_line,
        current_translation,
        next_line,
        next_translation,
        current_progress=0.0,
    ):
        safe_title = safe_strip(title)
        safe_current_line = "" if current_line is None else str(current_line)
        safe_current_translation = "" if current_translation is None else str(current_translation)
        safe_next_line = "" if next_line is None else str(next_line)
        safe_next_translation = "" if next_translation is None else str(next_translation)

        self.song_label.setText(safe_title)
        self.last_track_name = safe_title
        self.current_main_text = safe_current_line
        self.current_translation_label.setProperty("plain_text", safe_current_translation)
        self.subtitle_label.setText(safe_next_line)
        self.subtitle_translation_label.setText(safe_next_translation)
        self._apply_main_lyric_color(current_progress)

    def animate_current_line(self):
        if not self.cached_lyrics:
            return

        estimated_progress = self._estimated_progress_ms()
        current_line, current_translation, next_line, next_translation, current_progress = self._find_active_lines(
            estimated_progress
        )
        self._set_labels(
            self.last_track_name,
            current_line,
            current_translation,
            next_line,
            next_translation,
            current_progress,
        )

    def refresh(self):
        try:
            if self.spotify is None:
                self.is_playing = False
                self.current_track_id = None
                self.current_track_key = None
                self.current_track_name = ""
                self.current_track_artist = ""
                self.current_track_lyric_offset_ms = 0
                self.base_lyrics = []
                self.cached_lyrics = []
                self._sync_track_timing_controls()
                self._set_labels(
                    self.tr("spotify_unconfigured_title"),
                    self.tr("spotify_unconfigured_message"),
                    "",
                    "",
                    "",
                    0.0,
                )
                return

            track_info = self.spotify.currently_playing()
            if not track_info or not track_info.get("is_playing"):
                self.is_playing = False
                self.last_progress_ms = 0
                self.last_progress_timestamp = time.monotonic()
                self.current_track_id = None
                self.current_track_key = None
                self.current_track_name = ""
                self.current_track_artist = ""
                self.current_track_lyric_offset_ms = 0
                self.base_lyrics = []
                self.cached_lyrics = []
                self._sync_track_timing_controls()
                self._set_labels(
                    self.tr("spotify_paused_title"),
                    self.tr("spotify_waiting_message"),
                    "",
                    "",
                    "",
                    0.0,
                )
                return

            item = track_info.get("item")
            if not item:
                self.is_playing = False
                self._set_labels(
                    self.tr("spotify_unable_title"),
                    self.tr("spotify_unable_message"),
                    "",
                    "",
                    "",
                    0.0,
                )
                return

            track_name = safe_strip(item.get("name"))
            artists = item.get("artists") or []
            artist_names = [
                safe_strip(artist.get("name"))
                for artist in artists
                if isinstance(artist, dict) and safe_strip(artist.get("name"))
            ]
            artist_name = ", ".join(artist_names)
            track_id = item.get("id") or build_translation_key(track_name, artist_name)
            if not track_name:
                track_name = self.tr("spotify_unable_title")
            self.is_playing = True
            self.last_progress_ms = track_info.get("progress_ms", 0)
            self.last_progress_timestamp = time.monotonic()
            self.current_track_name = track_name
            self.current_track_artist = artist_name
            self.current_track_key = self._build_track_key(track_id, track_name, artist_name)
            self.current_track_lyric_offset_ms = self.lyric_offset_for_key(self.current_track_key)
            self._sync_track_timing_controls()

            if track_id != self.current_track_id:
                self.base_lyrics, self.cached_lyrics = self._load_track_lyrics(
                    track_name,
                    artist_name,
                    item.get("duration_ms", 0),
                )
                self.current_track_id = track_id
                if self.translation_window.isVisible():
                    self.translation_window.sync_from_overlay()

            estimated_progress = self._estimated_progress_ms()
            current_line, current_translation, next_line, next_translation, current_progress = self._find_active_lines(
                estimated_progress
            )
            self._set_labels(
                f"{track_name} - {artist_name}",
                current_line,
                current_translation,
                next_line,
                next_translation,
                current_progress,
            )
            self._log_terminal_debug(estimated_progress, current_line, next_line)
        except SpotifyOauthError as exc:
            self.spotify = None
            self.current_track_id = None
            self.current_track_key = None
            self.current_track_name = ""
            self.current_track_artist = ""
            self.current_track_lyric_offset_ms = 0
            self.base_lyrics = []
            self.cached_lyrics = []
            self._sync_track_timing_controls()
            self._set_labels(
                self.tr("spotify_key_error_title"),
                self.tr("spotify_key_error_message"),
                "",
                "",
                "",
                0.0,
            )
        except Exception as exc:
            log_warning("Unexpected error while refreshing Spotify playback.", exc)
            self._sync_track_timing_controls()
            self._set_labels(
                self.tr("spotify_error_title"),
                self.tr("spotify_error_message", error=exc),
                "",
                "",
                "",
                0.0,
            )

    def closeEvent(self, event):
        if hasattr(self, "control_window"):
            self.control_window.close()
        if hasattr(self, "settings_window"):
            self.settings_window.close()
        if hasattr(self, "translation_window"):
            self.translation_window.close()
        stop_netease_api_if_needed()
        super().closeEvent(event)


def main():
    start_netease_api_if_needed()
    app = QApplication(sys.argv)
    _configure_macos_app()
    app.setQuitOnLastWindowClosed(True)

    overlay = LyricsOverlay()
    overlay.show()
    overlay._ensure_on_top(force_front=True)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
