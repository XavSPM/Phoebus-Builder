"""
Command-line interface and entry point for Phoebus Native Installer Builder.
Supports GUI (PySide6 / Qt 6), interactive terminal wizard (CLI), and headless automated batch mode.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

# Silence verbose Wayland textinput debug warnings on Fedora / GNOME
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland*=false;qt.qpa.wayland.textinput=false;qt.qpa.services*=false"

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .config import BuildConfig, get_workspace_dir
from .wizard import InteractiveWizard, ask_yes_no, Style
from .packager import PhoebusPackager


def parse_args(args: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="phoebus-builder",
        description="GUI and automated packager for custom Phoebus native installers (Debian .deb, RPM .rpm, Windows .msi)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  phoebus-builder                                # Launch PySide6 GUI (default)
  phoebus-builder --config configs/my_project    # Open PySide6 GUI prefilled with this project
  phoebus-builder --config configs/my_project -y # Immediate headless batch build (CI/CD)
  phoebus-builder --cli                          # Force terminal text wizard
  phoebus-builder --dry-run                      # Validate configuration without building
        """
    )

    parser.add_argument(
        "-c", "--config",
        help="Path to a project directory or JSON configuration file (e.g. configs/my_project/config.json)",
        type=str,
        default=None
    )
    parser.add_argument(
        "-y", "--non-interactive",
        help="Immediate non-interactive batch build (uses loaded parameters)",
        action="store_true"
    )
    parser.add_argument(
        "--cli",
        help="Force interactive command-line terminal wizard",
        action="store_true"
    )
    parser.add_argument(
        "--gui",
        help="Force opening the PySide6 desktop GUI",
        action="store_true"
    )
    parser.add_argument(
        "--platform",
        choices=["linux", "windows", "auto"],
        help="Target platform override (linux, windows, auto)",
        default=None
    )
    parser.add_argument(
        "--win-package-type",
        choices=["msi", "exe"],
        help="Windows installer format override (msi, exe)",
        default=None
    )
    parser.add_argument(
        "--name",
        help="Application name override",
        type=str
    )
    parser.add_argument(
        "--version",
        help="Application version override (e.g. 5.0.2)",
        type=str
    )
    parser.add_argument(
        "--phoebus-version",
        help="Phoebus tag or branch (e.g. v5.0.2)",
        type=str
    )
    parser.add_argument(
        "--local-sources", "--sources-dir",
        dest="local_sources",
        help="Path to local Phoebus sources directory or archive (.zip, .tar.gz)",
        type=str
    )
    parser.add_argument(
        "--java-version",
        help="Adoptium Java JDK major version (e.g. 25 or 21)",
        type=str
    )
    parser.add_argument(
        "--local-jdk", "--jdk-dir",
        dest="local_jdk",
        help="Path to local JDK directory or archive (.zip, .tar.gz)",
        type=str
    )
    parser.add_argument(
        "--local-maven", "--maven-dir",
        dest="local_maven",
        help="Path to local Apache Maven directory or archive",
        type=str
    )
    parser.add_argument(
        "--clean", "--clean-cache",
        dest="clean_cache",
        help="Purge temporary build directory and caches (JDKs, Maven work artifacts) without modifying configs/",
        action="store_true"
    )
    parser.add_argument(
        "--dry-run",
        help="Display summary without downloading sources or triggering compilation",
        action="store_true"
    )
    parser.add_argument(
        "--workspace",
        help="Workspace directory for sources, projects, and artifacts (default: user-configured workspace)",
        type=str,
        default=None
    )

    return parser.parse_args(args)


