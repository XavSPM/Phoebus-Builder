"""
Preferences configuration (settings.ini) editor and manipulator module.
Provides a studio-grade PySide6 text editor with line numbers, active line highlighting,
syntax highlighting, search navigation with occurrences count, and CLI fallback modes.
"""

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Optional

# Silence verbose Wayland debug warnings
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland*=false;qt.qpa.wayland.textinput=false;qt.qpa.services*=false"


class SettingsEditor:
    """Settings.ini file editor (PySide6 GUI, system text editor, interactive CLI)."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

    @classmethod
    def set_ini_property(cls, filepath: Path, key: str, value: str) -> bool:
        """Updates or adds an active (uncommented) property in a settings.ini file."""
        filepath = Path(filepath)
        if not filepath.exists():
            filepath.write_text(f"{key}={value}\n", encoding="utf-8")
            return True

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        updated = False
        new_line = f"{key}={value}\n"

        for i, line in enumerate(lines):
            clean = line.strip()
            if clean.startswith("#"):
                clean = clean.lstrip("#").strip()
            if clean.startswith(f"{key}=") or clean.startswith(f"{key} =") or clean.startswith(f"{key}\t="):
                lines[i] = new_line
                updated = True
                break

        if not updated:
            lines.append(f"\n{new_line}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return True

    @classmethod
    def open_pyside6_editor(cls, filepath: Path, parent=None) -> bool:
        """
        Opens a standalone studio-grade PySide6 text editor.
        Includes line numbering, search bar with occurrences count, active line highlight,
        and syntax coloring.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            print(f"  [!] File {filepath} does not exist.")
            return False

        try:
            from PySide6.QtWidgets import (
                QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                QPlainTextEdit, QPushButton, QLineEdit, QLabel,
                QMessageBox, QTextEdit, QFrame
            )
            from PySide6.QtGui import (
                QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
                QKeySequence, QShortcut, QTextCursor, QTextDocument, QPainter, QPaintEvent, QResizeEvent
            )
            from PySide6.QtCore import Qt, QRect, QSize
        except ImportError:
            print("  [!] PySide6 is not available, falling back to system editor.")
            return cls.open_in_system_editor(filepath)

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                initial_content = f.read()
        except Exception as e:
            print(f"  [!] Unable to read file {filepath}: {e}")
            return False

        from .i18n import t, get_language
        from .theme import apply_app_theme

        app = QApplication.instance()
        created_app = False
        if app is None:
            app = QApplication([])
            created_app = True
            apply_app_theme(app)

        class IniHighlighter(QSyntaxHighlighter):
            """Syntax highlighter for .ini / properties files."""
            def __init__(self, document):
                super().__init__(document)

                # Comments # or ;
                self.comment_format = QTextCharFormat()
                self.comment_format.setForeground(QColor("#64748b"))
                self.comment_format.setFontItalic(True)

                # Keys
                self.key_format = QTextCharFormat()
                self.key_format.setForeground(QColor("#0284c7"))
                self.key_format.setFontWeight(QFont.Weight.Bold)

                # Equal operator =
                self.operator_format = QTextCharFormat()
                self.operator_format.setForeground(QColor("#dc2626"))

                # Section Headers [Section]
                self.header_format = QTextCharFormat()
                self.header_format.setForeground(QColor("#7c3aed"))
                self.header_format.setFontWeight(QFont.Weight.Bold)

            def highlightBlock(self, text: str):
                trimmed = text.strip()
                if trimmed.startswith("#") or trimmed.startswith(";"):
                    self.setFormat(0, len(text), self.comment_format)
                    return

                if trimmed.startswith("[") and trimmed.endswith("]"):
                    self.setFormat(0, len(text), self.header_format)
                    return

                if "=" in text:
                    eq_idx = text.index("=")
                    self.setFormat(0, eq_idx, self.key_format)
                    self.setFormat(eq_idx, 1, self.operator_format)

        class LineNumberArea(QWidget):
            def __init__(self, editor):
                super().__init__(editor)
                self.code_editor = editor

            def sizeHint(self):
                return QSize(self.code_editor.line_number_area_width(), 0)

            def paintEvent(self, event: QPaintEvent):
                self.code_editor.lineNumberAreaPaintEvent(event)

        class CodeEditor(QPlainTextEdit):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.line_number_area = LineNumberArea(self)
                self.search_selections = []

                self.blockCountChanged.connect(self.update_line_number_area_width)
                self.updateRequest.connect(self.update_line_number_area)
                self.cursorPositionChanged.connect(self.highlight_current_line)

                self.update_line_number_area_width(0)
                self.highlight_current_line()

            def line_number_area_width(self):
                digits = 1
                max_val = max(1, self.blockCount())
                while max_val >= 10:
                    max_val //= 10
                    digits += 1
                space = 16 + self.fontMetrics().horizontalAdvance("9") * digits
                return space

            def update_line_number_area_width(self, _):
                self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

            def update_line_number_area(self, rect: QRect, dy: int):
                if dy:
                    self.line_number_area.scroll(0, dy)
                else:
                    self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

                if rect.contains(self.viewport().rect()):
                    self.update_line_number_area_width(0)

            def resizeEvent(self, event: QResizeEvent):
                super().resizeEvent(event)
                cr = self.contentsRect()
                self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

            def highlight_current_line(self):
                extra_selections = list(self.search_selections)
                if not self.isReadOnly():
                    selection = QTextEdit.ExtraSelection()
                    line_color = QColor("#f1f5f9")
                    selection.format.setBackground(line_color)
                    selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
                    selection.cursor = self.textCursor()
                    selection.cursor.clearSelection()
                    extra_selections.append(selection)
                self.setExtraSelections(extra_selections)

            def lineNumberAreaPaintEvent(self, event: QPaintEvent):
                painter = QPainter(self.line_number_area)
                painter.fillRect(event.rect(), QColor("#f8fafc"))

                block = self.firstVisibleBlock()
                block_number = block.blockNumber()
                top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
                bottom = top + int(self.blockBoundingRect(block).height())

                while block.isValid() and top <= event.rect().bottom():
                    if block.isVisible() and bottom >= event.rect().top():
                        number = str(block_number + 1)
                        painter.setPen(QColor("#94a3b8"))
                        painter.setFont(self.font())
                        painter.drawText(0, top, self.line_number_area.width() - 8, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number)

                    block = block.next()
                    top = bottom
                    bottom = top + int(self.blockBoundingRect(block).height())
                    block_number += 1

                # Right border separator for line numbers
                painter.setPen(QColor("#e2e8f0"))
                painter.drawLine(self.line_number_area.width() - 1, event.rect().top(), self.line_number_area.width() - 1, event.rect().bottom())

        class EditorWindow(QDialog):
            def __init__(self, path: Path, content: str, parent=None):
                super().__init__(parent)
                self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                self.filepath = path
                self.saved_successfully = False
                self.matches: List[QTextCursor] = []
                self.current_match_idx = -1

                self.setWindowTitle(t("editor_title", filename=self.filepath.name))
                self.resize(980, 680)
                self.setMinimumSize(700, 450)

                # Main layout
                layout = QVBoxLayout(self)
                layout.setContentsMargins(10, 10, 10, 10)
                layout.setSpacing(6)

                toolbar_frame = QWidget(self)
                tb_layout = QHBoxLayout(toolbar_frame)
                tb_layout.setContentsMargins(0, 0, 0, 0)
                tb_layout.setSpacing(6)

                self.btn_save = QPushButton(f"{t('btn_save')} (Ctrl+S)", toolbar_frame)
                self.btn_save.clicked.connect(self.save_file)
                tb_layout.addWidget(self.btn_save)

                self.btn_close = QPushButton(t("btn_close"), toolbar_frame)
                self.btn_close.clicked.connect(self.close)
                tb_layout.addWidget(self.btn_close)

                lbl_sep = QLabel("|", toolbar_frame)
                tb_layout.addWidget(lbl_sep)

                lbl_search = QLabel(t("editor_search_label"), toolbar_frame)
                tb_layout.addWidget(lbl_search)

                self.search_edit = QLineEdit(toolbar_frame)
                self.search_edit.setPlaceholderText("Ctrl+F")
                self.search_edit.setFixedWidth(200)
                self.search_edit.textChanged.connect(self.on_search_text_changed)
                self.search_edit.returnPressed.connect(lambda: self.find_next(reverse=False))
                tb_layout.addWidget(self.search_edit)

                self.btn_prev = QPushButton(t("editor_btn_find_prev"), toolbar_frame)
                self.btn_prev.setToolTip("Shift+F3")
                self.btn_prev.clicked.connect(lambda: self.find_next(reverse=True))
                tb_layout.addWidget(self.btn_prev)

                self.btn_next = QPushButton(t("editor_btn_find_next"), toolbar_frame)
                self.btn_next.setToolTip("F3 / Entrée")
                self.btn_next.clicked.connect(lambda: self.find_next(reverse=False))
                tb_layout.addWidget(self.btn_next)

                self.lbl_count = QLabel("", toolbar_frame)
                tb_layout.addWidget(self.lbl_count)

                tb_layout.addStretch()
                layout.addWidget(toolbar_frame)

                self.editor = CodeEditor(self)
                self.editor.search_selections = []
                mono_font = QFont("Monospace", 10)
                mono_font.setStyleHint(QFont.StyleHint.Monospace)
                self.editor.setFont(mono_font)
                self.editor.setPlainText(content)
                self.highlighter = IniHighlighter(self.editor.document())
                self.editor.textChanged.connect(self.on_text_modified)
                layout.addWidget(self.editor, 1)

                sb_frame = QWidget(self)
                sb_layout = QHBoxLayout(sb_frame)
                sb_layout.setContentsMargins(4, 2, 4, 2)

                self.lbl_file = QLabel(str(self.filepath), sb_frame)
                self.lbl_file.setStyleSheet("color: #64748b; font-size: 11px;")
                sb_layout.addWidget(self.lbl_file)

                sb_layout.addStretch()

                self.lbl_status = QLabel(t("status_ready"), sb_frame)
                self.lbl_status.setStyleSheet("font-size: 11px;")
                sb_layout.addWidget(self.lbl_status)
                layout.addWidget(sb_frame)

                QShortcut(QKeySequence("Ctrl+S"), self, self.save_file)
                QShortcut(QKeySequence("Ctrl+F"), self, self.focus_search)
                QShortcut(QKeySequence("F3"), self, lambda: self.find_next(reverse=False))
                QShortcut(QKeySequence("Shift+F3"), self, lambda: self.find_next(reverse=True))

            def focus_search(self):
                self.search_edit.setFocus()
                self.search_edit.selectAll()

            def on_text_modified(self):
                self.lbl_status.setText("Modifié" if get_language() == "fr" else "Modified")
                self.lbl_status.setStyleSheet("color: #ea580c; font-weight: 700; font-size: 11px;")

            def on_search_text_changed(self, text: str):
                query = text.strip()
                extra_selections = []
                self.matches.clear()
                self.current_match_idx = -1

                if not query:
                    self.lbl_count.setText("")
                    self.editor.search_selections = []
                    self.editor.highlight_current_line()
                    return

                doc = self.editor.document()
                cursor = QTextCursor(doc)

                while True:
                    cursor = doc.find(query, cursor, QTextDocument.FindFlag(0))
                    if cursor.isNull():
                        break
                    self.matches.append(QTextCursor(cursor))
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(cursor)
                    sel.format.setBackground(QColor("#fef08a"))
                    sel.format.setForeground(QColor("#000000"))
                    extra_selections.append(sel)

                if self.matches:
                    self.current_match_idx = 0
                    self.editor.search_selections = extra_selections
                    self.highlight_current_match()
                    self.lbl_count.setText(f"1/{len(self.matches)}")
                else:
                    self.editor.search_selections = []
                    self.editor.highlight_current_line()
                    self.lbl_count.setText("0")

            def highlight_current_match(self):
                if not self.matches or self.current_match_idx < 0:
                    return

                selections = list(self.editor.search_selections)
                cur_cursor = self.matches[self.current_match_idx]
                curr_sel = QTextEdit.ExtraSelection()
                curr_sel.cursor = cur_cursor
                curr_sel.format.setBackground(QColor("#f97316"))
                curr_sel.format.setForeground(QColor("#ffffff"))
                selections.append(curr_sel)

                self.editor.setExtraSelections(selections)
                self.editor.setTextCursor(cur_cursor)
                self.editor.ensureCursorVisible()

            def find_next(self, reverse: bool = False):
                if not self.matches:
                    return

                if reverse:
                    self.current_match_idx = (self.current_match_idx - 1) % len(self.matches)
                else:
                    self.current_match_idx = (self.current_match_idx + 1) % len(self.matches)

                self.highlight_current_match()
                self.lbl_count.setText(f"{self.current_match_idx + 1}/{len(self.matches)}")

            def save_file(self):
                try:
                    text = self.editor.toPlainText()
                    with open(self.filepath, "w", encoding="utf-8") as f:
                        f.write(text)
                    self.saved_successfully = True
                    self.editor.document().setModified(False)
                    self.lbl_status.setText(t("editor_saved_status"))
                    self.lbl_status.setStyleSheet("color: #16a34a; font-weight: 700; font-size: 11px;")
                    return True
                except Exception as e:
                    box = QMessageBox(QMessageBox.Icon.Critical, t("dlg_build_error_title"), t("editor_save_err", err=str(e)), QMessageBox.StandardButton.NoButton, self)
                    btn = box.addButton(t("btn_close"), QMessageBox.ButtonRole.AcceptRole)
                    btn.setMinimumWidth(85)
                    box.setDefaultButton(btn)
                    box.exec()
                    return False

            def _prompt_save_before_close(self) -> bool:
                """
                Checks if document has unsaved modifications.
                Returns True if window can proceed to close, False if user cancelled closing.
                """
                if not self.editor.document().isModified():
                    return True

                box = QMessageBox(
                    QMessageBox.Icon.Question,
                    t("editor_close_title"),
                    t("editor_close_msg", filename=self.filepath.name),
                    QMessageBox.StandardButton.NoButton,
                    self
                )
                btn_save = box.addButton(t("btn_save"), QMessageBox.ButtonRole.AcceptRole)
                btn_discard = box.addButton(t("btn_discard"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = box.addButton(t("btn_cancel"), QMessageBox.ButtonRole.RejectRole)

                btn_save.setMinimumWidth(85)
                btn_discard.setMinimumWidth(110)
                btn_cancel.setMinimumWidth(85)
                box.setDefaultButton(btn_save)

                box.exec()
                clicked = box.clickedButton()

                if clicked == btn_save:
                    return self.save_file()
                elif clicked == btn_discard:
                    self.editor.document().setModified(False)
                    return True
                else:  # Cancel or window closed
                    return False

            def reject(self):
                if self._prompt_save_before_close():
                    self.editor.document().setModified(False)
                    super().reject()

            def closeEvent(self, event):
                if self._prompt_save_before_close():
                    self.editor.document().setModified(False)
                    event.accept()
                else:
                    event.ignore()

        window = EditorWindow(filepath, initial_content, parent)
        try:
            if created_app:
                window.show()
                app.exec()
            else:
                window.exec()
        finally:
            saved = window.saved_successfully
            try:
                window.setParent(None)
                window.deleteLater()
            except Exception:
                pass

        if saved:
            print(f"  {cls.GREEN}✓ Modifications saved successfully in {filepath.name}.{cls.RESET}")
            return True
        else:
            print(f"  {cls.DIM}(No modifications saved in {filepath.name}){cls.RESET}")
            return False

    @classmethod
    def open_gui_editor(cls, filepath: Path, parent=None) -> bool:
        """Alias to open graphical PySide6 editor."""
        return cls.open_pyside6_editor(filepath, parent=parent)

    @classmethod
    def open_tkinter_editor(cls, filepath: Path) -> bool:
        """Backward-compatibility alias pointing to PySide6 editor."""
        return cls.open_pyside6_editor(filepath)

    @classmethod
    def open_in_system_editor(cls, filepath: Path) -> bool:
        """Opens the file in the default system text editor (nano, vi, gedit, notepad)."""
        filepath = Path(filepath)
        if not filepath.exists():
            print(f"  [!] File {filepath} does not exist.")
            return False

        is_windows = platform.system().lower() == "windows"
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

        if not editor:
            if is_windows:
                editor = "notepad.exe"
            else:
                for candidate in ["gedit", "kate", "nano", "micro", "vi", "vim"]:
                    if shutil.which(candidate):
                        editor = candidate
                        break
                if not editor:
                    editor = "nano"

        print(f"  [>] Opening {filepath.name} with '{editor}'...")
        try:
            subprocess.run([editor, str(filepath)], check=True)
            print(f"  [OK] Saved modifications to {filepath.name}.")
            return True
        except Exception as e:
            print(f"  [!] Failed to launch editor '{editor}': {e}")
            return False

    @classmethod
    def interactive_property_editor(cls, filepath: Path) -> None:
        """Interactive CLI assistant to search and edit properties in settings.ini."""
        filepath = Path(filepath)
        if not filepath.exists():
            print(f"  [!] File {filepath} does not exist.")
            return

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        print("\n--- INTERACTIVE PROPERTY EDITOR ---")
        print("Type a keyword to search for a property (e.g. 'alarm', 'server', 'dir', 'pv', 'font').")
        print("Type 'q' or 'quit' to exit property editor.\n")

        while True:
            try:
                query = input("Search property (or 'q' to quit): ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not query or query.lower() in ["q", "quit", "exit"]:
                break

            matches: List[Tuple[int, str]] = []
            for idx, line in enumerate(lines):
                line_clean = line.strip()
                if "=" in line_clean and query.lower() in line_clean.lower():
                    matches.append((idx, line_clean))

            if not matches:
                print(f"  No properties found matching '{query}'. Try another keyword.")
                continue

            print(f"\nMatching properties ({len(matches)}):")
            display_limit = min(15, len(matches))
            for i in range(display_limit):
                line_idx, text = matches[i]
                is_commented = text.startswith("#")
                status = " (commented/default)" if is_commented else " [ACTIVE]"
                print(f"  {i + 1}) Line {line_idx + 1}: {text}{status}")

            if len(matches) > display_limit:
                print(f"  ... and {len(matches) - display_limit} other matches.")

            print("\nEnter item number (1-{0}) to edit, or press Enter for a new search:".format(display_limit))
            try:
                choice = input("Choice: ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not choice or not choice.isdigit():
                continue

            chosen_idx = int(choice) - 1
            if not (0 <= chosen_idx < display_limit):
                print("Invalid choice.")
                continue

            target_line_idx, target_line_text = matches[chosen_idx]
            print(f"\nSelected property: {target_line_text}")

            clean_prop = target_line_text.lstrip("#").strip()
            key_part, current_val = clean_prop.split("=", 1) if "=" in clean_prop else (clean_prop, "")
            key_part = key_part.strip()
            current_val = current_val.strip()

            print(f"Key: {key_part}")
            print(f"Current value: {current_val if current_val else '(empty)'}")

            try:
                new_val = input("New value (leave empty to keep, '-' to clear): ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not new_val:
                print("No change.")
                continue

            if new_val == "-":
                new_val = ""

            new_line_content = f"{key_part}={new_val}\n"
            lines[target_line_idx] = new_line_content

            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f"  ✓ Property updated: {key_part}={new_val}\n")

        print("Finished editing properties.")
