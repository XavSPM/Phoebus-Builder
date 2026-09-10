import os
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List
from .downloader import DownloadManager, safe_rmtree
from .config import get_workspace_dir


class JvmManager:
    """Adoptium JDK management, jdeps dependency analysis, and jlink runtime creation."""

    MANUAL_MODULES = [
        "java.base",
        "java.logging",
        "java.xml",
        "jdk.crypto.ec",
        "java.desktop",
        "java.management",
        "java.naming",
        "java.sql",
        "java.net.http",
        "java.scripting",
        "jdk.jsobject",
        "jdk.unsupported",
        "jdk.unsupported.desktop",
        "jdk.xml.dom",
    ]

    def __init__(self, build_dir: Optional[Path] = None, java_version: str = "25", is_windows: bool = False, base_dir: Optional[Path] = None, jdk_dir: Optional[Path] = None, local_jdk_path: Optional[Path | str] = None):
        self.base_dir = base_dir or get_workspace_dir()
        self.java_version = str(java_version).split()[0]  # Extracts e.g. "25" from "25 (Adoptium Temurin)"
        self.is_windows = is_windows
        self.build_dir = build_dir or (self.base_dir / "sources" / "jdk")
        self.local_jdk_path = Path(local_jdk_path) if local_jdk_path else None
        
        # Shared JDK storage path: sources/jdk/jdk-<version>-<win|linux>
        if jdk_dir:
            self.jdk_dir = jdk_dir
        elif self.local_jdk_path and self.local_jdk_path.is_dir() and self.is_jdk_ready(self.local_jdk_path, is_windows):
            self.jdk_dir = self.local_jdk_path
        else:
            shared_jdk_base = self.base_dir / "sources" / "jdk"
            target_name = f"jdk-{self.java_version}-{'win' if is_windows else 'linux'}"
            self.jdk_dir = shared_jdk_base / target_name

    @classmethod
    def is_jdk_ready(cls, jdk_dir: Optional[Path], is_windows: bool = False) -> bool:
        """Verifies if the JDK directory exists and contains valid java and jpackage executables."""
        if not jdk_dir or not jdk_dir.exists() or not jdk_dir.is_dir():
            return False
        exe_ext = ".exe" if is_windows else ""
        java_exe = jdk_dir / "bin" / f"java{exe_ext}"
        jpackage_exe = jdk_dir / "bin" / f"jpackage{exe_ext}"
        return java_exe.exists() and jpackage_exe.exists()

    @classmethod
    def _get_subprocess_kwargs(cls, is_windows: bool) -> dict:
        kwargs = {}
        if is_windows:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
        return kwargs

    @classmethod
    def get_jdk_version(cls, jdk_dir: Path, is_windows: bool = False) -> str:
        """Runs bin/java -version to extract the major version string."""
        exe_ext = ".exe" if is_windows else ""
        java_exe = jdk_dir / "bin" / f"java{exe_ext}"
        if not java_exe.exists():
            return ""
        try:
            res = subprocess.run(
                [str(java_exe), "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                **cls._get_subprocess_kwargs(is_windows)
            )
            output = (res.stderr or "") + (res.stdout or "")
            import re
            m = re.search(r'version "(\d+)', output)
            if m:
                return m.group(1)
        except Exception:
            pass
        return ""

    @classmethod
    def detect_system_jdks(cls, is_windows: bool = False) -> List[Path]:
        """Detects available installed JDKs on the host system."""
        found: List[Path] = []
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            p = Path(java_home)
            if cls.is_jdk_ready(p, is_windows) and p not in found:
                found.append(p)

        candidates: List[Path] = []
        if is_windows:
            prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            for base in [prog_files, prog_files_x86]:
                if not base:
                    continue
                p_base = Path(base)
                for vendor in ["Eclipse Adoptium", "Java", "BellSoft", "Microsoft", "Zulu"]:
                    vendor_dir = p_base / vendor
                    if vendor_dir.exists():
                        candidates.extend([d for d in vendor_dir.iterdir() if d.is_dir()])
        else:
            search_dirs = [
                Path("/usr/lib/jvm"),
                Path("/usr/java"),
                Path("/opt/java"),
                Path("/Library/Java/JavaVirtualMachines"),
            ]
            for sdir in search_dirs:
                if sdir.exists() and sdir.is_dir():
                    try:
                        for item in sdir.iterdir():
                            if item.is_dir():
                                candidates.append(item)
                                if (item / "Contents" / "Home").is_dir():
                                    candidates.append(item / "Contents" / "Home")
                    except Exception:
                        pass

        for cand in candidates:
            if cls.is_jdk_ready(cand, is_windows) and cand not in found:
                found.append(cand)

        return found

    @classmethod
    def prepare_local_jdk(cls, local_path: Path | str, target_dir: Optional[Path] = None, is_windows: bool = False) -> Path:
        """
        Validates or extracts a local JDK from a folder or archive (.zip, .tar.gz).
        """
        p = Path(local_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Local JDK path does not exist: {p}")

        if p.is_dir():
            if cls.is_jdk_ready(p, is_windows):
                return p
            if (p / "Contents" / "Home").is_dir() and cls.is_jdk_ready(p / "Contents" / "Home", is_windows):
                return p / "Contents" / "Home"
            raise ValueError(f"Directory '{p}' does not appear to be a valid JDK (missing bin/java or bin/jpackage).")

        archive_name = p.name.lower()
        if not (archive_name.endswith(".zip") or archive_name.endswith(".tar.gz") or archive_name.endswith(".tgz")):
            raise ValueError(f"Unsupported archive format for local JDK: {p.name}")

        dest = target_dir or (get_workspace_dir() / "sources" / "jdk" / f"jdk-local-{p.stem}")
        DownloadManager.extract_archive(p, dest, clean_target=True, strip_root=True)
        if cls.is_jdk_ready(dest, is_windows):
            return dest
        for sub in dest.iterdir():
            if sub.is_dir() and cls.is_jdk_ready(sub, is_windows):
                return sub

        raise RuntimeError(f"Extracted JDK archive in '{dest}' does not contain valid java and jpackage executables.")

    def get_adoptium_url(self) -> str:
        """Constructs the Adoptium Temurin GA download URL."""
        os_name = "windows" if self.is_windows else "linux"
        arch = "x64"
        return f"https://api.adoptium.net/v3/binary/latest/{self.java_version}/ga/{os_name}/{arch}/jdk/hotspot/normal/eclipse"

    def ensure_jdk(self) -> Path:
        """Prepares or downloads the JDK if necessary into storage."""
        if self.local_jdk_path:
            ready_jdk = self.prepare_local_jdk(self.local_jdk_path, is_windows=self.is_windows)
            self.jdk_dir = ready_jdk
            print(f"  [OK] Local JDK ready: {self.jdk_dir}")
            return self.jdk_dir

        if self.is_jdk_ready(self.jdk_dir, self.is_windows):
            print(f"  [OK] JDK {self.java_version} ready: {self.jdk_dir}")
            return self.jdk_dir

        # Check legacy project location e.g. build_dir/jdk or build_dir/jdk_win
        legacy_dir = self.build_dir / ("jdk_win" if self.is_windows else "jdk")
        if self.is_jdk_ready(legacy_dir, self.is_windows):
            print(f"  [OK] Reusing JDK from legacy build path: {legacy_dir}")
            return legacy_dir

        print(f"  [>] Preparing JDK {self.java_version} ({'Windows' if self.is_windows else 'Linux'})...")
        archive_ext = "zip" if self.is_windows else "tar.gz"
        archive_dir = self.jdk_dir.parent
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"jdk-{self.java_version}-{'win' if self.is_windows else 'linux'}.{archive_ext}"

        try:
            DownloadManager.download_file(self.get_adoptium_url(), archive_path)
            DownloadManager.extract_archive(archive_path, self.jdk_dir, clean_target=True, strip_root=True)
        finally:
            archive_path.unlink(missing_ok=True)

        if not self.is_jdk_ready(self.jdk_dir, self.is_windows):
            raise RuntimeError(f"Failed to configure JDK in {self.jdk_dir}")

        print(f"  [OK] JDK configured in: {self.jdk_dir}")
        return self.jdk_dir

    def get_bin(self, name: str) -> Path:
        """Returns path to a JDK binary executable."""
        exe_ext = ".exe" if self.is_windows else ""
        bin_path = self.jdk_dir / "bin" / f"{name}{exe_ext}"
        if not bin_path.exists():
            raise FileNotFoundError(f"Binary {name} not found in {self.jdk_dir / 'bin'}")
        if not self.is_windows:
            try:
                bin_path.chmod(bin_path.stat().st_mode | 0o755)
            except Exception:
                pass
        return bin_path

    def analyze_dependencies(self, main_jar: Path, lib_dir: Optional[Path] = None) -> List[str]:
        """Detects required Java modules via jdeps."""
        jdeps_exe = self.get_bin("jdeps")
        classpath = str(main_jar)
        if lib_dir and lib_dir.exists():
            sep = ";" if self.is_windows else ":"
            classpath += f"{sep}{lib_dir}/*"

        cmd = [
            str(jdeps_exe),
            "--print-module-deps",
            "--ignore-missing-deps",
            "--multi-release", str(self.java_version),
            "--class-path", classpath,
            str(main_jar)
        ]

        print("  [>] Analyzing Java dependencies (jdeps)...")
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                **self._get_subprocess_kwargs(self.is_windows)
            )
            output = res.stdout.strip()
            lines = [l.strip() for l in output.splitlines() if l.strip() and not l.startswith("Warning")]
            modules = []
            for line in lines:
                modules.extend([m.strip() for m in line.split(",") if m.strip()])
            print(f"  [OK] Modules detected: {', '.join(modules) if modules else 'none'}")
            return modules
        except Exception as e:
            print(f"  [!] Warning: jdeps could not analyze dependencies ({e}). Using default module list.")
            return []

    def create_custom_runtime(self, main_jar: Path, lib_dir: Optional[Path], output_dir: Path) -> Optional[Path]:
        """Creates a minimal lightweight Java runtime with jlink."""
        print("  [>] Generating minimal runtime (jlink)...")
        detected = self.analyze_dependencies(main_jar, lib_dir)
        all_modules = sorted(list(set(self.MANUAL_MODULES + detected)))
        modules_arg = ",".join(all_modules)

        print(f"  [>] Included modules ({len(all_modules)}): {modules_arg}")

        if output_dir.exists():
            safe_rmtree(output_dir)

        jlink_exe = self.get_bin("jlink")
        cmd = [
            str(jlink_exe),
            "--add-modules", modules_arg,
            "--no-header-files",
            "--no-man-pages",
            "--strip-debug",
            "--compress=zip-6",
            "--output", str(output_dir)
        ]

        jmods_dir = self.jdk_dir / "jmods"
        if jmods_dir.exists():
            cmd.extend(["--module-path", str(jmods_dir)])

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **self._get_subprocess_kwargs(self.is_windows)
            )
            print(f"  [OK] Minimal Java runtime created in: {output_dir}")
            return output_dir
        except subprocess.CalledProcessError as e:
            print(f"  [!] jlink failed ({e.stderr.strip() if e.stderr else e}). Falling back to full JDK.")
            if output_dir.exists():
                safe_rmtree(output_dir, ignore_errors=True)
            return None
