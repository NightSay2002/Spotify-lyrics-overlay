import html
import json
import os
import platform
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urljoin

import requests
import spotipy
from bs4 import BeautifulSoup
from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
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


def similarity_score(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


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


def align_translations_to_lyrics(lyrics_data, translation_pairs):
    if not lyrics_data:
        return []

    aligned_lyrics = [dict(lyric, translation="") for lyric in lyrics_data]
    if not translation_pairs:
        return aligned_lyrics

    pair_index = 0
    window_size = 20

    for lyric in aligned_lyrics:
        lyric_text = lyric.get("text", "").strip()
        normalized_lyric = normalize_text(lyric_text)
        if not normalized_lyric:
            continue

        best_match_index = None
        best_match_score = 0.0
        search_end = min(pair_index + window_size, len(translation_pairs))

        for index in range(pair_index, search_end):
            candidate = translation_pairs[index]
            score = translation_match_score(normalized_lyric, candidate["normalized_original"])
            if score > best_match_score:
                best_match_index = index
                best_match_score = score

        if best_match_index is None or best_match_score < 0.6:
            for index in range(pair_index, len(translation_pairs)):
                candidate = translation_pairs[index]
                score = translation_match_score(normalized_lyric, candidate["normalized_original"])
                if score > best_match_score:
                    best_match_index = index
                    best_match_score = score

        if best_match_index is None or best_match_score < 0.56:
            continue

        lyric["translation"] = translation_pairs[best_match_index]["translation"]
        pair_index = best_match_index + 1

    return aligned_lyrics


def parse_manual_translation_block(raw_text, track_label=""):
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
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
            }
        )

    return translation_pairs


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
        track_name = str(value.get("track_name", "")).strip()
        artist_name = str(value.get("artist_name", "")).strip()
        content = str(value.get("content", "")).strip()
        if not track_name or not content:
            continue
        normalized_key = key or build_translation_key(track_name, artist_name)
        normalized_data[normalized_key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": content,
        }

    return normalized_data


def save_manual_translation_inputs(manual_translation_inputs):
    payload = {}
    for key, value in manual_translation_inputs.items():
        if not isinstance(value, dict):
            continue
        track_name = str(value.get("track_name", "")).strip()
        artist_name = str(value.get("artist_name", "")).strip()
        content = str(value.get("content", "")).strip()
        if not track_name or not content:
            continue
        payload[key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": content,
        }

    with open(MANUAL_TRANSLATIONS_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def build_translation_key(track_name, artist_name):
    normalized_track = normalize_text(track_name)
    normalized_artist = normalize_text(artist_name)
    return f"{normalized_track}::{normalized_artist}"


def detect_chinese_song(lyrics_data):
    sample_text = "".join(
        lyric.get("text", "") for lyric in lyrics_data if lyric.get("text", "").strip()
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
        self.drag_button.setFixedSize(56, 24)
        self.drag_button.clicked.connect(self.overlay.toggle_drag_mode)
        self.drag_button.setStyleSheet(button_style)

        self.settings_button = QPushButton("設定")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setFixedSize(56, 24)
        self.settings_button.clicked.connect(self.overlay.toggle_settings_window)
        self.settings_button.setStyleSheet(button_style)

        self.translation_button = QPushButton("翻譯")
        self.translation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translation_button.setFixedSize(56, 24)
        self.translation_button.clicked.connect(self.overlay.toggle_translation_window)
        self.translation_button.setStyleSheet(button_style)

        self.close_button = QPushButton("關閉")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(56, 24)
        self.close_button.clicked.connect(self.overlay.quit_app)
        self.close_button.setStyleSheet(button_style)

        layout.addWidget(self.drag_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.translation_button)
        layout.addWidget(self.close_button)
        self.apply_button_style("#0F172A")

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
        self.drag_button.setText("鎖定" if enabled else "移動")

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.overlay.pick_text_color)
        form.addRow("字色", self.color_button)

        self.end_color_button = QPushButton()
        self.end_color_button.clicked.connect(self.overlay.pick_end_text_color)
        form.addRow("終點色", self.end_color_button)

        self.button_color_button = QPushButton()
        self.button_color_button.clicked.connect(self.overlay.pick_button_color)
        form.addRow("按鈕色", self.button_color_button)

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

        form.addRow("主字幕", self.main_size)
        form.addRow("主翻譯", self.main_translation_size)
        form.addRow("副字幕", self.subtitle_size)
        form.addRow("副翻譯", self.subtitle_translation_size)
        form.addRow("歌名距離", self.gap_song)
        form.addRow("行距 1", self.gap_primary)
        form.addRow("行距 2", self.gap_middle)
        form.addRow("行距 3", self.gap_subtitle)
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

        self.spotify_client_id = QLineEdit()
        self.spotify_client_secret = QLineEdit()
        self.spotify_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.spotify_redirect_uri = QLineEdit()

        spotify_form.addRow("Client ID", self.spotify_client_id)
        spotify_form.addRow("Client Secret", self.spotify_client_secret)
        spotify_form.addRow("Redirect URI", self.spotify_redirect_uri)
        layout.addLayout(spotify_form)

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

        self.track_name_input = QLineEdit()
        self.artist_name_input = QLineEdit()
        form.addRow("歌名", self.track_name_input)
        form.addRow("歌手", self.artist_name_input)

        self.hint_label = QLabel("每兩行一組：原文 / 翻譯。開頭重複歌名會自動略過。")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: rgba(226, 232, 240, 0.82); font-size: 12px;")

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
        layout.addWidget(self.editor)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)

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
        if not self.track_name_input.text().strip():
            self.track_name_input.setText(self.overlay.current_track_name)
        if not self.artist_name_input.text().strip():
            self.artist_name_input.setText(self.overlay.current_track_artist)
        if not self.editor.toPlainText().strip():
            self.editor.blockSignals(True)
            self.editor.setPlainText(
                self.overlay.translation_content_for_key(self.overlay.current_track_key)
            )
            self.editor.blockSignals(False)


