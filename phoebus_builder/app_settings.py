"""
Persistent application-level settings for Phoebus Builder.
Stores global user preferences such as workspace directory, language, and first-run completion.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def get_settings_file_path() -> Path:
    """Returns the path to the global application settings JSON file in ~/.phoebus-builder/."""
    try:
        home = Path.home().resolve()
    except Exception:
        home = Path.cwd().resolve()
    app_dir = home / ".phoebus-builder"
    try:
        app_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    new_path = app_dir / ".phoebus-builder-app.json"

    # Auto-migrate legacy file from user home if present
    old_path = home / ".phoebus-builder-app.json"
    if old_path.exists() and not new_path.exists():
        try:
            import shutil
            shutil.copy2(old_path, new_path)
        except Exception:
            pass

    return new_path


def load_app_settings() -> Dict[str, Any]:
    """Loads and returns the application settings dictionary."""
    p = get_settings_file_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_app_settings(data: Dict[str, Any]) -> None:
    """Saves the application settings dictionary to the user configuration file."""
    p = get_settings_file_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_saved_workspace_dir() -> Optional[Path]:
    """Returns the user-configured workspace directory if set and non-empty."""
    data = load_app_settings()
    ws = data.get("workspace_dir")
    if ws and isinstance(ws, str) and ws.strip():
        return Path(ws.strip()).resolve()
    return None


def set_saved_workspace_dir(path: Path | str) -> None:
    """Persists the selected workspace directory in the application settings."""
    data = load_app_settings()
    data["workspace_dir"] = str(Path(path).resolve())
    save_app_settings(data)


def is_first_run() -> bool:
    """Checks if this is the first time the user launches Phoebus Builder."""
    data = load_app_settings()
    return not bool(data.get("first_run_completed", False))


def set_first_run_completed(completed: bool = True) -> None:
    """Marks first-run setup as completed in the application settings."""
    data = load_app_settings()
    data["first_run_completed"] = completed
    save_app_settings(data)


def get_saved_language() -> Optional[str]:
    """Returns the user's preferred language ('fr' or 'en') if saved."""
    data = load_app_settings()
    lang = data.get("language")
    if lang and isinstance(lang, str) and lang.lower() in ("fr", "en"):
        return lang.lower()
    return None


def set_saved_language(lang: str) -> None:
    """Persists the user's preferred language in the application settings."""
    if lang.lower() in ("fr", "en"):
        data = load_app_settings()
        data["language"] = lang.lower()
        save_app_settings(data)
