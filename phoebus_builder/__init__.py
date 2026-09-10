"""
Phoebus Builder
A GUI and automated builder for custom Phoebus native desktop installers (Debian .deb, RPM .rpm, Windows .msi).
"""

__version__ = "1.0.0"

from .config import BuildConfig
from .wizard import InteractiveWizard
from .packager import PhoebusPackager
from .downloader import DownloadManager
from .jvm import JvmManager
from .settings_generator import SettingsGenerator
from .settings_editor import SettingsEditor
from .file_browser import NativeFileBrowser
from .image_utils import ImageValidator
try:
    from .gui import PhoebusBuilderGUI, launch_gui
except ImportError:
    PhoebusBuilderGUI = None
    launch_gui = None
from .modules import PHOEBUS_MODULES, PhoebusPomManager
from .i18n import t, get_language, set_language
from .cli import main

__all__ = [
    "__version__",
    "main",
    "BuildConfig",
    "InteractiveWizard",
    "PhoebusPackager",
    "DownloadManager",
    "JvmManager",
    "SettingsGenerator",
    "SettingsEditor",
    "NativeFileBrowser",
    "ImageValidator",
    "PhoebusBuilderGUI",
    "launch_gui",
    "PHOEBUS_MODULES",
    "PhoebusPomManager",
    "t",
    "get_language",
    "set_language",
]