class LyricsOverlay(QWidget):

    def __init__(self):
        super().__init__()
        self.app_settings = load_app_settings()
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
        self.text_style = {
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

        self.current_lyric_label = QLabel("Waiting for Spotify playback...")
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
            return "No synced lyrics found.", "", "", "", 0.0

        current_line = "..."
        current_translation = ""
        next_line = ""
        next_translation = ""
        current_progress = 0.0

        for index, lyric in enumerate(self.cached_lyrics):
            if progress_ms >= lyric["time"]:
                current_line = lyric["text"] or "..."
                current_translation = lyric.get("translation", "")
                start_time = lyric["time"]
                end_time = self.cached_lyrics[index + 1]["time"] if index + 1 < len(self.cached_lyrics) else start_time + 4000
                duration = max(end_time - start_time, 1)
                current_progress = min(max((progress_ms - start_time) / duration, 0.0), 1.0)
                if index + 1 < len(self.cached_lyrics):
                    next_line = self.cached_lyrics[index + 1]["text"] or ""
                    next_translation = self.cached_lyrics[index + 1].get("translation", "")
            else:
                if current_line == "...":
                    next_line = lyric.get("text", "")
                    next_translation = lyric.get("translation", "")
                break

        return current_line, current_translation, next_line, next_translation, current_progress

    def _estimated_progress_ms(self):
        if not self.is_playing:
            return self.last_progress_ms

        elapsed_ms = int((time.monotonic() - self.last_progress_timestamp) * 1000)
        return max(self.last_progress_ms + elapsed_ms, 0)

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
            (self.song_label, self.song_label.text().strip()),
            (self.current_lyric_label, self.current_main_text.strip()),
            (
                self.current_translation_label,
                (self.current_translation_label.property("plain_text") or "").strip(),
            ),
            (self.subtitle_label, self.subtitle_label.text().strip()),
            (self.subtitle_translation_label, self.subtitle_translation_label.text().strip()),
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

    def save_spotify_settings(self):
        client_id = self.settings_window.spotify_client_id.text().strip()
        client_secret = self.settings_window.spotify_client_secret.text().strip()
        redirect_uri = self.settings_window.spotify_redirect_uri.text().strip()
        if not client_id or not client_secret or not redirect_uri:
            self.settings_window.set_spotify_status("Spotify key 不可留空。", error=True)
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
                    "請填入 Spotify Client ID、Client Secret 和 Redirect URI。",
                    error=True,
                )
                return
            self.current_track_id = None
            self.settings_window.set_spotify_status("Spotify key 已儲存，之後會一直保留。")
        except Exception as exc:
            self.spotify = None
            self.settings_window.set_spotify_status(f"儲存失敗：{exc}", error=True)

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
        self.settings_window.set_spotify_status("Spotify key 已清除。")

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
            "選擇字幕顏色",
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
            "選擇主字幕終點色",
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
            "選擇按鈕顏色",
        )
        if not selected_color.isValid():
            return

        self.text_style["button_color"] = selected_color.name().upper()
        self.control_window.apply_button_style(self.text_style["button_color"])
        self.settings_window.set_button_color_preview(self.text_style["button_color"])

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

    def _manual_translation_pairs_for_current(self):
        raw_text = self.translation_content_for_key(self.current_track_key)
        if not raw_text:
            return []

        return parse_manual_translation_block(
            raw_text, f"{self.current_track_name} - {self.current_track_artist}"
        )

    def _build_cached_lyrics(self, lyrics_data):
        if not lyrics_data:
            return []

        translation_pairs = self._manual_translation_pairs_for_current()
        return align_translations_to_lyrics(lyrics_data, translation_pairs)

    def _translation_inputs_to_key(self):
        track_name = self.translation_window.track_name_input.text().strip()
        artist_name = self.translation_window.artist_name_input.text().strip()
        if not track_name:
            return "", "", ""
        return build_translation_key(track_name, artist_name), track_name, artist_name

    def load_translation_for_inputs(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        if not storage_key:
            self.translation_window.set_status("請先輸入歌名。", error=True)
            return

        content = self.translation_content_for_key(storage_key)
        self.translation_window.editor.setPlainText(content)
        if content:
            self.translation_window.set_status("已載入已儲存的翻譯。")
        else:
            self.translation_window.set_status("這首歌目前沒有已儲存的翻譯。")

    def apply_manual_translations(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        raw_text = self.translation_window.editor.toPlainText().strip()
        if not storage_key:
            self.translation_window.set_status("請先輸入歌名。", error=True)
            return

        if not raw_text:
            self.manual_translation_inputs.pop(storage_key, None)
            save_manual_translation_inputs(self.manual_translation_inputs)
            if storage_key == self.current_track_key:
                self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
                self.animate_current_line()
            self.translation_window.set_status("已清空這首歌的手動翻譯。")
            return

        translation_pairs = parse_manual_translation_block(
            raw_text, f"{track_name} - {artist_name}"
        )
        if not translation_pairs:
            self.translation_window.set_status("格式不對，請用原文 / 翻譯成對貼上。", error=True)
            return

        self.manual_translation_inputs[storage_key] = {
            "track_name": track_name,
            "artist_name": artist_name,
            "content": raw_text,
        }
        save_manual_translation_inputs(self.manual_translation_inputs)

        if storage_key == self.current_track_key:
            self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
            matched_count = sum(1 for lyric in self.cached_lyrics if lyric.get("translation"))
            self.translation_window.set_status(f"已儲存並套用 {matched_count} 行翻譯。")
            self.animate_current_line()
            return

        self.translation_window.set_status("已儲存到 JSON，播放到這首歌時會自動套用。")

    def clear_manual_translations(self):
        storage_key, track_name, artist_name = self._translation_inputs_to_key()
        if not storage_key:
            self.translation_window.set_status("請先輸入歌名。", error=True)
            return

        self.manual_translation_inputs.pop(storage_key, None)
        save_manual_translation_inputs(self.manual_translation_inputs)
        self.translation_window.editor.clear()
        if storage_key == self.current_track_key:
            self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
            self.animate_current_line()
        self.translation_window.set_status("已刪除這首歌的 JSON 翻譯。")

    def _set_labels(
        self,
        title,
        current_line,
        current_translation,
        next_line,
        next_translation,
        current_progress=0.0,
    ):
        self.song_label.setText(title)
        self.last_track_name = title
        self.current_main_text = current_line
        self.current_translation_label.setProperty("plain_text", current_translation or "")
        self.subtitle_label.setText(next_line or "")
        self.subtitle_translation_label.setText(next_translation or "")
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
                self.base_lyrics = []
                self.cached_lyrics = []
                self._set_labels(
                    "Spotify 未設定",
                    "Open 設定 and add Spotify Client ID / Secret",
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
                self.base_lyrics = []
                self.cached_lyrics = []
                self._set_labels(
                    "Spotify paused",
                    "Waiting for Spotify playback...",
                    "",
                    "",
                    "",
                    0.0,
                )
                return

            item = track_info.get("item")
            if not item:
                self.is_playing = False
                self._set_labels("Spotify", "Unable to read current track.", "", "", "", 0.0)
                return

            track_id = item["id"]
            track_name = item["name"]
            artist_name = ", ".join(artist["name"] for artist in item["artists"])
            self.is_playing = True
            self.last_progress_ms = track_info.get("progress_ms", 0)
            self.last_progress_timestamp = time.monotonic()
            self.current_track_name = track_name
            self.current_track_artist = artist_name
            self.current_track_key = self._build_track_key(track_id, track_name, artist_name)

            if track_id != self.current_track_id:
                self.base_lyrics = parse_lrc(
                    get_best_synced_lyrics(track_name, artist_name, item.get("duration_ms", 0))
                )
                self.cached_lyrics = self._build_cached_lyrics(self.base_lyrics)
                self.current_track_id = track_id

            current_line, current_translation, next_line, next_translation, current_progress = self._find_active_lines(
                self.last_progress_ms
            )
            self._set_labels(
                f"{track_name} - {artist_name}",
                current_line,
                current_translation,
                next_line,
                next_translation,
                current_progress,
            )
        except SpotifyOauthError as exc:
            self.spotify = None
            self.current_track_id = None
            self.current_track_key = None
            self.base_lyrics = []
            self.cached_lyrics = []
            self._set_labels(
                "Spotify Key Error",
                "請到設定填入 Spotify Client ID / Secret / Redirect URI",
                "",
                "",
                "",
                0.0,
            )
        except Exception as exc:
            self._set_labels("Spotify Error", f"Error: {exc}", "", "", "", 0.0)

    def closeEvent(self, event):
        if hasattr(self, "control_window"):
            self.control_window.close()
        if hasattr(self, "settings_window"):
            self.settings_window.close()
        if hasattr(self, "translation_window"):
            self.translation_window.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    _configure_macos_app()
    app.setQuitOnLastWindowClosed(True)

    overlay = LyricsOverlay()
    overlay.show()
    overlay._ensure_on_top(force_front=True)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
