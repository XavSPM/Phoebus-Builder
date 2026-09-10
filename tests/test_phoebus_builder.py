"""
Comprehensive Unit Test Suite for Phoebus Builder.
"""

import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from phoebus_builder.config import BuildConfig
from phoebus_builder.i18n import TRANSLATIONS, get_language, set_language, t
from phoebus_builder.image_utils import ImageValidator
from phoebus_builder.jvm import JvmManager
from phoebus_builder.modules import PHOEBUS_MODULES, PhoebusPomManager
from phoebus_builder.packager import PhoebusPackager
from phoebus_builder.settings_editor import SettingsEditor
from phoebus_builder.settings_generator import SettingsGenerator
from phoebus_builder.cli import parse_args
from phoebus_builder.gui import PhoebusBuilderGUI, JvmDownloadWorkerThread, SourcesDownloadWorkerThread


class TestI18n(unittest.TestCase):
    """Tests internationalization dictionary consistency and formatting."""

    def test_translation_key_parity(self):
        fr_keys = set(TRANSLATIONS["fr"].keys())
        en_keys = set(TRANSLATIONS["en"].keys())
        self.assertEqual(fr_keys, en_keys, f"Discrepancies found: FR-only: {fr_keys - en_keys}, EN-only: {en_keys - fr_keys}")

    def test_default_language_is_en(self):
        import phoebus_builder.i18n as i18n
        self.assertEqual(i18n._CURRENT_LANG, "en")

    def test_language_switching(self):
        set_language("fr")
        self.assertEqual(get_language(), "fr")
        self.assertEqual(t("app_title"), "Phoebus Builder")

        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(t("app_title"), "Phoebus Builder")

    def test_variable_interpolation(self):
        set_language("fr")
        rendered = t("editor_title", filename="mon_fichier.ini")
        self.assertIn("mon_fichier.ini", rendered)

    def test_positional_only_key_safety(self):
        # Passing 'key' in kwargs should not fail with TypeError
        set_language("fr")
        res = t("editor_title", key="some_val", filename="test.ini")
        self.assertIn("test.ini", res)

    def test_fallback_behavior(self):
        set_language("fr")
        self.assertEqual(t("non_existent_key_xyz"), "non_existent_key_xyz")

    def test_qtdict_translator_fallback_returns_none(self):
        """Ensures QtDictTranslator returns None for missing keys so Qt keeps default strings (e.g. English context menu)."""
        from phoebus_builder.i18n import QtDictTranslator
        if QtDictTranslator is not None:
            trans_en = QtDictTranslator("en")
            # '&Undo' is not in TRANSLATIONS dictionary
            self.assertIsNone(trans_en.translate("QLineEdit", "&Undo"))
            # Existing key should be translated
            self.assertEqual(trans_en.translate("PhoebusBuilderGUI", "btn_save_project"), "Save")