def main(cli_args: Optional[Sequence[str]] = None) -> int:
    args = parse_args(cli_args)

    try:
        base_dir = get_workspace_dir(args.workspace)
    except RuntimeError:
        base_dir = None

    if args.clean_cache:
        if base_dir is None:
            print(f"{Style.RED}Error: No workspace directory configured. Please specify --workspace <path>.{Style.RESET}")
            return 1
        print(f"\n{Style.BOLD}Purging build cache...{Style.RESET}")
        freed, count = PhoebusPackager.clean_build_cache(base_dir)
        size_str = PhoebusPackager.format_size(freed)
        if count > 0:
            print(f"  {Style.GREEN}✓ Build cache successfully purged ({count} items removed, {size_str} freed).{Style.RESET}\n")
        else:
            print(f"  {Style.DIM}Build directory is already clean (0 B).{Style.RESET}\n")
        return 0

    if base_dir is None and args.non_interactive:
        print(f"{Style.RED}Error: No workspace directory configured. Please specify --workspace <path> or launch the GUI to configure it.{Style.RESET}")
        return 1

    if base_dir is None and args.cli:
        print(f"\n{Style.BOLD}No workspace directory configured.{Style.RESET}")
        from .wizard import ask_text
        ws_input = ask_text(
            "Please enter a workspace directory path to store projects and sources",
            default="",
            validator=lambda s: len(s.strip()) > 0,
            error_msg="Workspace path cannot be empty."
        )
        base_dir = get_workspace_dir(ws_input)
        from .app_settings import set_saved_workspace_dir
        set_saved_workspace_dir(base_dir)

    config = None
    if base_dir is not None:
        if args.config:
            config_path = Path(args.config)
            if not config_path.is_absolute():
                config_path = (base_dir / config_path).resolve() if not config_path.exists() else config_path.resolve()
            if not config_path.exists():
                print(f"{Style.RED}Error: Configuration path '{args.config}' not found.{Style.RESET}")
                return 1
            config = BuildConfig.from_project(config_path, base_dir=base_dir)
            print(f"  {Style.GREEN}✓ Loaded configuration from: {args.config}{Style.RESET}")
        elif (base_dir / "configs").exists() and [d for d in (base_dir / "configs").iterdir() if d.is_dir() and (d / "config.json").exists()]:
            proj_dirs = [d for d in (base_dir / "configs").iterdir() if d.is_dir() and (d / "config.json").exists()]
            latest_proj = max(proj_dirs, key=lambda p: (p / "config.json").stat().st_mtime)
            config = BuildConfig.from_project(latest_proj, base_dir=base_dir)
            print(f"  {Style.GREEN}✓ Loaded project from: {latest_proj}/{Style.RESET}")
    elif args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(f"{Style.RED}Error: Configuration path '{args.config}' not found.{Style.RESET}")
            return 1
        config = BuildConfig.from_project(config_path)

    if any([args.name, args.version, args.phoebus_version, args.local_sources, args.java_version, args.local_jdk, args.local_maven, args.platform, args.win_package_type]):
        if config is None:
            config = BuildConfig()
        if args.name:
            config.app_name = args.name
        if args.version:
            config.app_version = args.version
        if args.phoebus_version:
            config.phoebus_branch = args.phoebus_version
        if args.local_sources:
            config.use_local_sources = True
            config.local_sources_path = args.local_sources
        if args.java_version:
            config.version_java = args.java_version
        if args.local_jdk:
            config.use_local_jdk = True
            config.local_jdk_path = args.local_jdk
        if args.local_maven:
            config.use_local_maven = True
            config.local_maven_path = args.local_maven
        if args.platform:
            config.target_platform = args.platform
        if args.win_package_type:
            config.windows_package_type = args.win_package_type

    if args.dry_run:
        if config is None:
            print(f"{Style.RED}Error: No project found in configs/. Please create a project or specify --config <path>.{Style.RESET}")
            return 1
        print(f"\n{Style.YELLOW}[DRY-RUN MODE] Configuration validated. No build executed.{Style.RESET}")
        print(f"  • Application: {config.app_name} v{config.app_version}")
        if config.use_local_sources:
            print(f"  • Phoebus:     Local ({config.local_sources_path})")
        else:
            print(f"  • Phoebus:     GitHub ({config.phoebus_branch})")
        if config.use_local_jdk:
            print(f"  • Java:        Local ({config.local_jdk_path})")
        else:
            print(f"  • Java:        Adoptium ({config.version_java})")
        if config.use_local_maven:
            print(f"  • Maven:       Local ({config.local_maven_path})")
        print(f"  • Platform:    {config.target_platform}")
        errors = config.validate()
        if errors:
            print(f"\n{Style.RED}Configuration errors detected:{Style.RESET}")
            for err in errors:
                print(f"  • {err}")
            return 1
        return 0

    if not args.non_interactive and not args.cli:
        try:
            from .gui import launch_gui
            launch_gui(config)
            return 0
        except ModuleNotFoundError as e:
            if "PySide6" in str(e):
                print(f"{Style.YELLOW}[!] PySide6 is not installed. To run the modern desktop GUI, install it via:{Style.RESET}")
                print(f"    • Fedora: {Style.CYAN}sudo dnf install python3-pyside6{Style.RESET} or {Style.CYAN}pip install PySide6{Style.RESET}")
                print(f"    • Debian/Ubuntu: {Style.CYAN}pip install PySide6{Style.RESET}")
                print(f"{Style.DIM}Falling back to terminal wizard...{Style.RESET}\n")
            else:
                print(f"{Style.YELLOW}[!] Unable to initialize GUI ({e}). Falling back to terminal wizard...{Style.RESET}")
            wizard = InteractiveWizard(config, base_dir=base_dir)
            config = wizard.run()
        except Exception as e:
            print(f"{Style.YELLOW}[!] Unable to initialize GUI ({e}). Falling back to terminal wizard...{Style.RESET}")
            wizard = InteractiveWizard(config, base_dir=base_dir)
            config = wizard.run()
    elif args.cli and not args.non_interactive:
        wizard = InteractiveWizard(config, base_dir=base_dir)
        config = wizard.run()
        
        print(f"\n{Style.BOLD}Ready to build.{Style.RESET}")
        should_build = ask_yes_no("Launch native installer build now?", default=True)
        if not should_build:
            print("\nBuild cancelled.")
            return 0
    else:
        if config is None:
            print(f"{Style.RED}Error: No project found in configs/. Please create a project or specify --config <path>.{Style.RESET}")
            return 1
        errors = config.validate()
        if errors:
            print(f"{Style.RED}Configuration errors detected:{Style.RESET}")
            for err in errors:
                print(f"  • {err}")
            return 1
        missing_tools = config.check_system_prerequisites()
        if missing_tools:
            print(f"{Style.RED}Missing required system prerequisites:{Style.RESET}")
            for err in missing_tools:
                print(f"  • {err}")
            return 1

    try:
        packager = PhoebusPackager(config, base_dir=base_dir)
        output_file = packager.build()
        print(f"{Style.GREEN}{Style.BOLD}✓ Completed successfully!{Style.RESET} Installer generated in: {output_file}")
        return 0
    except KeyboardInterrupt:
        print(f"\n\n{Style.YELLOW}Build interrupted by user.{Style.RESET}")
        return 130
    except Exception as e:
        print(f"\n{Style.RED}{Style.BOLD}❌ BUILD FAILED:{Style.RESET} {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
