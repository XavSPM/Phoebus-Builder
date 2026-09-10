"""
Configuration module for Phoebus Native Installer Builder.
Handles loading, saving, and validating build settings and project bundles.
"""

from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
import shutil
import zipfile
from typing import Optional, Dict, Any, List, Tuple
from .modules import PhoebusPomManager


def get_workspace_dir(custom_dir: Optional[str | Path] = None) -> Path:
    """
    Returns the workspace base directory for projects, cached sources, and build artifacts.
    Priority:
    1. Explicit custom_dir parameter if provided.
    2. PHOEBUS_BUILDER_WORKSPACE environment variable if set.
    3. User-configured workspace directory saved in global application settings.
    Raises RuntimeError if no workspace directory has been specified.
    """
    if custom_dir:
        p = Path(custom_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    env_ws = os.environ.get("PHOEBUS_BUILDER_WORKSPACE")
    if env_ws:
        p = Path(env_ws).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    try:
        from .app_settings import get_saved_workspace_dir
        saved_ws = get_saved_workspace_dir()
        if saved_ws:
            saved_ws.mkdir(parents=True, exist_ok=True)
            return saved_ws
    except Exception:
        pass

    raise RuntimeError(
        "Aucun répertoire de travail configuré. Veuillez spécifier un répertoire de travail via "
        "l'assistant de premier démarrage, les paramètres de l'application, ou l'argument --workspace."
    )


@dataclass
class BuildConfig:
    """Configuration structure for Phoebus native packaging."""
    # Application metadata
    app_name: str = "Phoebus"
    app_version: str = ""
    app_description: str = ""
    app_vendor: str = ""
    app_copyright: str = ""
    app_url: str = ""
    deb_maintainer: str = ""
    
    # Versioning & Dependencies
    phoebus_branch: str = "v5.0.2"
    version_java: str = "25"
    phoebus_preference_folder: str = ".phoebus"

    # Phoebus modules and extensions selected for Maven compilation (pom.xml)
    enabled_modules: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Default application version to Phoebus version if not explicitly set
        if not self.app_version and self.phoebus_branch:
            self.app_version = self.phoebus_branch.lstrip("vV")
        if not self.enabled_modules:
            self.enabled_modules = PhoebusPomManager.get_all_module_ids()
    
    # Platform settings
    target_platform: str = "auto"  # 'linux', 'windows', or 'auto'
    linux_package_type: str = "auto"  # 'auto', 'deb', or 'rpm'
    windows_package_type: str = "msi"  # 'msi' or 'exe'
    linux_menu_group: str = "Utility"
    linux_rpm_license: str = "EPL-1.0"
    
    # Settings generation and compilation options
    generate_settings_template: bool = True
    build_from_source: bool = True
    force_maven_rebuild: bool = False
    clean_temp_build: bool = True
    settings_template_file: str = "settings_template.ini"
    custom_settings_ini_path: str = ""

    # Local sources & offline tool options
    use_local_sources: bool = False
    local_sources_path: str = ""
    use_local_jdk: bool = False
    local_jdk_path: str = ""
    use_local_maven: bool = False
    local_maven_path: str = ""

    # Custom paths (relative to project folder or absolute)
    ui_dir: str = ""
    home_display_file: str = ""
    custom_logo_path: str = ""
    custom_splash_path: str = ""
    resources_linux_dir: str = "resources/linux"
    resources_windows_dir: str = "resources/windows"
    output_dir: str = "output"
    build_dir: str = "build"
    
    # Windows specific tools
    wix_url: str = "https://github.com/wixtoolset/wix3/releases/download/wix3112rtm/wix311-binaries.zip"

    @staticmethod
    def detect_linux_package_type() -> str:
        """Automatically detects native package type according to Linux distribution (deb or rpm)."""
        os_release = Path("/etc/os-release")
        if os_release.exists():
            content = os_release.read_text(encoding="utf-8", errors="ignore").lower()
            if any(distro in content for distro in ["fedora", "rhel", "redhat", "centos", "almalinux", "rocky", "suse"]):
                return "rpm"
            if any(distro in content for distro in ["debian", "ubuntu", "mint", "kali", "raspbian", "pop"]):
                return "deb"
        import shutil
        if shutil.which("rpmbuild") and not shutil.which("dpkg-deb"):
            return "rpm"
        return "deb"

    def get_settings_template_path(self, base_dir: Optional[Path] = None) -> Optional[Path]:
        """Finds the settings_template.ini for the configured version under sources/phoebus/phoebus-<ver>/ or local sources."""
        base = base_dir or get_workspace_dir()
        candidates = []
        if self.use_local_sources and self.local_sources_path:
            p = Path(self.local_sources_path)
            if not p.is_absolute():
                p = base / p
            if p.is_dir():
                candidates.append(p / "settings_template.ini")
                candidates.append(p / "phoebus-product" / "settings_template.ini")

        raw_tag = (self.phoebus_branch or "").strip()
        clean_tag = raw_tag.lstrip("vV")
        if clean_tag:
            candidates.append(base / "sources" / "phoebus" / f"phoebus-{clean_tag}" / "settings_template.ini")
            candidates.append(base / "sources" / "phoebus" / f"phoebus-v{clean_tag}" / "settings_template.ini")
        candidates.append(base / "sources" / "settings_template.ini")
        for cand in candidates:
            if cand.exists() and cand.stat().st_size > 0:
                return cand
        sources_phoebus = base / "sources" / "phoebus"
        if sources_phoebus.exists():
            templates = sorted(list(sources_phoebus.glob("**/settings_template.ini")), reverse=True)
            if templates:
                return templates[0]
        return None

    @classmethod
    def from_settings_file(cls, filepath: str | Path) -> "BuildConfig":
        """Loads configuration from key=value file format (legacy settings)."""
        path = Path(filepath)
        if not path.exists():
            return cls()

        data: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    data[key] = val

        config = cls()
        mapping = {
            "APP_NAME": "app_name",
            "APP_VERSION": "app_version",
            "APP_DESCRIPTION": "app_description",
            "APP_VENDOR": "app_vendor",
            "APP_COPYRIGHT": "app_copyright",
            "APP_URL": "app_url",
            "DEB_MAINTAINER": "deb_maintainer",
            "PHOEBUS_BRANCH": "phoebus_branch",
            "VERSION_JAVA": "version_java",
            "PHOEBUS_PREFERENCE_FOLDER": "phoebus_preference_folder",
            "USE_LOCAL_SOURCES": "use_local_sources",
            "LOCAL_SOURCES_PATH": "local_sources_path",
            "USE_LOCAL_JDK": "use_local_jdk",
            "LOCAL_JDK_PATH": "local_jdk_path",
            "USE_LOCAL_MAVEN": "use_local_maven",
            "LOCAL_MAVEN_PATH": "local_maven_path",
            "LINUX_PACKAGE_TYPE": "linux_package_type",
            "WINDOWS_PACKAGE_TYPE": "windows_package_type",
            "LINUX_MENU_GROUP": "linux_menu_group",
            "LINUX_RPM_LICENSE": "linux_rpm_license",
            "WIX_URL": "wix_url",
            "CUSTOM_SETTINGS_INI_PATH": "custom_settings_ini_path",
            "UI_DIR": "ui_dir",
            "HOME_DISPLAY_FILE": "home_display_file",
            "CUSTOM_LOGO_PATH": "custom_logo_path",
            "CUSTOM_SPLASH_PATH": "custom_splash_path",
        }

        bool_fields = {"use_local_sources", "use_local_jdk", "use_local_maven"}
        for env_var, attr_name in mapping.items():
            if env_var in data and data[env_var]:
                val = data[env_var]
                if attr_name in bool_fields:
                    setattr(config, attr_name, str(val).lower() in ("true", "1", "yes"))
                else:
                    setattr(config, attr_name, val)

        return config

    @classmethod
    def from_json_file(cls, filepath: str | Path, base_dir: Optional[Path] = None) -> "BuildConfig":
        """Loads configuration from a JSON file."""
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    @classmethod
    def from_project(cls, target_path: str | Path, base_dir: Optional[Path] = None) -> "BuildConfig":
        """Loads configuration from a project directory (e.g. configs/mobilis/) or JSON file."""
        path = Path(target_path)
        base = base_dir or get_workspace_dir()
        if not path.is_absolute():
            path = base / path

        if path.is_dir():
            json_file = path / "config.json"
            if not json_file.exists():
                # Search for any .json file inside directory
                jsons = list(path.glob("*.json"))
                if jsons:
                    json_file = jsons[0]
                else:
                    raise FileNotFoundError(f"No config.json file found in project directory '{path}'.")
        else:
            json_file = path

        config = cls.from_json_file(json_file)
        proj_dir = json_file.parent

        # Adjust relative paths against project directory
        if config.custom_settings_ini_path:
            p = proj_dir / config.custom_settings_ini_path
            if p.exists():
                config.custom_settings_ini_path = str(p.relative_to(base) if p.is_relative_to(base) else p)
        elif (proj_dir / "settings.ini").exists():
            p = proj_dir / "settings.ini"
            config.custom_settings_ini_path = str(p.relative_to(base) if p.is_relative_to(base) else p)

        if config.custom_logo_path:
            p = proj_dir / config.custom_logo_path
            if p.exists():
                config.custom_logo_path = str(p.relative_to(base) if p.is_relative_to(base) else p)
        else:
            for cand in ["logo.png", "logo.ico", "site_logo.png", "site_logo.ico"]:
                if (proj_dir / cand).exists():
                    p = proj_dir / cand
                    config.custom_logo_path = str(p.relative_to(base) if p.is_relative_to(base) else p)
                    break

        if config.custom_splash_path:
            p = proj_dir / config.custom_splash_path
            if p.exists():
                config.custom_splash_path = str(p.relative_to(base) if p.is_relative_to(base) else p)
        elif (proj_dir / "site_splash.png").exists():
            p = proj_dir / "site_splash.png"
            config.custom_splash_path = str(p.relative_to(base) if p.is_relative_to(base) else p)

        if config.ui_dir:
            p = proj_dir / config.ui_dir
            if p.exists() and p.is_dir():
                config.ui_dir = str(p.relative_to(base) if p.is_relative_to(base) else p)
        elif (proj_dir / "ui").exists() and (proj_dir / "ui").is_dir():
            p = proj_dir / "ui"
            config.ui_dir = str(p.relative_to(base) if p.is_relative_to(base) else p)
        if config.local_sources_path:
            p = Path(config.local_sources_path)
            if not p.is_absolute() and (proj_dir / p).exists():
                config.local_sources_path = str((proj_dir / p).resolve())

        if config.local_jdk_path:
            p = Path(config.local_jdk_path)
            if not p.is_absolute() and (proj_dir / p).exists():
                config.local_jdk_path = str((proj_dir / p).resolve())

        if config.local_maven_path:
            p = Path(config.local_maven_path)
            if not p.is_absolute() and (proj_dir / p).exists():
                config.local_maven_path = str((proj_dir / p).resolve())

        config.build_dir = str((proj_dir / "build").relative_to(base) if (proj_dir / "build").is_relative_to(base) else (proj_dir / "build"))

        return config

    def save_to_project_bundle(self, project_name: Optional[str] = None, base_dir: Optional[Path] = None) -> Path:
        """
        Saves and consolidates the entire project into a dedicated directory: configs/<project_name>/.
        Automatically gathers config.json, settings.ini, logo, splash screen, and UI files.
        """
        import shutil

        base = base_dir or get_workspace_dir()
        name = project_name or (self.app_name.lower().replace(" ", "_") if self.app_name else "phoebus_project")
        proj_dir = base / "configs" / name
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Consolidate project files into destination folder
        if self.custom_settings_ini_path:
            src_ini = Path(self.custom_settings_ini_path)
            if not src_ini.is_absolute():
                src_ini = base / src_ini
            dest_ini = proj_dir / "settings.ini"
            if src_ini.exists() and src_ini.resolve() != dest_ini.resolve():
                shutil.copy2(src_ini, dest_ini)
                self.custom_settings_ini_path = str(dest_ini.relative_to(base))
            elif dest_ini.exists():
                self.custom_settings_ini_path = str(dest_ini.relative_to(base))

        if self.custom_logo_path:
            src_logo = Path(self.custom_logo_path)
            if not src_logo.is_absolute():
                src_logo = base / src_logo
            if src_logo.exists():
                from .image_utils import ImageValidator
                import platform
                is_win = (self.target_platform == "windows") or (platform.system() == "Windows")
                if is_win and src_logo.suffix.lower() != ".ico":
                    dest_logo = proj_dir / "logo.ico"
                    ImageValidator.convert_to_ico(src_logo, dest_logo)
                else:
                    dest_logo = proj_dir / src_logo.name
                    if src_logo.resolve() != dest_logo.resolve():
                        shutil.copy2(src_logo, dest_logo)
                self.custom_logo_path = str(dest_logo.relative_to(base))

                # Ensure 64x64 site_logo.png exists in project folder
                site_logo_target = proj_dir / "site_logo.png"
                if not site_logo_target.exists():
                    try:
                        ImageValidator.generate_site_logo(dest_logo, site_logo_target, target_size=(64, 64))
                    except Exception:
                        pass

        if self.custom_splash_path:
            src_splash = Path(self.custom_splash_path)
            if not src_splash.is_absolute():
                src_splash = base / src_splash
            if src_splash.exists():
                dest_splash = proj_dir / "site_splash.png"
                if src_splash.resolve() != dest_splash.resolve():
                    shutil.copy2(src_splash, dest_splash)
                self.custom_splash_path = str(dest_splash.relative_to(base))

        if self.ui_dir:
            src_ui = Path(self.ui_dir)
            if not src_ui.is_absolute():
                src_ui = base / src_ui
            dest_ui = proj_dir / "ui"
            if src_ui.exists() and src_ui.is_dir() and src_ui.resolve() != dest_ui.resolve():
                if dest_ui.exists():
                    shutil.rmtree(dest_ui)
                shutil.copytree(src_ui, dest_ui)
                self.ui_dir = str(dest_ui.relative_to(base))
            elif dest_ui.exists():
                self.ui_dir = str(dest_ui.relative_to(base))

        self.build_dir = str((proj_dir / "build").relative_to(base) if (proj_dir / "build").is_relative_to(base) else (proj_dir / "build"))
        json_path = proj_dir / "config.json"
        self.save_to_json_file(json_path)

        return proj_dir

    @staticmethod
    def export_project_to_zip(project_name: str, dest_zip: str | Path, base_dir: Optional[Path] = None) -> Path:
        """
        Exports a complete project directory (configs/<project_name>/) into a portable .zip archive.
        """
        base = base_dir or get_workspace_dir()
        proj_dir = base / "configs" / project_name
        if not proj_dir.exists() or not proj_dir.is_dir():
            raise FileNotFoundError(f"Project directory does not exist: {proj_dir}")

        dest = Path(dest_zip).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in proj_dir.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(proj_dir)
                    zf.write(item, arcname=str(rel_path))

        return dest

    @staticmethod
    def import_project_from_zip(
        zip_path: str | Path,
        target_name: Optional[str] = None,
        base_dir: Optional[Path] = None,
        overwrite: bool = False
    ) -> Tuple[str, Path]:
        """
        Imports a project from a .zip archive into the workspace (configs/<target_name>/).
        Validates zip integrity and protects against Zip Slip attacks.
        Returns a tuple of (imported_project_name, project_directory_path).
        """
        base = base_dir or get_workspace_dir()
        src_zip = Path(zip_path).resolve()
        if not src_zip.exists():
            raise FileNotFoundError(f"Archive file does not exist: {src_zip}")

        with zipfile.ZipFile(src_zip, "r") as zf:
            namelist = zf.namelist()
            config_entry = None
            for name in namelist:
                parts = Path(name).parts
                if parts and parts[-1] == "config.json":
                    if name == "config.json":
                        config_entry = name
                        break
                    elif config_entry is None:
                        config_entry = name

            if not config_entry:
                raise ValueError("Invalid project archive: 'config.json' not found inside the ZIP.")

            prefix = str(Path(config_entry).parent)
            if prefix == ".":
                prefix = ""

            with zf.open(config_entry) as cf:
                try:
                    data = json.load(cf)
                    detected_name = data.get("app_name", "").strip()
                except Exception:
                    detected_name = ""

            raw_name = target_name or detected_name or src_zip.stem
            final_name = raw_name.lower().replace(" ", "_").strip()
            if not final_name:
                final_name = "imported_project"

            dest_dir = base / "configs" / final_name
            if dest_dir.exists() and not overwrite:
                raise FileExistsError(f"Project '{final_name}' already exists in workspace.")

            dest_dir.mkdir(parents=True, exist_ok=True)

            for member in zf.infolist():
                if member.is_dir():
                    continue

                member_path = member.filename
                if prefix and member_path.startswith(prefix + "/"):
                    rel_name = member_path[len(prefix) + 1:]
                elif prefix and member_path == prefix:
                    continue
                else:
                    rel_name = member_path

                target_file = (dest_dir / rel_name).resolve()
                if not target_file.is_relative_to(dest_dir.resolve()):
                    raise ValueError(f"Malicious archive entry detected (Zip Slip): {member.filename}")

                target_file.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as sfp, open(target_file, "wb") as dfp:
                    shutil.copyfileobj(sfp, dfp)

            cfg_path = dest_dir / "config.json"
            if cfg_path.exists():
                cfg = BuildConfig.from_json_file(cfg_path, base_dir=base)
                cfg.save_to_project_bundle(final_name, base_dir=base)

        return final_name, dest_dir

    @staticmethod
    def duplicate_project(source_name: str, target_name: str, base_dir: Optional[Path] = None) -> Path:
        """
        Duplicates an existing project folder to a new name.
        """
        base = base_dir or get_workspace_dir()
        src_dir = base / "configs" / source_name
        if not src_dir.exists() or not src_dir.is_dir():
            raise FileNotFoundError(f"Source project does not exist: {src_dir}")

        clean_target = target_name.lower().replace(" ", "_").strip()
        if not clean_target:
            raise ValueError("Target project name cannot be empty.")

        dest_dir = base / "configs" / clean_target
        if dest_dir.exists():
            raise FileExistsError(f"Target project '{clean_target}' already exists.")

        shutil.copytree(src_dir, dest_dir)
        cfg_path = dest_dir / "config.json"
        if cfg_path.exists():
            cfg = BuildConfig.from_json_file(cfg_path, base_dir=base)
            cfg.app_name = target_name
            cfg.save_to_project_bundle(clean_target, base_dir=base)

        return dest_dir

    def save_to_settings_file(self, filepath: str | Path) -> None:
        """Saves configuration in key=value format."""
        path = Path(filepath)
        content = f"""# Configuration generated by Phoebus Builder
APP_NAME="{self.app_name}"
APP_VERSION="{self.app_version}"
APP_DESCRIPTION="{self.app_description}"
APP_VENDOR="{self.app_vendor}"
APP_COPYRIGHT="{self.app_copyright}"
APP_URL="{self.app_url}"
DEB_MAINTAINER="{self.deb_maintainer}"

PHOEBUS_BRANCH="{self.phoebus_branch}"
VERSION_JAVA="{self.version_java}"
PHOEBUS_PREFERENCE_FOLDER="{self.phoebus_preference_folder}"

USE_LOCAL_SOURCES="{str(self.use_local_sources).lower()}"
LOCAL_SOURCES_PATH="{self.local_sources_path}"
USE_LOCAL_JDK="{str(self.use_local_jdk).lower()}"
LOCAL_JDK_PATH="{self.local_jdk_path}"
USE_LOCAL_MAVEN="{str(self.use_local_maven).lower()}"
LOCAL_MAVEN_PATH="{self.local_maven_path}"

LINUX_MENU_GROUP="{self.linux_menu_group}"
WIX_URL="{self.wix_url}"

CUSTOM_SETTINGS_INI_PATH="{self.custom_settings_ini_path}"
UI_DIR="{self.ui_dir}"
HOME_DISPLAY_FILE="{self.home_display_file}"
CUSTOM_LOGO_PATH="{self.custom_logo_path}"
CUSTOM_SPLASH_PATH="{self.custom_splash_path}"
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def save_to_json_file(self, filepath: str | Path) -> None:
        """Saves configuration to a JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=4, ensure_ascii=False)

    def validate(self) -> list[str]:
        """Validates required configuration fields."""
        from .i18n import t
        errors = []
        if not self.app_name.strip():
            errors.append(t("dlg_val_app_name"))
        if not self.app_version.strip():
            errors.append(t("dlg_val_app_version"))

        if self.use_local_sources:
            if not self.local_sources_path.strip():
                errors.append(t("dlg_val_local_sources_missing"))
            else:
                p = Path(self.local_sources_path)
                if not p.exists():
                    errors.append(t("dlg_val_local_sources_missing"))
        else:
            if not self.phoebus_branch.strip():
                errors.append(t("dlg_val_phoebus_branch"))

        if self.use_local_jdk:
            if not self.local_jdk_path.strip():
                errors.append(t("dlg_val_local_jdk_missing"))
            else:
                p = Path(self.local_jdk_path)
                if not p.exists():
                    errors.append(t("dlg_val_local_jdk_missing"))
        else:
            if not self.version_java.strip():
                errors.append(t("dlg_val_java_version"))

        if self.use_local_maven:
            if not self.local_maven_path.strip():
                errors.append(t("dlg_val_local_maven_missing"))
            else:
                p = Path(self.local_maven_path)
                if not p.exists():
                    errors.append(t("dlg_val_local_maven_missing"))

        return errors

    def check_system_prerequisites(self) -> list[str]:
        """Checks for required system tools on the host OS."""
        import platform
        import shutil
        from .i18n import t

        missing = []
        is_win = (self.target_platform.lower() == "windows") if self.target_platform != "auto" else (platform.system().lower() == "windows")

        from .downloader import DownloadManager
        shared_maven = get_workspace_dir() / "sources" / "maven"
        mvn_bin = "mvn.cmd" if is_win else "mvn"
        local_maven_ok = False
        if self.use_local_maven and self.local_maven_path:
            p_mvn = Path(self.local_maven_path)
            if p_mvn.exists():
                local_maven_ok = True

        if not local_maven_ok and not shutil.which(mvn_bin) and not shutil.which("mvn") and not DownloadManager.is_maven_ready(shared_maven):
            if is_win:
                missing.append(t("dlg_prereq_mvn_win"))
            else:
                missing.append(t("dlg_prereq_mvn_linux"))

        if not is_win and not shutil.which("tar"):
            missing.append(t("dlg_prereq_tar"))

        if not is_win:
            pkg_type = self.linux_package_type if self.linux_package_type in ["deb", "rpm"] else self.detect_linux_package_type()
            if pkg_type == "deb":
                if not shutil.which("fakeroot"):
                    missing.append(t("dlg_prereq_fakeroot"))
                if not shutil.which("dpkg-deb"):
                    missing.append(t("dlg_prereq_dpkg"))
            elif pkg_type == "rpm":
                if not shutil.which("rpmbuild"):
                    missing.append(t("dlg_prereq_rpmbuild"))

        return missing