class TestBuildConfig(unittest.TestCase):
    """Tests configuration creation, serialization, deserialization, and validation."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config(self):
        cfg = BuildConfig(app_name="TestApp", phoebus_branch="v5.0.5")
        self.assertEqual(cfg.app_name, "TestApp")
        self.assertEqual(cfg.app_version, "5.0.5")
        self.assertEqual(len(cfg.enabled_modules), len(PhoebusPomManager.get_all_module_ids()))
        self.assertEqual(cfg.enabled_modules, PhoebusPomManager.get_all_module_ids())
        self.assertEqual(PhoebusPomManager.get_default_enabled_module_ids(), PhoebusPomManager.get_all_module_ids())
        self.assertEqual(cfg.validate(), [])

    def test_validation_errors(self):
        cfg = BuildConfig(app_name="", app_version="", phoebus_branch="", version_java="")
        errors = cfg.validate()
        self.assertTrue(len(errors) >= 4)

    def test_json_roundtrip(self):
        cfg = BuildConfig(
            app_name="CustomControl",
            app_version="2.1.0",
            phoebus_branch="v5.0.2",
            version_java="25",
            linux_menu_group="Science",
            enabled_modules=["core-launcher", "core-pv-ca", "app-display-runtime"]
        )
        json_file = self.temp_dir / "config.json"
        cfg.save_to_json_file(json_file)

        loaded = BuildConfig.from_json_file(json_file)
        self.assertEqual(loaded.app_name, "CustomControl")
        self.assertEqual(loaded.app_version, "2.1.0")
        self.assertEqual(loaded.linux_menu_group, "Science")
        self.assertEqual(loaded.enabled_modules, ["core-launcher", "core-pv-ca", "app-display-runtime"])

    def test_legacy_settings_import_export(self):
        cfg = BuildConfig(
            app_name="LegacyApp",
            app_version="1.0.0",
            phoebus_branch="v5.0.2",
            app_vendor="Acme Corp"
        )
        settings_file = self.temp_dir / "settings_export.ini"
        cfg.save_to_settings_file(settings_file)

        imported = BuildConfig.from_settings_file(settings_file)
        self.assertEqual(imported.app_name, "LegacyApp")
        self.assertEqual(imported.app_version, "1.0.0")
        self.assertEqual(imported.app_vendor, "Acme Corp")

    def test_export_and_import_project_zip(self):
        # 1. Setup sample project folder in temp_dir / "configs" / "demo_proj"
        proj_dir = self.temp_dir / "configs" / "demo_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)

        cfg = BuildConfig(
            app_name="Demo Proj",
            app_version="1.2.3",
            phoebus_branch="v5.0.2",
            custom_settings_ini_path="configs/demo_proj/settings.ini"
        )
        cfg.save_to_json_file(proj_dir / "config.json")
        (proj_dir / "settings.ini").write_text("org.csstudio.display.builder/font=Arial\n", encoding="utf-8")
        ui_dir = proj_dir / "ui"
        ui_dir.mkdir(parents=True, exist_ok=True)
        (ui_dir / "main.bob").write_text("<display></display>", encoding="utf-8")

        # 2. Export to zip
        dest_zip = self.temp_dir / "exported_demo.zip"
        res_zip = BuildConfig.export_project_to_zip("demo_proj", dest_zip, base_dir=self.temp_dir)
        self.assertTrue(res_zip.exists())
        self.assertTrue(res_zip.stat().st_size > 0)

        # 3. Import from zip to new project
        imported_name, imported_dir = BuildConfig.import_project_from_zip(
            dest_zip,
            target_name="imported_demo",
            base_dir=self.temp_dir
        )
        self.assertEqual(imported_name, "imported_demo")
        self.assertTrue(imported_dir.exists())
        self.assertTrue((imported_dir / "config.json").exists())
        self.assertTrue((imported_dir / "settings.ini").exists())
        self.assertTrue((imported_dir / "ui" / "main.bob").exists())

        imported_cfg = BuildConfig.from_json_file(imported_dir / "config.json", base_dir=self.temp_dir)
        self.assertEqual(imported_cfg.app_name, "Demo Proj")
        self.assertEqual(imported_cfg.app_version, "1.2.3")

    def test_import_project_zip_slip_rejection(self):
        import zipfile
        bad_zip = self.temp_dir / "malicious.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("config.json", json.dumps({"app_name": "Slip"}))
            zf.writestr("../../etc/passwd", "root:x:0:0:")

        with self.assertRaises(ValueError) as ctx:
            BuildConfig.import_project_from_zip(bad_zip, target_name="slip_test", base_dir=self.temp_dir)
        self.assertIn("Zip Slip", str(ctx.exception))

    def test_import_project_invalid_zip(self):
        import zipfile
        empty_zip = self.temp_dir / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("unrelated.txt", "hello")

        with self.assertRaises(ValueError) as ctx:
            BuildConfig.import_project_from_zip(empty_zip, base_dir=self.temp_dir)
        self.assertIn("config.json", str(ctx.exception))

    def test_duplicate_project(self):
        proj_dir = self.temp_dir / "configs" / "original_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        cfg = BuildConfig(app_name="Original", app_version="1.0.0")
        cfg.save_to_json_file(proj_dir / "config.json")
        (proj_dir / "settings.ini").write_text("key=value\n", encoding="utf-8")

        dup_dir = BuildConfig.duplicate_project("original_proj", "cloned_proj", base_dir=self.temp_dir)
        self.assertTrue(dup_dir.exists())
        self.assertTrue((dup_dir / "config.json").exists())
        self.assertTrue((dup_dir / "settings.ini").exists())

        dup_cfg = BuildConfig.from_json_file(dup_dir / "config.json", base_dir=self.temp_dir)
        self.assertEqual(dup_cfg.app_name, "cloned_proj")


class TestSettingsEditor(unittest.TestCase):
    """Tests INI property updating, inserting, and uncommenting."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_ini_property_existing_commented(self):
        ini_file = self.temp_dir / "settings.ini"
        ini_file.write_text("# org.phoebus.ui/default_window_title=DefaultTitle\n", encoding="utf-8")

        SettingsEditor.set_ini_property(ini_file, "org.phoebus.ui/default_window_title", "My New Title")
        content = ini_file.read_text(encoding="utf-8")
        self.assertIn("org.phoebus.ui/default_window_title=My New Title\n", content)
        self.assertNotIn("# org.phoebus.ui/default_window_title", content)

    def test_set_ini_property_new(self):
        ini_file = self.temp_dir / "settings.ini"
        ini_file.write_text("existing.prop=123\n", encoding="utf-8")

        SettingsEditor.set_ini_property(ini_file, "new.prop", "abc")
        content = ini_file.read_text(encoding="utf-8")
        self.assertIn("new.prop=abc\n", content)
        self.assertIn("existing.prop=123\n", content)


