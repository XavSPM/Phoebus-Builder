"""
Interactive CLI wizard module for configuring and building custom Phoebus native installers.
"""

import json
import os
import platform
import re
import sys
import urllib.request
from pathlib import Path
from typing import List, Optional, Callable

from .config import BuildConfig, get_workspace_dir
from .downloader import DownloadManager
from .settings_generator import SettingsGenerator
from .settings_editor import SettingsEditor
from .file_browser import NativeFileBrowser
from .image_utils import ImageValidator


# ANSI terminal styling codes
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BG_BLUE = "\033[44m"


def print_banner():
    """Prints a styled welcoming banner in the terminal."""
    print(f"""{Style.CYAN}{Style.BOLD}
  ╔══════════════════════════════════════════════════════════════════╗
  ║                                                                  ║
  ║      🚀  CUSTOM PHOEBUS NATIVE INSTALLER GENERATOR               ║
  ║                                                                  ║
  ╚══════════════════════════════════════════════════════════════════╝{Style.RESET}
    {Style.DIM}Automated native packaging (.deb / .rpm / .msi) with Adoptium & jpackage{Style.RESET}
""")


def ask_text(
    prompt: str,
    default: str = "",
    validator: Optional[Callable[[str], bool]] = None,
    error_msg: str = "Invalid input.",
    optional: bool = False
) -> str:
    """Prompts for text input with default values and optional field handling."""
    while True:
        if optional:
            if default:
                default_display = f" {Style.DIM}[optional, default: {default} | '-' to clear]{Style.RESET}"
            else:
                default_display = f" {Style.DIM}[optional, press Enter to skip]{Style.RESET}"
        else:
            default_display = f" {Style.DIM}[default: {default}]{Style.RESET}" if default else f" {Style.DIM}[required]{Style.RESET}"

        sys.stdout.write(f"{Style.BOLD}?{Style.RESET} {prompt}{default_display}: ")
        sys.stdout.flush()
        try:
            val = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

        # Clear optional field
        if optional and val.lower() in ["-", "none", "clear", "skip"]:
            return ""

        if not val:
            if optional:
                return default if default else ""
            elif default:
                return default
            else:
                print(f"  {Style.RED}⚠ This field is required.{Style.RESET}")
                continue

        if validator and not validator(val):
            print(f"  {Style.RED}⚠ {error_msg}{Style.RESET}")
            continue

        return val


