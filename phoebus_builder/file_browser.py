"""
File and directory browsing helper module based on PySide6 GUI dialogs.
Uses PySide6.QtWidgets (QFileDialog and QMessageBox),
with fallback to console Tab-completion (readline) in headless / SSH environments.
"""

import glob
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from .i18n import t

# Silence verbose Wayland debug warnings
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland*=false;qt.qpa.wayland.textinput=false;qt.qpa.services*=false"


class NativeFileBrowser:
    """Directory and file selection manager using PySide6."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

    @classmethod
    def _ensure_qapp(cls):
        """Ensures a QApplication instance is initialized."""
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            app = QApplication.instance()
            if app is None:
                QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
                app = QApplication([])
            else:
                app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
            return app
        except Exception:
            return None

    @classmethod
    def show_warning_dialog(cls, title: str, message: str) -> None:
        """Displays a Qt warning dialog box."""
        try:
            from PySide6.QtWidgets import QMessageBox
            cls._ensure_qapp()
            QMessageBox.warning(None, title, message)
        except Exception:
            pass

    @classmethod
    def _get_default_browse_dir(cls, start_path: Optional[str | Path] = None) -> Path:
        if start_path:
            return Path(start_path).resolve()
        try:
            from .config import get_workspace_dir
            return get_workspace_dir()
        except Exception:
            return Path.cwd()

    @classmethod
    def get_existing_directory(
        cls,
        parent=None,
        caption: str = "",
        start_dir: Optional[str | Path] = None,
    ) -> str:
        """Opens a well-dimensioned directory chooser dialog with explicit button labels."""
        cls._ensure_qapp()
        initial = str(cls._get_default_browse_dir(start_dir))
        dlg = QFileDialog(parent, caption or t("dlg_btn_select_dir"), initial)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setLabelText(QFileDialog.DialogLabel.Accept, t("dlg_btn_select_dir"))
        dlg.setLabelText(QFileDialog.DialogLabel.Reject, t("btn_cancel"))
        dlg.setLabelText(QFileDialog.DialogLabel.LookIn, t("dlg_lbl_look_in"))
        dlg.setLabelText(QFileDialog.DialogLabel.FileName, t("dlg_lbl_file_name"))
        dlg.resize(850, 520)

        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            selected = dlg.selectedFiles()
            if selected:
                return selected[0]
        return ""

    @classmethod
    def get_open_file_name(
        cls,
        parent=None,
        caption: str = "",
        start_dir: Optional[str | Path] = None,
        filter: str = ""
    ) -> str:
        """Opens a well-dimensioned file chooser dialog with explicit button labels."""
        cls._ensure_qapp()
        initial = str(cls._get_default_browse_dir(start_dir))
        dlg = QFileDialog(parent, caption or t("dlg_btn_open_file"), initial, filter)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
        dlg.setLabelText(QFileDialog.DialogLabel.Accept, t("dlg_btn_open_file"))
        dlg.setLabelText(QFileDialog.DialogLabel.Reject, t("btn_cancel"))
        dlg.setLabelText(QFileDialog.DialogLabel.LookIn, t("dlg_lbl_look_in"))
        dlg.setLabelText(QFileDialog.DialogLabel.FileName, t("dlg_lbl_file_name"))
        dlg.setLabelText(QFileDialog.DialogLabel.FileType, t("dlg_lbl_file_type"))
        dlg.resize(850, 520)

        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            selected = dlg.selectedFiles()
            if selected:
                return selected[0]
        return ""

    @classmethod
    def browse_directory(
        cls,
        start_path: Optional[Path] = None,
        title: str = "Select UI Displays Directory"
    ) -> str:
        """
        Opens a PySide6 directory chooser dialog.
        Returns an empty string if cancelled or closed.
        """
        initial_dir = cls._get_default_browse_dir(start_path)

        print(f"\n  [>] Opening file browser ({title})...")

        gui_opened = False
        try:
            cls._ensure_qapp()
            gui_opened = True
            folder = cls.get_existing_directory(None, caption=title, start_dir=initial_dir)
            if folder:
                p = Path(folder).resolve()
                rel = cls._format_path(p)
                print(f"  {cls.GREEN}✓ Selected directory:{cls.RESET} {cls.CYAN}{cls.BOLD}{rel}{cls.RESET}")
                return rel
            else:
                print(f"  {cls.DIM}(Directory selection cancelled){cls.RESET}")
                return ""
        except Exception:
            pass

        # If GUI could not open (headless / SSH)
        if not gui_opened:
            return cls._prompt_console_directory(initial_dir, title)

        return ""

    @classmethod
    def browse_file(
        cls,
        start_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
        title: str = "Select a File",
        extension: str = "",
        file_desc: str = "Files",
        restrict_to_base: bool = False
    ) -> str:
        """
        Opens a PySide6 file chooser dialog (e.g. .ini or .bob).
        If restrict_to_base=True, enforces that selected file is inside base_dir.
        Returns an empty string if cancelled or closed.
        """
        initial_dir = cls._get_default_browse_dir(start_path)
        ref_base = (base_dir or initial_dir).resolve()

        filter_ext = f"*{extension}" if extension else "*.*"
        filter_str = f"{file_desc} ({filter_ext});;All Files (*.*)"

        while True:
            print(f"\n  [>] Opening file browser ({title})...")
            if restrict_to_base:
                print(f"      {cls.DIM}(File must be located within '{ref_base}'){cls.RESET}")

            gui_opened = False
            chosen_file: Optional[str] = None

            try:
                cls._ensure_qapp()
                gui_opened = True
                f = cls.get_open_file_name(None, caption=title, start_dir=initial_dir, filter=filter_str)
                if f:
                    chosen_file = f
                else:
                    print(f"  {cls.DIM}(File selection cancelled){cls.RESET}")
                    return ""
            except Exception:
                pass

            # Handle selected file
            if chosen_file:
                p = Path(chosen_file).resolve()

                # Check path containment constraint
                if restrict_to_base:
                    is_valid = True
                    try:
                        if not p.is_relative_to(ref_base):
                            is_valid = False
                    except AttributeError:
                        if os.path.relpath(p, ref_base).startswith(".."):
                            is_valid = False

                    if not is_valid:
                        warn_msg = (
                            f"The selected file ('{p.name}') is located outside the UI displays folder.\n\n"
                            f"Required location:\n{ref_base}\n\n"
                            f"Please choose a file inside this folder or its subfolders."
                        )
                        print(f"\n  {cls.RED}⚠ Error: Selected file ({p.name}) is outside UI folder.{cls.RESET}")
                        print(f"  {cls.YELLOW}Please select a file inside: {ref_base}{cls.RESET}\n")
                        cls.show_warning_dialog("Invalid File Location", warn_msg)
                        continue

                try:
                    rel_target = ref_base if restrict_to_base else cls._get_default_browse_dir()
                    result_path = os.path.relpath(p, rel_target)
                    if not restrict_to_base and result_path.startswith(".."):
                        result_path = str(p)
                except ValueError:
                    result_path = str(p)

                print(f"  {cls.GREEN}✓ Selected file:{cls.RESET} {cls.CYAN}{cls.BOLD}{result_path}{cls.RESET}")
                return result_path

            # If GUI could not open (headless / SSH)
            if not gui_opened:
                return cls._prompt_console_file(ref_base, title, extension, restrict_to_base)

            return ""

    @classmethod
    def _prompt_console_directory(cls, initial_dir: Path, title: str) -> str:
        """Prompts for directory path in console with Tab autocompletion."""
        default_val = cls._format_path(initial_dir)
        cls._setup_readline_completer(is_dir_only=True)

        while True:
            sys.stdout.write(f"\n{cls.BOLD}?{cls.RESET} UI displays directory path ([Tab] to autocomplete, Enter to cancel) [{default_val}]: ")
            sys.stdout.flush()
            try:
                ans = input().strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nOperation cancelled.")
                return ""

            if ans.lower() in ["-", "cancel", "none"]:
                return ""

            chosen = ans if ans else default_val
            p = Path(chosen).expanduser().resolve()
            if p.exists() and p.is_dir():
                return cls._format_path(p)
            else:
                print(f"  {cls.RED}⚠ Directory '{chosen}' does not exist. Please enter a valid path.{cls.RESET}")

    @classmethod
    def _prompt_console_file(cls, base_dir: Path, title: str, extension: str, restrict_to_base: bool) -> str:
        """Prompts for file path in console with Tab autocompletion."""
        cls._setup_readline_completer(is_dir_only=False, base_dir=base_dir if restrict_to_base else cls._get_default_browse_dir())

        # Determine default file
        default_file = ""
        if extension == ".ini":
            if Path("resources/linux/settings.ini").exists():
                default_file = "resources/linux/settings.ini"
            elif Path("settings.ini").exists():
                default_file = "settings.ini"
        elif extension == ".bob":
            if (base_dir / "main.bob").exists():
                default_file = "main.bob"
            elif (base_dir / "index.bob").exists():
                default_file = "index.bob"
            elif (base_dir / "accueil.bob").exists():
                default_file = "accueil.bob"
            else:
                bob_files = sorted(list(base_dir.glob(f"**/*{extension}")))
                if bob_files:
                    for b in bob_files:
                        if b.name.lower() in ["main.bob", "accueil.bob", "index.bob"]:
                            try:
                                default_file = os.path.relpath(b, base_dir)
                            except ValueError:
                                default_file = b.name
                            break
                    if not default_file and bob_files:
                        try:
                            default_file = os.path.relpath(bob_files[0], base_dir)
                        except ValueError:
                            default_file = bob_files[0].name

        while True:
            sys.stdout.write(f"\n{cls.BOLD}?{cls.RESET} File path ([Tab] to autocomplete, '-' to cancel) [{default_file}]: ")
            sys.stdout.flush()
            try:
                ans = input().strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nOperation cancelled.")
                return ""

            if ans.lower() in ["-", "cancel", "none"]:
                return ""

            chosen = ans if ans else default_file
            if not chosen:
                return ""

            cand_in_base = (base_dir / chosen).resolve()
            cand_direct = Path(chosen).resolve()

            if cand_in_base.exists():
                target_path = cand_in_base
            elif cand_direct.exists():
                target_path = cand_direct
            else:
                target_path = cand_in_base

            # Verify base containment
            if restrict_to_base:
                try:
                    if not target_path.is_relative_to(base_dir.resolve()):
                        warn_msg = (
                            f"The specified file ('{chosen}') is outside the UI directory.\n\n"
                            f"Required folder: {base_dir}"
                        )
                        print(f"  {cls.RED}⚠ Error: File must be inside directory '{base_dir}'.{cls.RESET}")
                        cls.show_warning_dialog("Invalid File Location", warn_msg)
                        continue
                except AttributeError:
                    if os.path.relpath(target_path, base_dir.resolve()).startswith(".."):
                        print(f"  {cls.RED}⚠ Error: File must be inside directory '{base_dir}'.{cls.RESET}")
                        continue

            if not target_path.exists():
                print(f"  {cls.RED}⚠ File '{chosen}' does not exist. Please choose an existing file.{cls.RESET}")
                continue

            ref = base_dir.resolve() if restrict_to_base else cls._get_default_browse_dir()
            try:
                rel = os.path.relpath(target_path, ref)
                return rel if not rel.startswith("..") else str(target_path)
            except ValueError:
                return str(target_path)

    @classmethod
    def _setup_readline_completer(cls, is_dir_only: bool = True, base_dir: Optional[Path] = None):
        """Enables intelligent Tab auto-completion for readline."""
        try:
            import readline

            def path_completer(text: str, state: int):
                expanded = os.path.expanduser(text)
                if base_dir and not os.path.isabs(expanded):
                    search_pattern = str(base_dir / expanded) + "*"
                else:
                    search_pattern = expanded + "*"

                matches = []
                for p in glob.glob(search_pattern):
                    if is_dir_only and not os.path.isdir(p):
                        continue
                    if base_dir and not os.path.isabs(expanded):
                        try:
                            rel = os.path.relpath(p, base_dir)
                            matches.append(rel + ("/" if os.path.isdir(p) else ""))
                        except ValueError:
                            matches.append(p + ("/" if os.path.isdir(p) else ""))
                    else:
                        matches.append(p + ("/" if os.path.isdir(p) else ""))

                try:
                    return matches[state]
                except IndexError:
                    return None

            readline.set_completer_delims(" \t\n;")
            readline.set_completer(path_completer)
            readline.parse_and_bind("tab: complete")
        except Exception:
            pass

    @classmethod
    def _format_path(cls, p: Path) -> str:
        """Formats path relative to working directory if possible."""
        try:
            rel = os.path.relpath(p, cls._get_default_browse_dir())
            return rel if not rel.startswith("..") else str(p)
        except ValueError:
            return str(p)