class TestSettingsGenerator(unittest.TestCase):
    """Tests scanning *preferences.properties and generating template."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_settings(self):
        mock_src = self.temp_dir / "app" / "module" / "src" / "main" / "resources"
        mock_src.mkdir(parents=True, exist_ok=True)
        prop_file = mock_src / "test_preferences.properties"
        prop_file.write_text(
            "# Package org.phoebus.test\n"
            "# ------------------------\n"
            "# Property description\n"
            "prop_key=default_val\n",
            encoding="utf-8"
        )

        out_template = self.temp_dir / "template.ini"
        count = SettingsGenerator.extract_settings_from_properties(out_template, self.temp_dir)
        self.assertEqual(count, 1)
        content = out_template.read_text(encoding="utf-8")
        self.assertIn("org.phoebus.test/prop_key=default_val", content)

    def test_generate_from_sources_in_sources_dir(self):
        mock_src = self.temp_dir / "sources" / "phoebus" / "phoebus-5.0.2"
        res_dir = mock_src / "app" / "module" / "src" / "main" / "resources"
        res_dir.mkdir(parents=True, exist_ok=True)
        (res_dir / "test_preferences.properties").write_text(
            "# Package org.phoebus.test\nkey1=val1\n",
            encoding="utf-8"
        )
        res_path = SettingsGenerator.generate_from_sources(mock_src)
        self.assertEqual(res_path, mock_src / "settings_template.ini")
        self.assertTrue(res_path.exists())

        cfg = BuildConfig(phoebus_branch="v5.0.2")
        found = cfg.get_settings_template_path(self.temp_dir)
        self.assertEqual(found, res_path)


class TestPhoebusPomManager(unittest.TestCase):
    """Tests Maven POM XML manipulation and module filtering."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_filter_product_pom(self):
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <dependencies>
    <dependency>
      <groupId>org.phoebus</groupId>
      <artifactId>core-launcher</artifactId>
      <version>5.0.2</version>
    </dependency>
    <dependency>
      <groupId>org.phoebus</groupId>
      <artifactId>core-pv-ca</artifactId>
      <version>5.0.2</version>
    </dependency>
    <dependency>
      <groupId>org.phoebus</groupId>
      <artifactId>core-pv-mqtt</artifactId>
      <version>5.0.2</version>
    </dependency>
    <dependency>
      <groupId>org.phoebus</groupId>
      <artifactId>unmanaged-thirdparty</artifactId>
      <version>1.0</version>
    </dependency>
  </dependencies>
</project>"""
        pom_file = self.temp_dir / "pom.xml"
        pom_file.write_text(pom_content, encoding="utf-8")

        # Keep core-pv-ca, disable core-pv-mqtt
        enabled = {"core-launcher", "core-pv-ca"}
        PhoebusPomManager.filter_product_pom(pom_file, enabled)

        tree = ET.parse(pom_file)
        root = tree.getroot()
        ns = {"mvn": "http://maven.apache.org/POM/4.0.0"}
        deps = root.findall(".//mvn:dependency", ns) or root.findall(".//dependency")
        artifact_ids = []
        for d in deps:
            art = d.find("mvn:artifactId", ns) if "mvn" in ns else d.find("artifactId")
            if art is None:
                art = d.find("artifactId")
            if art is not None and art.text:
                artifact_ids.append(art.text.strip())

        self.assertIn("core-launcher", artifact_ids)  # Mandatory preserved
        self.assertIn("core-pv-ca", artifact_ids)     # Kept
        self.assertNotIn("core-pv-mqtt", artifact_ids) # Removed
        self.assertIn("unmanaged-thirdparty", artifact_ids) # Unmanaged preserved

    def test_dependency_resolution(self):
        # app-databrowser depends on app-rtplot
        resolved = PhoebusPomManager.resolve_dependencies(["app-databrowser"])
        self.assertIn("app-databrowser", resolved)
        self.assertIn("app-rtplot", resolved)
        self.assertIn("core-launcher", resolved)  # Core modules always included

        # app-alarm-logging-ui depends on app-alarm-ui and app-alarm-datasouce
        resolved_alarm = PhoebusPomManager.resolve_dependencies(["app-alarm-logging-ui"])
        self.assertIn("app-alarm-ui", resolved_alarm)
        self.assertIn("app-alarm-datasouce", resolved_alarm)

        # app-display-waterfallplot depends on app-display-runtime and app-databrowser (which pulls app-rtplot)
        resolved_waterfall = PhoebusPomManager.resolve_dependencies(["app-display-waterfallplot"])
        self.assertIn("app-display-waterfallplot", resolved_waterfall)
        self.assertIn("app-display-runtime", resolved_waterfall)
        self.assertIn("app-databrowser", resolved_waterfall)
        self.assertIn("app-rtplot", resolved_waterfall)

    def test_discover_modules_from_pom(self):
        pom_content = """<project xmlns="http://maven.apache.org/POM/4.0.0">
    <dependencies>
        <dependency><artifactId>core-launcher</artifactId></dependency>
        <dependency><artifactId>core-pv-ca</artifactId></dependency>
        <dependency><artifactId>app-brand-new-feature</artifactId></dependency>
    </dependencies>
