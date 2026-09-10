"""
Complete Native GUI (PySide6 / Qt 6) module for Phoebus Builder.
Uses 100% standard/native Qt system styling (Breeze/Adwaita/Windows native widgets),
with native QTranslator, event-driven language switching, and robust background build execution.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Silence verbose Wayland textinput debug warnings on Fedora / GNOME
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland*=false;qt.qpa.wayland.textinput=false;qt.qpa.services*=false"

from PySide6.QtCore import Qt, QThread, Signal, QObject, QEvent, QSize
from PySide6.QtGui import QPixmap, QImage, QFont, QTextCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QScrollArea,
    QPlainTextEdit, QTextEdit, QProgressBar, QFileDialog, QMessageBox,
    QDialog, QFrame, QMenu
)

from .config import BuildConfig, get_workspace_dir
from .downloader import DownloadManager
from .image_utils import ImageValidator
from .jvm import JvmManager
from .packager import PhoebusPackager
from .settings_editor import SettingsEditor
from .settings_generator import SettingsGenerator
from .modules import PHOEBUS_MODULES, PhoebusPomManager
from .wizard import fetch_recent_phoebus_tags
from .i18n import t, get_language, set_language
from .theme import apply_app_theme
from .file_browser import NativeFileBrowser

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    """Removes ANSI terminal escape sequences."""
    return ANSI_ESCAPE_RE.sub('', text)


class BuildWorkerThread(QThread):
    """Background worker thread executing Phoebus compilation and packaging."""
    log_signal = Signal(str)
    build_finished = Signal(bool, str, bool)

    def __init__(self, config: BuildConfig, base_dir: Path):
        super().__init__()
        self.config = config
        self.base_dir = base_dir
        self.packager: Optional[PhoebusPackager] = None

    def cancel(self):
        """Interrupts build execution and terminates active child subprocesses."""
        if self.packager:
            self.packager.cancel()
        self.requestInterruption()

    def run(self):
        class StdoutRedirector:
            def __init__(self, emit_fn):
                self.emit_fn = emit_fn

            def write(self, text):
                if not text:
                    return
                for line in text.splitlines():
                    clean = strip_ansi(line.rstrip("\r\n"))
                    if clean:
                        self.emit_fn(clean)

            def flush(self):
                pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = StdoutRedirector(self.log_signal.emit)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            self.packager = PhoebusPackager(self.config, base_dir=self.base_dir)
            output_pkg = self.packager.build()
            self.log_signal.emit(f"\n[SUCCESS] Native installer package created in: {output_pkg}\n")
            self.build_finished.emit(True, str(output_pkg), False)
        except (InterruptedError, KeyboardInterrupt):
            self.log_signal.emit("\n[CANCELLED] Build stopped by user.\n")
            self.build_finished.emit(False, "Stopped by user.", True)
        except Exception as e:
            self.log_signal.emit(f"\n[ERROR] Build failed: {e}\n")
            self.build_finished.emit(False, str(e), False)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

class SourcesDownloadWorkerThread(QThread):
    """Background worker thread to download and extract Phoebus source files."""
    log_signal = Signal(str)
    download_finished = Signal(bool, str)

    def __init__(self, tag: str, base_dir: Path, app_name: str):
        super().__init__()
        self.tag = tag
        self.base_dir = base_dir
        self.app_name = app_name

    def run(self):
        class StdoutRedirector:
            def __init__(self, emit_fn):
                self.emit_fn = emit_fn

            def write(self, text):
                if not text:
                    return
                for line in text.splitlines():
                    clean = strip_ansi(line.rstrip("\r\n"))
                    if clean:
                        self.emit_fn(clean)

            def flush(self):
                pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = StdoutRedirector(self.log_signal.emit)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            shared_sources_base = self.base_dir / "sources" / "phoebus"
            shared_sources_base.mkdir(parents=True, exist_ok=True)
            sources_dir = DownloadManager.download_phoebus_sources(
                tag=self.tag,
                build_dir=shared_sources_base,
                force=False
            )
            self.download_finished.emit(True, str(sources_dir))
        except Exception as e:
            self.download_finished.emit(False, str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class JvmDownloadWorkerThread(QThread):
    """Background worker thread to download and configure Adoptium JDK."""
    log_signal = Signal(str)
    download_finished = Signal(bool, str)

    def __init__(self, java_version: str, is_windows: bool, base_dir: Path):
        super().__init__()
        self.java_version = java_version
        self.is_windows = is_windows
        self.base_dir = base_dir

    def run(self):
        class StdoutRedirector:
            def __init__(self, emit_fn):
                self.emit_fn = emit_fn

            def write(self, text):
                if not text:
                    return
                for line in text.splitlines():
                    clean = strip_ansi(line.rstrip("\r\n"))
                    if clean:
                        self.emit_fn(clean)

            def flush(self):
                pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = StdoutRedirector(self.log_signal.emit)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            jvm = JvmManager(
                base_dir=self.base_dir,
                java_version=self.java_version,
                is_windows=self.is_windows
            )
            jdk_path = jvm.ensure_jdk()
            self.download_finished.emit(True, str(jdk_path))
        except Exception as e:
            self.download_finished.emit(False, str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class MavenDownloadWorkerThread(QThread):
    """Background worker thread to download and configure portable Apache Maven."""
    log_signal = Signal(str)
    download_finished = Signal(bool, str)

    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

    def run(self):
        class StdoutRedirector:
            def __init__(self, emit_fn):
                self.emit_fn = emit_fn

            def write(self, text):
                if not text:
                    return
                for line in text.splitlines():
                    clean = strip_ansi(line.rstrip("\r\n"))
                    if clean:
                        self.emit_fn(clean)

            def flush(self):
                pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = StdoutRedirector(self.log_signal.emit)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            maven_path = DownloadManager.ensure_maven(self.base_dir, force=True)
            self.download_finished.emit(True, str(maven_path))
        except Exception as e:
            self.download_finished.emit(False, str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class WixDownloadWorkerThread(QThread):
    """Background worker thread to download and configure WiX Toolset."""
    log_signal = Signal(str)
    download_finished = Signal(bool, str)

    def __init__(self, base_dir: Path, wix_url: str):
        super().__init__()
        self.base_dir = base_dir
        self.wix_url = wix_url

    def run(self):
        class StdoutRedirector:
            def __init__(self, emit_fn):
                self.emit_fn = emit_fn

            def write(self, text):
                if not text:
                    return
                for line in text.splitlines():
                    clean = strip_ansi(line.rstrip("\r\n"))
                    if clean:
                        self.emit_fn(clean)

            def flush(self):
                pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = StdoutRedirector(self.log_signal.emit)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            wix_path = DownloadManager.ensure_wix(self.base_dir, force=True, url=self.wix_url)
            self.download_finished.emit(True, str(wix_path))
        except Exception as e:
            self.download_finished.emit(False, str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class FirstRunDialog(QDialog):
    """Initial setup dialog displayed on the first startup of Phoebus Builder to choose workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("dlg_first_run_title"))
        self.resize(580, 290)
        self.setMinimumSize(520, 260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Welcome header
        self.lbl_welcome = QLabel(t("first_run_welcome"), self)
        self.lbl_welcome.setWordWrap(True)
        f = self.lbl_welcome.font()
        f.setPointSize(f.pointSize() + 1)
        self.lbl_welcome.setFont(f)
        layout.addWidget(self.lbl_welcome)

        # Workspace path row
        ws_layout = QHBoxLayout()
        ws_layout.setSpacing(8)

        self.edit_path = QLineEdit(self)
        self.edit_path.setPlaceholderText(t("dlg_select_workspace_placeholder"))
        ws_layout.addWidget(self.edit_path, 1)

        self.btn_browse = QPushButton(t("btn_browse"), self)
        self.btn_browse.clicked.connect(self._on_browse)
        ws_layout.addWidget(self.btn_browse)

        layout.addLayout(ws_layout)

        # Workspace Hint
        self.lbl_hint = QLabel(t("lbl_workspace_hint"), self)
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        # Validation error message
        self.lbl_err = QLabel("", self)
        self.lbl_err.setStyleSheet("color: #dc2626; font-size: 11px;")
        layout.addWidget(self.lbl_err)

        layout.addStretch()

        # Bottom bar: Language selector & Start button
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.lbl_lang = QLabel(t("language_label"), self)
        bottom_bar.addWidget(self.lbl_lang)

        self.combo_lang = QComboBox(self)
        self.combo_lang.addItems(["English", "Français"])
        self.combo_lang.setCurrentText("English" if get_language() == "en" else "Français")
        self.combo_lang.currentTextChanged.connect(self._on_lang_changed)
        bottom_bar.addWidget(self.combo_lang)

        bottom_bar.addStretch()

        self.btn_start = QPushButton(t("btn_start_app"), self)
        self.btn_start.setDefault(True)
        self.btn_start.setMinimumHeight(32)
        self.btn_start.setMinimumWidth(120)
        btn_font = self.btn_start.font()
        btn_font.setBold(True)
        self.btn_start.setFont(btn_font)
        self.btn_start.clicked.connect(self._on_start)
        bottom_bar.addWidget(self.btn_start)

        layout.addLayout(bottom_bar)

    def _on_lang_changed(self, text: str):
        lang = "en" if text == "English" else "fr"
        set_language(lang)
        from .app_settings import set_saved_language
        set_saved_language(lang)
        self.setWindowTitle(t("dlg_first_run_title"))
        self.lbl_welcome.setText(t("first_run_welcome"))
        self.btn_browse.setText(t("btn_browse"))
        self.edit_path.setPlaceholderText(t("dlg_select_workspace_placeholder"))
        self.lbl_hint.setText(t("lbl_workspace_hint"))
        self.lbl_lang.setText(t("language_label"))
        self.btn_start.setText(t("btn_start_app"))

    def _on_browse(self):
        curr = self.edit_path.text().strip() or str(Path.home())
        chosen = NativeFileBrowser.get_existing_directory(self, caption=t("dlg_first_run_title"), start_dir=curr)
        if chosen:
            self.edit_path.setText(chosen)
            self.lbl_err.setText("")

    def _on_start(self):
        txt = self.edit_path.text().strip()
        if not txt:
            self.lbl_err.setText(t("dlg_workspace_required"))
            return
        target = Path(txt).resolve()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.lbl_err.setText(str(e))
            return
        from .app_settings import set_saved_workspace_dir, set_first_run_completed
        set_saved_workspace_dir(target)
        set_first_run_completed(True)
        self.accept()


class AppSettingsDialog(QDialog):
    """Application settings dialog to configure workspace location, language, and general preferences."""

    def __init__(self, current_workspace: Path, parent=None):
        super().__init__(parent)
        self.current_workspace = current_workspace.resolve()
        self.new_workspace: Optional[Path] = None
        self.initial_language: str = get_language()
        self.new_language: str = self.initial_language
        self.migrate_requested: bool = False

        self.setWindowTitle(t("dlg_settings_title"))
        self.resize(600, 310)
        self.setMinimumSize(540, 260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Workspace label
        self.lbl_ws = QLabel(t("lbl_workspace_dir"), self)
        f = self.lbl_ws.font()
        f.setBold(True)
        self.lbl_ws.setFont(f)
        layout.addWidget(self.lbl_ws)

        # Workspace path row
        ws_layout = QHBoxLayout()
        ws_layout.setSpacing(8)

        self.edit_ws = QLineEdit(self)
        self.edit_ws.setText(str(self.current_workspace))
        self.edit_ws.textChanged.connect(self._on_ws_text_changed)
        ws_layout.addWidget(self.edit_ws, 1)

        self.btn_browse = QPushButton(t("btn_browse"), self)
        self.btn_browse.clicked.connect(self._on_browse)
        ws_layout.addWidget(self.btn_browse)

        layout.addLayout(ws_layout)

        # Workspace hint
        self.lbl_hint = QLabel(t("lbl_workspace_hint"), self)
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        # Migration checkbox
        self.chk_migrate = QCheckBox(t("chk_migrate_data"), self)
        self.chk_migrate.setChecked(True)
        self.chk_migrate.setVisible(False)
        layout.addWidget(self.chk_migrate)

        # Language selection
        lang_layout = QHBoxLayout()
        lang_layout.setSpacing(10)
        self.lbl_app_lang = QLabel(t("language_label"), self)
        f_lang = self.lbl_app_lang.font()
        f_lang.setBold(True)
        self.lbl_app_lang.setFont(f_lang)
        lang_layout.addWidget(self.lbl_app_lang)

        self.combo_app_lang = QComboBox(self)
        self.combo_app_lang.addItems(["English", "Français"])
        self.combo_app_lang.setCurrentText("English" if self.initial_language == "en" else "Français")
        self.combo_app_lang.currentTextChanged.connect(self._on_lang_changed)
        lang_layout.addWidget(self.combo_app_lang)
        lang_layout.addStretch()

        layout.addLayout(lang_layout)

        layout.addStretch()

        # Bottom buttons: Cancel and Save
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_box.addStretch()

        self.btn_cancel = QPushButton(t("btn_cancel"), self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(t("btn_save"), self)
        self.btn_save.setDefault(True)
        self.btn_save.setMinimumWidth(90)
        btn_save_font = self.btn_save.font()
        btn_save_font.setBold(True)
        self.btn_save.setFont(btn_save_font)
        self.btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _on_lang_changed(self, text: str):
        selected_code = "en" if text == "English" else "fr"
        self.new_language = selected_code
        set_language(selected_code)
        self._retranslate()

    def _retranslate(self):
        self.setWindowTitle(t("dlg_settings_title"))
        self.lbl_ws.setText(t("lbl_workspace_dir"))
        self.btn_browse.setText(t("btn_browse"))
        self.lbl_hint.setText(t("lbl_workspace_hint"))
        self.chk_migrate.setText(t("chk_migrate_data"))
        self.lbl_app_lang.setText(t("language_label"))
        self.btn_cancel.setText(t("btn_cancel"))
        self.btn_save.setText(t("btn_save"))

    def reject(self):
        if get_language() != self.initial_language:
            set_language(self.initial_language)
        super().reject()

    def _on_ws_text_changed(self, text: str):
        target = Path(text.strip()).resolve() if text.strip() else self.current_workspace
        old_configs = self.current_workspace / "configs"
        if target != self.current_workspace and old_configs.is_dir():
            has_items = any(old_configs.iterdir())
            self.chk_migrate.setVisible(has_items)
        else:
            self.chk_migrate.setVisible(False)

    def _on_browse(self):
        curr = self.edit_ws.text().strip() or str(self.current_workspace)
        chosen = NativeFileBrowser.get_existing_directory(self, caption=t("dlg_settings_title"), start_dir=curr)
        if chosen:
            self.edit_ws.setText(chosen)

    def _on_save(self):
        txt = self.edit_ws.text().strip()
        if not txt:
            return
        target = Path(txt).resolve()
        self.new_workspace = target
        self.migrate_requested = self.chk_migrate.isChecked() and not self.chk_migrate.isHidden()

        self.new_language = "en" if self.combo_app_lang.currentText() == "English" else "fr"
        set_language(self.new_language)
        from .app_settings import set_saved_language
        set_saved_language(self.new_language)
        self.accept()


class PhoebusBuilderGUI(QMainWindow):
    """Native PySide6 desktop application for building native Phoebus packages."""

    def __init__(self, initial_config: Optional[BuildConfig] = None, base_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.config = initial_config or BuildConfig()
        self.base_dir = Path(base_dir).resolve() if base_dir else get_workspace_dir()

        # Host environment detection
        self.is_windows = platform.system().lower() == "windows"
        self.current_os = platform.system()

        # Worker threads
        self.build_thread: Optional[BuildWorkerThread] = None
        self.sources_thread: Optional[SourcesDownloadWorkerThread] = None
        self.jvm_thread: Optional[JvmDownloadWorkerThread] = None
        self.maven_thread: Optional[MavenDownloadWorkerThread] = None
        self.wix_thread: Optional[WixDownloadWorkerThread] = None
        self._updating_modules: bool = False

        # Build native UI layout
        self._setup_window()
        self._init_ui()

        # Initial translation pass
        self.retranslateUi()

        # Load initial profiles & data
        self._refresh_profiles_list()
        projects = self._list_projects()
        if projects:
            self._load_selected_profile(0)
        else:
            self._sync_config_to_ui()
            self._prompt_new_project()

    def _setup_window(self):
        """Configures window geometry, icon and base properties."""
        self.resize(1000, 780)
        self.setMinimumSize(920, 650)
        icon_path = Path(__file__).parent / "assets" / "phoebus-builder.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def changeEvent(self, event: QEvent):
        """Native Qt event triggered when a new QTranslator is installed."""
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslateUi()
        super().changeEvent(event)

    def _msg_info(self, title: str, message: str, button_text: Optional[str] = None):
        """Displays a clean informational message box with an explicit, well-sized button."""
        box = QMessageBox(QMessageBox.Icon.Information, title, message, QMessageBox.StandardButton.NoButton, self)
        btn = box.addButton(button_text or t("btn_ok"), QMessageBox.ButtonRole.AcceptRole)
        btn.setMinimumWidth(85)
        box.setDefaultButton(btn)
        box.exec()

    def _msg_warning(self, title: str, message: str, button_text: Optional[str] = None):
        """Displays a clean warning message box with an explicit, well-sized button."""
        box = QMessageBox(QMessageBox.Icon.Warning, title, message, QMessageBox.StandardButton.NoButton, self)
        btn = box.addButton(button_text or t("btn_ok"), QMessageBox.ButtonRole.AcceptRole)
        btn.setMinimumWidth(85)
        box.setDefaultButton(btn)
        box.exec()

    def _msg_error(self, title: str, message: str, button_text: Optional[str] = None):
        """Displays a clean error message box with an explicit, well-sized button."""
        box = QMessageBox(QMessageBox.Icon.Critical, title, message, QMessageBox.StandardButton.NoButton, self)
        btn = box.addButton(button_text or t("btn_close"), QMessageBox.ButtonRole.AcceptRole)
        btn.setMinimumWidth(85)
        box.setDefaultButton(btn)
        box.exec()

    def _msg_confirm(self, title: str, message: str, yes_text: Optional[str] = None, no_text: Optional[str] = None, default_yes: bool = False) -> bool:
        """Displays a clean confirmation question box with explicit Yes/No buttons."""
        box = QMessageBox(QMessageBox.Icon.Question, title, message, QMessageBox.StandardButton.NoButton, self)
        btn_yes = box.addButton(yes_text or t("btn_yes"), QMessageBox.ButtonRole.YesRole)
        btn_no = box.addButton(no_text or t("btn_no"), QMessageBox.ButtonRole.NoRole)
        btn_yes.setMinimumWidth(85)
        btn_no.setMinimumWidth(85)
        box.setDefaultButton(btn_yes if default_yes else btn_no)
        box.exec()
        return box.clickedButton() == btn_yes

    def _get_online_tags(self) -> List[str]:
        """Fetches official Phoebus release tags from GitHub or falls back smoothly if offline."""
        try:
            return fetch_recent_phoebus_tags()
        except Exception:
            return ["v5.0.5", "v5.0.2", "v4.7.3", "v4.7.2"]


    def _init_ui(self):
        """Builds standard native widgets and layouts."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Top Header & Project Selection Bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(10)

        # Visual frame grouping all project-specific controls
        self.proj_frame = QFrame(central_widget)
        self.proj_frame.setObjectName("project_bar_frame")
        self.proj_frame.setStyleSheet("""
            QFrame#project_bar_frame {
                border: 1px solid rgba(128, 128, 128, 0.28);
                border-radius: 6px;
                background-color: rgba(128, 128, 128, 0.06);
            }
        """)
        proj_layout = QHBoxLayout(self.proj_frame)
        proj_layout.setContentsMargins(8, 4, 8, 4)
        proj_layout.setSpacing(6)

        self.lbl_proj_bar = QLabel(self.proj_frame)
        font_proj = self.lbl_proj_bar.font()
        font_proj.setBold(True)
        self.lbl_proj_bar.setFont(font_proj)
        proj_layout.addWidget(self.lbl_proj_bar)

        self.profile_combo = QComboBox(self.proj_frame)
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.currentIndexChanged.connect(self._load_selected_profile)
        proj_layout.addWidget(self.profile_combo)

        # Vertical separator between project selector and project buttons
        proj_sep = QFrame(self.proj_frame)
        proj_sep.setFrameShape(QFrame.VLine)
        proj_sep.setFrameShadow(QFrame.Sunken)
        proj_layout.addWidget(proj_sep)

        self.btn_save_proj = QPushButton(self.proj_frame)
        self.btn_save_proj.clicked.connect(self._save_current_profile)
        proj_layout.addWidget(self.btn_save_proj)

        self.btn_new_proj = QPushButton(self.proj_frame)
        self.btn_new_proj.clicked.connect(self._prompt_new_project)
        proj_layout.addWidget(self.btn_new_proj)

        self.btn_proj_actions = QPushButton(self.proj_frame)
        proj_menu = QMenu(self.btn_proj_actions)
        self.action_export_proj = proj_menu.addAction("")
        self.action_export_proj.triggered.connect(self._export_current_project)
        self.action_import_proj = proj_menu.addAction("")
        self.action_import_proj.triggered.connect(self._import_project_zip)
        proj_menu.addSeparator()
        self.action_duplicate_proj = proj_menu.addAction("")
        self.action_duplicate_proj.triggered.connect(self._duplicate_current_project)
        self.action_open_dir_proj = proj_menu.addAction("")
        self.action_open_dir_proj.triggered.connect(self._open_project_directory)
        proj_menu.addSeparator()
        self.action_delete_proj = proj_menu.addAction("")
        self.action_delete_proj.triggered.connect(self._delete_current_project)
        self.btn_proj_actions.setMenu(proj_menu)
        proj_layout.addWidget(self.btn_proj_actions)

        self.lbl_proj_status = QLabel(self.proj_frame)
        self.lbl_proj_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: bold; margin-left: 4px;")
        proj_layout.addWidget(self.lbl_proj_status)

        top_bar.addWidget(self.proj_frame)
        top_bar.addStretch()

        self.btn_app_settings = QPushButton(central_widget)
        self.btn_app_settings.clicked.connect(self._open_app_settings)
        top_bar.addWidget(self.btn_app_settings)

        main_layout.addLayout(top_bar)

        self.tab_widget = QTabWidget(central_widget)
        main_layout.addWidget(self.tab_widget, 1)

        self.tab_tech = QWidget()
        self._init_tab_tech()
        self.tab_widget.addTab(self.tab_tech, "")

        self.tab_identity = QWidget()
        self._init_tab_identity()
        self.tab_widget.addTab(self.tab_identity, "")

        self.tab_settings = QWidget()
        self._init_tab_settings()
        self.tab_widget.addTab(self.tab_settings, "")

        self.tab_modules = QWidget()
        self._init_tab_modules()
        self.tab_widget.addTab(self.tab_modules, "")

        self.tab_logo = QWidget()
        self._init_tab_logo()
        self.tab_widget.addTab(self.tab_logo, "")

        self.tab_splash = QWidget()
        self._init_tab_splash()
        self.tab_widget.addTab(self.tab_splash, "")

        self.tab_build = QWidget()
        self._init_tab_build()
        self.tab_widget.addTab(self.tab_build, "")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _format_section_header(self, title_lbl: QLabel, sub_lbl: QLabel):
        f = title_lbl.font()
        f.setBold(True)
        title_lbl.setFont(f)
        sub_lbl.setWordWrap(True)

    def _init_tab_tech(self):
        layout = QVBoxLayout(self.tab_tech)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_tech_title = QLabel(self.tab_tech)
        layout.addWidget(self.lbl_tech_title)

        self.lbl_tech_sub = QLabel(self.tab_tech)
        layout.addWidget(self.lbl_tech_sub)
        self._format_section_header(self.lbl_tech_title, self.lbl_tech_sub)

        form_group = QGroupBox("", self.tab_tech)
        form_layout = QGridLayout(form_group)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(14)
        row = 0

        # --- Section Phoebus Sources ---
        self.lbl_sources_mode = QLabel(t("sources_mode_label"), form_group)
        form_layout.addWidget(self.lbl_sources_mode, row, 0)
        src_mode_box = QHBoxLayout()
        self.radio_src_github = QRadioButton(t("sources_mode_github"), form_group)
        self.radio_src_local = QRadioButton(t("sources_mode_local"), form_group)
        self.radio_src_github.setChecked(True)
        self.bg_src_mode = QButtonGroup(form_group)
        self.bg_src_mode.addButton(self.radio_src_github)
        self.bg_src_mode.addButton(self.radio_src_local)
        src_mode_box.addWidget(self.radio_src_github)
        src_mode_box.addWidget(self.radio_src_local)
        src_mode_box.addStretch()
        self.radio_src_github.toggled.connect(self._on_sources_mode_changed)
        form_layout.addLayout(src_mode_box, row, 1)
        row += 1

        # Phoebus GitHub version
        self.lbl_phoebus_version = QLabel(t("phoebus_version_label"), form_group)
        form_layout.addWidget(self.lbl_phoebus_version, row, 0)
        recent_tags = self._get_online_tags()
        self.recent_tags_list = recent_tags if recent_tags else ["v5.0.5", "v5.0.2"]
        self.combo_tags = QComboBox(form_group)
        self.combo_tags.setMinimumWidth(260)
        self.combo_tags.currentTextChanged.connect(self._on_tag_combo_changed)
        form_layout.addWidget(self.combo_tags, row, 1)

        # Phoebus Local sources path (hidden by default)
        self.lbl_local_sources = QLabel(t("local_sources_path_label"), form_group)
        self.lbl_local_sources.setVisible(False)
        form_layout.addWidget(self.lbl_local_sources, row, 0)

        local_src_box = QHBoxLayout()
        local_src_box.setSpacing(8)
        self.edit_local_sources = QLineEdit(form_group)
        self.edit_local_sources.setPlaceholderText(t("local_sources_placeholder"))
        self.edit_local_sources.textChanged.connect(self._on_local_sources_changed)
        self.edit_local_sources.setVisible(False)
        local_src_box.addWidget(self.edit_local_sources, 1)

        self.btn_browse_sources_dir = QPushButton(t("btn_browse_sources_dir"), form_group)
        self.btn_browse_sources_dir.clicked.connect(self._browse_sources_dir)
        self.btn_browse_sources_dir.setVisible(False)
        local_src_box.addWidget(self.btn_browse_sources_dir)

        self.btn_browse_sources_archive = QPushButton(t("btn_browse_sources_archive"), form_group)
        self.btn_browse_sources_archive.clicked.connect(self._browse_sources_archive)
        self.btn_browse_sources_archive.setVisible(False)
        local_src_box.addWidget(self.btn_browse_sources_archive)
        form_layout.addLayout(local_src_box, row, 1)
        row += 1

        # Custom Tag (hidden by default)
        self.lbl_custom_tag = QLabel(form_group)
        self.edit_custom_tag = QLineEdit(form_group)
        self.edit_custom_tag.setMinimumWidth(260)
        self.lbl_custom_tag.setVisible(False)
        self.edit_custom_tag.setVisible(False)
        self.edit_custom_tag.textChanged.connect(self._on_custom_tag_changed)
        form_layout.addWidget(self.lbl_custom_tag, row, 0)
        form_layout.addWidget(self.edit_custom_tag, row, 1)
        row += 1

        # Phoebus sources status & download button
        self.lbl_sources_status_title = QLabel(form_group)
        form_layout.addWidget(self.lbl_sources_status_title, row, 0)

        src_box = QHBoxLayout()
        src_box.setSpacing(10)
        self.lbl_sources_status = QLabel(form_group)
        src_box.addWidget(self.lbl_sources_status)

        self.btn_download_sources = QPushButton(form_group)
        self.btn_download_sources.clicked.connect(self._start_sources_download)
        src_box.addWidget(self.btn_download_sources)

        self.sources_download_progress = QProgressBar(form_group)
        self.sources_download_progress.setRange(0, 0)
        self.sources_download_progress.setMaximumWidth(160)
        self.sources_download_progress.setVisible(False)
        src_box.addWidget(self.sources_download_progress)
        src_box.addStretch()
        form_layout.addLayout(src_box, row, 1)
        row += 1

        # --- Section JVM (Java) ---
        self.lbl_jvm_mode = QLabel(t("jvm_mode_label"), form_group)
        form_layout.addWidget(self.lbl_jvm_mode, row, 0)
        jvm_mode_box = QHBoxLayout()
        self.radio_jvm_adoptium = QRadioButton(t("jvm_mode_adoptium"), form_group)
        self.radio_jvm_local = QRadioButton(t("jvm_mode_local"), form_group)
        self.radio_jvm_adoptium.setChecked(True)
        self.bg_jvm_mode = QButtonGroup(form_group)
        self.bg_jvm_mode.addButton(self.radio_jvm_adoptium)
        self.bg_jvm_mode.addButton(self.radio_jvm_local)
        jvm_mode_box.addWidget(self.radio_jvm_adoptium)
        jvm_mode_box.addWidget(self.radio_jvm_local)
        jvm_mode_box.addStretch()
        self.radio_jvm_adoptium.toggled.connect(self._on_jvm_mode_changed)
        form_layout.addLayout(jvm_mode_box, row, 1)
        row += 1

        # JVM Selector (Adoptium)
        self.lbl_java_version = QLabel(t("java_version_label"), form_group)
        form_layout.addWidget(self.lbl_java_version, row, 0)
        self.combo_java = QComboBox(form_group)
        self.combo_java.addItems(["25 (Adoptium Temurin)", "21 (LTS standard)", "17 (LTS)"])
        self.combo_java.setMinimumWidth(260)
        self.combo_java.currentTextChanged.connect(self._on_java_combo_changed)
        form_layout.addWidget(self.combo_java, row, 1)

        # JVM Local path (hidden by default)
        self.lbl_local_jdk = QLabel(t("local_jdk_path_label"), form_group)
        self.lbl_local_jdk.setVisible(False)
        form_layout.addWidget(self.lbl_local_jdk, row, 0)

        local_jdk_box = QHBoxLayout()
        local_jdk_box.setSpacing(8)
        self.edit_local_jdk = QLineEdit(form_group)
        self.edit_local_jdk.setPlaceholderText(t("local_jdk_placeholder"))
        self.edit_local_jdk.textChanged.connect(self._on_local_jdk_changed)
        self.edit_local_jdk.setVisible(False)
        local_jdk_box.addWidget(self.edit_local_jdk, 1)

        self.btn_browse_jdk_dir = QPushButton(t("btn_browse_jdk_dir"), form_group)
        self.btn_browse_jdk_dir.clicked.connect(self._browse_jdk_dir)
        self.btn_browse_jdk_dir.setVisible(False)
        local_jdk_box.addWidget(self.btn_browse_jdk_dir)

        self.btn_detect_system_jdk = QPushButton(t("btn_detect_system_jdk"), form_group)
        self.btn_detect_system_jdk.clicked.connect(self._detect_system_jdk)
        self.btn_detect_system_jdk.setVisible(False)
        local_jdk_box.addWidget(self.btn_detect_system_jdk)
        form_layout.addLayout(local_jdk_box, row, 1)
        row += 1

        # JVM Status & Download
        self.lbl_jvm_status_title = QLabel(form_group)
        form_layout.addWidget(self.lbl_jvm_status_title, row, 0)

        jvm_box = QHBoxLayout()
        jvm_box.setSpacing(10)
        self.lbl_jvm_status = QLabel(form_group)
        jvm_box.addWidget(self.lbl_jvm_status)

        self.btn_download_jvm = QPushButton(form_group)
        self.btn_download_jvm.clicked.connect(self._start_jvm_download)
        jvm_box.addWidget(self.btn_download_jvm)

        self.jvm_download_progress = QProgressBar(form_group)
        self.jvm_download_progress.setRange(0, 0)
        self.jvm_download_progress.setMaximumWidth(160)
        self.jvm_download_progress.setVisible(False)
        jvm_box.addWidget(self.jvm_download_progress)
        jvm_box.addStretch()
        form_layout.addLayout(jvm_box, row, 1)
        row += 1

        # --- Section Maven ---
        self.lbl_maven_mode = QLabel(t("maven_mode_label"), form_group)
        form_layout.addWidget(self.lbl_maven_mode, row, 0)
        mvn_mode_box = QHBoxLayout()
        self.radio_mvn_auto = QRadioButton(t("maven_mode_auto"), form_group)
        self.radio_mvn_local = QRadioButton(t("maven_mode_local"), form_group)
        self.radio_mvn_auto.setChecked(True)
        self.bg_mvn_mode = QButtonGroup(form_group)
        self.bg_mvn_mode.addButton(self.radio_mvn_auto)
        self.bg_mvn_mode.addButton(self.radio_mvn_local)
        mvn_mode_box.addWidget(self.radio_mvn_auto)
        mvn_mode_box.addWidget(self.radio_mvn_local)
        mvn_mode_box.addStretch()
        self.radio_mvn_auto.toggled.connect(self._on_maven_mode_changed)
        form_layout.addLayout(mvn_mode_box, row, 1)
        row += 1

        # Local Maven path (hidden by default)
        self.lbl_local_maven = QLabel(t("local_maven_path_label"), form_group)
        self.lbl_local_maven.setVisible(False)
        form_layout.addWidget(self.lbl_local_maven, row, 0)

        local_mvn_box = QHBoxLayout()
        local_mvn_box.setSpacing(8)
        self.edit_local_maven = QLineEdit(form_group)
        self.edit_local_maven.setPlaceholderText(t("local_maven_placeholder"))
        self.edit_local_maven.textChanged.connect(self._on_local_maven_changed)
        self.edit_local_maven.setVisible(False)
        local_mvn_box.addWidget(self.edit_local_maven, 1)

        self.btn_browse_maven_dir = QPushButton(t("btn_browse_maven_dir"), form_group)
        self.btn_browse_maven_dir.clicked.connect(self._browse_maven_dir)
        self.btn_browse_maven_dir.setVisible(False)
        local_mvn_box.addWidget(self.btn_browse_maven_dir)
        form_layout.addLayout(local_mvn_box, row, 1)
        row += 1

        # Maven Status & Download
        self.lbl_maven_status_title = QLabel(form_group)
        form_layout.addWidget(self.lbl_maven_status_title, row, 0)

        maven_box = QHBoxLayout()
        maven_box.setSpacing(10)
        self.lbl_maven_status = QLabel(form_group)
        maven_box.addWidget(self.lbl_maven_status)

        self.btn_download_maven = QPushButton(form_group)
        self.btn_download_maven.clicked.connect(self._start_maven_download)
        maven_box.addWidget(self.btn_download_maven)

        self.maven_download_progress = QProgressBar(form_group)
        self.maven_download_progress.setRange(0, 0)
        self.maven_download_progress.setMaximumWidth(160)
        self.maven_download_progress.setVisible(False)
        maven_box.addWidget(self.maven_download_progress)
        maven_box.addStretch()
        form_layout.addLayout(maven_box, row, 1)
        row += 1

        # WiX Toolset (on Windows)
        if self.is_windows:
            self.lbl_wix_status_title = QLabel(form_group)
            form_layout.addWidget(self.lbl_wix_status_title, row, 0)

            wix_box = QHBoxLayout()
            wix_box.setSpacing(10)
            self.lbl_wix_status = QLabel(form_group)
            wix_box.addWidget(self.lbl_wix_status)

            self.btn_download_wix = QPushButton(form_group)
            self.btn_download_wix.clicked.connect(self._start_wix_download)
            wix_box.addWidget(self.btn_download_wix)

            self.wix_download_progress = QProgressBar(form_group)
            self.wix_download_progress.setRange(0, 0)
            self.wix_download_progress.setMaximumWidth(160)
            self.wix_download_progress.setVisible(False)
            wix_box.addWidget(self.wix_download_progress)
            wix_box.addStretch()

            form_layout.addLayout(wix_box, row, 1)
            row += 1

            self.lbl_win_pkg = QLabel(form_group)
            form_layout.addWidget(self.lbl_win_pkg, row, 0)

            win_box = QHBoxLayout()
            self.radio_msi = QRadioButton("MSI (.msi)", form_group)
            self.radio_exe = QRadioButton("EXE (.exe)", form_group)
            self.radio_msi.setChecked(True)
            win_box.addWidget(self.radio_msi)
            win_box.addWidget(self.radio_exe)
            win_box.addStretch()
            form_layout.addLayout(win_box, row, 1)
            row += 1

        self.chk_force_maven = QCheckBox(t("force_maven_label"), form_group)
        self.chk_force_maven.setToolTip(t("force_maven_hint"))
        form_layout.addWidget(self.chk_force_maven, row, 1)
        row += 1

        self.chk_clean_temp_build = QCheckBox(t("clean_temp_build_label"), form_group)
        self.chk_clean_temp_build.setToolTip(t("clean_temp_build_hint"))
        self.chk_clean_temp_build.setChecked(True)
        form_layout.addWidget(self.chk_clean_temp_build, row, 1)
        row += 1

        form_layout.setColumnStretch(1, 1)
        layout.addWidget(form_group)
        layout.addStretch()

    def _on_custom_tag_changed(self, text: str):
        if text.strip():
            self.config.phoebus_branch = text.strip()
            self._update_sources_status()
            if hasattr(self, "modules_scroll_layout"):
                self._populate_modules_ui()

    def _on_tag_combo_changed(self, text: str):
        is_other = text in (t("other_version_option"), "Autre version spécifique...", "Other specific version...")
        self.lbl_custom_tag.setVisible(is_other)
        self.edit_custom_tag.setVisible(is_other)
        tag = self.edit_custom_tag.text().strip() if is_other else text
        if tag:
            self.config.phoebus_branch = tag
            clean_ver = tag.lstrip("vV")
            if hasattr(self, "edit_app_version") and clean_ver:
                self.edit_app_version.setText(clean_ver)
            self._update_sources_status()
            if hasattr(self, "modules_scroll_layout"):
                self._populate_modules_ui()

    def _on_sources_mode_changed(self):
        is_local = self.radio_src_local.isChecked()
        self.config.use_local_sources = is_local

        self.lbl_phoebus_version.setVisible(not is_local)
        self.combo_tags.setVisible(not is_local)
        is_other = self.combo_tags.currentText() in (t("other_version_option"), "Autre version spécifique...", "Other specific version...")
        self.lbl_custom_tag.setVisible(not is_local and is_other)
        self.edit_custom_tag.setVisible(not is_local and is_other)
        self.btn_download_sources.setVisible(not is_local)

        self.lbl_local_sources.setVisible(is_local)
        self.edit_local_sources.setVisible(is_local)
        self.btn_browse_sources_dir.setVisible(is_local)
        self.btn_browse_sources_archive.setVisible(is_local)

        self._update_sources_status()
        if hasattr(self, "modules_scroll_layout"):
            self._populate_modules_ui()

    def _on_local_sources_changed(self, text: str):
        self.config.local_sources_path = text.strip()
        self._update_sources_status()
        if hasattr(self, "modules_scroll_layout"):
            self._populate_modules_ui()

    def _browse_sources_dir(self):
        d = NativeFileBrowser.get_existing_directory(self, caption=t("sources_mode_local"))
        if d:
            self.edit_local_sources.setText(d)
            self.config.local_sources_path = d
            self._update_sources_status()
            if hasattr(self, "modules_scroll_layout"):
                self._populate_modules_ui()

    def _browse_sources_archive(self):
        f = NativeFileBrowser.get_open_file_name(
            self,
            caption=t("sources_mode_local"),
            filter="Archives (*.tar.gz *.tgz *.zip);;All Files (*.*)"
        )
        if f:
            self.edit_local_sources.setText(f)
            self.config.local_sources_path = f
            self._update_sources_status()

    def _on_jvm_mode_changed(self):
        is_local = self.radio_jvm_local.isChecked()
        self.config.use_local_jdk = is_local

        self.lbl_java_version.setVisible(not is_local)
        self.combo_java.setVisible(not is_local)
        self.btn_download_jvm.setVisible(not is_local)

        self.lbl_local_jdk.setVisible(is_local)
        self.edit_local_jdk.setVisible(is_local)
        self.btn_browse_jdk_dir.setVisible(is_local)
        self.btn_detect_system_jdk.setVisible(is_local)

        self._update_jvm_status()

    def _on_local_jdk_changed(self, text: str):
        self.config.local_jdk_path = text.strip()
        self._update_jvm_status()

    def _browse_jdk_dir(self):
        d = NativeFileBrowser.get_existing_directory(self, caption=t("jvm_mode_local"))
        if d:
            self.edit_local_jdk.setText(d)
            self.config.local_jdk_path = d
            self._update_jvm_status()

    def _detect_system_jdk(self):
        jdks = JvmManager.detect_system_jdks(self.is_windows)
        if jdks:
            self.edit_local_jdk.setText(str(jdks[0]))
            self.config.local_jdk_path = str(jdks[0])
            self._update_jvm_status()
            self.log(f"[OK] System JDK detected: {jdks[0]}")
        else:
            self._msg_info(t("dlg_info_title"), "Aucun JDK compatible détecté avec JAVA_HOME ou les chemins système.")

    def _on_maven_mode_changed(self):
        is_local = self.radio_mvn_local.isChecked()
        self.config.use_local_maven = is_local
        self.btn_download_maven.setVisible(not is_local)

        self.lbl_local_maven.setVisible(is_local)
        self.edit_local_maven.setVisible(is_local)
        self.btn_browse_maven_dir.setVisible(is_local)

        self._update_maven_status()

    def _on_local_maven_changed(self, text: str):
        self.config.local_maven_path = text.strip()
        self._update_maven_status()

    def _browse_maven_dir(self):
        d = NativeFileBrowser.get_existing_directory(self, caption=t("maven_mode_local"))
        if d:
            self.edit_local_maven.setText(d)
            self.config.local_maven_path = d
            self._update_maven_status()

    def _get_active_jdk_dir(self) -> Path:
        j_ver = self.config.version_java or "25"
        j_ver_clean = str(j_ver).split()[0]
        return self.base_dir / "sources" / "jdk" / f"jdk-{j_ver_clean}-{'win' if self.is_windows else 'linux'}"

    def _is_jvm_ready(self) -> bool:
        if hasattr(self, "radio_jvm_local") and self.radio_jvm_local.isChecked():
            if not self.config.local_jdk_path:
                return False
            p = Path(self.config.local_jdk_path)
            if not p.is_absolute():
                p = self.base_dir / p
            if p.is_dir():
                if JvmManager.is_jdk_ready(p, self.is_windows):
                    return True
                if (p / "Contents" / "Home").is_dir() and JvmManager.is_jdk_ready(p / "Contents" / "Home", self.is_windows):
                    return True
            if p.is_file() and p.name.lower().endswith((".tar.gz", ".tgz", ".zip")) and p.exists():
                return True
            return False

        jdk_path = self._get_active_jdk_dir()
        if JvmManager.is_jdk_ready(jdk_path, self.is_windows):
            return True
        proj_name = self.config.app_name.lower().replace(" ", "_") if self.config.app_name else "project"
        legacy_dir = self.base_dir / "configs" / proj_name / "build" / ("jdk_win" if self.is_windows else "jdk")
        return JvmManager.is_jdk_ready(legacy_dir, self.is_windows)

    def _on_java_combo_changed(self, text: str):
        j_ver = text.strip()
        if j_ver.startswith("25"):
            self.config.version_java = "25"
        elif j_ver.startswith("21"):
            self.config.version_java = "21"
        elif j_ver.startswith("17"):
            self.config.version_java = "17"
        else:
            self.config.version_java = j_ver.split()[0]
        self._update_jvm_status()

    def _update_build_button_state(self):
        if not hasattr(self, "btn_build"):
            return
        if self.build_thread and self.build_thread.isRunning():
            return

        sources_ready = (self._find_active_product_pom() is not None)
        if not sources_ready and hasattr(self, "radio_src_local") and self.radio_src_local.isChecked() and self.config.local_sources_path:
            p_src = Path(self.config.local_sources_path)
            if p_src.is_file() and p_src.name.lower().endswith((".tar.gz", ".tgz", ".zip")) and p_src.exists():
                sources_ready = True

        jvm_ready = self._is_jvm_ready()
        all_ready = sources_ready and jvm_ready

        self.btn_build.setEnabled(all_ready)
        if not sources_ready:
            self.btn_build.setToolTip(t("build_disabled_no_sources"))
        elif not jvm_ready:
            self.btn_build.setToolTip(t("build_disabled_no_jvm"))
        else:
            self.btn_build.setToolTip("")

    def _update_sources_status(self):
        if not hasattr(self, "lbl_sources_status"):
            return

        is_local = hasattr(self, "radio_src_local") and self.radio_src_local.isChecked()
        if is_local:
            active_pom = self._find_active_product_pom()
            is_ready = active_pom is not None and active_pom.exists() and active_pom.stat().st_size > 0
            if not is_ready and self.config.local_sources_path:
                p = Path(self.config.local_sources_path)
                if p.is_file() and p.name.lower().endswith((".tar.gz", ".tgz", ".zip")) and p.exists():
                    is_ready = True

            if is_ready:
                self.lbl_sources_status.setText(f"<span style='color: #4ec9b0; font-weight: bold;'>{t('sources_status_local_ready')}</span>")
            else:
                self.lbl_sources_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('sources_status_local_invalid')}</span>")
        else:
            tag = self.config.phoebus_branch or "v5.0.5"
            active_pom = self._find_active_product_pom()
            is_ready = active_pom is not None and active_pom.exists() and active_pom.stat().st_size > 0

            if is_ready:
                self.lbl_sources_status.setText(f"<span style='color: #4ec9b0; font-weight: bold;'>{t('sources_status_ready', version=tag)}</span>")
                self.btn_download_sources.setText(f"✓ {t('btn_download_sources')}")
                self.btn_download_sources.setEnabled(True)
            else:
                self.lbl_sources_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('sources_status_missing')}</span>")
                self.btn_download_sources.setText(f"⬇ {t('btn_download_sources')}")
                self.btn_download_sources.setEnabled(True)

        self._update_build_button_state()

    def _update_jvm_status(self):
        if not hasattr(self, "lbl_jvm_status"):
            return

        is_local = hasattr(self, "radio_jvm_local") and self.radio_jvm_local.isChecked()
        if is_local:
            is_ready = self._is_jvm_ready()
            if is_ready:
                detected_ver = ""
                p = Path(self.config.local_jdk_path) if self.config.local_jdk_path else None
                if p and p.is_dir():
                    detected_ver = JvmManager.get_jdk_version(p, self.is_windows)
                    if not detected_ver:
                        for sub in p.iterdir():
                            if sub.is_dir():
                                detected_ver = JvmManager.get_jdk_version(sub, self.is_windows)
                                if detected_ver:
                                    break
                lbl_txt = t('jvm_status_local_ready', version=detected_ver or self.config.version_java or "?")
                self.lbl_jvm_status.setText(f"<span style='color: #4ec9b0; font-weight: bold;'>{lbl_txt}</span>")
            else:
                self.lbl_jvm_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('jvm_status_local_invalid')}</span>")
        else:
            j_ver = str(self.config.version_java or "25").split()[0]
            is_ready = self._is_jvm_ready()

            if is_ready:
                self.lbl_jvm_status.setText(f"<span style='color: #4ec9b0; font-weight: bold;'>{t('jvm_status_ready', version=j_ver)}</span>")
                self.btn_download_jvm.setText(f"✓ {t('btn_download_jvm')}")
                self.btn_download_jvm.setEnabled(True)
            else:
                self.lbl_jvm_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('jvm_status_missing', version=j_ver)}</span>")
                self.btn_download_jvm.setText(f"⬇ {t('btn_download_jvm')}")
                self.btn_download_jvm.setEnabled(True)

        self._update_build_button_state()

    def _start_sources_download(self):
        if self.sources_thread and self.sources_thread.isRunning():
            return

        tag = self.combo_tags.currentText().strip()
        if tag in (t("other_version_option"), "Autre version spécifique...", "Other specific version..."):
            tag = self.edit_custom_tag.text().strip() or "v5.0.5"
        self.config.phoebus_branch = tag

        self.btn_download_sources.setEnabled(False)
        self.lbl_sources_status.setText(f"<span style='color: #569cd6;'>{t('sources_downloading', version=tag)}</span>")
        if hasattr(self, "sources_download_progress"):
            self.sources_download_progress.setVisible(True)

        self.sources_thread = SourcesDownloadWorkerThread(tag, self.base_dir, self.config.app_name)
        self.sources_thread.log_signal.connect(self.log)
        self.sources_thread.download_finished.connect(self._on_sources_download_finished)
        self.sources_thread.start()
        self.log(f"[>] {t('sources_downloading', version=tag)}")

    def _on_sources_download_finished(self, success: bool, result: str):
        if hasattr(self, "sources_download_progress"):
            self.sources_download_progress.setVisible(False)
        self.btn_download_sources.setEnabled(True)
        tag = self.config.phoebus_branch or "v5.0.5"

        if success:
            self.log(f"[OK] {t('sources_download_success', version=tag)}")
            self._update_sources_status()
            if hasattr(self, "modules_scroll_layout"):
                pom_to_use = self._find_active_product_pom()
                if pom_to_use and pom_to_use.exists():
                    discovered_ids = [m.artifact_id for m in PhoebusPomManager.discover_modules_from_pom(pom_to_use)]
                    if not self.config.enabled_modules or len(self.config.enabled_modules) >= len(PHOEBUS_MODULES):
                        self.config.enabled_modules = discovered_ids
                self._populate_modules_ui()
            self._msg_info(t("dlg_info_title"), t("sources_download_success", version=tag))
        else:
            self.log(f"[ERROR] {t('sources_download_error', error=result)}")
            self._update_sources_status()
            self._msg_error(t("dlg_build_error_title"), t("sources_download_error", error=result))

    def _start_jvm_download(self):
        if self.jvm_thread and self.jvm_thread.isRunning():
            return

        j_ver = str(self.config.version_java or "25").split()[0]
        self.btn_download_jvm.setEnabled(False)
        self.lbl_jvm_status.setText(f"<span style='color: #569cd6;'>{t('jvm_downloading', version=j_ver)}</span>")
        if hasattr(self, "jvm_download_progress"):
            self.jvm_download_progress.setVisible(True)

        self.jvm_thread = JvmDownloadWorkerThread(j_ver, self.is_windows, self.base_dir)
        self.jvm_thread.log_signal.connect(self.log)
        self.jvm_thread.download_finished.connect(self._on_jvm_download_finished)
        self.jvm_thread.start()
        self.log(f"[>] {t('jvm_downloading', version=j_ver)}")

    def _on_jvm_download_finished(self, success: bool, result: str):
        if hasattr(self, "jvm_download_progress"):
            self.jvm_download_progress.setVisible(False)
        self.btn_download_jvm.setEnabled(True)
        j_ver = str(self.config.version_java or "25").split()[0]

        if success:
            self.log(f"[OK] {t('jvm_download_success', version=j_ver)}")
            self._update_jvm_status()
            self._msg_info(t("dlg_info_title"), t("jvm_download_success", version=j_ver))
        else:
            self.log(f"[ERROR] {t('jvm_download_error', error=result)}")
            self._update_jvm_status()
            self._msg_error(t("dlg_build_error_title"), t("jvm_download_error", error=result))

    def _is_maven_ready(self) -> Tuple[bool, str]:
        if hasattr(self, "radio_mvn_local") and self.radio_mvn_local.isChecked():
            if not self.config.local_maven_path:
                return False, "missing"
            p = Path(self.config.local_maven_path)
            if not p.is_absolute():
                p = self.base_dir / p
            if p.is_dir():
                if DownloadManager.is_maven_ready(p):
                    return True, "local"
            if p.is_file():
                if p.name.lower() in ("mvn", "mvn.cmd", "mvn.bat"):
                    return True, "local"
                if p.name.lower().endswith((".zip", ".tar.gz", ".tgz")):
                    return True, "local"
            return False, "missing"

        shared_maven = self.base_dir / "sources" / "maven"
        if DownloadManager.is_maven_ready(shared_maven):
            return True, "sources"
        mvn_bin = "mvn.cmd" if self.is_windows else "mvn"
        if shutil.which(mvn_bin) or shutil.which("mvn"):
            return True, "sys"
        return False, "missing"

    def _update_maven_status(self):
        if not hasattr(self, "lbl_maven_status"):
            return
        ready, loc = self._is_maven_ready()
        if ready:
            if loc == "local":
                txt = f"<span style='color: #4ec9b0; font-weight: bold;'>{t('maven_status_local_ready')}</span>"
            elif loc == "sys":
                txt = f"<span style='color: #4ec9b0; font-weight: bold;'>{t('maven_status_ready_sys')}</span>"
            else:
                txt = f"<span style='color: #4ec9b0; font-weight: bold;'>{t('maven_status_ready_sources')}</span>"
            self.lbl_maven_status.setText(txt)
            self.btn_download_maven.setText(f"✓ {t('btn_download_maven')}")
            self.btn_download_maven.setEnabled(True)
        else:
            if hasattr(self, "radio_mvn_local") and self.radio_mvn_local.isChecked():
                self.lbl_maven_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('maven_status_local_invalid')}</span>")
            else:
                self.lbl_maven_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('maven_status_missing')}</span>")
            self.btn_download_maven.setText(f"⬇ {t('btn_download_maven')}")
            self.btn_download_maven.setEnabled(True)

    def _start_maven_download(self):
        if self.maven_thread and self.maven_thread.isRunning():
            return
        self.btn_download_maven.setEnabled(False)
        self.lbl_maven_status.setText(f"<span style='color: #569cd6;'>{t('maven_downloading')}</span>")
        if hasattr(self, "maven_download_progress"):
            self.maven_download_progress.setVisible(True)

        self.maven_thread = MavenDownloadWorkerThread(self.base_dir)
        self.maven_thread.log_signal.connect(self.log)
        self.maven_thread.download_finished.connect(self._on_maven_download_finished)
        self.maven_thread.start()
        self.log(f"[>] {t('maven_downloading')}")

    def _on_maven_download_finished(self, success: bool, result: str):
        if hasattr(self, "maven_download_progress"):
            self.maven_download_progress.setVisible(False)
        self.btn_download_maven.setEnabled(True)
        if success:
            self.log(f"[OK] {t('maven_download_success')}")
            self._update_maven_status()
            self._msg_info(t("dlg_info_title"), t("maven_download_success"))
        else:
            self.log(f"[ERROR] {t('maven_download_error', error=result)}")
            self._update_maven_status()
            self._msg_error(t("dlg_build_error_title"), t("maven_download_error", error=result))

    def _is_wix_ready(self) -> Tuple[bool, str]:
        if not self.is_windows:
            return True, "sys"
        if shutil.which("candle.exe") and shutil.which("light.exe"):
            return True, "sys"
        shared_wix = self.base_dir / "sources" / "wix"
        if DownloadManager.is_wix_ready(shared_wix):
            return True, "sources"
        return False, "missing"

    def _update_wix_status(self):
        if not self.is_windows or not hasattr(self, "lbl_wix_status"):
            return
        ready, loc = self._is_wix_ready()
        if ready:
            txt_key = "wix_status_ready_sys" if loc == "sys" else "wix_status_ready_sources"
            self.lbl_wix_status.setText(f"<span style='color: #4ec9b0; font-weight: bold;'>{t(txt_key)}</span>")
            self.btn_download_wix.setText(f"✓ {t('btn_download_wix')}")
            self.btn_download_wix.setEnabled(True)
        else:
            self.lbl_wix_status.setText(f"<span style='color: #ce9178; font-weight: bold;'>{t('wix_status_missing')}</span>")
            self.btn_download_wix.setText(f"⬇ {t('btn_download_wix')}")
            self.btn_download_wix.setEnabled(True)

    def _start_wix_download(self):
        if not self.is_windows:
            return
        if self.wix_thread and self.wix_thread.isRunning():
            return
        self.btn_download_wix.setEnabled(False)
        self.lbl_wix_status.setText(f"<span style='color: #569cd6;'>{t('wix_downloading')}</span>")
        if hasattr(self, "wix_download_progress"):
            self.wix_download_progress.setVisible(True)

        self.wix_thread = WixDownloadWorkerThread(self.base_dir, self.config.wix_url)
        self.wix_thread.log_signal.connect(self.log)
        self.wix_thread.download_finished.connect(self._on_wix_download_finished)
        self.wix_thread.start()
        self.log(f"[>] {t('wix_downloading')}")

    def _on_wix_download_finished(self, success: bool, result: str):
        if hasattr(self, "wix_download_progress"):
            self.wix_download_progress.setVisible(False)
        if hasattr(self, "btn_download_wix"):
            self.btn_download_wix.setEnabled(True)
        if success:
            self.log(f"[OK] {t('wix_download_success')}")
            self._update_wix_status()
            self._msg_info(t("dlg_info_title"), t("wix_download_success"))
        else:
            self.log(f"[ERROR] {t('wix_download_error', error=result)}")
            self._update_wix_status()
            self._msg_error(t("dlg_build_error_title"), t("wix_download_error", error=result))

    def _init_tab_identity(self):
        layout = QVBoxLayout(self.tab_identity)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_identity_title = QLabel(self.tab_identity)
        layout.addWidget(self.lbl_identity_title)

        self.lbl_identity_sub = QLabel(self.tab_identity)
        layout.addWidget(self.lbl_identity_sub)
        self._format_section_header(self.lbl_identity_title, self.lbl_identity_sub)

        form_group = QGroupBox("", self.tab_identity)
        f_layout = QGridLayout(form_group)
        f_layout.setContentsMargins(14, 14, 14, 14)
        f_layout.setVerticalSpacing(10)
        f_layout.setHorizontalSpacing(14)

        self.edit_app_name = QLineEdit(form_group)
        self.edit_app_name.textChanged.connect(self._on_app_name_changed)

        self.edit_app_version = QLineEdit(form_group)
        self.edit_app_desc = QLineEdit(form_group)
        self.edit_app_vendor = QLineEdit(form_group)
        self.edit_app_copyright = QLineEdit(form_group)
        self.edit_app_url = QLineEdit(form_group)
        self.edit_deb_maintainer = QLineEdit(form_group)

        self.identity_labels = {}
        fields = [
            ("app_name_label", self.edit_app_name, "Ex: MyPhoebusApp"),
            ("app_version_label", self.edit_app_version, "Ex: 1.0.0 / 5.0.2"),
            ("app_desc_label", self.edit_app_desc, "Ex: EPICS Control Interface"),
            ("app_vendor_label", self.edit_app_vendor, "Ex: My Organization"),
            ("app_copyright_label", self.edit_app_copyright, "Ex: Copyright (c) 2026"),
            ("app_url_label", self.edit_app_url, "Ex: https://example.org"),
            ("deb_maintainer_label", self.edit_deb_maintainer, "Ex: Support <support@example.org>"),
        ]

        for row, (key, edit, placeholder) in enumerate(fields):
            lbl = QLabel(form_group)
            self.identity_labels[key] = lbl
            edit.setPlaceholderText(placeholder)
            edit.setMinimumWidth(320)
            f_layout.addWidget(lbl, row, 0)
            f_layout.addWidget(edit, row, 1)

        layout.addWidget(form_group)
        layout.addStretch()

    def _on_app_name_changed(self, text: str):
        if text.strip():
            clean = text.strip().lower().replace(" ", "_")
            if hasattr(self, "edit_pref_folder"):
                current_pref = self.edit_pref_folder.text().strip()
                if not current_pref or current_pref.startswith("."):
                    self.edit_pref_folder.setText(f".{clean}")

    # --- TAB 3: SETTINGS & DISPLAYS ---
    def _init_tab_settings(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_settings_title = QLabel(self.tab_settings)
        layout.addWidget(self.lbl_settings_title)

        self.lbl_settings_sub = QLabel(self.tab_settings)
        layout.addWidget(self.lbl_settings_sub)
        self._format_section_header(self.lbl_settings_title, self.lbl_settings_sub)

        self.g_pref = QGroupBox(self.tab_settings)
        l_pref = QHBoxLayout(self.g_pref)
        l_pref.setContentsMargins(14, 14, 14, 14)
        self.edit_pref_folder = QLineEdit(self.g_pref)
        self.edit_pref_folder.setMinimumWidth(260)
        l_pref.addWidget(self.edit_pref_folder)
        self.lbl_pref_hint = QLabel(self.g_pref)
        l_pref.addWidget(self.lbl_pref_hint)
        l_pref.addStretch()
        layout.addWidget(self.g_pref)

        self.g_ini = QGroupBox(self.tab_settings)
        l_ini = QVBoxLayout(self.g_ini)
        l_ini.setContentsMargins(14, 14, 14, 14)
        l_ini.setSpacing(8)
        r_ini = QHBoxLayout()
        self.edit_settings_ini = QLineEdit(self.g_ini)
        r_ini.addWidget(self.edit_settings_ini)

        self.btn_browse_ini = QPushButton(self.g_ini)
        self.btn_browse_ini.clicked.connect(self._browse_settings_ini)
        r_ini.addWidget(self.btn_browse_ini)

        self.btn_edit_ini = QPushButton(self.g_ini)
        self.btn_edit_ini.clicked.connect(self._open_settings_editor)
        r_ini.addWidget(self.btn_edit_ini)
        l_ini.addLayout(r_ini)

        self.btn_gen_ini = QPushButton(self.g_ini)
        self.btn_gen_ini.clicked.connect(self._generate_new_settings_ini)
        l_ini.addWidget(self.btn_gen_ini, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.g_ini)

        self.g_ui = QGroupBox(self.tab_settings)
        l_ui = QVBoxLayout(self.g_ui)
        l_ui.setContentsMargins(14, 14, 14, 14)
        l_ui.setSpacing(8)

        self.lbl_ui_hint = QLabel(self.g_ui)
        self.lbl_ui_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        self.lbl_ui_hint.setWordWrap(True)
        l_ui.addWidget(self.lbl_ui_hint)

        r_uidir = QHBoxLayout()
        self.edit_ui_dir = QLineEdit(self.g_ui)
        r_uidir.addWidget(self.edit_ui_dir)

        self.btn_browse_ui = QPushButton(self.g_ui)
        self.btn_browse_ui.clicked.connect(self._browse_ui_dir)
        r_uidir.addWidget(self.btn_browse_ui)

        self.btn_clear_ui = QPushButton(self.g_ui)
        self.btn_clear_ui.clicked.connect(self._clear_ui_dir)
        r_uidir.addWidget(self.btn_clear_ui)
        l_ui.addLayout(r_uidir)

        # Home display
        l_home = QHBoxLayout()
        self.lbl_home = QLabel(self.g_ui)
        l_home.addWidget(self.lbl_home)

        self.edit_home_display = QLineEdit(self.g_ui)
        l_home.addWidget(self.edit_home_display)

        self.btn_browse_home = QPushButton(self.g_ui)
        self.btn_browse_home.clicked.connect(self._browse_home_bob)
        l_home.addWidget(self.btn_browse_home)
        l_ui.addLayout(l_home)

        self.lbl_home_hint = QLabel(self.g_ui)
        self.lbl_home_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        self.lbl_home_hint.setWordWrap(True)
        l_ui.addWidget(self.lbl_home_hint)

        layout.addWidget(self.g_ui)
        layout.addStretch()

    def _get_project_dir(self, name: Optional[str] = None) -> Path:
        """Returns the project directory under self.base_dir / 'configs' / <project_name>."""
        proj_name = name or (self.edit_app_name.text().strip().lower().replace(" ", "_") if hasattr(self, "edit_app_name") and self.edit_app_name.text().strip() else "project")
        proj_dir = self.base_dir / "configs" / proj_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir

    def _resolve_relative_path(self, path_str: str) -> Path:
        """Resolves a file path against self.base_dir."""
        if not path_str:
            return Path()
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.base_dir / p

    def _browse_settings_ini(self):
        f = NativeFileBrowser.get_open_file_name(
            self,
            caption="settings.ini",
            filter="INI / Properties (*.ini *.properties);;All Files (*.*)"
        )
        if f:
            self.edit_settings_ini.setText(f)

    def _open_settings_editor(self):
        ini_path = self.edit_settings_ini.text().strip()
        proj_dir = self._get_project_dir()
        proj_ini = proj_dir / "settings.ini"

        resolved_ini = self._resolve_relative_path(ini_path) if ini_path else None
        if not resolved_ini or not resolved_ini.exists():
            if proj_ini.exists():
                ini_path = str(proj_ini)
                self.edit_settings_ini.setText(ini_path)
            else:
                tmpl = self.config.get_settings_template_path(self.base_dir)
                if tmpl and tmpl.exists():
                    proj_ini.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(tmpl, proj_ini)
                    ini_path = str(proj_ini)
                    self.edit_settings_ini.setText(ini_path)
                    self.config.custom_settings_ini_path = ini_path
                else:
                    self._msg_warning(t("dlg_info_title"), t("dlg_settings_need_file"))
                    return
        SettingsEditor.open_pyside6_editor(self._resolve_relative_path(ini_path), parent=self)

    def _generate_new_settings_ini(self):
        try:
            proj_dir = self._get_project_dir()

            if hasattr(self, "radio_src_local") and self.radio_src_local.isChecked() and self.config.local_sources_path:
                p_src = Path(self.config.local_sources_path)
                if not p_src.is_absolute():
                    p_src = self.base_dir / p_src
                self.log(f"[>] Preparing local Phoebus sources...")
                sources_dir = DownloadManager.prepare_local_sources(p_src)
            else:
                tag = self.combo_tags.currentText().strip()
                if tag in (t("other_version_option"), "Autre version spécifique...", "Other specific version..."):
                    tag = self.edit_custom_tag.text().strip() or "v5.0.2"
                shared_sources_base = self.base_dir / "sources" / "phoebus"
                shared_sources_base.mkdir(parents=True, exist_ok=True)
                self.log(f"[>] Preparing Phoebus {tag} sources...")
                sources_dir = DownloadManager.download_phoebus_sources(tag, shared_sources_base)

            template_path = sources_dir / "settings_template.ini"
            if not template_path.exists() or template_path.stat().st_size == 0:
                SettingsGenerator.generate_from_sources(sources_dir, template_path)
            out_file = proj_dir / "settings.ini"
            shutil.copy2(template_path, out_file)
            rel_out = str(out_file.relative_to(self.base_dir)) if out_file.is_relative_to(self.base_dir) else str(out_file)
            self.edit_settings_ini.setText(rel_out)
            self.config.custom_settings_ini_path = rel_out
            self._msg_info(t("dlg_settings_generated_title"), t("dlg_settings_generated", path=str(out_file)))
            self.log(f"[OK] settings.ini generated: {out_file}")
        except Exception as e:
            self._msg_error(t("dlg_build_error_title"), f"{e}")

    def _browse_ui_dir(self):
        d = NativeFileBrowser.get_existing_directory(
            self,
            caption="UI / .bob directory"
        )
        if d:
            proj_dir = self._get_project_dir()
            target_ui = proj_dir / "ui"

            if Path(d).resolve() != target_ui.resolve():
                shutil.copytree(Path(d), target_ui, dirs_exist_ok=True)
                self.log(f"[OK] UI directory -> {target_ui}")

            rel_ui = str(target_ui.relative_to(self.base_dir)) if target_ui.is_relative_to(self.base_dir) else str(target_ui)
            self.edit_ui_dir.setText(rel_ui)
            self.config.ui_dir = rel_ui

    def _clear_ui_dir(self):
        proj_dir = self._get_project_dir()
        target_ui = proj_dir / "ui"

        if not target_ui.exists() or not any(target_ui.iterdir()):
            self._msg_info(t("dlg_info_title"), t("dlg_ui_already_empty", path=str(target_ui)))
            return

        if self._msg_confirm(t("dlg_confirm_title"), t("dlg_confirm_clear_ui", path=str(target_ui)), default_yes=False):
            try:
                for item in target_ui.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                self.edit_home_display.setText("")
                self.config.home_display_file = ""
                self._msg_info(t("dlg_ui_cleared_title"), t("dlg_ui_cleared", path=str(target_ui)))
                self.log(f"[OK] UI directory cleared: {target_ui}")
            except Exception as e:
                self._msg_error(t("dlg_build_error_title"), f"{e}")

    def _browse_home_bob(self):
        proj_dir = self._get_project_dir()
        target_ui = proj_dir / "ui"
        target_ui.mkdir(parents=True, exist_ok=True)

        ui_dir = self.edit_ui_dir.text().strip()
        start_dir = self._resolve_relative_path(ui_dir) if ui_dir else target_ui
        start = str(start_dir) if start_dir.exists() else str(target_ui)

        f = NativeFileBrowser.get_open_file_name(
            self,
            caption="Home Display (.bob)",
            start_dir=start,
            filter="Phoebus Display (*.bob);;All Files (*.*)"
        )
        if f:
            src_file = Path(f)
            try:
                rel = src_file.resolve().relative_to(target_ui.resolve())
                rel_str = str(rel)
            except ValueError:
                dest_file = target_ui / src_file.name
                if src_file.resolve() != dest_file.resolve():
                    shutil.copy2(src_file, dest_file)
                rel_str = src_file.name
                self.log(f"[OK] .bob -> {dest_file}")

            rel_ui = str(target_ui.relative_to(self.base_dir)) if target_ui.is_relative_to(self.base_dir) else str(target_ui)
            self.edit_ui_dir.setText(rel_ui)
            self.config.ui_dir = rel_ui
            self.edit_home_display.setText(rel_str)
            self.config.home_display_file = rel_str

    # --- TAB 4: MODULES ---
    def _init_tab_modules(self):
        layout = QVBoxLayout(self.tab_modules)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_modules_title = QLabel(self.tab_modules)
        layout.addWidget(self.lbl_modules_title)

        self.lbl_modules_sub = QLabel(self.tab_modules)
        layout.addWidget(self.lbl_modules_sub)
        self._format_section_header(self.lbl_modules_title, self.lbl_modules_sub)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_mod_all = QPushButton(self.tab_modules)
        self.btn_mod_all.clicked.connect(self._select_all_modules)
        btn_bar.addWidget(self.btn_mod_all)

        self.btn_mod_std = QPushButton(self.tab_modules)
        self.btn_mod_std.clicked.connect(self._select_standard_modules)
        btn_bar.addWidget(self.btn_mod_std)

        self.btn_mod_mini = QPushButton(self.tab_modules)
        self.btn_mod_mini.clicked.connect(self._select_minimal_modules)
        btn_bar.addWidget(self.btn_mod_mini)

        self.btn_mod_desel = QPushButton(self.tab_modules)
        self.btn_mod_desel.clicked.connect(self._deselect_optional_modules)
        btn_bar.addWidget(self.btn_mod_desel)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        scroll = QScrollArea(self.tab_modules)
        scroll.setWidgetResizable(True)
        self.modules_scroll_content = QWidget()
        self.modules_scroll_layout = QVBoxLayout(self.modules_scroll_content)
        self.modules_scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.modules_scroll_layout.setSpacing(10)

        self.current_modules_list = list(PHOEBUS_MODULES)
        self.module_checkboxes: Dict[str, QCheckBox] = {}
        self.module_desc_labels: Dict[str, QLabel] = {}
        self.module_cat_groups: Dict[str, QGroupBox] = {}

        scroll.setWidget(self.modules_scroll_content)
        layout.addWidget(scroll, 1)
        self._populate_modules_ui()

    def _find_active_product_pom(self) -> Optional[Path]:
        """Locates the active phoebus-product/pom.xml for current project and specific version or local sources."""
        if hasattr(self, "radio_src_local") and self.radio_src_local.isChecked():
            if not self.config.local_sources_path:
                return None
            p = Path(self.config.local_sources_path)
            if not p.is_absolute():
                p = self.base_dir / p
            if p.is_dir() and DownloadManager.is_valid_sources_dir(p):
                return p / "phoebus-product" / "pom.xml"
            # En mode local, NE JAMAIS retomber sur le cache des versions distantes ni itérer les sous-dossiers !
            return None

        proj_name = self.config.app_name.lower().replace(" ", "_") if self.config.app_name else "project"
        raw_tag = (self.config.phoebus_branch or "").strip()
        clean_tag = raw_tag.lstrip("vV")

        if not clean_tag:
            return None

        # Look specifically for directories matching this version
        possible_dirs = [
            self.base_dir / "sources" / "phoebus" / f"phoebus-{clean_tag}",
            self.base_dir / "sources" / "phoebus" / f"phoebus-v{clean_tag}",
            self.base_dir / "configs" / "sources" / "phoebus" / f"phoebus-{clean_tag}",
            self.base_dir / "configs" / "sources" / "phoebus" / f"phoebus-v{clean_tag}",
            self.base_dir / "configs" / proj_name / "sources" / f"phoebus-{clean_tag}",
        ]

        for pdir in possible_dirs:
            pom = pdir / "phoebus-product" / "pom.xml"
            if pom.exists() and pom.stat().st_size > 0 and (pdir / "pom.xml").exists() and (pdir / "pom.xml").stat().st_size > 0:
                return pom

        return None

    def _populate_modules_ui(self, pom_file: Optional[Path] = None):
        """Builds or refreshes the modules UI with standard and dynamically discovered modules."""
        # Clear existing widgets
        while self.modules_scroll_layout.count():
            item = self.modules_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.module_checkboxes.clear()
        self.module_desc_labels.clear()
        self.module_cat_groups.clear()

        # Discover modules from pom.xml if available
        pom_to_use = pom_file or self._find_active_product_pom()
        lang = get_language()
        tag = self.config.phoebus_branch or "v5.0.5"

        if pom_to_use is None or not pom_to_use.exists() or pom_to_use.stat().st_size == 0:
            # Sources are missing!
            if hasattr(self, "btn_mod_all"):
                self.btn_mod_all.setEnabled(False)
                self.btn_mod_std.setEnabled(False)
                self.btn_mod_mini.setEnabled(False)
                self.btn_mod_desel.setEnabled(False)

            placeholder_widget = QWidget(self.modules_scroll_content)
            p_layout = QVBoxLayout(placeholder_widget)
            p_layout.setSpacing(16)
            p_layout.setContentsMargins(20, 20, 20, 20)

            icon_lbl = QLabel("📦", placeholder_widget)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("font-size: 40px;")
            p_layout.addWidget(icon_lbl, 0, Qt.AlignCenter)

            msg_lbl = QLabel(t("modules_no_sources_placeholder", version=tag), placeholder_widget)
            msg_lbl.setAlignment(Qt.AlignCenter)
            msg_lbl.setStyleSheet("font-size: 13px; color: #a0a0a0; padding: 6px 10px;")
            msg_lbl.setWordWrap(True)
            p_layout.addWidget(msg_lbl)

            btn_dl = QPushButton(f"⬇ {t('btn_download_sources_now')}", placeholder_widget)
            btn_dl.setObjectName("primaryButton")
            btn_dl.setStyleSheet("font-weight: bold; padding: 8px 20px;")
            btn_dl.clicked.connect(self._start_sources_download)
            p_layout.addWidget(btn_dl, 0, Qt.AlignCenter)

            self.modules_scroll_layout.addStretch()
            self.modules_scroll_layout.addWidget(placeholder_widget)
            self.modules_scroll_layout.addStretch()
            return

        # Sources present -> enable buttons
        if hasattr(self, "btn_mod_all"):
            self.btn_mod_all.setEnabled(True)
            self.btn_mod_std.setEnabled(True)
            self.btn_mod_mini.setEnabled(True)
            self.btn_mod_desel.setEnabled(True)

        self.current_modules_list = PhoebusPomManager.discover_modules_from_pom(pom_to_use)

        enabled_set = set(self.config.enabled_modules) if self.config.enabled_modules else set(m.artifact_id for m in self.current_modules_list)
        lang = get_language()

        for mod in self.current_modules_list:
            cat_key = mod.category
            if cat_key not in self.module_cat_groups:
                cat_group = QGroupBox(self.modules_scroll_content)
                cat_l = QVBoxLayout(cat_group)
                cat_l.setContentsMargins(12, 12, 12, 12)
                cat_l.setSpacing(6)
                cat_group.setTitle(mod.get_category(lang))
                self.module_cat_groups[cat_key] = cat_group
                self.modules_scroll_layout.addWidget(cat_group)
            else:
                cat_group = self.module_cat_groups[cat_key]
                cat_l = cat_group.layout()

            m_box = QVBoxLayout()
            m_box.setSpacing(2)
            cb = QCheckBox(cat_group)
            chk_text = f"{mod.get_label(lang)} ({mod.artifact_id})"
            if mod.is_core:
                chk_text += f"  {t('module_core_badge')}"
            cb.setText(chk_text)

            is_checked = (mod.artifact_id in enabled_set) if self.config.enabled_modules else True
            cb.setChecked(is_checked)
            if mod.is_core:
                cb.setEnabled(False)
                cb.setChecked(True)

            cb.toggled.connect(lambda checked, aid=mod.artifact_id: self._on_module_toggled(aid, checked))
            self.module_checkboxes[mod.artifact_id] = cb
            m_box.addWidget(cb)

            lbl_desc = QLabel(cat_group)
            lbl_desc.setWordWrap(True)
            desc_text = f"    {mod.get_description(lang)}"
            if mod.depends_on:
                dep_names = ", ".join(mod.depends_on)
                desc_text += f" — <i style='color: #64748b;'>({t('module_deps_label', deps=dep_names)})</i>"
                lbl_desc.setTextFormat(Qt.TextFormat.RichText)
            lbl_desc.setText(desc_text)
            self.module_desc_labels[mod.artifact_id] = lbl_desc
            m_box.addWidget(lbl_desc)

            cat_l.addLayout(m_box)

    def _on_module_toggled(self, artifact_id: str, checked: bool):
        """Automatically checks dependencies when enabling a module, and unchecks dependents when disabling."""
        if getattr(self, "_updating_modules", False):
            return
        self._updating_modules = True
        try:
            if checked:
                # Auto-check required dependencies
                deps = PhoebusPomManager.get_dependencies(artifact_id)
                for dep_id in deps:
                    cb = self.module_checkboxes.get(dep_id)
                    if cb and not cb.isChecked():
                        cb.setChecked(True)
                        self.log(f"  [>] Auto-enabled dependency: {dep_id} (required by {artifact_id})")
            else:
                # Auto-uncheck modules depending on this one
                dependents = PhoebusPomManager.get_dependents(artifact_id)
                for dep_id in dependents:
                    cb = self.module_checkboxes.get(dep_id)
                    if cb and cb.isChecked():
                        cb.setChecked(False)
                        self.log(f"  [>] Auto-disabled: {dep_id} (depends on disabled {artifact_id})")
        finally:
            self._updating_modules = False

    def _select_all_modules(self):
        for aid, cb in self.module_checkboxes.items():
            cb.setChecked(True)

    def _select_minimal_modules(self):
        minimal = set(PhoebusPomManager.get_minimal_ui_module_ids())
        for aid, cb in self.module_checkboxes.items():
            cb.setChecked(aid in minimal)

    def _select_standard_modules(self):
        standard = set(PhoebusPomManager.get_standard_module_ids())
        for aid, cb in self.module_checkboxes.items():
            cb.setChecked(aid in standard)

    def _deselect_optional_modules(self):
        for mod in getattr(self, "current_modules_list", PHOEBUS_MODULES):
            if not mod.is_core and mod.artifact_id in self.module_checkboxes:
                self.module_checkboxes[mod.artifact_id].setChecked(False)

    def _init_tab_logo(self):
        layout = QVBoxLayout(self.tab_logo)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_logo_title = QLabel(self.tab_logo)
        layout.addWidget(self.lbl_logo_title)

        self.lbl_logo_sub = QLabel(self.tab_logo)
        layout.addWidget(self.lbl_logo_sub)
        self._format_section_header(self.lbl_logo_title, self.lbl_logo_sub)

        f_sel = QHBoxLayout()
        f_sel.setSpacing(8)
        self.edit_logo_path = QLineEdit(self.tab_logo)
        f_sel.addWidget(self.edit_logo_path)

        self.btn_browse_logo = QPushButton(self.tab_logo)
        self.btn_browse_logo.clicked.connect(self._browse_logo)
        f_sel.addWidget(self.btn_browse_logo)

        self.btn_def_logo = QPushButton(self.tab_logo)
        self.btn_def_logo.clicked.connect(lambda: self._set_logo(""))
        f_sel.addWidget(self.btn_def_logo)
        layout.addLayout(f_sel)

        self.lbl_logo_status = QLabel(self.tab_logo)
        layout.addWidget(self.lbl_logo_status)

        self.lbl_logo_preview = QLabel(self.tab_logo)
        self.lbl_logo_preview.setFixedSize(72, 72)
        self.lbl_logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo_preview.setFrameShape(QFrame.Shape.StyledPanel)
        layout.addWidget(self.lbl_logo_preview)

        layout.addStretch()

    def _browse_logo(self):
        filter_str = (
            "Icons & Images (*.ico *.png *.jpg *.jpeg *.bmp);;Windows Icon (*.ico);;PNG Image (*.png);;All Files (*.*)"
            if self.is_windows
            else "Images (*.png *.jpg *.jpeg *.ico);;PNG Image (*.png);;All Files (*.*)"
        )
        allowed_formats = (".ico", ".png", ".jpg", ".jpeg", ".bmp")
        while True:
            f = NativeFileBrowser.get_open_file_name(
                self,
                caption=f"Logo ({'ico / png' if self.is_windows else 'png'})",
                filter=filter_str
            )
            if not f:
                break
            if ImageValidator.validate_image(
                f,
                expected_size=None,
                image_type_label=f"Logo ({self.current_os})",
                expected_format=allowed_formats
            ):
                self._set_logo(f)
                break

    def _set_logo(self, path_str: str):
        if path_str:
            p_src = self._resolve_relative_path(path_str)
            if p_src.exists():
                proj_dir = self._get_project_dir()
                if self.is_windows:
                    dest_logo = proj_dir / (p_src.name if p_src.suffix.lower() == ".ico" else "logo.ico")
                    ImageValidator.convert_to_ico(p_src, dest_logo)
                    # Always ensure 64x64 site_logo.png is generated
                    site_logo_target = proj_dir / "site_logo.png"
                    ImageValidator.generate_site_logo(p_src, site_logo_target, target_size=(64, 64))
                    self.log(f"[OK] Logo (.ico multi-resolutions) -> {dest_logo}")
                    self.log(f"[OK] site_logo.png (64x64) -> {site_logo_target}")
                else:
                    if p_src.suffix.lower() == ".png":
                        dest_logo = proj_dir / p_src.name
                        if p_src.resolve() != dest_logo.resolve():
                            shutil.copy2(p_src, dest_logo)
                    else:
                        dest_logo = proj_dir / "logo.png"
                        try:
                            from PySide6.QtGui import QImage
                            img = QImage(str(p_src))
                            if not img.isNull():
                                img.save(str(dest_logo), "PNG")
                            else:
                                shutil.copy2(p_src, dest_logo)
                        except Exception:
                            shutil.copy2(p_src, dest_logo)
                    site_logo_target = proj_dir / "site_logo.png"
                    ImageValidator.generate_site_logo(p_src, site_logo_target, target_size=(64, 64))
                    self.log(f"[OK] Logo (.png) -> {dest_logo}")
                    self.log(f"[OK] site_logo.png (64x64) -> {site_logo_target}")

                try:
                    rel_path = str(dest_logo.relative_to(self.base_dir))
                except ValueError:
                    rel_path = str(dest_logo)
                path_str = rel_path

        self.edit_logo_path.setText(path_str)
        self.config.custom_logo_path = path_str
        self._update_logo_preview()

    def _update_logo_preview(self):
        p_str = self.edit_logo_path.text().strip()
        p = self._resolve_relative_path(p_str) if p_str else None
        if p and p.exists():
            dims = ImageValidator.get_image_dimensions(p)
            req_ext = ".ico" if self.is_windows else ".png"
            dim_str = f"{dims[0]}x{dims[1]} px" if dims else "OK"
            if p.suffix.lower() == req_ext or (self.is_windows and p.suffix.lower() in [".ico", ".png"]):
                self.lbl_logo_status.setText(t("logo_valid_status", name=p.name, dims=dim_str))
            else:
                self.lbl_logo_status.setText(t("logo_invalid_status", format=p.suffix, req_ext=req_ext))

            pixmap = QPixmap(str(p))
            if not pixmap.isNull():
                self.lbl_logo_preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.lbl_logo_preview.setText("ICO" if self.is_windows else "OK")
        else:
            self.lbl_logo_status.setText(t("logo_none_status"))
            res_dir = Path(self.config.resources_windows_dir if self.is_windows else self.config.resources_linux_dir)
            if not res_dir.is_absolute():
                res_dir = self.base_dir / res_dir
            if not res_dir.exists():
                res_dir = Path(__file__).parent / "resources" / ("windows" if self.is_windows else "linux")
            default_icon = res_dir / ("logo.ico" if self.is_windows else "logo.png")

            if default_icon.exists():
                pixmap = QPixmap(str(default_icon))
                if not pixmap.isNull():
                    self.lbl_logo_preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    self.lbl_logo_preview.clear()
                    self.lbl_logo_preview.setText("Défaut" if get_language() == "fr" else "Default")
            else:
                self.lbl_logo_preview.clear()
                self.lbl_logo_preview.setText("Défaut" if get_language() == "fr" else "Default")

    def _init_tab_splash(self):
        layout = QVBoxLayout(self.tab_splash)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_splash_title = QLabel(self.tab_splash)
        layout.addWidget(self.lbl_splash_title)

        self.lbl_splash_sub = QLabel(self.tab_splash)
        layout.addWidget(self.lbl_splash_sub)
        self._format_section_header(self.lbl_splash_title, self.lbl_splash_sub)

        f_sel = QHBoxLayout()
        f_sel.setSpacing(8)
        self.edit_splash_path = QLineEdit(self.tab_splash)
        f_sel.addWidget(self.edit_splash_path)

        self.btn_browse_splash = QPushButton(self.tab_splash)
        self.btn_browse_splash.clicked.connect(self._browse_splash)
        f_sel.addWidget(self.btn_browse_splash)

        self.btn_def_splash = QPushButton(self.tab_splash)
        self.btn_def_splash.clicked.connect(lambda: self._set_splash(""))
        f_sel.addWidget(self.btn_def_splash)
        layout.addLayout(f_sel)

        self.lbl_splash_status = QLabel(self.tab_splash)
        layout.addWidget(self.lbl_splash_status)

        self.lbl_splash_preview = QLabel(self.tab_splash)
        self.lbl_splash_preview.setFixedSize(240, 150)
        self.lbl_splash_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_splash_preview.setFrameShape(QFrame.Shape.StyledPanel)
        layout.addWidget(self.lbl_splash_preview)

        layout.addStretch()

    def _browse_splash(self):
        while True:
            f = NativeFileBrowser.get_open_file_name(
                self,
                caption="Splash (.png, 480x300 px)",
                filter="PNG Image (*.png);;All Files (*.*)"
            )
            if not f:
                break
            if ImageValidator.validate_image(
                f,
                expected_size=(480, 300),
                image_type_label="Splash",
                expected_format=".png"
            ):
                self._set_splash(f)
                break

    def _set_splash(self, path_str: str):
        if path_str:
            p_src = self._resolve_relative_path(path_str)
            if p_src.exists():
                proj_dir = self._get_project_dir()
                dest_splash = proj_dir / "site_splash.png"
                if p_src.resolve() != dest_splash.resolve():
                    shutil.copy2(p_src, dest_splash)
                try:
                    rel_path = str(dest_splash.relative_to(self.base_dir))
                except ValueError:
                    rel_path = str(dest_splash)
                path_str = rel_path
                self.log(f"[OK] Splash -> {dest_splash}")

        self.edit_splash_path.setText(path_str)
        self.config.custom_splash_path = path_str
        self._update_splash_preview()

    def _update_splash_preview(self):
        p_str = self.edit_splash_path.text().strip()
        p = self._resolve_relative_path(p_str) if p_str else None
        if p and p.exists():
            dims = ImageValidator.get_image_dimensions(p)
            if dims == (480, 300) and p.suffix.lower() == ".png":
                self.lbl_splash_status.setText(t("splash_valid_status", name=p.name, dims=f"{dims[0]}x{dims[1]}"))
            else:
                self.lbl_splash_status.setText(t("splash_invalid_status", dims=dims))

            pixmap = QPixmap(str(p))
            if not pixmap.isNull():
                self.lbl_splash_preview.setPixmap(pixmap.scaled(240, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.lbl_splash_preview.setText(t("splash_preview_unavailable"))
        else:
            self.lbl_splash_status.setText(t("splash_none_status"))
            default_splash = Path(__file__).parent / "resources" / "splash.png"
            if default_splash.exists():
                pixmap = QPixmap(str(default_splash))
                if not pixmap.isNull():
                    self.lbl_splash_preview.setPixmap(pixmap.scaled(240, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    self.lbl_splash_preview.clear()
                    self.lbl_splash_preview.setText(t("splash_default_preview"))
            else:
                self.lbl_splash_preview.clear()
                self.lbl_splash_preview.setText(t("splash_default_preview"))

    # --- TAB 7: BUILD & SUMMARY ---
    def _init_tab_build(self):
        layout = QVBoxLayout(self.tab_build)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.lbl_build_title = QLabel(self.tab_build)
        layout.addWidget(self.lbl_build_title)

        self.lbl_build_sub = QLabel(self.tab_build)
        layout.addWidget(self.lbl_build_sub)
        self._format_section_header(self.lbl_build_title, self.lbl_build_sub)

        self.dest_group = QGroupBox(self.tab_build)
        d_layout = QHBoxLayout(self.dest_group)
        d_layout.setContentsMargins(14, 14, 14, 14)
        d_layout.setSpacing(8)
        self.edit_output_dir = QLineEdit(self.dest_group)
        d_layout.addWidget(self.edit_output_dir)

        self.btn_browse_out = QPushButton(self.dest_group)
        self.btn_browse_out.clicked.connect(self._browse_output_dir)
        d_layout.addWidget(self.btn_browse_out)

        self.btn_open_out = QPushButton(self.dest_group)
        self.btn_open_out.clicked.connect(self._open_output_dir)
        d_layout.addWidget(self.btn_open_out)
        layout.addWidget(self.dest_group)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_build = QPushButton(self.tab_build)
        self.btn_build.setDefault(True)
        self.btn_build.clicked.connect(self._start_build_thread)
        btn_box.addWidget(self.btn_build)

        self.btn_stop = QPushButton(self.tab_build)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_build)
        btn_box.addWidget(self.btn_stop)

        self.btn_clean = QPushButton(self.tab_build)
        self.btn_clean.clicked.connect(self._clean_build_cache)
        btn_box.addWidget(self.btn_clean)

        self.lbl_build_status = QLabel(self.tab_build)
        btn_box.addWidget(self.lbl_build_status)

        btn_box.addStretch()
        layout.addLayout(btn_box)

        self.progress_bar = QProgressBar(self.tab_build)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_console_title = QLabel(self.tab_build)
        layout.addWidget(self.lbl_console_title)

        self.log_console = QPlainTextEdit(self.tab_build)
        self.log_console.setObjectName("log_console")
        self.log_console.setReadOnly(True)
        mono_font = QFont("Monospace", 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_console.setFont(mono_font)
        layout.addWidget(self.log_console, 1)

    def _browse_output_dir(self):
        start = self.edit_output_dir.text().strip() or "output"
        start_path = Path(start) if Path(start).is_absolute() else (self.base_dir / start)
        start_path.mkdir(parents=True, exist_ok=True)
        d = NativeFileBrowser.get_existing_directory(
            self,
            caption=t("dest_box_title") if t("dest_box_title") != "dest_box_title" else "Dossier de destination",
            start_dir=start_path
        )
        if d:
            self.edit_output_dir.setText(d)
            self.config.output_dir = d
            self._update_summary()

    def _open_output_dir(self):
        dest = self.edit_output_dir.text().strip() or "output"
        dest_path = Path(dest) if Path(dest).is_absolute() else (self.base_dir / dest)
        dest_path.mkdir(parents=True, exist_ok=True)
        try:
            if self.is_windows:
                os.startfile(str(dest_path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(dest_path)])
            else:
                subprocess.run(["xdg-open", str(dest_path)])
        except Exception as e:
            self._msg_error(t("dlg_build_error_title"), f"{e}")

    def _on_tab_changed(self, idx: int):
        self._update_logo_preview()
        self._update_splash_preview()
        self._update_summary()

    # --- RETRANSLATE UI (Native Qt Pattern) ---
    def retranslateUi(self):
        """Translates and refreshes all UI strings in place without widget destruction."""
        target_pkg = ".deb / .rpm" if not self.is_windows else ".msi / .exe"
        req_ext = ".ico" if self.is_windows else ".png"
        lang = get_language()

        # Window & Header
        self.setWindowTitle(f"{t('app_title')} — [{self.current_os}]")
        if hasattr(self, "btn_app_settings"):
            self.btn_app_settings.setText(t("btn_app_settings"))

        # Profile Bar
        self.lbl_proj_bar.setText(t("project_bar_label"))
        self.btn_save_proj.setText(t("btn_save_project"))
        self.btn_new_proj.setText(t("btn_new_project"))
        if hasattr(self, "btn_proj_actions"):
            self.btn_proj_actions.setText(t("btn_project_actions"))
        if hasattr(self, "action_export_proj"):
            self.action_export_proj.setText(t("action_export_project"))
        if hasattr(self, "action_import_proj"):
            self.action_import_proj.setText(t("action_import_project"))
        if hasattr(self, "action_duplicate_proj"):
            self.action_duplicate_proj.setText(t("action_duplicate_project"))
        if hasattr(self, "action_open_dir_proj"):
            self.action_open_dir_proj.setText(t("action_open_project_folder"))
        if hasattr(self, "action_delete_proj"):
            self.action_delete_proj.setText(t("action_delete_project"))

        # Tab Titles
        self.tab_widget.setTabText(0, t("tab_tech"))
        self.tab_widget.setTabText(1, t("tab_identity"))
        self.tab_widget.setTabText(2, t("tab_settings"))
        self.tab_widget.setTabText(3, t("tab_modules"))
        self.tab_widget.setTabText(4, t("tab_logo"))
        self.tab_widget.setTabText(5, t("tab_splash"))
        self.tab_widget.setTabText(6, t("tab_build"))

        # Tab 1
        self.lbl_tech_title.setText(t("tech_title"))
        self.lbl_tech_sub.setText(t("tech_subtitle"))
        self.lbl_phoebus_version.setText(t("phoebus_version_label"))
        self.lbl_custom_tag.setText(t("custom_tag_label"))
        self.edit_custom_tag.setPlaceholderText(t("custom_tag_placeholder"))
        if hasattr(self, "lbl_sources_status_title"):
            self.lbl_sources_status_title.setText(t("sources_status_label"))
        self._update_sources_status()
        self.lbl_java_version.setText(t("java_version_label"))
        if hasattr(self, "lbl_jvm_status_title"):
            self.lbl_jvm_status_title.setText(t("jvm_status_label"))
        self._update_jvm_status()
        if hasattr(self, "lbl_maven_status_title"):
            self.lbl_maven_status_title.setText(t("maven_status_label"))
        self._update_maven_status()
        if self.is_windows:
            if hasattr(self, "lbl_wix_status_title"):
                self.lbl_wix_status_title.setText(t("wix_status_label"))
            self._update_wix_status()
            if hasattr(self, "lbl_win_pkg"):
                self.lbl_win_pkg.setText(t("windows_package_type_label"))
        if hasattr(self, "chk_force_maven"):
            self.chk_force_maven.setText(t("force_maven_label"))
            self.chk_force_maven.setToolTip(t("force_maven_hint"))
        if hasattr(self, "chk_clean_temp_build"):
            self.chk_clean_temp_build.setText(t("clean_temp_build_label"))
            self.chk_clean_temp_build.setToolTip(t("clean_temp_build_hint"))

        # Combo tags items
        curr_tag = self.combo_tags.currentText()
        self.combo_tags.blockSignals(True)
        self.combo_tags.clear()
        self.combo_tags.addItems(self.recent_tags_list + [t("other_version_option")])
        idx = self.combo_tags.findText(curr_tag)
        if idx >= 0:
            self.combo_tags.setCurrentIndex(idx)
        else:
            self.combo_tags.setCurrentText(t("other_version_option"))
        self.combo_tags.blockSignals(False)

        self.lbl_identity_title.setText(t("identity_title"))
        self.lbl_identity_sub.setText(t("identity_subtitle"))
        for key, lbl in self.identity_labels.items():
            label_text = t(key)
            lbl.setText(label_text)

        self.lbl_settings_title.setText(t("settings_title"))
        self.lbl_settings_sub.setText(t("settings_subtitle"))
        self.g_pref.setTitle("1. " + t("pref_folder_label"))
        self.lbl_pref_hint.setText(t("pref_folder_hint"))
        self.g_ini.setTitle("2. " + t("settings_ini_label"))
        self.btn_browse_ini.setText(t("btn_browse"))
        self.btn_edit_ini.setText(t("btn_edit_settings"))
        self.btn_gen_ini.setText(t("btn_generate_default_settings"))
        self.g_ui.setTitle("3. " + t("ui_dir_label"))
        self.lbl_ui_hint.setText(t("ui_dir_hint"))
        self.btn_browse_ui.setText(t("btn_browse"))
        self.btn_clear_ui.setText(t("btn_clear_ui_dir"))
        self.lbl_home.setText(t("home_display_label"))
        self.lbl_home_hint.setText(t("home_display_hint"))
        self.edit_home_display.setPlaceholderText(t("home_display_placeholder"))
        self.btn_browse_home.setText(t("btn_browse"))

        self.lbl_modules_title.setText(t("modules_title"))
        self.lbl_modules_sub.setText(t("modules_subtitle"))
        self.btn_mod_all.setText(t("btn_select_all"))
        self.btn_mod_mini.setText(t("btn_select_minimal"))
        self.btn_mod_std.setText(t("btn_select_standard"))
        self.btn_mod_desel.setText(t("btn_deselect_optional"))

        for mod in getattr(self, "current_modules_list", PHOEBUS_MODULES):
            cat_group = self.module_cat_groups.get(mod.category)
            if cat_group:
                cat_group.setTitle(f"{mod.get_category(lang)}")
            cb = self.module_checkboxes.get(mod.artifact_id)
            if cb:
                chk_text = f"{mod.get_label(lang)} ({mod.artifact_id})"
                if mod.is_core:
                    chk_text += f"  {t('module_core_badge')}"
                cb.setText(chk_text)
            desc_lbl = self.module_desc_labels.get(mod.artifact_id)
            if desc_lbl:
                desc_text = f"    {mod.get_description(lang)}"
                if mod.depends_on:
                    dep_names = ", ".join(mod.depends_on)
                    desc_text += f" — <i style='color: #64748b;'>({t('module_deps_label', deps=dep_names)})</i>"
                    desc_lbl.setTextFormat(Qt.TextFormat.RichText)
                desc_lbl.setText(desc_text)

        self.lbl_logo_title.setText(f"{t('logo_title')} ({req_ext})")
        self.lbl_logo_sub.setText(t("logo_subtitle", req_ext=req_ext))
        self.btn_browse_logo.setText(t("btn_browse"))
        self.btn_def_logo.setText(t("btn_default"))

        self.lbl_splash_title.setText(t("splash_title"))
        self.lbl_splash_sub.setText(t("splash_subtitle"))
        self.btn_browse_splash.setText(t("btn_browse"))
        self.btn_def_splash.setText(t("btn_default"))

        self.lbl_build_title.setText(t("build_title"))
        self.lbl_build_sub.setText(t("build_subtitle"))
        self.dest_group.setTitle(t("dest_box_title"))
        self.btn_browse_out.setText(t("btn_browse"))
        self.btn_open_out.setText(t("btn_open_folder"))
        if not (self.build_thread and self.build_thread.isRunning()):
            self.btn_build.setText(t("btn_launch_build"))
        self.btn_stop.setText(t("btn_stop_build"))
        self.btn_clean.setText(t("btn_clean_cache"))

        self.lbl_console_title.setText(t("console_title"))

        self._update_logo_preview()
        self._update_splash_preview()
        self._update_summary()

    def _update_summary(self):
        self._sync_ui_to_config()

    # --- PROFILE & PROJECT MANAGEMENT ---
    def _refresh_profiles_list(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        projects = self._list_projects()
        if projects:
            self.profile_combo.addItems(projects)
        else:
            self.profile_combo.addItem("default")
        self.profile_combo.blockSignals(False)

    def _list_projects(self) -> List[str]:
        configs_dir = self.base_dir / "configs"
        projects = []
        if configs_dir.exists() and configs_dir.is_dir():
            for p in configs_dir.iterdir():
                if p.is_dir() and (p / "config.json").exists():
                    projects.append(p.name)

        profiles_dir = self.base_dir / "profiles"
        if profiles_dir.exists() and profiles_dir.is_dir():
            for f in profiles_dir.glob("*.json"):
                if f.stem not in projects:
                    projects.append(f.stem)

        return sorted(projects)

    def _load_selected_profile(self, index: int):
        name = self.profile_combo.currentText().strip()
        if not name:
            return

        proj_json = self.base_dir / "configs" / name / "config.json"
        legacy_json = self.base_dir / "profiles" / f"{name}.json"
        target = proj_json if proj_json.exists() else legacy_json

        if target.exists():
            try:
                self.config = BuildConfig.from_json_file(target)
                self._sync_config_to_ui()
                if hasattr(self, "lbl_proj_status"):
                    self.lbl_proj_status.setText("")
                self.log(f"[OK] Loaded project configuration: {target}")
            except Exception as e:
                self._msg_error(t("dlg_build_error_title"), f"{e}")

    def _save_current_profile(self, show_dialog: bool = False):
        self._sync_ui_to_config()
        name = self.profile_combo.currentText().strip()
        if not name:
            name = self.config.app_name.lower().replace(" ", "_") if self.config.app_name else "project"

        try:
            proj_dir = self.config.save_to_project_bundle(name, base_dir=self.base_dir)
            self._sync_config_to_ui()
            self._refresh_profiles_list()
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(proj_dir.name)
            self.profile_combo.blockSignals(False)

            from datetime import datetime
            now_str = datetime.now().strftime("%H:%M:%S")
            if hasattr(self, "lbl_proj_status"):
                self.lbl_proj_status.setText(t("status_project_saved", time=now_str))

            if show_dialog:
                self._msg_info(t("dlg_project_saved_title"), t("dlg_project_saved", path=str(proj_dir)))
            self.log(f"[OK] Project saved: {proj_dir}")
            return proj_dir
        except Exception as e:
            self._msg_error(t("dlg_build_error_title"), f"{e}")
            return None

    def _export_current_project(self):
        proj_dir = self._save_current_profile(show_dialog=False)
        if not proj_dir:
            return

        name = self.profile_combo.currentText().strip() or "project"
        default_zip = f"{name}.zip"

        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            t("dlg_export_title"),
            str(Path.home() / default_zip),
            t("dlg_export_filter") + " (*.zip)"
        )
        if not dest_file:
            return

        try:
            zip_path = BuildConfig.export_project_to_zip(name, dest_file, base_dir=self.base_dir)
            self._msg_info(t("dlg_export_title"), t("dlg_export_success", name=name, path=str(zip_path)))
            self.log(f"[OK] Project '{name}' exported to ZIP: {zip_path}")
        except Exception as e:
            self._msg_error(t("dlg_export_title"), t("dlg_export_error", err=str(e)))

    def _import_project_zip(self):
        src_zip, _ = QFileDialog.getOpenFileName(
            self,
            t("dlg_import_title"),
            str(Path.home()),
            t("dlg_import_filter") + " (*.zip)"
        )
        if not src_zip:
            return

        suggested_name = Path(src_zip).stem
        try:
            with zipfile.ZipFile(src_zip, "r") as zf:
                found_cfg = False
                for zname in zf.namelist():
                    if zname.endswith("config.json"):
                        found_cfg = True
                        with zf.open(zname) as cf:
                            cdata = json.load(cf)
                            if cdata.get("app_name"):
                                suggested_name = cdata["app_name"]
                        break
                if not found_cfg:
                    self._msg_error(t("dlg_import_title"), t("dlg_import_invalid_zip"))
                    return
        except Exception as e:
            self._msg_error(t("dlg_import_title"), t("dlg_import_error", err=str(e)))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(t("dlg_import_title"))
        dialog.setFixedSize(520, 240)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(20, 18, 20, 18)
        d_layout.setSpacing(10)

        lbl_prompt = QLabel(t("dlg_import_prompt"), dialog)
        font_prompt = lbl_prompt.font()
        font_prompt.setBold(True)
        lbl_prompt.setFont(font_prompt)
        d_layout.addWidget(lbl_prompt)

        edit_name = QLineEdit(dialog)
        clean_suggested = suggested_name.lower().replace(" ", "_")
        edit_name.setText(clean_suggested)
        d_layout.addWidget(edit_name)

        chk_overwrite = QCheckBox(t("dlg_import_overwrite"), dialog)
        d_layout.addWidget(chk_overwrite)

        lbl_err = QLabel("", dialog)
        lbl_err.setWordWrap(True)
        lbl_err.setStyleSheet("color: #dc2626; font-size: 11px;")
        d_layout.addWidget(lbl_err)

        edit_name.textChanged.connect(lambda: lbl_err.setText(""))
        chk_overwrite.toggled.connect(lambda: lbl_err.setText(""))

        d_layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_box.addStretch()

        btn_cancel = QPushButton(t("btn_cancel"), dialog)
        btn_cancel.clicked.connect(dialog.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton(t("dlg_btn_open_file"), dialog)
        btn_ok.setDefault(True)

        chosen_name = []
        overwrite_val = [False]

        def on_confirm():
            target_name = edit_name.text().strip().lower().replace(" ", "_")
            if not target_name:
                lbl_err.setText(t("dlg_invalid_project_name"))
                return

            dest_folder = self.base_dir / "configs" / target_name
            if dest_folder.exists() and not chk_overwrite.isChecked():
                lbl_err.setText(t("dlg_import_overwrite_confirm", name=target_name))
                return

            chosen_name.append(target_name)
            overwrite_val[0] = chk_overwrite.isChecked()
            dialog.accept()

        btn_ok.clicked.connect(on_confirm)
        edit_name.returnPressed.connect(on_confirm)
        btn_box.addWidget(btn_ok)
        d_layout.addLayout(btn_box)

        if dialog.exec() != QDialog.DialogCode.Accepted or not chosen_name:
            return

        final_proj_name = chosen_name[0]
        do_overwrite = overwrite_val[0]

        try:
            imported_name, proj_dir = BuildConfig.import_project_from_zip(
                src_zip,
                target_name=final_proj_name,
                base_dir=self.base_dir,
                overwrite=do_overwrite
            )
            self._refresh_profiles_list()
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(imported_name)
            self.profile_combo.blockSignals(False)

            self._load_selected_profile(0)
            self._msg_info(t("dlg_import_title"), t("dlg_import_success", name=imported_name))
            self.log(f"[OK] Project '{imported_name}' imported successfully from: {src_zip}")
        except Exception as e:
            self._msg_error(t("dlg_import_title"), t("dlg_import_error", err=str(e)))

    def _duplicate_current_project(self):
        current_name = self.profile_combo.currentText().strip()
        if not current_name:
            return

        self._save_current_profile(show_dialog=False)

        dialog = QDialog(self)
        dialog.setWindowTitle(t("dlg_duplicate_title"))
        dialog.setFixedSize(480, 200)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(20, 18, 20, 18)
        d_layout.setSpacing(10)

        lbl_prompt = QLabel(t("dlg_duplicate_prompt"), dialog)
        font_prompt = lbl_prompt.font()
        font_prompt.setBold(True)
        lbl_prompt.setFont(font_prompt)
        d_layout.addWidget(lbl_prompt)

        edit_name = QLineEdit(dialog)
        edit_name.setText(f"{current_name}_copy")
        d_layout.addWidget(edit_name)

        lbl_err = QLabel("", dialog)
        lbl_err.setWordWrap(True)
        lbl_err.setStyleSheet("color: #dc2626; font-size: 11px;")
        d_layout.addWidget(lbl_err)

        edit_name.textChanged.connect(lambda: lbl_err.setText(""))

        d_layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_box.addStretch()

        btn_cancel = QPushButton(t("btn_cancel"), dialog)
        btn_cancel.clicked.connect(dialog.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton(t("btn_create"), dialog)
        btn_ok.setDefault(True)

        chosen_name = []

        def on_confirm():
            new_name = edit_name.text().strip().lower().replace(" ", "_")
            if not new_name:
                lbl_err.setText(t("dlg_invalid_project_name"))
                return
            if (self.base_dir / "configs" / new_name).exists():
                lbl_err.setText(t("dlg_duplicate_exists", name=new_name))
                return
            chosen_name.append(new_name)
            dialog.accept()

        btn_ok.clicked.connect(on_confirm)
        edit_name.returnPressed.connect(on_confirm)
        btn_box.addWidget(btn_ok)
        d_layout.addLayout(btn_box)

        if dialog.exec() != QDialog.DialogCode.Accepted or not chosen_name:
            return

        new_project_name = chosen_name[0]
        try:
            new_dir = BuildConfig.duplicate_project(current_name, new_project_name, base_dir=self.base_dir)
            self._refresh_profiles_list()
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(new_project_name)
            self.profile_combo.blockSignals(False)
            self._load_selected_profile(0)
            self.log(f"[OK] Project duplicated to '{new_project_name}': {new_dir}")
        except Exception as e:
            self._msg_error(t("dlg_duplicate_title"), t("dlg_duplicate_error", err=str(e)))

    def _open_project_directory(self):
        current_name = self.profile_combo.currentText().strip()
        if not current_name:
            return
        proj_dir = self.base_dir / "configs" / current_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self.is_windows:
                os.startfile(str(proj_dir))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(proj_dir)])
            else:
                subprocess.run(["xdg-open", str(proj_dir)])
        except Exception as e:
            self._msg_error(t("dlg_build_error_title"), f"{e}")

    def _delete_current_project(self):
        projects = self._list_projects()
        if len(projects) <= 1:
            self._msg_warning(t("dlg_delete_title"), t("dlg_delete_only_project"))
            return

        current_name = self.profile_combo.currentText().strip()
        if not current_name:
            return

        confirmed = self._msg_confirm(
            t("dlg_delete_title"),
            t("dlg_delete_confirm", name=current_name)
        )
        if not confirmed:
            return

        proj_dir = self.base_dir / "configs" / current_name
        if proj_dir.exists() and proj_dir.is_dir():
            shutil.rmtree(proj_dir, ignore_errors=True)

        self.log(f"[OK] Project '{current_name}' deleted.")
        self._refresh_profiles_list()
        self._load_selected_profile(0)

    def _open_app_settings(self):
        """Opens the application settings dialog to allow changing workspace directory."""
        from .app_settings import set_saved_workspace_dir
        dlg = AppSettingsDialog(self.base_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.new_workspace and dlg.new_workspace != self.base_dir:
                new_ws = dlg.new_workspace
                try:
                    new_ws.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._msg_error(t("dlg_val_err_title"), str(e))
                    return

                if dlg.migrate_requested:
                    old_configs = self.base_dir / "configs"
                    new_configs = new_ws / "configs"
                    if old_configs.is_dir():
                        new_configs.mkdir(parents=True, exist_ok=True)
                        for item in old_configs.iterdir():
                            dest = new_configs / item.name
                            if not dest.exists():
                                try:
                                    if item.is_dir():
                                        shutil.copytree(item, dest)
                                    else:
                                        shutil.copy2(item, dest)
                                except Exception:
                                    pass

                set_saved_workspace_dir(new_ws)
                self.base_dir = new_ws

                self._refresh_profiles_list()
                projects = self._list_projects()
                if projects:
                    self._load_selected_profile(0)
                else:
                    self._sync_config_to_ui()

                self._update_sources_status()
                self._update_jvm_status()
                self._update_maven_status()
                if self.is_windows:
                    self._update_wix_status()
                self._update_summary()

                self._msg_info(
                    t("dlg_info_title"),
                    t("dlg_workspace_changed", path=str(new_ws))
                )

    def _prompt_new_project(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("dlg_new_project_title"))
        dialog.setFixedSize(480, 200)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(20, 18, 20, 18)
        d_layout.setSpacing(10)

        lbl_prompt = QLabel(t("dlg_new_project_prompt"), dialog)
        font_prompt = lbl_prompt.font()
        font_prompt.setBold(True)
        lbl_prompt.setFont(font_prompt)
        d_layout.addWidget(lbl_prompt)

        edit_name = QLineEdit(dialog)
        edit_name.setPlaceholderText("Ex: MonProjet" if get_language() == "fr" else "Ex: MyProject")
        d_layout.addWidget(edit_name)

        lbl_err = QLabel("", dialog)
        lbl_err.setWordWrap(True)
        lbl_err.setStyleSheet("color: #dc2626; font-size: 11px;")
        d_layout.addWidget(lbl_err)

        edit_name.textChanged.connect(lambda: lbl_err.setText(""))

        d_layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_box.addStretch()

        btn_cancel = QPushButton(t("btn_cancel"), dialog)
        btn_cancel.clicked.connect(dialog.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton(t("btn_create"), dialog)
        btn_ok.setDefault(True)

        def on_confirm():
            name = edit_name.text().strip()
            if not name:
                lbl_err.setText(t("dlg_invalid_project_name"))
                return
            dialog.accept()
            recent_tags = self._get_online_tags()
            latest_tag = recent_tags[0] if recent_tags else "v5.0.2"
            latest_ver = latest_tag.lstrip("vV") or "5.0.2"
            clean_pref = f".{name.lower().replace(' ', '_')}"

            pom_to_use = self._find_active_product_pom()
            if pom_to_use and pom_to_use.exists():
                discovered = PhoebusPomManager.discover_modules_from_pom(pom_to_use)
                all_mods = [m.artifact_id for m in discovered]
            else:
                all_mods = PhoebusPomManager.get_all_module_ids()

            self.config = BuildConfig(
                app_name=name,
                app_version=latest_ver,
                phoebus_branch=latest_tag,
                phoebus_preference_folder=clean_pref,
                enabled_modules=all_mods,
                ui_dir="",
                home_display_file="",
                custom_settings_ini_path="",
                custom_logo_path="",
                custom_splash_path="",
                app_description="",
                app_vendor="",
                app_copyright="",
                app_url="",
                deb_maintainer="",
            )
            proj_name = name.lower().replace(' ', '_')
            proj_dir = self.config.save_to_project_bundle(proj_name, base_dir=self.base_dir)
            self._refresh_profiles_list()
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(proj_dir.name)
            self.profile_combo.blockSignals(False)
            self._sync_config_to_ui()
            self.tab_widget.setCurrentIndex(0)
            self.log(f"[OK] New project '{name}' : {proj_dir}/")

        btn_ok.clicked.connect(on_confirm)
        edit_name.returnPressed.connect(on_confirm)
        btn_box.addWidget(btn_ok)
        d_layout.addLayout(btn_box)

        dialog.exec()

    # --- LOGGING ---
    def log(self, message: str):
        clean_msg = strip_ansi(message)
        self.log_console.appendPlainText(clean_msg)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    # --- LANGUAGE CHANGE ---
    def _on_language_changed(self, text: str):
        new_lang = "en" if text == "English" else "fr"
        set_language(new_lang)
        from .app_settings import set_saved_language
        set_saved_language(new_lang)

    # --- CONFIGURATION SYNC ---
    def _sync_ui_to_config(self):
        tag = self.combo_tags.currentText().strip()
        if tag in (t("other_version_option"), "Autre version spécifique...", "Other specific version..."):
            tag = self.edit_custom_tag.text().strip() or "v5.0.2"
        self.config.phoebus_branch = tag

        # Sources mode & local path
        if hasattr(self, "radio_src_local"):
            self.config.use_local_sources = self.radio_src_local.isChecked()
        if hasattr(self, "edit_local_sources"):
            self.config.local_sources_path = self.edit_local_sources.text().strip()

        # JVM mode & local path
        if hasattr(self, "radio_jvm_local"):
            self.config.use_local_jdk = self.radio_jvm_local.isChecked()
        if hasattr(self, "edit_local_jdk"):
            self.config.local_jdk_path = self.edit_local_jdk.text().strip()

        # Maven mode & local path
        if hasattr(self, "radio_mvn_local"):
            self.config.use_local_maven = self.radio_mvn_local.isChecked()
        if hasattr(self, "edit_local_maven"):
            self.config.local_maven_path = self.edit_local_maven.text().strip()

        j_ver = self.combo_java.currentText().strip()
        if j_ver.startswith("25"):
            self.config.version_java = "25"
        elif j_ver.startswith("21"):
            self.config.version_java = "21"
        elif j_ver.startswith("17"):
            self.config.version_java = "17"
        else:
            self.config.version_java = j_ver

        self.config.phoebus_preference_folder = self.edit_pref_folder.text().strip() or ".phoebus"

        self.config.app_name = self.edit_app_name.text().strip() or "Phoebus"
        self.config.app_version = self.edit_app_version.text().strip() or "5.0.2"
        self.config.app_description = self.edit_app_desc.text().strip()
        self.config.app_vendor = self.edit_app_vendor.text().strip()
        self.config.app_copyright = self.edit_app_copyright.text().strip()
        self.config.app_url = self.edit_app_url.text().strip()
        self.config.deb_maintainer = self.edit_deb_maintainer.text().strip()

        # Modules
        if self.module_checkboxes:
            self.config.enabled_modules = [aid for aid, cb in self.module_checkboxes.items() if cb.isChecked()]

        self.config.custom_settings_ini_path = self.edit_settings_ini.text().strip()
        self.config.ui_dir = self.edit_ui_dir.text().strip()
        self.config.home_display_file = self.edit_home_display.text().strip()

        self.config.custom_logo_path = self.edit_logo_path.text().strip()
        self.config.custom_splash_path = self.edit_splash_path.text().strip()
        self.config.output_dir = self.edit_output_dir.text().strip() or "output"
        if hasattr(self, "chk_force_maven"):
            self.config.force_maven_rebuild = self.chk_force_maven.isChecked()
        if hasattr(self, "chk_clean_temp_build"):
            self.config.clean_temp_build = self.chk_clean_temp_build.isChecked()
        if self.is_windows:
            self.config.windows_package_type = "exe" if hasattr(self, "radio_exe") and self.radio_exe.isChecked() else "msi"

        self.config.target_platform = "windows" if self.is_windows else "linux"

    def _sync_config_to_ui(self):
        # Sources mode & local path
        if hasattr(self, "radio_src_local") and hasattr(self, "radio_src_github"):
            if self.config.use_local_sources:
                self.radio_src_local.setChecked(True)
            else:
                self.radio_src_github.setChecked(True)
            self._on_sources_mode_changed()
        if hasattr(self, "edit_local_sources"):
            self.edit_local_sources.setText(self.config.local_sources_path or "")

        # JVM mode & local path
        if hasattr(self, "radio_jvm_local") and hasattr(self, "radio_jvm_adoptium"):
            if self.config.use_local_jdk:
                self.radio_jvm_local.setChecked(True)
            else:
                self.radio_jvm_adoptium.setChecked(True)
            self._on_jvm_mode_changed()
        if hasattr(self, "edit_local_jdk"):
            self.edit_local_jdk.setText(self.config.local_jdk_path or "")

        # Maven mode & local path
        if hasattr(self, "radio_mvn_local") and hasattr(self, "radio_mvn_auto"):
            if self.config.use_local_maven:
                self.radio_mvn_local.setChecked(True)
            else:
                self.radio_mvn_auto.setChecked(True)
            self._on_maven_mode_changed()
        if hasattr(self, "edit_local_maven"):
            self.edit_local_maven.setText(self.config.local_maven_path or "")

        # Tag
        tag = self.config.phoebus_branch or "v5.0.2"
        idx = self.combo_tags.findText(tag)
        if idx >= 0:
            self.combo_tags.setCurrentIndex(idx)
        else:
            other_txt = t("other_version_option")
            self.combo_tags.setCurrentText(other_txt)
            self.edit_custom_tag.setText(tag)
            self.lbl_custom_tag.setVisible(True)
            self.edit_custom_tag.setVisible(True)

        # Java
        j_ver = self.config.version_java or "25"
        for i in range(self.combo_java.count()):
            if self.combo_java.itemText(i).startswith(j_ver):
                self.combo_java.setCurrentIndex(i)
                break

        # Preference Folder
        self.edit_pref_folder.setText(self.config.phoebus_preference_folder or ".phoebus")

        if hasattr(self, "chk_force_maven"):
            self.chk_force_maven.setChecked(self.config.force_maven_rebuild)
        if hasattr(self, "chk_clean_temp_build"):
            self.chk_clean_temp_build.setChecked(self.config.clean_temp_build)

        # Identity
        self.edit_app_name.setText(self.config.app_name or "Phoebus")
        self.edit_app_version.setText(self.config.app_version or "5.0.2")
        self.edit_app_desc.setText(self.config.app_description or "")
        self.edit_app_vendor.setText(self.config.app_vendor or "")
        self.edit_app_copyright.setText(self.config.app_copyright or "")
        self.edit_app_url.setText(self.config.app_url or "")
        self.edit_deb_maintainer.setText(self.config.deb_maintainer or "")

        # Modules
        if not self.config.enabled_modules:
            pom_to_use = self._find_active_product_pom()
            if pom_to_use and pom_to_use.exists():
                self.config.enabled_modules = [m.artifact_id for m in PhoebusPomManager.discover_modules_from_pom(pom_to_use)]
            else:
                self.config.enabled_modules = PhoebusPomManager.get_all_module_ids()

        if hasattr(self, "modules_scroll_layout"):
            self._populate_modules_ui()
        enabled_set = set(self.config.enabled_modules)
        for aid, cb in self.module_checkboxes.items():
            cb.setChecked(aid in enabled_set)

        self.edit_settings_ini.setText(self.config.custom_settings_ini_path or "")
        self.edit_ui_dir.setText(self.config.ui_dir or "")
        self.edit_home_display.setText(self.config.home_display_file or "")

        self.edit_logo_path.setText(self.config.custom_logo_path or "")
        self.edit_splash_path.setText(self.config.custom_splash_path or "")
        self.edit_output_dir.setText(self.config.output_dir or "output")

        if self.is_windows and hasattr(self, "radio_exe"):
            is_exe = (self.config.windows_package_type or "").lower() == "exe"
            self.radio_exe.setChecked(is_exe)
            self.radio_msi.setChecked(not is_exe)

        self._update_logo_preview()
        self._update_splash_preview()
        self._update_summary()

    # --- BUILD PROCESS & THREADING ---
    def _start_build_thread(self):
        if self.build_thread and self.build_thread.isRunning():
            self._msg_warning(t("dlg_confirm_title"), t("dlg_build_busy"))
            return

        self._sync_ui_to_config()
        errors = self.config.validate()
        if errors:
            err_msg = "\n".join([f"• {e}" for e in errors])
            self._msg_error(t("dlg_val_err_title"), err_msg)
            return

        active_pom = self._find_active_product_pom()
        if active_pom is None or not active_pom.exists() or active_pom.stat().st_size == 0:
            tag = self.config.phoebus_branch or "v5.0.5"
            if self._msg_confirm(
                t("dlg_sources_missing_title"),
                t("dlg_sources_missing_msg", version=tag),
                default_yes=True
            ):
                self._start_sources_download()
            return

        if not self._is_jvm_ready():
            j_ver = str(self.config.version_java or "25").split()[0]
            if self._msg_confirm(
                t("dlg_jvm_missing_title"),
                t("dlg_jvm_missing_msg", version=j_ver),
                default_yes=True
            ):
                self._start_jvm_download()
            return

        missing_tools = self.config.check_system_prerequisites()
        if missing_tools:
            err_msg = t("dlg_prereq_intro") + "\n\n" + "\n\n".join([f"• {e}" for e in missing_tools])
            self._msg_error(t("dlg_prereq_title"), err_msg, button_text=t("btn_close"))
            return

        if not self._msg_confirm(
            t("dlg_confirm_title"),
            t("dlg_confirm_build", app_name=self.config.app_name, version=self.config.app_version),
            default_yes=True
        ):
            return

        try:
            proj_name = self.config.app_name.lower().replace(" ", "_") if self.config.app_name else "project"
            proj_dir = self.config.save_to_project_bundle(proj_name)
            self._sync_config_to_ui()
            self._refresh_profiles_list()
            self.profile_combo.setCurrentText(proj_dir.name)
        except Exception:
            pass

        self.btn_build.setText(t("btn_building"))
        self.btn_build.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_build_status.setText(t("status_building"))
        self.progress_bar.setVisible(True)

        self.log("\n=======================================================")
        self.log(f"   START BUILD : {self.config.app_name} v{self.config.app_version}")
        self.log("=======================================================")

        self.build_thread = BuildWorkerThread(self.config, base_dir=self.base_dir)
        self.build_thread.log_signal.connect(self.log)
        self.build_thread.build_finished.connect(self._on_build_completed)
        self.build_thread.start()

    def _stop_build(self):
        if not (self.build_thread and self.build_thread.isRunning()):
            return

        if self._msg_confirm(t("dlg_confirm_title"), t("dlg_confirm_stop"), default_yes=False):
            self.log("\n[INTERRUPTION] Stop request received...")
            self.lbl_build_status.setText(t("status_stopping"))
            self.btn_stop.setEnabled(False)
            self.build_thread.cancel()

    def _clean_build_cache(self):
        """Handles user request to safely purge build directory."""
        if self.build_thread and self.build_thread.isRunning():
            self._msg_warning(t("dlg_build_busy"), t("status_building"))
            return

        proj_name = self.config.app_name.lower().replace(" ", "_") if self.config.app_name else "project"
        if not self.config.build_dir or self.config.build_dir == "build":
            build_dir = self.base_dir / "configs" / proj_name / "build"
        else:
            b_path = Path(self.config.build_dir)
            build_dir = b_path if b_path.is_absolute() else (self.base_dir / b_path)

        size = PhoebusPackager.get_dir_size(build_dir)
        if size == 0 or not build_dir.exists():
            self._msg_info(t("dlg_clean_success_title"), t("dlg_clean_empty"))
            return

        size_str = PhoebusPackager.format_size(size)
        reply = QMessageBox.question(
            self,
            t("dlg_confirm_clean_title"),
            t("dlg_confirm_clean_msg", path=str(build_dir), size=size_str),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            freed, count = PhoebusPackager.clean_build_cache(self.base_dir, str(build_dir.relative_to(self.base_dir) if build_dir.is_relative_to(self.base_dir) else build_dir))
            freed_str = PhoebusPackager.format_size(freed)
            self._msg_info(t("dlg_clean_success_title"), t("dlg_clean_success_msg", size=freed_str))
            self.log(f"[OK] Build cache purged: {count} items removed, {freed_str} freed.")

    def _on_build_completed(self, success: bool, result_msg: str, is_cancelled: bool):
        self.progress_bar.setVisible(False)
        self.btn_build.setText(t("btn_launch_build"))
        self.btn_stop.setEnabled(False)
        self._update_sources_status()
        self._update_jvm_status()
        out_p = Path(self.config.output_dir) if self.config.output_dir else Path("output")
        output_dir = out_p if out_p.is_absolute() else (self.base_dir / out_p)
        log_file = str(output_dir / "build.log")

        if success:
            self.lbl_build_status.setText(t("status_success"))
            self._msg_info(t("dlg_build_success_title"), t("dlg_build_success_msg", result=result_msg, log_file=log_file))
        elif is_cancelled:
            self.lbl_build_status.setText(t("status_interrupted"))
            self._msg_warning(t("dlg_build_cancelled_title"), t("dlg_build_cancelled_msg"))
        else:
            self.lbl_build_status.setText(t("status_error"))
            self._msg_error(t("dlg_build_error_title"), t("dlg_build_error_msg", result=result_msg, log_file=log_file))


def launch_gui(initial_config: Optional[BuildConfig] = None):
    """Entry point to instantiate and start the PySide6 main loop with native translator."""

    app = QApplication.instance()
    created_app = False
    if app is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
        app = QApplication(sys.argv)
        created_app = True
    # Set application metadata for OS integration
    app.setApplicationName("phoebus-builder")
    app.setApplicationDisplayName("Phoebus Builder")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("phoebus-builder")

    # Apply modern professional theme
    apply_app_theme(app)

    # Set application-level icon
    icon_path = Path(__file__).parent / "assets" / "phoebus-builder.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Install initial translator from saved preference or locale
    from .app_settings import get_saved_language, is_first_run, get_saved_workspace_dir
    saved_lang = get_saved_language()
    if saved_lang:
        set_language(saved_lang)
    else:
        set_language("en")

    # Onboarding wizard on first run or if no workspace is configured
    if is_first_run() or get_saved_workspace_dir() is None:
        first_run_dlg = FirstRunDialog()
        first_run_dlg.exec()
        if not get_saved_workspace_dir():
            # User dismissed the dialog without choosing a workspace: exit cleanly
            return

    window = PhoebusBuilderGUI(initial_config)
    window.show()

    if created_app:
        sys.exit(app.exec())