def ask_choice(
    prompt: str,
    options: List[str],
    default_index: int = 0
) -> str:
    """Prompts user to select from a list of options."""
    print(f"\n{Style.BOLD}?{Style.RESET} {prompt}")
    for idx, opt in enumerate(options, 1):
        is_default = (idx - 1 == default_index)
        marker = f"{Style.GREEN}●{Style.RESET}" if is_default else "○"
        default_tag = f" {Style.DIM}(recommended / default){Style.RESET}" if is_default else ""
        print(f"   {marker} {idx}) {opt}{default_tag}")

    while True:
        sys.stdout.write(f"   Your choice {Style.DIM}[1-{len(options)}, default: {default_index + 1}]{Style.RESET}: ")
        sys.stdout.flush()
        try:
            choice = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

        if not choice:
            return options[default_index]

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]

        # Text matching
        for opt in options:
            if choice.lower() in opt.lower():
                return opt

        print(f"   {Style.RED}⚠ Invalid choice. Please enter a number between 1 and {len(options)}.{Style.RESET}")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompts a Yes/No question."""
    default_hint = "Y/n" if default else "y/N"
    while True:
        sys.stdout.write(f"{Style.BOLD}?{Style.RESET} {prompt} {Style.DIM}[{default_hint}]{Style.RESET}: ")
        sys.stdout.flush()
        try:
            ans = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

        if not ans:
            return default
        if ans in ["y", "yes", "o", "oui"]:
            return True
        if ans in ["n", "no", "non"]:
            return False

        print(f"   {Style.RED}⚠ Please answer 'y' (yes) or 'n' (no).{Style.RESET}")


def fetch_recent_phoebus_tags() -> List[str]:
    """Fetches official Phoebus release tags from GitHub API. Raises ConnectionError if network is down."""
    import ssl
    import urllib.error

    url = "https://api.github.com/repos/ControlSystemStudio/phoebus/releases?per_page=10"
    headers = {
        "User-Agent": "Phoebus-Builder/1.0",
        "Accept": "application/vnd.github.v3+json"
    }
    req = urllib.request.Request(url, headers=headers)
    ssl_ctx = DownloadManager.get_ssl_context()

    def _do_fetch(ctx: Optional[ssl.SSLContext]) -> List[str]:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tags = [rel["tag_name"] for rel in data if isinstance(rel, dict) and "tag_name" in rel]
            if tags:
                return tags
        raise ConnectionError("No official Phoebus releases returned by GitHub API.")

    try:
        try:
            return _do_fetch(ssl_ctx)
        except (urllib.error.URLError, ssl.SSLError) as ssl_err:
            err_str = str(ssl_err)
            if "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str or isinstance(ssl_err, ssl.SSLError):
                return _do_fetch(ssl._create_unverified_context())
            raise
    except Exception as e:
        raise ConnectionError(
            f"Unable to contact GitHub to retrieve Phoebus official releases.\n"
            f"An active Internet connection is required to fetch dependencies and build the installer.\n"
            f"Network error: {e}"
        )



class InteractiveWizard:
    """Step-by-step interactive CLI questionnaire to configure and package Phoebus."""

    def __init__(self, initial_config: Optional[BuildConfig] = None, base_dir: Optional[Path] = None):
        self.config = initial_config or BuildConfig()
        self.base_dir = base_dir or get_workspace_dir()

    def run(self) -> BuildConfig:
        """Executes all questionnaire steps."""
        print_banner()

        # Check if projects exist in configs/
        configs_dir = self.base_dir / "configs"
        has_projects = configs_dir.exists() and any(d.is_dir() and (d / "config.json").exists() for d in configs_dir.iterdir())
        if not has_projects:
            print(f"{Style.YELLOW}ℹ No existing project found in configs/. Let's create a new project!{Style.RESET}\n")
            proj_name = ask_text(
                "Project / Application Name",
                default=self.config.app_name if self.config.app_name and self.config.app_name != "Phoebus" else "MyPhoebusApp",
                validator=lambda s: len(s.strip()) > 0,
                error_msg="Project name cannot be empty.",
                optional=False
            )
            self.config.app_name = proj_name

        # --- STEP 1: Core Stack & Phoebus ---
        print(f"\n{Style.BG_BLUE}{Style.BOLD} 1. CORE STACK & PHOEBUS {Style.RESET}\n")

        # Phoebus release selection
        # Phoebus sources choice
        src_mode = ask_choice(
            "Phoebus source code origin",
            ["GitHub release (download online)", "Local sources (directory or archive)"],
            default_index=1 if self.config.use_local_sources else 0
        )

        if "Local" in src_mode:
            self.config.use_local_sources = True
            self.config.local_sources_path = ask_text(
                "Local Phoebus directory or archive path",
                default=self.config.local_sources_path,
                validator=lambda s: Path(s.strip()).exists(),
                error_msg="Path does not exist."
            )
        else:
            self.config.use_local_sources = False
            try:
                recent_tags = fetch_recent_phoebus_tags()
            except ConnectionError as e:
                print(f"  {Style.YELLOW}⚠ Warning: Could not fetch online tags from GitHub ({e.args[0].splitlines()[0] if e.args else e}). Using default version list.{Style.RESET}")
                recent_tags = ["v5.0.5", "v5.0.2", "v4.7.3"]

            phoebus_options = recent_tags + ["Other specific version..."]
            default_tag_idx = 0
            if self.config.phoebus_branch in recent_tags:
                default_tag_idx = recent_tags.index(self.config.phoebus_branch)

            chosen_tag = ask_choice(
                "Phoebus base release (GitHub)",
                phoebus_options,
                default_index=default_tag_idx
            )

            if chosen_tag == "Other specific version...":
                self.config.phoebus_branch = ask_text(
                    "Enter Phoebus git tag (e.g. v5.0.2)",
                    default="v5.0.2",
                    validator=lambda s: len(s.strip()) > 0
                )
            else:
                self.config.phoebus_branch = chosen_tag

        # Java JDK selection
        jvm_mode = ask_choice(
            "Java JVM origin",
            ["Adoptium Temurin (download online)", "Local JDK (directory or archive)"],
            default_index=1 if self.config.use_local_jdk else 0
        )

        if "Local" in jvm_mode:
            self.config.use_local_jdk = True
            detected = JvmManager.detect_system_jdks(platform.system().lower() == "windows")
            default_jdk = str(detected[0]) if detected else self.config.local_jdk_path
            self.config.local_jdk_path = ask_text(
                "Local JDK directory or archive path",
                default=default_jdk,
                validator=lambda s: Path(s.strip()).exists(),
                error_msg="Path does not exist."
            )
        else:
            self.config.use_local_jdk = False
            java_options = ["25 (Adoptium Temurin latest)", "21 (Standard LTS)", "17 (LTS)", "Other version..."]
            default_java_idx = 0 if self.config.version_java == "25" else (1 if self.config.version_java == "21" else 0)
            chosen_java = ask_choice(
                "Adoptium Temurin Java JDK major version",
                java_options,
                default_index=default_java_idx
            )

            if chosen_java.startswith("25"):
                self.config.version_java = "25"
            elif chosen_java.startswith("21"):
                self.config.version_java = "21"
            elif chosen_java.startswith("17"):
                self.config.version_java = "17"
            else:
                self.config.version_java = ask_text(
                    "Java major version number",
                    default="25",
                    validator=lambda s: s.isdigit()
                )

        # Maven selection
        mvn_mode = ask_choice(
            "Apache Maven tool origin",
            ["Automatic (system PATH or portable download)", "Custom local Maven (directory or archive)"],
            default_index=1 if self.config.use_local_maven else 0
        )
        if "Custom" in mvn_mode:
            self.config.use_local_maven = True
            self.config.local_maven_path = ask_text(
                "Local Maven directory or archive path",
                default=self.config.local_maven_path,
                validator=lambda s: Path(s.strip()).exists(),
                error_msg="Path does not exist."
            )
        else:
            self.config.use_local_maven = False

        # Windows installer format (MSI / EXE)
        if platform.system().lower() == "windows":
            win_pkg_options = ["MSI (.msi) - Standard Windows Installer", "EXE (.exe) - Executable Setup Installer"]
            default_win_idx = 0 if self.config.windows_package_type.lower() == "msi" else 1
            chosen_win_pkg = ask_choice(
                "Windows package installer format",
                win_pkg_options,
                default_index=default_win_idx
            )
            self.config.windows_package_type = "exe" if "exe" in chosen_win_pkg.lower() else "msi"

        self.config.build_from_source = True

        # --- STEP 2: Application Identity ---
        print(f"\n{Style.BG_BLUE}{Style.BOLD} 2. APPLICATION IDENTITY {Style.RESET}\n")
        
        self.config.app_name = ask_text(
            "Application Name",
            default=self.config.app_name,
            validator=lambda s: len(s.strip()) > 0,
            error_msg="Name cannot be empty.",
            optional=False
        )

        # Default version deduced from Phoebus branch
        phoebus_version_clean = self.config.phoebus_branch.lstrip("vV")
        default_app_version = self.config.app_version if self.config.app_version not in ("1.0.0", "", "0.0.0") else phoebus_version_clean

        self.config.app_version = ask_text(
            "Application Version",
            default=default_app_version,
            validator=lambda s: bool(re.match(r"^\d+(\.\d+)*", s.strip())),
            error_msg="Version must be numeric (e.g. 5.0.2 or 2.0).",
            optional=False
        )

        self.config.app_description = ask_text(
            "Application Short Description",
            default=self.config.app_description,
            optional=True
        )

        self.config.app_vendor = ask_text(
            "Vendor / Organization",
            default=self.config.app_vendor,
            optional=True
        )

        self.config.app_copyright = ask_text(
            "Copyright Notice",
            default=self.config.app_copyright,
            optional=True
        )

        self.config.app_url = ask_text(
            "Project Website / URL",
            default=self.config.app_url,
            optional=True
        )

        self.config.deb_maintainer = ask_text(
            "Maintainer Contact (Format: Name <email>)",
            default=self.config.deb_maintainer,
            optional=True
        )

        # --- STEP 3: Settings Configuration & UI ---
        print(f"\n{Style.BG_BLUE}{Style.BOLD} 3. PHOEBUS SETTINGS (settings.ini) & UI DISPLAYS {Style.RESET}\n")

        # 1. User preferences folder
        app_clean_name = self.config.app_name.strip().lower().replace(" ", "_")
        default_pref = f".{app_clean_name}" if app_clean_name else ".phoebus"
        pref_to_propose = self.config.phoebus_preference_folder
        if not pref_to_propose or pref_to_propose == ".phoebus":
            pref_to_propose = default_pref

        self.config.phoebus_preference_folder = ask_text(
            "User preference subfolder name",
            default=pref_to_propose
        )

        # 2. settings.ini configuration
        default_linux_ini = "resources/linux/settings.ini"
        default_win_ini = "resources/windows/settings.ini"
        has_existing_ini = Path(default_linux_ini).exists() or Path(default_win_ini).exists() or bool(self.config.custom_settings_ini_path)
        default_ini_path = self.config.custom_settings_ini_path or (default_linux_ini if Path(default_linux_ini).exists() else (default_win_ini if Path(default_win_ini).exists() else ""))

        use_existing = ask_yes_no(
            "Do you already have a settings.ini file?",
            default=has_existing_ini
        )

        settings_ini_file = None
        if use_existing:
            default_start = Path(default_ini_path).parent if default_ini_path and Path(default_ini_path).exists() else self.base_dir
            chosen_path = NativeFileBrowser.browse_file(
                start_path=default_start,
                base_dir=self.base_dir,
                title="Select settings.ini Configuration File",
                extension=".ini",
                file_desc="Phoebus Settings Files",
                restrict_to_base=False
            )
            if chosen_path:
                settings_ini_file = Path(chosen_path)
            else:
                print(f"  {Style.YELLOW}→ No file selected: generating a new settings.ini automatically.{Style.RESET}")
                use_existing = False

        if not use_existing or not settings_ini_file:
            # Generate new settings.ini from Phoebus sources
            if self.config.use_local_sources and self.config.local_sources_path:
                print(f"\n  [>] Preparing local Phoebus sources and generating settings.ini...")
                sources_dir = DownloadManager.prepare_local_sources(Path(self.config.local_sources_path))
            else:
                print(f"\n  [>] Downloading sources and generating settings.ini...")
                build_dir = Path(self.config.build_dir)
                sources_dir = DownloadManager.download_phoebus_sources(self.config.phoebus_branch, build_dir)
            settings_ini_file = Path("settings.ini")
            SettingsGenerator.generate_from_sources(sources_dir, settings_ini_file)
            print(f"  {Style.GREEN}✓ New settings.ini generated successfully.{Style.RESET}")

        if settings_ini_file and settings_ini_file.exists():
            self.config.custom_settings_ini_path = str(settings_ini_file)

            want_edit = ask_yes_no(
                f"Do you want to edit '{settings_ini_file.name}'?",
                default=not use_existing
            )
            if want_edit:
                SettingsEditor.open_pyside6_editor(settings_ini_file)

        # 3. UI displays directory
        print(f"\n{Style.BOLD}Embedding UI Displays:{Style.RESET}")
        print(f"{Style.DIM}You can embed UI screens (.bob), displays, and images into the application.")
        print(f"To do so, provide a directory containing all these files.{Style.RESET}")
        
        has_default_ui = bool(self.config.ui_dir and Path(self.config.ui_dir).exists())
        want_ui = ask_yes_no(
            "Do you want to embed custom UI displays (.bob, images)?",
            default=has_default_ui
        )

        if want_ui:
            start_dir = None
            if self.config.ui_dir and Path(self.config.ui_dir).exists():
                start_dir = Path(self.config.ui_dir)
            elif Path("resources/ui").exists():
                start_dir = Path("resources/ui")
            elif Path("resources").exists():
                start_dir = Path("resources")

            chosen_ui = NativeFileBrowser.browse_directory(
                start_path=start_dir,
                title="UI Displays Directory"
            )
            if chosen_ui:
                self.config.ui_dir = chosen_ui
            else:
                print(f"  {Style.YELLOW}→ No folder selected: no custom UI displays will be embedded.{Style.RESET}")
                self.config.ui_dir = ""
                want_ui = False

            # 4. Home display (home_display)
            if self.config.ui_dir and Path(self.config.ui_dir).exists():
                ui_path = Path(self.config.ui_dir).resolve()
                bob_files = sorted(list(ui_path.glob("**/*.bob")))

                print(f"\n{Style.BOLD}Application Home Display (home_display):{Style.RESET}")
                print(f"{Style.DIM}The main .bob interface file automatically opened on launch as the application's startup home screen (sets org.phoebus.ui/home_display).{Style.RESET}")

                want_home = ask_yes_no(
                    "Do you want to configure a main home display (home_display)?",
                    default=bool(bob_files)
                )

                if want_home:
                    chosen_rel_bob = NativeFileBrowser.browse_file(
                        start_path=ui_path,
                        base_dir=ui_path,
                        title="Select Main .bob Home Display",
                        extension=".bob",
                        file_desc="Phoebus Display Screens",
                        restrict_to_base=True
                    )

                    if chosen_rel_bob:
                        self.config.home_display_file = chosen_rel_bob
                        print(f"  {Style.GREEN}✓ Selected home display: {chosen_rel_bob}{Style.RESET}")
                    else:
                        print(f"  {Style.YELLOW}→ No file selected: default Phoebus home display will be used.{Style.RESET}")
                        self.config.home_display_file = ""

        # --- STEP 4: Application Logo ---
        is_windows = platform.system().lower() == "windows"
        self.config.target_platform = "windows" if is_windows else "linux"
        logo_ext = ".ico" if is_windows else ".png"
        logo_desc = "Windows Icon (*.ico)" if is_windows else "PNG Image (*.png)"
        os_label = "Windows" if is_windows else "Linux"

        print(f"\n{Style.BG_BLUE}{Style.BOLD} 4. APPLICATION LOGO ({logo_ext}) {Style.RESET}\n")
        print(f"{Style.DIM}Phoebus allows setting custom branding for window titles and system menus.{Style.RESET}")
        print(f"{Style.DIM}Expected format under {os_label}: {logo_ext} (high resolution supported).{Style.RESET}\n")

        want_custom_logo = ask_yes_no(
            f"Do you want to customize the application logo ({logo_ext})?",
            default=bool(self.config.custom_logo_path)
        )
        if want_custom_logo:
            while True:
                chosen_logo = NativeFileBrowser.browse_file(
                    start_path=self.base_dir,
                    base_dir=self.base_dir,
                    title=f"Select Logo Image ({logo_ext})",
                    extension=logo_ext,
                    file_desc=logo_desc,
                    restrict_to_base=False
                )
                if not chosen_logo:
                    print(f"  {Style.YELLOW}→ No logo selected: default Phoebus icon will be used.{Style.RESET}")
                    self.config.custom_logo_path = ""
                    break

                if ImageValidator.validate_image(
                    chosen_logo,
                    expected_size=None,
                    image_type_label=f"Logo ({os_label})",
                    expected_format=logo_ext
                ):
                    self.config.custom_logo_path = chosen_logo
                    print(f"  {Style.GREEN}✓ Custom logo configured: {chosen_logo}{Style.RESET}")
                    break
                else:
                    print(f"  {Style.YELLOW}→ Invalid file. Please select a valid {logo_ext} image or cancel.{Style.RESET}")
        else:
            self.config.custom_logo_path = ""

        # --- STEP 5: Startup Splash Screen ---
        print(f"\n{Style.BG_BLUE}{Style.BOLD} 5. STARTUP SPLASH SCREEN (site_splash.png) {Style.RESET}\n")
        print(f"{Style.DIM}You can replace the startup loading screen image displayed while Phoebus loads.{Style.RESET}")
        print(f"{Style.DIM}Required format: .png (480x300 px).{Style.RESET}\n")

        want_custom_splash = ask_yes_no(
            "Do you want to customize the startup splash screen (site_splash.png)?",
            default=bool(self.config.custom_splash_path)
        )
        if want_custom_splash:
            while True:
                chosen_splash = NativeFileBrowser.browse_file(
                    start_path=self.base_dir,
                    base_dir=self.base_dir,
                    title="Select Splash Screen Image (.png, 480x300 px)",
                    extension=".png",
                    file_desc="PNG Images (*.png)",
                    restrict_to_base=False
                )
                if not chosen_splash:
                    print(f"  {Style.YELLOW}→ No splash selected: default Phoebus splash will be used.{Style.RESET}")
                    self.config.custom_splash_path = ""
                    break

                if ImageValidator.validate_image(
                    chosen_splash,
                    expected_size=(480, 300),
                    image_type_label="Splash Screen",
                    expected_format=".png"
                ):
                    self.config.custom_splash_path = chosen_splash
                    print(f"  {Style.GREEN}✓ Custom splash screen configured: {chosen_splash}{Style.RESET}")
                    break
                else:
                    print(f"  {Style.YELLOW}→ Invalid file. Please select a .png (480x300 px) image or cancel.{Style.RESET}")
        else:
            self.config.custom_splash_path = ""

        # --- STEP 6: Configuration Summary ---
        print(f"\n{Style.BG_BLUE}{Style.BOLD} 6. CONFIGURATION SUMMARY {Style.RESET}\n")
        current_os = platform.system()
        if is_windows:
            win_pkg = self.config.windows_package_type.lower() if self.config.windows_package_type.lower() in ["msi", "exe"] else "msi"
            target_resolved = f"Windows (.{win_pkg}) [Host OS: {current_os}]"
        else:
            pkg_type = BuildConfig.detect_linux_package_type()
            target_resolved = f"Linux (.deb / .rpm) [Host OS: {current_os}]"

        desc_disp = self.config.app_description or f"{Style.DIM}(not set){Style.RESET}"
        vendor_disp = self.config.app_vendor or f"{Style.DIM}(not set){Style.RESET}"
        copyright_disp = self.config.app_copyright or f"{Style.DIM}(not set){Style.RESET}"
        url_disp = self.config.app_url or f"{Style.DIM}(not set){Style.RESET}"
        maint_disp = self.config.deb_maintainer or f"{Style.DIM}(not set){Style.RESET}"

        print(f"  • {Style.BOLD}Application Name:{Style.RESET}      {Style.CYAN}{self.config.app_name}{Style.RESET}")
        print(f"  • {Style.BOLD}Version:{Style.RESET}               {Style.GREEN}{self.config.app_version}{Style.RESET}")
        print(f"  • {Style.BOLD}Description:{Style.RESET}           {desc_disp}")
        print(f"  • {Style.BOLD}Vendor / Org:{Style.RESET}          {vendor_disp}")
        print(f"  • {Style.BOLD}Copyright:{Style.RESET}             {copyright_disp}")
        print(f"  • {Style.BOLD}Project URL:{Style.RESET}           {url_disp}")
        if self.config.use_local_sources:
            print(f"  • {Style.BOLD}Phoebus Source:{Style.RESET}        {Style.YELLOW}Local ({self.config.local_sources_path}){Style.RESET}")
        else:
            print(f"  • {Style.BOLD}Phoebus Release:{Style.RESET}       {Style.YELLOW}{self.config.phoebus_branch}{Style.RESET}")

        if self.config.use_local_jdk:
            print(f"  • {Style.BOLD}Java Version (JDK):{Style.RESET}    Local ({self.config.local_jdk_path})")
        else:
            print(f"  • {Style.BOLD}Java Version (JDK):{Style.RESET}    Adoptium {self.config.version_java}")

        if self.config.use_local_maven:
            print(f"  • {Style.BOLD}Maven Tool:{Style.RESET}            Local ({self.config.local_maven_path})")

        print(f"  • {Style.BOLD}Preference Folder:{Style.RESET}     {self.config.phoebus_preference_folder}")
        print(f"  • {Style.BOLD}Settings File:{Style.RESET}         {self.config.custom_settings_ini_path or 'settings.ini (generated)'}")
        ui_disp = self.config.ui_dir if self.config.ui_dir else f"{Style.DIM}(none){Style.RESET}"
        home_disp = f"$(phoebus.install)/ui/{self.config.home_display_file}?app=display_runtime" if self.config.home_display_file else f"{Style.DIM}(default Phoebus){Style.RESET}"
        logo_disp = self.config.custom_logo_path if self.config.custom_logo_path else f"{Style.DIM}(default Phoebus){Style.RESET}"
        splash_disp = self.config.custom_splash_path if self.config.custom_splash_path else f"{Style.DIM}(default Phoebus){Style.RESET}"
        print(f"  • {Style.BOLD}Build Mode:{Style.RESET}            Full Maven compilation from source")
        print(f"  • {Style.BOLD}UI Displays Folder:{Style.RESET}    {ui_disp}")
        print(f"  • {Style.BOLD}Home Display:{Style.RESET}          {home_disp}")
        print(f"  • {Style.BOLD}Custom Logo:{Style.RESET}           {logo_disp}")
        print(f"  • {Style.BOLD}Splash Screen:{Style.RESET}         {splash_disp}")
        print(f"  • {Style.BOLD}Target Platform:{Style.RESET}       {Style.MAGENTA}{target_resolved}{Style.RESET}")
        print(f"  • {Style.BOLD}Output Directory:{Style.RESET}      {self.config.output_dir}/\n")

        # Save project bundle
        save_profile = ask_yes_no("Do you want to save and consolidate this project bundle?", default=True)
        if save_profile:
            proj_name = self.config.app_name.lower().replace(' ', '_') if self.config.app_name else "project"
            proj_dir = self.config.save_to_project_bundle(proj_name, base_dir=self.base_dir)
            print(f"  {Style.GREEN}✓ Project and assets consolidated in: {proj_dir}/{Style.RESET}")
            print(f"    • {proj_dir}/config.json")
            if (proj_dir / "settings.ini").exists():
                print(f"    • {proj_dir}/settings.ini")
            if (proj_dir / "ui").exists():
                print(f"    • {proj_dir}/ui/")
            print(f"  {Style.DIM}💡 You can rebuild directly without questionnaire using:{Style.RESET}")
            print(f"     {Style.CYAN}python3 build_phoebus.py --config {proj_dir} -y{Style.RESET}\n")

        # System prerequisites check
        missing_tools = self.config.check_system_prerequisites()
        if missing_tools:
            print(f"\n{Style.RED}{Style.BOLD}⚠ WARNING: Missing system prerequisites:{Style.RESET}")
            for err in missing_tools:
                print(f"  • {err}")
            print()

        return self.config