</project>"""
        pom_file = self.temp_dir / "pom_discover.xml"
        pom_file.write_text(pom_content, encoding="utf-8")

        discovered = PhoebusPomManager.discover_modules_from_pom(pom_file)
        disc_ids = [m.artifact_id for m in discovered]
        self.assertIn("app-brand-new-feature", disc_ids)
        self.assertIn("core-launcher", disc_ids)
        self.assertIn("core-pv-ca", disc_ids)
        # Verify that catalog modules not present in this pom are masked/filtered out
        self.assertNotIn("app-3d-viewer", disc_ids)
        self.assertNotIn("app-display-waterfallplot", disc_ids)

        new_mod = next(m for m in discovered if m.artifact_id == "app-brand-new-feature")
        self.assertEqual(new_mod.category, "Nouveaux modules détectés")

        # Fallback when pom is None or non-existent
        all_mods = PhoebusPomManager.discover_modules_from_pom(None)
        self.assertEqual(len(all_mods), len(PHOEBUS_MODULES))

        non_existent_pom = self.temp_dir / "does_not_exist.xml"
        self.assertEqual(len(PhoebusPomManager.discover_modules_from_pom(non_existent_pom)), len(PHOEBUS_MODULES))

        # Empty 0-byte file should also safely fall back
        empty_pom = self.temp_dir / "empty_pom.xml"
        empty_pom.write_text("", encoding="utf-8")
        self.assertEqual(len(PhoebusPomManager.discover_modules_from_pom(empty_pom)), len(PHOEBUS_MODULES))

    def test_gui_find_active_product_pom_strict_version(self):
        # Create a mock source dir for v5.0.5
        v505_dir = self.temp_dir / "sources" / "phoebus" / "phoebus-5.0.5"
        (v505_dir / "phoebus-product").mkdir(parents=True, exist_ok=True)
        (v505_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
        (v505_dir / "phoebus-product" / "pom.xml").write_text("<project/>", encoding="utf-8")

        cfg = BuildConfig(phoebus_branch="v5.0.5")
        from phoebus_builder.gui import PhoebusBuilderGUI
        # Subclass or mock base_dir
        gui_dummy = type("DummyGUI", (), {
            "base_dir": self.temp_dir,
            "config": cfg,
            "_find_active_product_pom": PhoebusBuilderGUI._find_active_product_pom
        })()

        # Should match v5.0.5
        self.assertIsNotNone(gui_dummy._find_active_product_pom())

        # Should NOT match v5.0.2 because only 5.0.5 is present
        gui_dummy.config.phoebus_branch = "v5.0.2"
        self.assertIsNone(gui_dummy._find_active_product_pom())


class TestPhoebusPackager(unittest.TestCase):
    """Tests Linux resource preparation, logging, and cache cleanup."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.resources_dir = self.temp_dir / "resources" / "linux"
        self.resources_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prepare_linux_resources_with_template(self):
        template = self.resources_dir / "template.desktop"
        template.write_text(
            "[Desktop Entry]\n"
            "Name={APPLICATION_NAME}\n"
            "Comment={APPLICATION_DESCRIPTION}\n"
            "Exec={EXEC_PATH}\n"
            "Icon={ICON_PATH}\n"
            "Categories={CATEGORIES}\n",
            encoding="utf-8"
        )

        cfg = BuildConfig(
            app_name="MonSuperApp",
            app_description="Contrôle accélérateur",
            linux_menu_group="Physics",
            resources_linux_dir="resources/linux",
            build_dir="build_test"
        )
        packager = PhoebusPackager(cfg, base_dir=self.temp_dir)
        staging_dir = packager._prepare_linux_resources()

        desktop_out = staging_dir / "template.desktop"
        self.assertTrue(desktop_out.exists())
        content = desktop_out.read_text(encoding="utf-8")

        self.assertIn("Name=MonSuperApp", content)
        self.assertIn("Comment=Contrôle accélérateur", content)
        self.assertIn("Exec=/opt/monsuperapp/bin/MonSuperApp", content)
        self.assertIn("Icon=/opt/monsuperapp/lib/MonSuperApp.png", content)
        self.assertIn("Categories=Physics", content)

    def test_customize_app_launcher(self):
        sources = self.temp_dir / "sources"
        pkg_dir = sources / "core" / "launcher" / "src" / "main" / "java" / "org" / "phoebus" / "product"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "Launcher.java").write_text(
            "public class Launcher { void m() { Application.launch(PhoebusApplication.class, args); } }",
            encoding="utf-8"
        )

        cfg = BuildConfig(app_name="Mobilis Monitor")
        packager = PhoebusPackager(cfg, base_dir=self.temp_dir)
        wmclass = packager._customize_app_launcher(sources)

        self.assertEqual(wmclass, "org.phoebus.product.MobilisMonitorApp")
        self.assertTrue((pkg_dir / "MobilisMonitorApp.java").exists())
        launcher_code = (pkg_dir / "Launcher.java").read_text(encoding="utf-8")
        self.assertIn("Application.launch(MobilisMonitorApp.class,", launcher_code)

    def test_clean_build_cache(self):
        build_dir = self.temp_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "test_file.tmp").write_bytes(b"A" * 1024)
        sub_dir = build_dir / "subdir"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "sub_file.tmp").write_bytes(b"B" * 2048)

        # Create configs/ folder to ensure it is preserved
        configs_dir = self.temp_dir / "configs" / "my_project"
        configs_dir.mkdir(parents=True, exist_ok=True)
        (configs_dir / "config.json").write_text('{"app_name": "Test"}', encoding="utf-8")

        self.assertTrue(build_dir.exists())
        freed, count = PhoebusPackager.clean_build_cache(base_dir=self.temp_dir, build_dir_name="build")
        self.assertEqual(freed, 3072)
        self.assertEqual(count, 2)
        self.assertEqual(list(build_dir.iterdir()), [])

        # Verify configs/ is completely untouched
        self.assertTrue((configs_dir / "config.json").exists())

    def test_format_size(self):
        self.assertEqual(PhoebusPackager.format_size(500), "500 B")
        self.assertEqual(PhoebusPackager.format_size(1500), "1.5 KB")
        self.assertEqual(PhoebusPackager.format_size(1024 * 1024 * 50), "50.0 MB")
        self.assertEqual(PhoebusPackager.format_size(1024 * 1024 * 1024 * 2), "2.00 GB")

    def test_file_logging(self):
        cfg = BuildConfig(app_name="LoggingApp", build_dir="build_log_test", output_dir="output")
        packager = PhoebusPackager(cfg, base_dir=self.temp_dir)
        packager.output_dir.mkdir(parents=True, exist_ok=True)

        packager._log_handle = open(packager.log_file, "w", encoding="utf-8")
        packager._log("Starting test logging step")
        packager._log("Second step execution")
        packager._log_handle.close()
        packager._log_handle = None

        self.assertTrue(packager.log_file.exists())
        log_content = packager.log_file.read_text(encoding="utf-8")
        self.assertIn("Starting test logging step", log_content)
        self.assertIn("Second step execution", log_content)


