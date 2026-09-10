import os
import shutil
import stat
import sys
import tarfile
import urllib.error
import urllib.request
import ssl
import zipfile
from pathlib import Path
from typing import Optional, Callable


def safe_rmtree(path: Path | str, ignore_errors: bool = False) -> None:
    """Removes a directory tree safely on Windows, handling read-only attributes."""
    p = Path(path)
    if not p.exists():
        return

    def _handle_remove_readonly(func, file_path, exc_info):
        try:
            os.chmod(file_path, stat.S_IWRITE)
            func(file_path)
        except Exception:
            pass

    if sys.version_info >= (3, 12):
        def _on_exc(func, file_path, exc):
            try:
                os.chmod(file_path, stat.S_IWRITE)
                func(file_path)
            except Exception:
                pass
        shutil.rmtree(p, onexc=_on_exc, ignore_errors=ignore_errors)
    else:
        shutil.rmtree(p, onerror=_handle_remove_readonly, ignore_errors=ignore_errors)


class DownloadManager:
    """Download and archive extraction manager."""

    @staticmethod
    def get_ssl_context() -> ssl.SSLContext:
        """
        Builds a robust SSLContext that works across platforms (Windows, Linux, macOS),
        prioritizing certifi CA bundle, system trust store, with unverified fallback.
        """
        # 1. Try certifi bundle if available
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass

        # 2. Try default context with loaded system certs
        try:
            ctx = ssl.create_default_context()
            ctx.load_default_certs()
            return ctx
        except Exception:
            pass

        # 3. Fallback unverified context
        try:
            return ssl._create_unverified_context()
        except Exception:
            return ssl.create_default_context()

    @staticmethod
    def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
        """Displays a download progress bar in console."""
        if total_size <= 0:
            sys.stdout.write(f"\rDownloading... ({block_num * block_size / (1024 * 1024):.1f} MB)")
            sys.stdout.flush()
            return
        
        downloaded = block_num * block_size
        percent = min(100.0, downloaded * 100.0 / total_size)
        bar_length = 35
        filled_length = int(bar_length * percent / 100)
        bar = "=" * filled_length + "-" * (bar_length - filled_length)
        
        sys.stdout.write(
            f"\r [{bar}] {percent:5.1f}% ({downloaded / (1024 * 1024):.1f}/{total_size / (1024 * 1024):.1f} MB)"
        )
        sys.stdout.flush()

    @staticmethod
    def is_archive(path: Path | str) -> bool:
        """Returns True if the filename has a known archive extension."""
        name = str(path).lower()
        return name.endswith((".zip", ".tar.gz", ".tgz", ".tar"))

    @classmethod
    def is_valid_archive(cls, archive_path: Path | str) -> bool:
        """Verifies if an archive file (.zip, .tar.gz, .tgz) exists, is non-empty, and structurally intact."""
        p = Path(archive_path)
        if not p.exists() or not p.is_file() or p.stat().st_size == 0:
            return False

        name_lower = p.name.lower()
        if name_lower.endswith(".zip"):
            if not zipfile.is_zipfile(p):
                return False
            try:
                with zipfile.ZipFile(p, "r") as z:
                    if not z.infolist():
                        return False
                return True
            except Exception:
                return False
        elif name_lower.endswith((".tar.gz", ".tgz", ".tar")):
            if not tarfile.is_tarfile(p):
                return False
            try:
                with tarfile.open(p, "r:*") as t:
                    if not t.getmembers():
                        return False
                return True
            except Exception:
                return False
        return True

    @classmethod
    def download_file(
        cls,
        url: str,
        destination: Path,
        force: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout: int = 60,
    ) -> Path:
        """Downloads a remote file if not already cached locally."""
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and destination.stat().st_size > 0 and not force:
            if cls.is_archive(destination):
                if cls.is_valid_archive(destination):
                    print(f"  [OK] Cached file already exists: {destination.name}")
                    return destination
                else:
                    print(f"  [!] Cached file {destination.name} is incomplete or corrupted. Re-downloading...")
                    destination.unlink(missing_ok=True)
            else:
                print(f"  [OK] Cached file already exists: {destination.name}")
                return destination

        print(f"  [>] Downloading from: {url}")
        print(f"      To: {destination}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        ssl_ctx = cls.get_ssl_context()

        temp_dest = destination.parent / f"{destination.name}.part"
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)

        def _do_download(context: Optional[ssl.SSLContext]):
            with urllib.request.urlopen(req, context=context, timeout=timeout) as response, open(temp_dest, "wb") as out_file:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                block_size = 64 * 1024
                block_num = 0

                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    out_file.write(buffer)
                    downloaded += len(buffer)
                    block_num += 1
                    if progress_callback:
                        progress_callback(downloaded, total_size)
                    else:
                        cls._reporthook(block_num, block_size, total_size)

                if total_size > 0 and downloaded < total_size:
                    raise RuntimeError(
                        f"Download truncated for {destination.name}: received {downloaded}/{total_size} bytes."
                    )

        try:
            try:
                _do_download(ssl_ctx)
            except (urllib.error.URLError, ssl.SSLError) as ssl_err:
                # If certificate verification failed on Windows or corporate proxy, retry with unverified context
                err_str = str(ssl_err)
                if "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str or isinstance(ssl_err, ssl.SSLError):
                    print("  [!] SSL certificate verification failed. Retrying with permissive SSL context...")
                    if temp_dest.exists():
                        temp_dest.unlink(missing_ok=True)
                    unverified_ctx = ssl._create_unverified_context()
                    _do_download(unverified_ctx)
                else:
                    raise

            if cls.is_archive(temp_dest) and not cls.is_valid_archive(temp_dest):
                temp_dest.unlink(missing_ok=True)
                raise RuntimeError(f"Downloaded archive for {destination.name} failed integrity check.")

            if destination.exists():
                destination.unlink(missing_ok=True)
            shutil.move(str(temp_dest), str(destination))

            sys.stdout.write("\n")
            sys.stdout.flush()
            print(f"  [OK] Download completed: {destination.name}")
            return destination
        except Exception as e:
            sys.stdout.write("\n")
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)
            if destination.exists() and cls.is_archive(destination) and not cls.is_valid_archive(destination):
                destination.unlink(missing_ok=True)
            raise RuntimeError(f"Error downloading {url}: {e}")

    @classmethod
    def extract_archive(
        cls,
        archive_path: Path,
        extract_to: Path,
        clean_target: bool = False,
        strip_root: bool = False,
    ) -> Path:
        """Extracts a .tar.gz or .zip archive directly into extract_to, optionally stripping top-level directory prefix."""
        if clean_target and extract_to.exists():
            safe_rmtree(extract_to)

        extract_to.mkdir(parents=True, exist_ok=True)
        print(f"  [>] Extracting {archive_path.name}...")

        try:
            if archive_path.name.endswith(".tar.gz") or archive_path.name.endswith(".tgz"):
                with tarfile.open(archive_path, "r:gz") as tar:
                    members = tar.getmembers()
                    if strip_root:
                        first_parts = [m.name.split("/")[0] for m in members if "/" in m.name]
                        common_root = first_parts[0] if first_parts and all(m.name.startswith(first_parts[0] + "/") or m.name == first_parts[0] for m in members) else None
                        filtered_members = []
                        for m in members:
                            if common_root:
                                if m.name == common_root:
                                    continue
                                if m.name.startswith(common_root + "/"):
                                    m.name = m.name[len(common_root) + 1:]
                            if m.name:
                                filtered_members.append(m)
                        if hasattr(tarfile, "data_filter"):
                            tar.extractall(path=extract_to, members=filtered_members, filter="data")
                        else:
                            tar.extractall(path=extract_to, members=filtered_members)
                    else:
                        if hasattr(tarfile, "data_filter"):
                            tar.extractall(path=extract_to, filter="data")
                        else:
                            tar.extractall(path=extract_to)
            elif archive_path.name.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as z:
                    if strip_root:
                        infolist = z.infolist()
                        first_parts = [info.filename.split("/")[0] for info in infolist if "/" in info.filename]
                        common_root = first_parts[0] if first_parts and all(info.filename.startswith(first_parts[0] + "/") or info.filename in (first_parts[0], first_parts[0] + "/") for info in infolist) else None
                        for info in infolist:
                            orig = info.filename
                            if common_root:
                                if orig in (common_root, common_root + "/"):
                                    continue
                                if orig.startswith(common_root + "/"):
                                    info.filename = orig[len(common_root) + 1:]
                            if info.filename:
                                extracted_file = z.extract(info, path=extract_to)
                                if os.name != "nt":
                                    mode = (info.external_attr >> 16) & 0o777
                                    if mode:
                                        try:
                                            os.chmod(extracted_file, mode)
                                        except Exception:
                                            pass
                    else:
                        z.extractall(path=extract_to)
                        if os.name != "nt":
                            for info in z.infolist():
                                mode = (info.external_attr >> 16) & 0o777
                                if mode:
                                    try:
                                        os.chmod(extract_to / info.filename, mode)
                                    except Exception:
                                        pass
            else:
                raise ValueError(f"Unsupported archive format: {archive_path.name}")
        except Exception as e:
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)
            if clean_target and extract_to.exists():
                safe_rmtree(extract_to, ignore_errors=True)
            raise RuntimeError(f"Error extracting {archive_path.name}: {e}") from e

        print(f"  [OK] Extraction completed in {extract_to}")
        return extract_to

    @classmethod
    def is_valid_sources_dir(cls, sources_dir: Path) -> bool:
        """Verifies if the sources directory contains essential non-empty files."""
        if not sources_dir.exists() or not sources_dir.is_dir():
            return False
        root_pom = sources_dir / "pom.xml"
        product_pom = sources_dir / "phoebus-product" / "pom.xml"
        if not root_pom.exists() or root_pom.stat().st_size == 0:
            return False
        if not product_pom.exists() or product_pom.stat().st_size == 0:
            return False
        return True

    @classmethod
    def download_phoebus_sources(cls, tag: str, build_dir: Path, force: bool = False) -> Path:
        """Downloads and extracts Phoebus source code for the specified version tag directly into build_dir/phoebus-<ver>."""
        clean_tag = tag.lstrip('v')
        sources_dir = build_dir / f"phoebus-{clean_tag}"
        legacy_dir = build_dir / "sources" / f"phoebus-{clean_tag}"

        if not force:
            if cls.is_valid_sources_dir(sources_dir):
                print(f"  [OK] Phoebus sources already present: {sources_dir}")
                return sources_dir
            if cls.is_valid_sources_dir(legacy_dir):
                print(f"  [OK] Reusing sources from legacy subfolder: {legacy_dir}")
                return legacy_dir

        if sources_dir.exists() and not cls.is_valid_sources_dir(sources_dir):
            print(f"  [!] Detected incomplete or corrupted sources in {sources_dir}. Re-extracting...")
            safe_rmtree(sources_dir, ignore_errors=True)

        # Also remove legacy temp_src folders if left behind
        temp_extract = build_dir / f"temp_src_{tag}"
        if temp_extract.exists():
            safe_rmtree(temp_extract, ignore_errors=True)

        archive_name = f"phoebus-{tag}-sources.tar.gz"
        archive_path = build_dir / archive_name
        url = f"https://github.com/ControlSystemStudio/phoebus/archive/refs/tags/{tag}.tar.gz"

        # Check if archive exists but is corrupt
        if archive_path.exists() and archive_path.stat().st_size > 0:
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.getmembers()
            except Exception:
                print(f"  [!] Cached archive {archive_path.name} is corrupted. Re-downloading...")
                archive_path.unlink(missing_ok=True)

        print(f"\n  [>] Fetching Phoebus sources ({tag})...")
        cls.download_file(url, archive_path, force=force)

        try:
            cls.extract_archive(archive_path, sources_dir, clean_target=True, strip_root=True)
        finally:
            archive_path.unlink(missing_ok=True)

        if not cls.is_valid_sources_dir(sources_dir):
            raise RuntimeError(f"Phoebus sources extracted to {sources_dir} appear invalid or incomplete.")

        # Ensure settings_template.ini is generated inside sources_dir
        template_file = sources_dir / "settings_template.ini"
        if not template_file.exists() or template_file.stat().st_size == 0:
            try:
                from .settings_generator import SettingsGenerator
                SettingsGenerator.generate_from_sources(sources_dir, template_file)
            except Exception as e:
                print(f"  [!] Note: Could not auto-generate settings_template.ini: {e}")

        print(f"  [OK] Phoebus sources ready in: {sources_dir}")
        return sources_dir

    @classmethod
    def prepare_local_sources(cls, local_path: Path | str, target_dir: Optional[Path] = None, force: bool = False) -> Path:
        """
        Prepares local Phoebus sources from either a directory or an archive (.zip, .tar.gz, .tgz).
        If directory: validates pom.xml structure.
        If archive: extracts it into target_dir (default: sources/phoebus/phoebus-local).
        """
        p = Path(local_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Local sources path does not exist: {p}")

        if p.is_dir():
            if cls.is_valid_sources_dir(p):
                template_file = p / "settings_template.ini"
                if not template_file.exists() or template_file.stat().st_size == 0:
                    try:
                        from .settings_generator import SettingsGenerator
                        SettingsGenerator.generate_from_sources(p, template_file)
                    except Exception as e:
                        print(f"  [!] Note: Could not auto-generate settings_template.ini: {e}")
                return p

            raise ValueError(f"Directory '{p}' is not a valid Phoebus sources directory (missing pom.xml or phoebus-product/pom.xml).")

        archive_name = p.name.lower()
        if not (archive_name.endswith(".tar.gz") or archive_name.endswith(".tgz") or archive_name.endswith(".zip")):
            raise ValueError(f"Unsupported archive format for local sources: {p.name}")

        from .config import get_workspace_dir
        extract_dest = target_dir or (get_workspace_dir() / "sources" / "phoebus" / f"phoebus-local-{p.stem}")
        if not force and cls.is_valid_sources_dir(extract_dest):
            return extract_dest

        cls.extract_archive(p, extract_dest, clean_target=True, strip_root=True)
        if not cls.is_valid_sources_dir(extract_dest):
            for sub in extract_dest.iterdir():
                if sub.is_dir() and cls.is_valid_sources_dir(sub):
                    extract_dest = sub
                    break

        if not cls.is_valid_sources_dir(extract_dest):
            raise RuntimeError(f"Extracted archive '{p.name}' into '{extract_dest}' does not contain valid Phoebus sources.")

        template_file = extract_dest / "settings_template.ini"
        if not template_file.exists() or template_file.stat().st_size == 0:
            try:
                from .settings_generator import SettingsGenerator
                SettingsGenerator.generate_from_sources(extract_dest, template_file)
            except Exception as e:
                print(f"  [!] Note: Could not auto-generate settings_template.ini: {e}")

        return extract_dest

    MAVEN_URL = "https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.zip"
    WIX_URL = "https://github.com/wixtoolset/wix3/releases/download/wix3112rtm/wix311-binaries.zip"

    @classmethod
    def is_maven_ready(cls, maven_dir: Optional[Path]) -> bool:
        """Checks if portable Maven binaries exist in maven_dir."""
        if not maven_dir or not maven_dir.exists() or not maven_dir.is_dir():
            return False
        is_win = (sys.platform == "win32" or os.name == "nt")
        mvn_cmd = maven_dir / "bin" / ("mvn.cmd" if is_win else "mvn")
        mvn_plain = maven_dir / "bin" / "mvn"
        return (mvn_cmd.exists() or mvn_plain.exists()) and (maven_dir / "lib").exists()

    @classmethod
    def ensure_maven(cls, base_dir: Path, force: bool = False, url: Optional[str] = None) -> Path:
        """Downloads and configures portable Apache Maven in sources/maven."""
        maven_dir = base_dir / "sources" / "maven"
        if not force and cls.is_maven_ready(maven_dir):
            if os.name != "nt":
                bin_dir = maven_dir / "bin"
                if bin_dir.exists():
                    for item in bin_dir.iterdir():
                        if item.is_file() and item.suffix.lower() not in [".cmd", ".bat"]:
                            try:
                                item.chmod(item.stat().st_mode | 0o755)
                            except Exception:
                                pass
            print(f"  [OK] Apache Maven already ready: {maven_dir}")
            return maven_dir

        print(f"\n  [>] Preparing portable Apache Maven...")
        archive_dir = base_dir / "sources"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / "apache-maven-bin.zip"
        download_url = url or cls.MAVEN_URL

        try:
            cls.download_file(download_url, archive_path, force=force)
            cls.extract_archive(archive_path, maven_dir, clean_target=True, strip_root=True)
        finally:
            archive_path.unlink(missing_ok=True)

        if os.name != "nt":
            bin_dir = maven_dir / "bin"
            if bin_dir.exists():
                for item in bin_dir.iterdir():
                    if item.is_file() and item.suffix.lower() not in [".cmd", ".bat"]:
                        try:
                            item.chmod(item.stat().st_mode | 0o755)
                        except Exception:
                            pass

        if not cls.is_maven_ready(maven_dir):
            raise RuntimeError(f"Failed to configure Apache Maven in {maven_dir}")

        print(f"  [OK] Apache Maven configured in: {maven_dir}")
        return maven_dir

    @classmethod
    def prepare_local_maven(cls, local_path: Path | str, target_dir: Optional[Path] = None) -> Path:
        """
        Configures Maven from a local directory, direct binary executable, or archive file (.zip, .tar.gz).
        """
        p = Path(local_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Local Maven path does not exist: {p}")

        if p.is_file():
            if p.name.lower() in ("mvn", "mvn.cmd", "mvn.bat"):
                bin_dir = p.parent
                mvn_root = bin_dir.parent
                if cls.is_maven_ready(mvn_root):
                    return mvn_root
                return bin_dir

            archive_name = p.name.lower()
            if archive_name.endswith(".zip") or archive_name.endswith(".tar.gz") or archive_name.endswith(".tgz"):
                from .config import get_workspace_dir
                dest = target_dir or (get_workspace_dir() / "sources" / "maven")
                cls.extract_archive(p, dest, clean_target=True, strip_root=True)
                if not cls.is_maven_ready(dest):
                    for sub in dest.iterdir():
                        if sub.is_dir() and cls.is_maven_ready(sub):
                            dest = sub
                            break
                if os.name != "nt":
                    bin_dir = dest / "bin"
                    if bin_dir.exists():
                        for item in bin_dir.iterdir():
                            if item.is_file() and item.suffix.lower() not in [".cmd", ".bat"]:
                                try:
                                    item.chmod(item.stat().st_mode | 0o755)
                                except Exception:
                                    pass
                if not cls.is_maven_ready(dest):
                    raise RuntimeError(f"Extracted Maven archive does not contain a valid Maven distribution in {dest}")
                return dest

        if p.is_dir():
            if cls.is_maven_ready(p):
                return p
            if p.name.lower() == "bin" and cls.is_maven_ready(p.parent):
                return p.parent

            raise ValueError(f"Directory '{p}' is not a valid Maven directory (missing bin/mvn or lib/).")

        raise ValueError(f"Invalid local Maven path: {p}")

    @classmethod
    def is_wix_ready(cls, wix_dir: Optional[Path]) -> bool:
        """Checks if WiX Toolset binaries exist in wix_dir."""
        if not wix_dir or not wix_dir.exists() or not wix_dir.is_dir():
            return False
        candle = wix_dir / "candle.exe"
        light = wix_dir / "light.exe"
        return candle.exists() and light.exists()

    @classmethod
    def ensure_wix(cls, base_dir: Path, force: bool = False, url: Optional[str] = None) -> Path:
        """Downloads and configures WiX Toolset in sources/wix."""
        wix_dir = base_dir / "sources" / "wix"
        if not force and cls.is_wix_ready(wix_dir):
            print(f"  [OK] WiX Toolset already ready: {wix_dir}")
            return wix_dir

        print(f"\n  [>] Preparing WiX Toolset...")
        archive_dir = base_dir / "sources"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / "wix311-binaries.zip"
        download_url = url or cls.WIX_URL

        try:
            cls.download_file(download_url, archive_path, force=force)
            cls.extract_archive(archive_path, wix_dir, clean_target=True, strip_root=False)
        finally:
            archive_path.unlink(missing_ok=True)

        if not cls.is_wix_ready(wix_dir):
            raise RuntimeError(f"Failed to configure WiX Toolset in {wix_dir}")

        print(f"  [OK] WiX Toolset configured in: {wix_dir}")
        return wix_dir

