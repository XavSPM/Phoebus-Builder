"""
Packaging and orchestration module for building Phoebus native installers.
"""

import datetime
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from .config import BuildConfig, get_workspace_dir
from .downloader import DownloadManager
from .image_utils import ImageValidator
from .jvm import JvmManager
from .settings_generator import SettingsGenerator
from .modules import PhoebusPomManager

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    """Removes ANSI terminal escape sequences (colors, cursor movements, etc.)."""
    return ANSI_ESCAPE_RE.sub('', text)



class PhoebusPackager:
    """Complete packaging orchestrator for Phoebus native installers."""

    def __init__(self, config: BuildConfig, base_dir: Optional[Path] = None):
        self.config = config
        self.base_dir = base_dir or get_workspace_dir()
        proj_name = config.app_name.lower().replace(" ", "_") if config.app_name else "project"
        if not config.build_dir or config.build_dir == "build":
            self.build_dir = self.base_dir / "configs" / proj_name / "build"
        else:
            b_path = Path(config.build_dir)
            self.build_dir = b_path if b_path.is_absolute() else (self.base_dir / b_path)
        out_p = Path(config.output_dir) if config.output_dir else Path("output")
        self.output_dir = out_p if out_p.is_absolute() else (self.base_dir / out_p)
        self.log_file = self.output_dir / "build.log"
        self._log_handle = None
        self.current_process: Optional[subprocess.Popen] = None
        self._cancelled: bool = False
        
        # Platform detection
        if config.target_platform == "auto":
            self.is_windows = platform.system().lower() == "windows"
        else:
            self.is_windows = config.target_platform.lower() == "windows"

        local_jdk = config.local_jdk_path if config.use_local_jdk and config.local_jdk_path else None
        self.jvm_manager = JvmManager(
            base_dir=self.base_dir,
            build_dir=self.build_dir,
            java_version=config.version_java,
            is_windows=self.is_windows,
            local_jdk_path=local_jdk
        )

    def _log(self, msg: str = "", echo: bool = True):
        """Logs message to console and writes timestamped entry to build.log."""
        if echo and msg:
            print(msg, flush=True)
        if self._log_handle:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._log_handle.write(f"[{timestamp}] {msg}\n" if msg else "\n")
            self._log_handle.flush()

    def cancel(self):
        """Interrupts build execution and terminates active child subprocesses and their process trees."""
        self._cancelled = True
        self._log("[CANCEL] Cancellation requested by user.", echo=False)
        if self.current_process and self.current_process.poll() is None:
            try:
                if self.is_windows:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)],
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    )
                else:
                    pgid = os.getpgid(self.current_process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    try:
                        self.current_process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    self.current_process.terminate()
                    self.current_process.kill()
                except Exception:
                    pass

    def _run_cmd(self, cmd, cwd=None, env=None, stream_output: bool = False, capture_output: bool = False) -> Tuple[int, str]:
        """Runs a command with immediate cancellation support, live streaming, and file logging."""
        if self._cancelled:
            raise InterruptedError("Process interrupted by user.")

        cmd_str = ' '.join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        self._log(f"[EXEC] Command: {cmd_str} (cwd={cwd or '.'})", echo=False)

        kwargs = {}
        if not self.is_windows:
            kwargs["start_new_session"] = True
        else:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si

        if stream_output or capture_output:
            self.current_process = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                errors="replace",
                **kwargs
            )

            output_lines = []
            if self.current_process.stdout:
                for line in iter(self.current_process.stdout.readline, ""):
                    if self._cancelled:
                        try:
                            if self.is_windows:
                                subprocess.run(
                                    ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)],
                                    capture_output=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                                )
                            else:
                                os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                        except Exception:
                            try:
                                self.current_process.kill()
                            except Exception:
                                pass
                        raise InterruptedError("Process interrupted by user.")

                    clean_line = strip_ansi(line.rstrip("\r\n"))
                    if stream_output and clean_line:
                        print(clean_line, flush=True)
                    if self._log_handle and clean_line:
                        self._log_handle.write(f"  {clean_line}\n")
                        self._log_handle.flush()
                    if capture_output:
                        output_lines.append(strip_ansi(line))

                self.current_process.stdout.close()

            rc = self.current_process.wait()
            self.current_process = None
            self._log(f"[EXIT] Command finished with exit code {rc}", echo=False)
            if self._cancelled:
                raise InterruptedError("Process interrupted by user.")
            return rc, "".join(output_lines)
        else:
            self.current_process = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=env,
                text=True,
                **kwargs
            )
            rc = self.current_process.wait()
            self.current_process = None
            self._log(f"[EXIT] Command finished with exit code {rc}", echo=False)
            if self._cancelled:
                raise InterruptedError("Process interrupted by user.")
            return rc, ""

    def _ensure_sources_and_templates(self) -> Path:
        """Downloads Phoebus sources to project directory and generates settings template if requested."""
        if self._cancelled:
            raise InterruptedError("Process interrupted by user.")

        if self.config.use_local_sources and self.config.local_sources_path:
            p_src = Path(self.config.local_sources_path)
            if not p_src.is_absolute():
                p_src = self.base_dir / p_src
            sources_dir = DownloadManager.prepare_local_sources(p_src)
        else:
            # Store sources in shared sources/phoebus/
            shared_sources_base = self.base_dir / "sources" / "phoebus"
            shared_sources_base.mkdir(parents=True, exist_ok=True)

            sources_dir = DownloadManager.download_phoebus_sources(
                tag=self.config.phoebus_branch,
                build_dir=shared_sources_base
            )

        if self.config.generate_settings_template:
            template_path = sources_dir / "settings_template.ini"
            SettingsGenerator.generate_from_sources(
                sources_root=sources_dir,
                output_file=template_path,
                include_comments=True
            )

        return sources_dir

    @staticmethod
    def get_app_class_name(app_name: str) -> str:
        """Generates a valid Java class name for the project's unique JavaFX Application."""
        clean = re.sub(r'[^a-zA-Z0-9]', '', app_name) or "App"
        if clean[0].isdigit():
            clean = "App" + clean
        return f"{clean}App"

    def _customize_app_launcher(self, sources_dir: Path) -> str:
        """Generates a project-specific JavaFX Application class so Linux WM_CLASS is unique per app."""
        class_name = self.get_app_class_name(self.config.app_name)
        launcher_pkg_dir = sources_dir / "core" / "launcher" / "src" / "main" / "java" / "org" / "phoebus" / "product"
        if not launcher_pkg_dir.exists():
            return "org.phoebus.ui.application.PhoebusApplication"

        app_class_file = launcher_pkg_dir / f"{class_name}.java"
        app_class_content = f"""package org.phoebus.product;

import org.phoebus.ui.application.PhoebusApplication;

/**
 * Project-specific entry point for {self.config.app_name}.
 * Ensures unique Linux X11/Wayland WM_CLASS for dock grouping and icon resolution.
 */
public class {class_name} extends PhoebusApplication {{
}}
"""
        app_class_file.write_text(app_class_content, encoding="utf-8")

        launcher_file = launcher_pkg_dir / "Launcher.java"
        if launcher_file.exists():
            content = launcher_file.read_text(encoding="utf-8")
            # Replace Application.launch(...) with project-specific class
            content = re.sub(
                r'Application\.launch\([^,]+?\.class,',
                f'Application.launch({class_name}.class,',
                content
            )
            launcher_file.write_text(content, encoding="utf-8")

        return f"org.phoebus.product.{class_name}"

    def _build_from_sources_maven(self, sources_dir: Path) -> Tuple[Path, Path]:
        """Compiles Phoebus from sources with Maven in an isolated build directory, caching previous builds when modules are unchanged."""
        if self._cancelled:
            raise InterruptedError("Process interrupted by user.")

        # Isolated build workspace inside self.build_dir / "sources"
        build_sources_dir = self.build_dir / "sources"
        product_pom = build_sources_dir / "phoebus-product" / "pom.xml"
        modules_state_file = build_sources_dir / ".modules_state"
        class_name = self.get_app_class_name(self.config.app_name)
        current_modules_state = f"{class_name}:" + (",".join(sorted(self.config.enabled_modules)) if self.config.enabled_modules else "ALL")

        product_dir = build_sources_dir / "phoebus-product" / "target"
        product_zips = list(product_dir.glob("product-*.zip")) or list(product_dir.glob("phoebus-*.zip")) if product_dir.exists() else []
        work_dir = self.build_dir / ("jpackage_work_win" if self.is_windows else "jpackage_work")

        needs_compile = True

        if not self.config.force_maven_rebuild and product_zips and modules_state_file.exists() and build_sources_dir.exists():
            try:
                saved_state = modules_state_file.read_text(encoding="utf-8").strip()
                if saved_state == current_modules_state:
                    print(f"\n  [OK] Reusing previously compiled product ({product_zips[0].name}). Skipping Maven compilation.")
                    needs_compile = False
            except Exception:
                needs_compile = True

        if needs_compile:
            print(f"\n  [>] Preparing isolated build workspace in: {build_sources_dir}...")
            if build_sources_dir.exists() and self.config.force_maven_rebuild:
                shutil.rmtree(build_sources_dir, ignore_errors=True)

            if not build_sources_dir.exists():
                shutil.copytree(
                    sources_dir,
                    build_sources_dir,
                    ignore=shutil.ignore_patterns(".git", "target", "*.class", "*.log")
                )

            self._customize_app_launcher(build_sources_dir)

            if product_pom.exists() and self.config.enabled_modules:
                print(f"  [>] Customizing product ({len(self.config.enabled_modules)} selected modules)...")
                all_discovered = PhoebusPomManager.discover_modules_from_pom(product_pom)
                managed = {m.artifact_id for m in all_discovered}
                PhoebusPomManager.filter_product_pom(product_pom, set(self.config.enabled_modules), managed_modules=managed)

            print("\n  [>] Compiling Phoebus from sources using Maven (multithreaded -T 1C)...")
            
            # Locate Maven: check local_maven_path, sources/maven, system PATH, or ensure_maven
            mvn_cmd_path = None
            if self.config.use_local_maven and self.config.local_maven_path:
                p_mvn = Path(self.config.local_maven_path)
                if not p_mvn.is_absolute():
                    p_mvn = self.base_dir / p_mvn
                local_mvn_dir = DownloadManager.prepare_local_maven(p_mvn)
                candidate_cmd = local_mvn_dir / "bin" / ("mvn.cmd" if self.is_windows else "mvn")
                if candidate_cmd.exists():
                    mvn_cmd_path = candidate_cmd
                elif local_mvn_dir.is_file():
                    mvn_cmd_path = local_mvn_dir

            if not mvn_cmd_path or not mvn_cmd_path.exists():
                shared_maven = self.base_dir / "sources" / "maven"
                if DownloadManager.is_maven_ready(shared_maven):
                    mvn_cmd_path = shared_maven / "bin" / ("mvn.cmd" if self.is_windows else "mvn")
                else:
                    sys_mvn = shutil.which("mvn.cmd" if self.is_windows else "mvn") or shutil.which("mvn")
                    if sys_mvn:
                        mvn_cmd_path = Path(sys_mvn)
                    else:
                        print("  [>] Maven not detected. Downloading portable Apache Maven into sources/maven...")
                        DownloadManager.ensure_maven(self.base_dir)
                        mvn_cmd_path = shared_maven / "bin" / ("mvn.cmd" if self.is_windows else "mvn")
            
            env = os.environ.copy()
            env["JAVA_HOME"] = str(self.jvm_manager.jdk_dir)
            maven_bin_dir = mvn_cmd_path.parent
            if not self.is_windows and mvn_cmd_path.exists():
                try:
                    mvn_cmd_path.chmod(mvn_cmd_path.stat().st_mode | 0o755)
                except Exception:
                    pass
            env["PATH"] = f"{maven_bin_dir}{os.pathsep}{self.jvm_manager.jdk_dir / 'bin'}{os.pathsep}{env.get('PATH', '')}"

            cmd = [str(mvn_cmd_path), "-B", "-Dstyle.color=never", "clean", "install", "-DskipTests", "-T", "1C"]
            print(f"      Command: {' '.join(cmd)} (in {build_sources_dir})\n")

            rc, _ = self._run_cmd(cmd, cwd=build_sources_dir, env=env, stream_output=True)
            if rc != 0:
                raise RuntimeError(f"Maven build failed (exit code {rc}).")

            # Save module configuration signature
            modules_state_file.write_text(current_modules_state, encoding="utf-8")
            product_zips = list(product_dir.glob("product-*.zip")) or list(product_dir.glob("phoebus-*.zip"))

        if product_zips:
            main_jars = list(work_dir.glob("product-*.jar")) or list(work_dir.glob("phoebus-*.jar")) if work_dir.exists() else []
            if not main_jars:
                main_jars = list(work_dir.rglob("product-*.jar")) or list(work_dir.rglob("phoebus-*.jar")) if work_dir.exists() else []

            if not main_jars or needs_compile:
                print(f"  [>] Extracting Maven product: {product_zips[0].name}...")
                DownloadManager.extract_archive(product_zips[0], work_dir, clean_target=True)
                extracted_subdirs = [p for p in work_dir.iterdir() if p.is_dir()]
                extracted_root = extracted_subdirs[0] if extracted_subdirs else work_dir
            else:
                extracted_subdirs = [p for p in work_dir.iterdir() if p.is_dir()]
                extracted_root = extracted_subdirs[0] if extracted_subdirs else work_dir
        else:
            extracted_root = product_dir

        main_jars = list(extracted_root.glob("product-*.jar")) or list(extracted_root.glob("phoebus-*.jar"))
        if not main_jars:
            main_jars = list(extracted_root.rglob("product-*.jar")) or list(extracted_root.rglob("phoebus-*.jar"))

        if not main_jars:
            raise FileNotFoundError("Main product JAR not found after Maven compilation.")

        return extracted_root, main_jars[0]

    def _ensure_wix_modern_extensions(self, wix_exe: str) -> None:
        """Ensures WixToolset.Util.wixext and WixToolset.UI.wixext are installed for WiX 4/5."""
        w_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            res = subprocess.run([wix_exe, "extension", "list", "-g"], capture_output=True, text=True, timeout=5, creationflags=w_flags)
            output = res.stdout + res.stderr
            needed = ["WixToolset.Util.wixext", "WixToolset.UI.wixext"]
            missing = [ext for ext in needed if ext not in output]
            if missing:
                ver_res = subprocess.run([wix_exe, "--version"], capture_output=True, text=True, timeout=5, creationflags=w_flags)
                wix_ver = ver_res.stdout.strip().split("+")[0].strip() if ver_res.returncode == 0 else ""
                for ext in missing:
                    ext_spec = f"{ext}/{wix_ver}" if wix_ver else ext
                    print(f"  [>] Installing missing WiX extension: {ext_spec}...")
                    subprocess.run([wix_exe, "extension", "add", "-g", ext_spec], capture_output=True, text=True, timeout=30, creationflags=w_flags)
        except Exception:
            pass

    def _ensure_wix(self) -> Optional[Path]:
        """On Windows, verifies WiX Toolset in system PATH or sources/wix."""
        if not self.is_windows:
            return None

        wix_exe = shutil.which("wix.exe") or shutil.which("wix")
        if wix_exe:
            self._ensure_wix_modern_extensions(wix_exe)

        if shutil.which("candle.exe") and shutil.which("light.exe"):
            print("  [OK] WiX Toolset detected in system PATH.")
            return None

        shared_wix = self.base_dir / "sources" / "wix"
        if DownloadManager.is_wix_ready(shared_wix):
            print(f"  [OK] WiX Toolset found in {shared_wix}")
            os.environ["PATH"] = f"{shared_wix}{os.pathsep}{os.environ.get('PATH', '')}"
            return shared_wix

        # Check legacy location e.g. build_dir/wix
        legacy_wix = self.build_dir / "wix"
        if DownloadManager.is_wix_ready(legacy_wix):
            print(f"  [OK] WiX Toolset found in legacy path {legacy_wix}")
            os.environ["PATH"] = f"{legacy_wix}{os.pathsep}{os.environ.get('PATH', '')}"
            return legacy_wix

        print("  [>] Setting up WiX Toolset for MSI creation in sources/wix...")
        wix_dir = DownloadManager.ensure_wix(self.base_dir, url=self.config.wix_url)
        os.environ["PATH"] = f"{wix_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        return wix_dir

    def _prepare_phoebus(self, sources_dir: Path) -> Tuple[Path, Path]:
        """Builds Phoebus from sources with Maven and prepares staging work directory."""
        return self._build_from_sources_maven(sources_dir)

    def _inject_resources(self, extracted_root: Path, sources_dir: Optional[Path] = None) -> None:
        """Injects custom assets (UI, settings.ini, logo, splash screen) into Phoebus directory."""
        print("  [>] Injecting custom resources...")

        if self.config.ui_dir:
            ui_source_dir = self.base_dir / self.config.ui_dir
            if ui_source_dir.exists():
                dest_ui = extracted_root / "ui"
                print(f"      Copying UI directory from: {ui_source_dir} to {dest_ui}")
                if dest_ui.exists():
                    shutil.rmtree(dest_ui)
                shutil.copytree(ui_source_dir, dest_ui)
            else:
                print(f"  [!] UI directory not found ({ui_source_dir}), skipping.")

        target_settings_ini = extracted_root / "settings.ini"
        if self.config.custom_settings_ini_path:
            src_ini = Path(self.config.custom_settings_ini_path)
            if not src_ini.is_absolute():
                src_ini = self.base_dir / src_ini
            if src_ini.exists():
                print(f"      Copying settings.ini from: {src_ini}")
                shutil.copy2(src_ini, target_settings_ini)

        if self.config.custom_logo_path:
            src_logo = Path(self.config.custom_logo_path)
            if not src_logo.is_absolute():
                src_logo = self.base_dir / src_logo
            if src_logo.exists():
                print(f"      Copying logo ({src_logo.name}): {src_logo}")
                if self.is_windows:
                    if src_logo.suffix.lower() == ".ico":
                        shutil.copy2(src_logo, extracted_root / "logo.ico")
                    else:
                        ImageValidator.convert_to_ico(src_logo, extracted_root / "logo.ico")
                    # Also provide site_logo.png and logo.png for Phoebus runtime
                    ImageValidator.generate_site_logo(src_logo, extracted_root / "site_logo.png", target_size=(64, 64))
                    try:
                        from PySide6.QtGui import QImage
                        img = QImage(str(src_logo))
                        if not img.isNull():
                            img.save(str(extracted_root / "logo.png"), "PNG")
                    except Exception:
                        pass
                else:
                    if src_logo.suffix.lower() == ".png":
                        shutil.copy2(src_logo, extracted_root / "logo.png")
                    else:
                        try:
                            from PySide6.QtGui import QImage
                            img = QImage(str(src_logo))
                            if not img.isNull():
                                img.save(str(extracted_root / "logo.png"), "PNG")
                        except Exception:
                            shutil.copy2(src_logo, extracted_root / "logo.png")
                    ImageValidator.generate_site_logo(src_logo, extracted_root / "site_logo.png", target_size=(64, 64))
                print("      [OK] logo and site_logo.png (64x64) generated")
        else:
            default_logo = self._resolve_icon(sources_dir, extracted_root)
            if default_logo and default_logo.exists():
                if self.is_windows:
                    shutil.copy2(default_logo, extracted_root / "logo.ico")
                else:
                    shutil.copy2(default_logo, extracted_root / "logo.png")
                ImageValidator.generate_site_logo(default_logo, extracted_root / "site_logo.png", target_size=(64, 64))
                print("      [OK] site_logo.png (64x64) generated from default Phoebus icon")

        if self.config.custom_splash_path:
            src_splash = Path(self.config.custom_splash_path)
            if not src_splash.is_absolute():
                src_splash = self.base_dir / src_splash
            if src_splash.exists():
                print(f"      Copying splash screen from: {src_splash}")
                shutil.copy2(src_splash, extracted_root / "site_splash.png")

        if target_settings_ini.exists():
            from .settings_editor import SettingsEditor

            if self.config.app_name and self.config.app_name.strip().lower() != "phoebus":
                app_title = self.config.app_name.strip()
                SettingsEditor.set_ini_property(target_settings_ini, "org.phoebus.ui/default_window_title", app_title)
                SettingsEditor.set_ini_property(target_settings_ini, "org.phoebus.ui/window_title_format", f"{app_title}: %s")
                print(f"      org.phoebus.ui/default_window_title = {app_title}")
                print(f"      org.phoebus.ui/window_title_format = {app_title}: %s")

            if self.config.home_display_file:
                home_val = f"$(phoebus.install)/ui/{self.config.home_display_file}?app=display_runtime"
                SettingsEditor.set_ini_property(target_settings_ini, "org.phoebus.ui/home_display", home_val)
                print(f"      org.phoebus.ui/home_display = {home_val}")

    def _resolve_icon(self, sources_dir: Optional[Path] = None, extracted_root: Optional[Path] = None) -> Optional[Path]:
        """Resolves the icon file to use for packaging.
        Falls back to default resources, Phoebus sources, or Phoebus JARs if no custom logo is provided.
        """
        target_ext = ".ico" if self.is_windows else ".png"

        # 1. Custom logo path specified by user
        if self.config.custom_logo_path:
            cand = Path(self.config.custom_logo_path)
            if not cand.is_absolute():
                cand = self.base_dir / cand
            if cand.exists():
                if self.is_windows:
                    # Always ensure a complete multi-resolution .ico (256 to 16 px) is used for jpackage
                    ico_dest = self.build_dir / "custom_logo.ico"
                    if ImageValidator.convert_to_ico(cand, ico_dest):
                        return ico_dest
                    elif cand.suffix.lower() == target_ext:
                        return cand
                else:
                    if cand.suffix.lower() == target_ext:
                        return cand
                    png_dest = self.build_dir / "custom_logo.png"
                    try:
                        from PySide6.QtGui import QImage
                        img = QImage(str(cand))
                        if not img.isNull() and img.save(str(png_dest), "PNG"):
                            return png_dest
                    except Exception:
                        pass

        # 2. Project resource directory or package builtin
        res_dir = Path(self.config.resources_windows_dir if self.is_windows else self.config.resources_linux_dir)
        if not res_dir.is_absolute():
            res_dir = self.base_dir / res_dir
        if not res_dir.exists():
            res_dir = Path(__file__).parent / "resources" / ("windows" if self.is_windows else "linux")
        cand_res = res_dir / f"logo{target_ext}"
        if cand_res.exists():
            return cand_res

        # 3. Phoebus default logo extraction / fallback
        phoebus_default_png = None

        # 3a. Search in sources_dir
        if sources_dir and sources_dir.exists():
            src_candidates = [
                sources_dir / "core" / "ui" / "src" / "main" / "resources" / "icons" / "logo.png",
            ]
            for sc in src_candidates:
                if sc.exists():
                    phoebus_default_png = sc
                    break
            if not phoebus_default_png:
                matches = list(sources_dir.rglob("icons/logo.png"))
                if matches:
                    phoebus_default_png = matches[0]

        # 3b. Search in extracted_root JARs
        if not phoebus_default_png and extracted_root and extracted_root.exists():
            import zipfile
            jar_files = list(extracted_root.glob("*.jar")) + list(extracted_root.glob("lib/*.jar"))
            for jar in jar_files:
                try:
                    with zipfile.ZipFile(jar, "r") as z:
                        if "icons/logo.png" in z.namelist():
                            target_extracted = self.build_dir / "phoebus_default_logo.png"
                            target_extracted.write_bytes(z.read("icons/logo.png"))
                            phoebus_default_png = target_extracted
                            break
                except Exception:
                    pass

        # 3c. Fallback to bundled resources in package
        if not phoebus_default_png:
            bundled_png = Path(__file__).parent / "resources" / "linux" / "logo.png"
            if bundled_png.exists():
                phoebus_default_png = bundled_png

        if phoebus_default_png and phoebus_default_png.exists():
            if not self.is_windows:
                return phoebus_default_png
            else:
                # Convert PNG to ICO for Windows
                ico_dest = self.build_dir / "phoebus_default_logo.ico"
                if ImageValidator.convert_to_ico(phoebus_default_png, ico_dest):
                    return ico_dest

        return None

    def _prepare_linux_resources(self, icon_file: Optional[Path] = None) -> Path:
        """Prepares Linux resource directory for jpackage (.desktop, icons)."""
        staging_res = self.build_dir / "linux_resources"
        staging_res.mkdir(parents=True, exist_ok=True)

        app_name = self.config.app_name
        app_name_lower = app_name.lower().replace(" ", "-")
        comment = self.config.app_description or f"{app_name} Interface"
        category = self.config.linux_menu_group or "Utility"

        src_res = Path(self.config.resources_linux_dir)
        if not src_res.is_absolute():
            src_res = self.base_dir / src_res
        if not src_res.exists():
            src_res = Path(__file__).parent / "resources" / "linux"

        if src_res.exists():
            for item in src_res.iterdir():
                if item.is_file() and not item.name.endswith(".desktop"):
                    shutil.copy2(item, staging_res / item.name)

        if icon_file and icon_file.exists():
            shutil.copy2(icon_file, staging_res / f"{app_name}.png")

        # Load desktop template from source resources if available, or use default
        custom_desktop_src = None
        if src_res.exists():
            if (src_res / f"{app_name}.desktop").exists():
                custom_desktop_src = src_res / f"{app_name}.desktop"
            elif (src_res / "template.desktop").exists():
                custom_desktop_src = src_res / "template.desktop"

        app_wmclass = f"org.phoebus.product.{self.get_app_class_name(app_name)}"

        if custom_desktop_src:
            desktop_raw = custom_desktop_src.read_text(encoding="utf-8")
        else:
            desktop_raw = """[Desktop Entry]
Name={APPLICATION_NAME}
Comment={APPLICATION_DESCRIPTION}
Exec=/opt/{APPLICATION_NAME_LOWER}/bin/{APPLICATION_NAME}
Icon=/opt/{APPLICATION_NAME_LOWER}/lib/{APPLICATION_NAME}.png
Terminal=false
Type=Application
Categories={CATEGORIES}
MimeType=
StartupWMClass={STARTUP_WMCLASS}
"""

        # Perform variable substitutions
        replacements = {
            "{APPLICATION_NAME}": app_name,
            "{app_name}": app_name,
            "{APPLICATION_NAME_LOWER}": app_name_lower,
            "{app_name_lower}": app_name_lower,
            "{APPLICATION_DESCRIPTION}": comment,
            "{comment}": comment,
            "{CATEGORIES}": category,
            "{category}": category,
            "{EXEC_PATH}": f"/opt/{app_name_lower}/bin/{app_name}",
            "{ICON_PATH}": f"/opt/{app_name_lower}/lib/{app_name}.png",
            "{STARTUP_WMCLASS}": app_wmclass,
        }
        desktop_content = desktop_raw
        for placeholder, value in replacements.items():
            desktop_content = desktop_content.replace(placeholder, value)

        (staging_res / f"{app_name}.desktop").write_text(desktop_content, encoding="utf-8")
        (staging_res / "template.desktop").write_text(desktop_content, encoding="utf-8")

        return staging_res

    def build(self) -> Path:
        """Executes full native installer build workflow with file logging."""
        try:
            self.build_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(self.log_file, "w", encoding="utf-8", errors="replace")
        except PermissionError as e:
            raise PermissionError(f"Accès refusé au dossier '{self.output_dir}' : {e}. Veuillez vérifier le dossier de destination dans l'onglet '7. Construction'.")

        try:
            self._log("=======================================================")
            self._log(f"   STARTING BUILD: {self.config.app_name} v{self.config.app_version}")
            self._log(f"   Log File: {self.log_file}")
            self._log(f"   Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("=======================================================\n")

            # Automatically resolve required module dependencies
            resolved_modules = PhoebusPomManager.resolve_dependencies(self.config.enabled_modules)
            if len(resolved_modules) != len(self.config.enabled_modules):
                added = set(resolved_modules) - set(self.config.enabled_modules)
                self._log(f"  [>] Auto-resolved {len(added)} module dependencies: {', '.join(sorted(added))}")
                self.config.enabled_modules = resolved_modules

            missing_tools = self.config.check_system_prerequisites()
            if missing_tools:
                err_details = "\n".join([f"  • {m}" for m in missing_tools])
                self._log(f"\n  [!] MISSING SYSTEM PREREQUISITES:\n{err_details}\n")
                raise RuntimeError(f"Missing required system tools:\n{err_details}")

            jdk_dir = self.jvm_manager.ensure_jdk()

            if self.is_windows:
                self._ensure_wix()

            sources_dir = self._ensure_sources_and_templates()
            extracted_root, main_jar = self._prepare_phoebus(sources_dir)
            self._inject_resources(extracted_root, sources_dir)

            custom_runtime_name = "jre_custom_win" if self.is_windows else "jre_custom"
            custom_runtime_path = self.build_dir / custom_runtime_name
            lib_dir = extracted_root / "lib"
            runtime_dir = self.jvm_manager.create_custom_runtime(main_jar, lib_dir if lib_dir.exists() else None, custom_runtime_path)

            jpackage_exe = self.jvm_manager.get_bin("jpackage")
            self._log("\n  [>] Packaging with jpackage...")

            jpackage_cmd = [
                str(jpackage_exe),
                "--verbose",
                "--input", str(extracted_root),
                "--main-jar", str(main_jar.name),
                "--name", self.config.app_name,
                "--app-version", self.config.app_version,
                "--dest", str(self.output_dir),
                "--java-options", "-Dfile.encoding=UTF-8",
                "--java-options", f"-Dphoebus.folder.name.preference={self.config.phoebus_preference_folder}",
            ]

            if self.config.app_description and self.config.app_description.strip():
                jpackage_cmd.extend(["--description", self.config.app_description.strip()])
            if self.config.app_vendor and self.config.app_vendor.strip():
                jpackage_cmd.extend(["--vendor", self.config.app_vendor.strip()])
            if self.config.app_copyright and self.config.app_copyright.strip():
                jpackage_cmd.extend(["--copyright", self.config.app_copyright.strip()])
            if self.config.app_url and self.config.app_url.strip():
                jpackage_cmd.extend(["--about-url", self.config.app_url.strip()])

            if runtime_dir and runtime_dir.exists():
                jpackage_cmd.extend(["--runtime-image", str(runtime_dir)])

            if self.is_windows:
                win_pkg_type = self.config.windows_package_type.lower() if self.config.windows_package_type.lower() in ["msi", "exe"] else "msi"
                jpackage_cmd.extend([
                    "--type", win_pkg_type,
                    "--win-dir-chooser",
                    "--win-shortcut",
                    "--win-menu",
                    "--win-menu-group", "Utility"
                ])
                icon_file = self._resolve_icon(sources_dir, extracted_root)
                if icon_file:
                    self._log(f"      Using application icon: {icon_file}")
                    jpackage_cmd.extend(["--icon", str(icon_file)])
            else:
                pkg_type = self.config.linux_package_type
                if not pkg_type or pkg_type == "auto":
                    pkg_type = BuildConfig.detect_linux_package_type()

                jpackage_cmd.extend([
                    "--type", pkg_type,
                    "--linux-shortcut",
                    "--linux-menu-group", self.config.linux_menu_group,
                ])
                if pkg_type == "deb":
                    if self.config.deb_maintainer and self.config.deb_maintainer.strip():
                        jpackage_cmd.extend(["--linux-deb-maintainer", self.config.deb_maintainer.strip()])
                    elif self.config.app_vendor and self.config.app_vendor.strip():
                        jpackage_cmd.extend(["--linux-deb-maintainer", self.config.app_vendor.strip()])
                elif pkg_type == "rpm":
                    if self.config.linux_rpm_license and self.config.linux_rpm_license.strip():
                        jpackage_cmd.extend(["--linux-rpm-license-type", self.config.linux_rpm_license.strip()])

                icon_file = self._resolve_icon(sources_dir, extracted_root)
                if icon_file:
                    self._log(f"      Using application icon: {icon_file}")
                    jpackage_cmd.extend(["--icon", str(icon_file)])

                res_dir = self._prepare_linux_resources(icon_file)
                jpackage_cmd.extend(["--resource-dir", str(res_dir)])

            # Execute jpackage
            self._log(f"      Command: {' '.join(jpackage_cmd[:8])} ...\n")
            rc, _ = self._run_cmd(jpackage_cmd, stream_output=True)

            if rc != 0:
                raise RuntimeError(f"jpackage failed with exit code {rc}. See {self.log_file} for full details.")

            # Locate generated package file
            if self.is_windows:
                win_pkg = self.config.windows_package_type.lower() if self.config.windows_package_type.lower() in ["msi", "exe"] else "msi"
                pattern = f"*.{win_pkg}"
            else:
                pattern = "*.deb" if self.config.linux_package_type == "deb" else ("*.rpm" if self.config.linux_package_type == "rpm" else "*.*")
            generated_files = sorted(list(self.output_dir.glob(pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
            if not generated_files and self.is_windows:
                generated_files = sorted(list(self.output_dir.glob("*.msi")) + list(self.output_dir.glob("*.exe")), key=lambda p: p.stat().st_mtime, reverse=True)

            if generated_files:
                output_file = generated_files[0]
                size_mb = output_file.stat().st_size / (1024 * 1024)
                self._log("\n=======================================================")
                self._log("   INSTALLER CREATED SUCCESSFULLY!")
                self._log("=======================================================")
                self._log(f"  File: {output_file}")
                self._log(f"  Size: {size_mb:.2f} MB")
                self._log(f"  Log:  {self.log_file}")
                self._log("=======================================================\n")

                if self.config.clean_temp_build and self.build_dir.exists():
                    self._log("  [>] Cleaning up temporary build workspace to free disk space...")
                    try:
                        for item in self.build_dir.iterdir():
                            try:
                                if item.is_dir():
                                    shutil.rmtree(item, ignore_errors=True)
                                else:
                                    item.unlink(missing_ok=True)
                            except Exception:
                                pass
                        # Remove empty build dir if possible
                        try:
                            self.build_dir.rmdir()
                        except Exception:
                            pass
                        self._log("  [OK] Build workspace cleaned up successfully.\n")
                    except Exception as e:
                        self._log(f"  [!] Note: unable to completely clean build directory: {e}\n")

                return output_file
            else:
                self._log(f"\n  [OK] Packaging finished in {self.output_dir}")
                return self.output_dir
        finally:
            if self._log_handle:
                try:
                    self._log_handle.close()
                except Exception:
                    pass
                self._log_handle = None

    @staticmethod
    def format_size(bytes_count: int) -> str:
        """Formats byte count into human-readable size (KB, MB, GB)."""
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"

    @classmethod
    def get_dir_size(cls, path: Path) -> int:
        """Calculates total disk usage of a directory in bytes."""
        total = 0
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except Exception:
                    pass
        return total

    @classmethod
    def clean_build_cache(cls, base_dir: Optional[Path] = None, build_dir_name: str = "build") -> Tuple[int, int]:
        """
        Safely purges temporary build artifacts, extracted sources, and downloaded JDKs from build_dir.
        User project configurations in configs/ are strictly preserved.
        Returns:
            Tuple[int, int]: (freed_bytes, number_of_items_deleted)
        """
        base = base_dir or get_workspace_dir()
        build_path = Path(build_dir_name) if Path(build_dir_name).is_absolute() else (base / build_dir_name)
        if not build_path.exists():
            return 0, 0

        freed_bytes = cls.get_dir_size(build_path)
        removed_count = 0

        for item in build_path.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                    removed_count += 1
                else:
                    item.unlink(missing_ok=True)
                    removed_count += 1
            except Exception as e:
                print(f"  [!] Unable to delete {item.name}: {e}")

        return freed_bytes, removed_count