class TestCli(unittest.TestCase):
    """Tests CLI argument parsing."""

    def test_cli_parser(self):
        args = parse_args(["--name", "CLIApp", "--version", "3.0.0", "--dry-run", "--platform", "linux"])
        self.assertEqual(args.name, "CLIApp")
        self.assertEqual(args.version, "3.0.0")
        self.assertTrue(args.dry_run)
        self.assertEqual(args.platform, "linux")

    def test_cli_clean_flag(self):
        args = parse_args(["--clean"])
        self.assertTrue(args.clean_cache)

        args2 = parse_args(["--clean-cache"])
        self.assertTrue(args2.clean_cache)


class TestJvmManager(unittest.TestCase):
    """Tests JDK validation and shared paths."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_shared_jdk_path_resolution(self):
        jvm = JvmManager(base_dir=self.temp_dir, java_version="25 (Adoptium Temurin)", is_windows=False)
        expected_path = self.temp_dir / "sources" / "jdk" / "jdk-25-linux"
        self.assertEqual(jvm.jdk_dir, expected_path)
        self.assertEqual(jvm.java_version, "25")

        jvm_win = JvmManager(base_dir=self.temp_dir, java_version="21", is_windows=True)
        expected_win = self.temp_dir / "sources" / "jdk" / "jdk-21-win"
        self.assertEqual(jvm_win.jdk_dir, expected_win)

    def test_is_jdk_ready(self):
        # Empty dir should fail
        self.assertFalse(JvmManager.is_jdk_ready(self.temp_dir / "empty_jdk", is_windows=False))

        # Create valid mock JDK
        mock_jdk = self.temp_dir / "mock_jdk"
        bin_dir = mock_jdk / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "java").write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "jpackage").write_text("#!/bin/sh\n", encoding="utf-8")

        self.assertTrue(JvmManager.is_jdk_ready(mock_jdk, is_windows=False))
        self.assertFalse(JvmManager.is_jdk_ready(mock_jdk, is_windows=True))

        # Add Windows executables
        (bin_dir / "java.exe").write_text("", encoding="utf-8")
        (bin_dir / "jpackage.exe").write_text("", encoding="utf-8")
        self.assertTrue(JvmManager.is_jdk_ready(mock_jdk, is_windows=True))


from phoebus_builder.downloader import DownloadManager, safe_rmtree
from phoebus_builder.wizard import fetch_recent_phoebus_tags


class TestDownloadManager(unittest.TestCase):
    """Tests DownloadManager, SSL context resolution, archive extraction, and safe_rmtree."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        safe_rmtree(self.temp_dir, ignore_errors=True)

    def test_get_ssl_context(self):
        ctx = DownloadManager.get_ssl_context()
        self.assertIsNotNone(ctx)

    def test_safe_rmtree(self):
        sub_dir = self.temp_dir / "dir_to_remove" / "nested"
        sub_dir.mkdir(parents=True, exist_ok=True)
        file_path = sub_dir / "file.txt"
        file_path.write_text("content", encoding="utf-8")

        self.assertTrue(file_path.exists())
        safe_rmtree(self.temp_dir / "dir_to_remove")
        self.assertFalse((self.temp_dir / "dir_to_remove").exists())

    def test_is_valid_sources_dir(self):
        invalid_dir = self.temp_dir / "invalid_sources"
        invalid_dir.mkdir()
        self.assertFalse(DownloadManager.is_valid_sources_dir(invalid_dir))

        valid_dir = self.temp_dir / "valid_sources"
        (valid_dir / "phoebus-product").mkdir(parents=True)
        (valid_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
        (valid_dir / "phoebus-product" / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.assertTrue(DownloadManager.is_valid_sources_dir(valid_dir))

    def test_extract_zip_archive(self):
        import zipfile
        zip_path = self.temp_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("test_file.txt", "hello zip")

        extract_dest = self.temp_dir / "extracted_zip"
        DownloadManager.extract_archive(zip_path, extract_dest)
        self.assertTrue((extract_dest / "test_file.txt").exists())
        self.assertEqual((extract_dest / "test_file.txt").read_text(encoding="utf-8"), "hello zip")

    def test_is_maven_ready(self):
        self.assertFalse(DownloadManager.is_maven_ready(self.temp_dir / "empty_mvn"))

        mock_mvn = self.temp_dir / "mock_maven"
        bin_dir = mock_mvn / "bin"
        lib_dir = mock_mvn / "lib"
        bin_dir.mkdir(parents=True, exist_ok=True)
        lib_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "mvn").write_text("", encoding="utf-8")
        (bin_dir / "mvn.cmd").write_text("", encoding="utf-8")
        self.assertTrue(DownloadManager.is_maven_ready(mock_mvn))

    def test_is_wix_ready(self):
        self.assertFalse(DownloadManager.is_wix_ready(self.temp_dir / "empty_wix"))

        mock_wix = self.temp_dir / "mock_wix"
        mock_wix.mkdir(parents=True, exist_ok=True)
        (mock_wix / "candle.exe").write_text("", encoding="utf-8")
        self.assertFalse(DownloadManager.is_wix_ready(mock_wix))

        (mock_wix / "light.exe").write_text("", encoding="utf-8")
        self.assertTrue(DownloadManager.is_wix_ready(mock_wix))


class TestLocalSources(unittest.TestCase):
    """Tests local sources, JDK, and Maven preparation and validation."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_sources_validation(self):
        cfg = BuildConfig(app_name="TestApp", app_version="1.0.0")
        cfg.use_local_sources = True
        cfg.local_sources_path = str(self.temp_dir / "non_existent_folder")

        errors = cfg.validate()
        self.assertTrue(any("sources locales" in e.lower() or "local phoebus" in e.lower() for e in errors))

        # Create valid local folder
        valid_dir = self.temp_dir / "valid_phoebus"
        (valid_dir / "phoebus-product").mkdir(parents=True, exist_ok=True)
        (valid_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
        (valid_dir / "phoebus-product" / "pom.xml").write_text("<project/>", encoding="utf-8")

        cfg.local_sources_path = str(valid_dir)
        errors_valid = cfg.validate()
        self.assertEqual(len(errors_valid), 0)

    def test_prepare_local_sources(self):
        valid_dir = self.temp_dir / "my_phoebus_repo"
        (valid_dir / "phoebus-product").mkdir(parents=True, exist_ok=True)
        (valid_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
        (valid_dir / "phoebus-product" / "pom.xml").write_text("<project/>", encoding="utf-8")

        res_dir = DownloadManager.prepare_local_sources(valid_dir)
        self.assertEqual(res_dir, valid_dir)

    def test_prepare_local_maven(self):
        mock_mvn = self.temp_dir / "my_local_maven"
        bin_dir = mock_mvn / "bin"
        lib_dir = mock_mvn / "lib"
        bin_dir.mkdir(parents=True, exist_ok=True)
        lib_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "mvn").write_text("", encoding="utf-8")
        (bin_dir / "mvn.cmd").write_text("", encoding="utf-8")

        res_mvn = DownloadManager.prepare_local_maven(mock_mvn)
        self.assertEqual(res_mvn, mock_mvn)

    def test_prepare_local_jdk(self):
        mock_jdk = self.temp_dir / "my_local_jdk"
        bin_dir = mock_jdk / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "java").write_text("", encoding="utf-8")
        (bin_dir / "jpackage").write_text("", encoding="utf-8")

        res_jdk = JvmManager.prepare_local_jdk(mock_jdk, is_windows=False)
        self.assertEqual(res_jdk, mock_jdk)

    def test_cli_local_options(self):
        args = parse_args([
            "--name", "TestApp",
            "--local-sources", "/tmp/local_phoebus",
            "--local-jdk", "/tmp/local_jdk",
            "--local-maven", "/tmp/local_maven",
            "--dry-run"
        ])
        self.assertEqual(args.local_sources, "/tmp/local_phoebus")
        self.assertEqual(args.local_jdk, "/tmp/local_jdk")
        self.assertEqual(args.local_maven, "/tmp/local_maven")

    def test_get_workspace_dir(self):
        from phoebus_builder.config import get_workspace_dir
        # Explicit custom dir
        custom = self.temp_dir / "custom_ws"
        self.assertEqual(get_workspace_dir(custom), custom.resolve())

        # Environment variable override
        os.environ["PHOEBUS_BUILDER_WORKSPACE"] = str(custom)
        try:
            self.assertEqual(get_workspace_dir(), custom.resolve())
        finally:
            del os.environ["PHOEBUS_BUILDER_WORKSPACE"]


class TestImageValidator(unittest.TestCase):
    """Tests ImageValidator conversion and validation routines."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_convert_to_ico_and_generate_site_logo(self):
        from PySide6.QtGui import QImage
        # Create sample PNG image
        sample_png = self.temp_dir / "sample.png"
        img = QImage(128, 128, QImage.Format.Format_ARGB32)
        img.fill(0xFF112233)
        img.save(str(sample_png), "PNG")

        # Convert to ICO
        dest_ico = self.temp_dir / "converted.ico"
        success = ImageValidator.convert_to_ico(sample_png, dest_ico)
        self.assertTrue(success)
        self.assertTrue(dest_ico.exists())
        self.assertGreater(dest_ico.stat().st_size, 0)

        # Generate site_logo.png
        site_logo = self.temp_dir / "site_logo.png"
        success_logo = ImageValidator.generate_site_logo(dest_ico, site_logo, target_size=(64, 64))
        self.assertTrue(success_logo)
        self.assertTrue(site_logo.exists())
        dims = ImageValidator.get_image_dimensions(site_logo)
        self.assertEqual(dims, (64, 64))

    def test_validate_image_formats(self):
        from PySide6.QtGui import QImage
        sample_png = self.temp_dir / "test.png"
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        img.fill(0xFF00FF00)
        img.save(str(sample_png), "PNG")

        # Validate with single format
        self.assertTrue(ImageValidator.validate_image(sample_png, expected_format=".png"))
        # Validate with list of formats
        self.assertTrue(ImageValidator.validate_image(sample_png, expected_format=(".ico", ".png")))


class TestAppSettings(unittest.TestCase):
    """Tests global application settings management, first-run status, and workspace persistence."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_settings_file = self.temp_dir / ".phoebus-builder-app.json"
        import phoebus_builder.app_settings as app_settings
        self.orig_get_settings_file = app_settings.get_settings_file_path
        app_settings.get_settings_file_path = lambda: self.mock_settings_file

    def tearDown(self):
        import phoebus_builder.app_settings as app_settings
        app_settings.get_settings_file_path = self.orig_get_settings_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_first_run_cycle(self):
        from phoebus_builder.app_settings import is_first_run, set_first_run_completed
        self.assertTrue(is_first_run())
        set_first_run_completed(True)
        self.assertFalse(is_first_run())
        set_first_run_completed(False)
        self.assertTrue(is_first_run())

    def test_saved_workspace(self):
        from phoebus_builder.app_settings import get_saved_workspace_dir, set_saved_workspace_dir
        self.assertIsNone(get_saved_workspace_dir())
        target_ws = self.temp_dir / "my_custom_workspace"
        set_saved_workspace_dir(target_ws)
        self.assertEqual(get_saved_workspace_dir(), target_ws.resolve())

    def test_saved_language(self):
        from phoebus_builder.app_settings import get_saved_language, set_saved_language
        self.assertIsNone(get_saved_language())
        set_saved_language("en")
        self.assertEqual(get_saved_language(), "en")
        set_saved_language("fr")
        self.assertEqual(get_saved_language(), "fr")

    def test_get_workspace_dir_with_settings(self):
        from phoebus_builder.config import get_workspace_dir
        from phoebus_builder.app_settings import set_saved_workspace_dir
        target_ws = self.temp_dir / "configured_ws"
        set_saved_workspace_dir(target_ws)

        # Clear env var if set
        old_env = os.environ.pop("PHOEBUS_BUILDER_WORKSPACE", None)
        try:
            resolved = get_workspace_dir()
            self.assertEqual(resolved, target_ws.resolve())
        finally:
            if old_env is not None:
                os.environ["PHOEBUS_BUILDER_WORKSPACE"] = old_env

    def test_first_run_dialog_logic(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import FirstRunDialog
        from phoebus_builder.app_settings import is_first_run, get_saved_workspace_dir
        app = QApplication.instance() or QApplication([])
        dlg = FirstRunDialog()
        custom_dir = self.temp_dir / "first_run_target"
        dlg.edit_path.setText(str(custom_dir))
        dlg._on_start()
        self.assertFalse(is_first_run())
        self.assertEqual(get_saved_workspace_dir(), custom_dir.resolve())

    def test_app_settings_dialog_migration_flag(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import AppSettingsDialog
        app = QApplication.instance() or QApplication([])
        # Prepare old workspace with a config
        old_ws = self.temp_dir / "old_ws"
        (old_ws / "configs" / "demo").mkdir(parents=True, exist_ok=True)
        (old_ws / "configs" / "demo" / "config.json").write_text("{}", encoding="utf-8")

        new_ws = self.temp_dir / "new_ws"
        dlg = AppSettingsDialog(old_ws)
        dlg.edit_ws.setText(str(new_ws))
        self.assertFalse(dlg.chk_migrate.isHidden())
        dlg._on_save()
        self.assertEqual(dlg.new_workspace, new_ws.resolve())
        self.assertTrue(dlg.migrate_requested)

    def test_settings_file_location_in_dot_phoebus_builder(self):
        import phoebus_builder.app_settings as app_settings
        # Temporarily restore real get_settings_file_path
        app_settings.get_settings_file_path = self.orig_get_settings_file
        path = app_settings.get_settings_file_path()
        self.assertEqual(path.name, ".phoebus-builder-app.json")
        self.assertEqual(path.parent.name, ".phoebus-builder")
        # Re-mock for other tests
        app_settings.get_settings_file_path = lambda: self.mock_settings_file

    def test_get_workspace_dir_raises_without_configuration(self):
        from phoebus_builder.config import get_workspace_dir
        old_env = os.environ.pop("PHOEBUS_BUILDER_WORKSPACE", None)
        try:
            with self.assertRaises(RuntimeError):
                get_workspace_dir()
        finally:
            if old_env is not None:
                os.environ["PHOEBUS_BUILDER_WORKSPACE"] = old_env

    def test_first_run_dialog_requires_input(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import FirstRunDialog
        from phoebus_builder.app_settings import is_first_run
        app = QApplication.instance() or QApplication([])
        dlg = FirstRunDialog()
        # Initial path should be empty (no default workspace)
        self.assertEqual(dlg.edit_path.text(), "")
        # Clicking start with empty path should be rejected
        dlg._on_start()
        self.assertTrue(is_first_run())
        self.assertNotEqual(dlg.lbl_err.text(), "")

    def test_strictly_workspace_only_for_projects(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import PhoebusBuilderGUI
        app = QApplication.instance() or QApplication([])

        # Create user workspace with only project "user_proj"
        user_ws = self.temp_dir / "user_workspace"
        (user_ws / "configs" / "user_proj").mkdir(parents=True, exist_ok=True)
        (user_ws / "configs" / "user_proj" / "config.json").write_text('{"app_name": "UserApp"}', encoding="utf-8")

        # Instantiate GUI explicitly pointing to user_ws
        gui = PhoebusBuilderGUI(base_dir=user_ws)
        projects = gui._list_projects()

        # It must ONLY contain "user_proj", and never projects from CWD
        self.assertEqual(projects, ["user_proj"])

    def test_app_settings_dialog_language_change(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import AppSettingsDialog
        from phoebus_builder.app_settings import get_saved_language
        from phoebus_builder.i18n import get_language, set_language
        app = QApplication.instance() or QApplication([])

        set_language("en")
        dlg = AppSettingsDialog(self.temp_dir)
        self.assertEqual(dlg.combo_app_lang.currentText(), "English")

        # Change language in dialog (live retranslate)
        dlg.combo_app_lang.setCurrentText("Français")
        self.assertEqual(get_language(), "fr")
        self.assertEqual(dlg.lbl_app_lang.text(), "Langue :")

        # Rejection restores previous language
        dlg.reject()
        self.assertEqual(get_language(), "en")

        # Save persists new language
        dlg2 = AppSettingsDialog(self.temp_dir)
        dlg2.combo_app_lang.setCurrentText("Français")
        dlg2._on_save()
        self.assertEqual(dlg2.new_language, "fr")
        self.assertEqual(get_language(), "fr")
        self.assertEqual(get_saved_language(), "fr")

    def test_first_run_dialog_defaults_to_english(self):
        from PySide6.QtWidgets import QApplication
        from phoebus_builder.gui import FirstRunDialog
        from phoebus_builder.i18n import set_language
        app = QApplication.instance() or QApplication([])
        set_language("en")
        dlg = FirstRunDialog()
        self.assertEqual(dlg.combo_lang.currentText(), "English")


if __name__ == "__main__":
    unittest.main()




