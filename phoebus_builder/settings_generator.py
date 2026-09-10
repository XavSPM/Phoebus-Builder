"""
Settings template generator module based on scanning *preferences.properties files
in Phoebus source code (equivalent to Phoebus create_settings_template.py).
"""

import glob
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Optional


class SettingsGenerator:
    """Generates settings_template.ini from Phoebus source tree or modules."""

    @staticmethod
    def _remove_duplicate_properties(prop_files: List[str]) -> List[str]:
        """Removes duplicate property files keeping a single occurrence."""
        unique = {}
        for path in prop_files:
            filename = os.path.basename(path)
            if filename not in unique:
                unique[filename] = path
        return list(unique.values())

    @classmethod
    def extract_settings_from_properties(
        cls,
        out_file_path: Path,
        search_dir: Path,
        include_comments: bool = True,
        verbose: bool = False
    ) -> int:
        """
        Scans all *preferences.properties files under search_dir
        and writes a complete settings configuration template.
        """
        pattern = str(search_dir) + "/**/*preferences.properties"
        prop_files = glob.glob(pattern, recursive=True)
        prop_files_unique = cls._remove_duplicate_properties(prop_files)

        out_file_path.parent.mkdir(parents=True, exist_ok=True)
        count_props = 0

        with open(out_file_path, "w", encoding="utf-8") as out_f:
            for prop_file in sorted(prop_files_unique):
                if verbose:
                    print(f"  [>] Processing: {os.path.relpath(prop_file, search_dir)}")

                package_str = ""
                try:
                    with open(prop_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except Exception as e:
                    print(f"  [!] Unable to read {prop_file}: {e}")
                    continue

                for line in lines:
                    line = line.strip()
                    if line.startswith("# Package "):
                        package_str = line[10:].strip()
                        banner = f"\n#{'=' * (len(line) + 2)}\n# {line}\n#{'=' * (len(line) + 2)}\n"
                        out_f.write(banner)
                    elif "--------" in line:
                        continue
                    elif "=" in line:
                        count_props += 1
                        if line.startswith("#"):
                            if include_comments:
                                out_f.write(f"# {package_str}/{line[1:].strip()}\n")
                        else:
                            out_f.write(f"# {package_str}/{line}\n")
                    elif line != "" and not line.startswith("#"):
                        count_props += 1
                        out_f.write(f"# {package_str}/{line}\n")
                    else:
                        if include_comments:
                            out_f.write(line + "\n")

        return count_props

    @classmethod
    def generate_from_sources(
        cls,
        sources_root: Path,
        output_file: Optional[Path] = None,
        include_comments: bool = True
    ) -> Path:
        """Generates template file from Phoebus source root directory (default: sources_root / settings_template.ini)."""
        target_out = output_file or (sources_root / "settings_template.ini")
        print(f"  [>] Generating {target_out.name} from sources ({sources_root})...")
        count = cls.extract_settings_from_properties(
            out_file_path=target_out,
            search_dir=sources_root,
            include_comments=include_comments
        )
        print(f"  [OK] Template successfully generated: {target_out} ({count} indexed properties)")
        return target_out
