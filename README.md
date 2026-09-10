# Phoebus Builder

[![GitHub Repository](https://img.shields.io/badge/GitHub-XavSPM%2FPhoebus--Builder-blue?logo=github)](https://github.com/XavSPM/Phoebus-Builder)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python)](https://www.python.org/)
[![GUI PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-green?logo=qt)](https://pypi.org/project/PySide6/)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Phoebus Builder** is a comprehensive Python software suite featuring a modern graphical interface (**PySide6 / Qt 6 GUI**) and an interactive command-line wizard (CLI) to configure, customize, build, and generate standalone native installers for **Control System Studio (Phoebus)** on **Linux** (`.deb`, `.rpm`) and **Windows** (`.msi`, `.exe`).

![Phoebus Builder](./doc/phoebus-bulder.png)

---

## Table of Contents

- [Key Features](#key-features)
- [System Prerequisites](#system-prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Workspace & Settings Architecture](#workspace--settings-architecture)
- [Graphical User Interface (GUI)](#graphical-user-interface-gui)
- [Command Line & CI/CD Automation](#command-line--cicd-automation)
- [Automated Testing](#automated-testing)
- [Project Layout](#project-layout)
- [License & Authors](#license--authors)

---

## Key Features

* **PySide6 / Qt 6 GUI & Interactive Console Wizard**: Full 7-tab desktop application with real-time logging and image preview, alongside an interactive terminal wizard and a non-interactive batch mode for continuous integration.
* **Bilingual English / French**: Starts in **English** by default on first launch, with instantaneous switching to **French** via the Settings dialog.
* **Workspace Directory**: Complete isolation of project profiles, downloaded sources, and generated installers.
* **Online or Local Sources (Offline Mode)**:
  * Automatic download from official GitHub Phoebus releases, or direct use of a local source directory or archive (`.zip`, `.tar.gz`).
  * Dynamic discovery of application modules parsed directly from the Phoebus `pom.xml`.
* **Flexible Java JDK Management**:
  * Automated download of **Adoptium Temurin** JDKs (Java 17, 21 LTS, 25).
  * Support for local JDK installations (including `jpackage`) with automatic environment detection (`JAVA_HOME`).
* **Apache Maven Integration**:
  * Automatic detection from system `PATH` or standalone portable download.
  * Support for custom local Maven installations (directory or archive).
* **Comprehensive Customization**:
  * Integrated visual editor and automatic generator for `settings.ini`.
  * Seamless embedding of `.bob` user interface displays and default startup home screen selection (`home_display`).
  * Automatic validation and formatting for application icons (`site_logo.png` / `.ico`) and splash screens (480x300 px).
* **Standalone Native Installers**:
  * **Linux**: Native Debian (`.deb`) and Red Hat / Fedora / Rocky (`.rpm`) packages with full desktop menu integration.
  * **Windows**: Windows Installer (`.msi`) or executable setup (`.exe`) via WiX Toolset.
  * Embedded, stripped-down Java runtime via `jlink` / `jpackage` (no pre-installed Java required on end-user machines).

---

## System Prerequisites

| Tool | Linux (Fedora / RHEL / Rocky) | Linux (Debian / Ubuntu) | Windows (10 / 11) |
|---|---|---|---|
| **Python** | Python 3.9+ (`python3-pip`) | Python 3.9+ (`python3-pip`) | Python 3.9+ |
| **Packaging Tools** | `sudo dnf install rpm-build` | `sudo apt install fakeroot dpkg` | WiX Toolset 3.11 (auto-downloaded) |

---

## Installation

Clone the repository from GitHub:

```bash
git clone https://github.com/XavSPM/Phoebus-Builder.git
cd Phoebus-Builder
```

### Option A: Direct Installation

```bash
pip install .
```

Once installed, the `phoebus-builder` command is directly available in your terminal.

Your operating system may prevent installing packages outside of your system package manager (PEP 668).

If that is the case, you can force the installation:

```bash
pip install --break-system-packages .
```

### Option B: Virtual Environment

```bash
# 1. Create the virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (CMD):
.venv\Scripts\activate.bat

# 3. Install the package in editable development mode
pip install --upgrade pip
pip install -e .
```

---

## Quick Start

Launch the application using one of the following methods:

```bash
# 1. Via the global command line
phoebus-builder

# 2. Via the Python module execution
python3 -m phoebus_builder

# 3. Via the script at the project root
python3 build_phoebus.py

# 4. If installed with Option A, launch via your desktop application menu
```

---

## Workspace & Settings Architecture

Phoebus Builder ensures a clean and clutter-free filesystem:

1. **First-Run Setup Assistant**:
   - On the first launch, the application prompts you to select your **Workspace Directory**.
   - No default folder is enforced: you maintain full control over the location of your project configurations, sources, and build artifacts.

2. **Global User Preferences (`~/.phoebus-builder/.phoebus-builder-app.json`)**:
   - Global application preferences (selected workspace path, interface language, first-run completion flag) are stored in:
     - **Linux**: `/home/<user>/.phoebus-builder/.phoebus-builder-app.json`
     - **Windows**: `C:\Users\<User>\.phoebus-builder\.phoebus-builder-app.json`

3. **Internal Workspace Structure**:
   ```
   <your-workspace>/
   ├── configs/            # Project configuration profiles (e.g. configs/mobilis/)
   │   └── <project_name>/
   │       ├── config.json
   │       ├── settings.ini
   │       ├── logo.png / logo.ico
   │       ├── site_splash.png
   │       └── ui/          # Embedded .bob displays
   ├── sources/            # Phoebus sources and JDK caches
   │   ├── phoebus/
   │   ├── jdk/
   │   └── maven/
   └── output/             # Compiled native installers (.deb, .rpm, .msi, .exe)
   ```

4. **Settings Dialog (⚙ Settings)**:
   - Accessible at any time via the **⚙ Settings** button in the top right corner of the GUI to:
     - Change the workspace directory location (with an option to migrate existing projects).
     - Switch the interface language between **English** and **Français**.

---

## Graphical User Interface (GUI)

The GUI guides the packaging workflow through **7 structured tabs**:

1. **Core Stack**: Choose the official Phoebus version (e.g. `v5.0.5`) or local sources, select the Java Virtual Machine (Adoptium Temurin 17, 21, 25 or local JDK), configure Maven, and select the installer format (`.msi` / `.exe` on Windows).
2. **App Identity**: Application metadata (Name, Version, Description, Vendor, Copyright, Web URL, Maintainer).
3. **Settings & UI**: Visual editor and automatic generation for `settings.ini`, selection of `.bob` display folders, and default home screen selection (`home_display`).
4. **Phoebus Modules**: Visual selection of Phoebus modules with quick presets (*UI Only*, *Standard*, *Custom*) to optimize package size.
5. **Logo**: Preview and validation of the application icon (automatically generates `site_logo.png` 64x64 and `logo.ico`).
6. **Splash Screen**: Preview and crop of the startup splash screen (480x300 px).
7. **Build**: Comprehensive summary of build options, output directory selection, and real-time multithreaded build progress tracking.

---

## Command Line & CI/CD Automation

Phoebus Builder is fully controllable via the command line for headless server environments or CI/CD pipelines:

```bash
# Open the GUI pre-loaded with a specific project
phoebus-builder --config configs/mobilis

# Explicitly specify a workspace directory
phoebus-builder --workspace /path/to/workspace

# Trigger immediate build in non-interactive batch mode (CI/CD)
phoebus-builder --config configs/mobilis -y

# Validate configuration and prerequisites without building (dry-run)
phoebus-builder --config configs/mobilis --dry-run

# Force the interactive step-by-step terminal wizard
phoebus-builder --cli

# Clean temporary build caches
phoebus-builder --clean

# Override configuration options on the fly
phoebus-builder --config configs/mobilis -y --platform windows --win-package-type exe
```

---

## Automated Testing

The project includes an extensive automated unit test suite validating configuration models, system detection, internationalization parity, image conversions, and settings persistence:

```bash
python3 -m unittest discover tests
```

---

## Project Layout

```
Phoebus-Builder/
├── .gitignore
├── LICENSE
├── MANIFEST.in
├── pyproject.toml              # PEP 621 packaging metadata
├── README.md                   # English documentation
├── README_FR.md                # French documentation
├── build_phoebus.py            # Direct entry point script
├── configs/                    # Bundled project profiles
│   └── <project_name_1>/
│   └── <project_name_2>/
├── doc/                        # Documentation & screenshots
│   └── phoebus-bulder.png
├── phoebus_builder/            # Main Python package
│   ├── app_settings.py         # Global preferences persistence
│   ├── assets/                 # Desktop launcher and icons
│   ├── cli.py                  # CLI router and entry points
│   ├── config.py               # BuildConfig model and validation
│   ├── downloader.py           # Download manager for Phoebus, Maven, WiX
│   ├── file_browser.py         # Native file dialog helpers
│   ├── gui.py                  # PySide6 desktop GUI (7 tabs)
│   ├── i18n.py                 # Multi-language translation engine
│   ├── image_utils.py          # Image validator and ICO converter
│   ├── jvm.py                  # Adoptium & local JDK manager
│   ├── modules.py              # Phoebus module discovery and pom.xml parser
│   ├── packager.py             # Maven compilation and jpackage execution
│   ├── resources/              # Packaging templates and scripts
│   ├── settings_editor.py      # Visual editor for settings.ini
│   ├── settings_generator.py   # Automatic settings.ini generator
│   ├── theme.py                # Desktop styling and themes
│   └── wizard.py               # Interactive CLI questionnaire
└── tests/                      # Automated unit test suite
```

---

## License & Authors

* **Author**: Xavier Goiziou (<xavier.goiziou@gmail.com>)
* **Repository**: [https://github.com/XavSPM/Phoebus-Builder](https://github.com/XavSPM/Phoebus-Builder)
* **License**: This project is licensed under the [MIT License](LICENSE).
