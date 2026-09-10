import struct
from pathlib import Path
from typing import Optional, Tuple, Union, Sequence
from .i18n import t


class ImageValidator:
    """Image validation and resizing utility (logo and splash screen)."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

    @classmethod
    def get_image_dimensions(cls, filepath: Path | str) -> Optional[Tuple[int, int]]:
        """Returns image dimensions (width, height) in pixels. For multi-resolution files (e.g. .ico), returns the maximum resolution."""
        path = Path(filepath)
        if not path.exists():
            return None

        # Binary check for ICO files (finds maximum resolution)
        if path.suffix.lower() == ".ico":
            try:
                with open(path, "rb") as f:
                    header = f.read(6)
                    if len(header) >= 6:
                        reserved, ico_type, count = struct.unpack("<HHH", header)
                        if reserved == 0 and ico_type == 1 and count > 0:
                            max_w, max_h = 0, 0
                            for _ in range(count):
                                entry = f.read(16)
                                if len(entry) < 16:
                                    break
                                w = 256 if entry[0] == 0 else entry[0]
                                h = 256 if entry[1] == 0 else entry[1]
                                if w > max_w:
                                    max_w, max_h = w, h
                            if max_w > 0:
                                return (max_w, max_h)
            except Exception:
                pass

        # Read via PySide6
        try:
            from PySide6.QtGui import QImageReader
            reader = QImageReader(str(path))
            count = reader.imageCount()
            if count > 1:
                max_w, max_h = 0, 0
                for i in range(count):
                    reader.jumpToImage(i)
                    sz = reader.size()
                    if sz.isValid() and sz.width() > max_w:
                        max_w, max_h = sz.width(), sz.height()
                if max_w > 0:
                    return (max_w, max_h)
            size = reader.size()
            if size.isValid() and size.width() > 0 and size.height() > 0:
                return (size.width(), size.height())
        except Exception:
            pass

        # Binary fallback for PNG files
        try:
            with open(path, "rb") as f:
                header = f.read(32)
                if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
                    w, h = struct.unpack(">II", header[16:24])
                    return (w, h)
        except Exception:
            pass

        return None

    @classmethod
    def convert_to_ico(
        cls,
        src_path: Path | str,
        dest_path: Path | str,
        sizes: Tuple[int, ...] = (256, 128, 96, 64, 48, 32, 24, 16)
    ) -> bool:
        """Converts an image (PNG, JPG, BMP, or existing ICO) into a standard multi-resolution Windows .ico file."""
        src = Path(src_path)
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            return False

        # If already ICO with full multi-resolution set (>=6 sizes), keep as is
        if src.suffix.lower() == ".ico":
            try:
                from PySide6.QtGui import QImageReader
                r = QImageReader(str(src))
                if r.imageCount() >= 6:
                    if src.resolve() != dest.resolve():
                        import shutil
                        shutil.copy2(src, dest)
                    return True
            except Exception:
                pass

        # Try Pillow if installed
        try:
            from PIL import Image
            img = Image.open(src)
            img.save(dest, format="ICO", sizes=[(s, s) for s in sizes])
            return True
        except Exception:
            pass

        # Use PySide6 QImage + multi-resolution PNG in ICO format
        try:
            from PySide6.QtGui import QImage
            from PySide6.QtCore import QBuffer, QIODevice, Qt

            qimg = QImage(str(src))
            if not qimg.isNull():
                images_png = []
                for s in sizes:
                    scaled = qimg.scaled(
                        s, s,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.WriteOnly)
                    scaled.save(buf, "PNG")
                    images_png.append((s, bytes(buf.data())))

                num_images = len(images_png)
                header = struct.pack("<HHH", 0, 1, num_images)
                entries = []
                offset = 6 + 16 * num_images
                data_blobs = []
                for s, data in images_png:
                    w_b = 0 if s == 256 else s
                    h_b = 0 if s == 256 else s
                    size_data = len(data)
                    entry = struct.pack("<BBBBHHII", w_b, h_b, 0, 0, 1, 32, size_data, offset)
                    entries.append(entry)
                    data_blobs.append(data)
                    offset += size_data

                ico_bytes = header + b"".join(entries) + b"".join(data_blobs)
                dest.write_bytes(ico_bytes)
                return True
        except Exception:
            pass

        # Fallback: QImage direct save
        try:
            from PySide6.QtGui import QImage
            qimg = QImage(str(src))
            if not qimg.isNull():
                return qimg.save(str(dest), "ICO")
        except Exception:
            pass

        return False

    @classmethod
    def generate_site_logo(
        cls,
        src_path: Path | str,
        dest_path: Path | str,
        target_size: Tuple[int, int] = (64, 64)
    ) -> bool:
        """Generates the 64x64 version of the logo for site_logo.png."""
        src = Path(src_path)
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            return False

        try:
            from PySide6.QtGui import QImage
            from PySide6.QtCore import Qt
            qimg = QImage(str(src))
            if not qimg.isNull():
                scaled = qimg.scaled(
                    target_size[0], target_size[1],
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                return scaled.save(str(dest), "PNG")
        except Exception:
            pass

        try:
            import shutil
            shutil.copy2(src, dest)
            return True
        except Exception:
            return False

    @classmethod
    def validate_image(
        cls,
        image_path: Path | str,
        expected_size: Optional[Tuple[int, int]] = None,
        image_type_label: str = "Logo",
        expected_format: Optional[Union[str, Sequence[str]]] = None
    ) -> bool:
        """Validates image format and dimensions."""
        path = Path(image_path)
        if not path.exists():
            print(f"  {cls.RED}✗ File not found: {image_path}{cls.RESET}")
            return False

        current_ext = path.suffix.lower()

        if expected_format:
            if isinstance(expected_format, (list, tuple, set)):
                target_exts = [e.lower() for e in expected_format]
            else:
                target_exts = [expected_format.lower()]

            if current_ext not in target_exts:
                target_str = " / ".join(target_exts)
                print(f"  {cls.RED}✗ Invalid format for {image_type_label}:{cls.RESET}")
                print(f"    • File: {path.name} ({cls.RED}{current_ext}{cls.RESET})")
                print(f"    • Required: {cls.GREEN}{target_str}{cls.RESET}")
                cls._show_error_dialog(
                    title=t("dlg_img_invalid_format_title"),
                    message=t(
                        "dlg_img_invalid_format_msg",
                        filename=path.name,
                        current_ext=current_ext,
                        label=image_type_label,
                        req_ext=target_str
                    )
                )
                return False

        dims = cls.get_image_dimensions(path)
        if expected_size is not None:
            expected_w, expected_h = expected_size
            if dims:
                w, h = dims
                if (w, h) != expected_size:
                    print(f"  {cls.RED}✗ Invalid dimensions for {image_type_label}:{cls.RESET}")
                    print(f"    • Current image: {path.name} ({cls.RED}{w}x{h} px{cls.RESET})")
                    print(f"    • Required resolution: {cls.GREEN}{cls.BOLD}{expected_w}x{expected_h} px{cls.RESET}")
                    cls._show_error_dialog(
                        title=t("dlg_img_invalid_dims_title"),
                        message=t(
                            "dlg_img_invalid_dims_msg",
                            filename=path.name,
                            w=w,
                            h=h,
                            label=image_type_label,
                            expected_w=expected_w,
                            expected_h=expected_h
                        )
                    )
                    return False

                print(f"  {cls.GREEN}✓ Valid image ({w}x{h} px, {current_ext}) for {image_type_label}.{cls.RESET}")
                return True
        else:
            if dims:
                w, h = dims
                print(f"  {cls.GREEN}✓ Accepted image ({w}x{h} px, {current_ext}) for {image_type_label}.{cls.RESET}")
            else:
                print(f"  {cls.GREEN}✓ Selected image: {path.name} ({current_ext}){cls.RESET}")
            return True

        return True

    @classmethod
    def _show_error_dialog(cls, title: str, message: str) -> None:
        """Displays an error dialog if the Qt application instance is running."""
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            from .i18n import t
            app = QApplication.instance()
            created_temp_app = False
            if app is None:
                app = QApplication([])
                created_temp_app = True
            msg_box = QMessageBox(QMessageBox.Icon.Critical, title, message, QMessageBox.StandardButton.NoButton)
            btn = msg_box.addButton(t("btn_close"), QMessageBox.ButtonRole.AcceptRole)
            btn.setMinimumWidth(85)
            msg_box.setDefaultButton(btn)
            msg_box.exec()
            if created_temp_app:
                app.quit()
        except Exception:
            pass
