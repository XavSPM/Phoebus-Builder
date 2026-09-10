"""
Internationalization (i18n) module for Phoebus Builder using native PySide6 QTranslator.
Supports French (FR) and English (EN) with dynamic runtime switching via Qt LanguageChange events.
"""

from typing import Dict, Any, Optional

try:
    from PySide6.QtCore import QTranslator, QCoreApplication, QEvent
except ImportError:
    QTranslator = None
    QCoreApplication = None
    QEvent = None

_CURRENT_LANG = "en"
_ACTIVE_TRANSLATOR = None

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "fr": {
        # Header & Title Bar
        "app_title": "Phoebus Builder",
        "app_subtitle": "Créateur & Générateur d'Installateurs Natifs Phoebus",
        "project_bar_label": "Projet actif :",
        "btn_save_project": "Enregistrer",
        "btn_new_project": "Nouveau...",
        "btn_open_project": "Ouvrir...",
        "btn_export_project": "Exporter (.zip)...",
        "btn_import_project": "Importer (.zip)...",
        "btn_project_actions": "Actions",
        "action_export_project": "Exporter le projet (.zip)...",
        "action_import_project": "Importer un projet (.zip)...",
        "action_duplicate_project": "Dupliquer le projet...",
        "action_open_project_folder": "Ouvrir le dossier du projet",
        "action_delete_project": "Supprimer le projet...",
        "status_project_saved": "✓ Enregistré à {time}",
        "btn_app_settings": "⚙ Paramètres",
        "language_label": "Langue :",

        # Tabs
        "tab_tech": "1. Socle Technique",
        "tab_identity": "2. Identité App",
        "tab_settings": "3. Paramètres & IHM",
        "tab_modules": "4. Modules Phoebus",
        "tab_logo": "5. Logo",
        "tab_splash": "6. Splash Screen",
        "tab_build": "7. Construction",

        # Tab 1 : Technical Stack & Versions
        "tech_title": "1. Socle Technique & Versions Phoebus / Java",
        "tech_subtitle": "Sélectionnez la version officielle de Phoebus et la version de machine virtuelle Java (Adoptium Temurin).",
        "sources_mode_label": "Origine des sources Phoebus :",
        "sources_mode_github": "Dépôt distant GitHub (Releases)",
        "sources_mode_local": "Sources locales (dossier ou archive)",
        "local_sources_path_label": "Chemin des sources locales :",
        "local_sources_placeholder": "Dossier racine Phoebus ou archive .zip / .tar.gz",
        "btn_browse_sources_dir": "Dossier...",
        "btn_browse_sources_archive": "Archive...",
        "phoebus_version_label": "Version officielle de Phoebus :",
        "custom_tag_label": "Tag personnalisé GitHub :",
        "custom_tag_placeholder": "Ex: v5.0.2 ou nom de branche",
        "btn_download_sources": "Télécharger les sources Phoebus",
        "sources_status_label": "Sources Phoebus :",
        "sources_status_ready": "✓ Sources présentes ({version})",
        "sources_status_local_ready": "✓ Sources locales prêtes",
        "sources_status_local_invalid": "✗ Sources locales invalides (pom.xml introuvable)",
        "sources_status_missing": "✗ Sources non téléchargées pour cette version",
        "sources_downloading": "Téléchargement des sources ({version})...",
        "sources_download_success": "Sources téléchargées et extraites avec succès pour la version {version}.",
        "sources_download_error": "Erreur lors du téléchargement des sources : {error}",
        "jvm_mode_label": "Origine de la JVM (Java) :",
        "jvm_mode_adoptium": "Télécharger Adoptium Temurin",
        "jvm_mode_local": "JDK local (dossier, archive ou système)",
        "java_version_label": "Version de la JVM (Java) :",
        "local_jdk_path_label": "Chemin du JDK local :",
        "local_jdk_placeholder": "Dossier JDK (avec bin/java et bin/jpackage) ou archive",
        "btn_browse_jdk_dir": "Parcourir JDK...",
        "btn_detect_system_jdk": "Détecter JAVA_HOME",
        "btn_download_jvm": "Télécharger la JVM Adoptium",
        "jvm_status_label": "Machine Virtuelle Java :",
        "jvm_status_ready": "✓ JVM Java {version} prête",
        "jvm_status_local_ready": "✓ JDK local prêt ({version})",
        "jvm_status_local_missing_jpackage": "✗ JDK incomplet (jpackage manquant dans bin/)",
        "jvm_status_local_invalid": "✗ JDK invalide (bin/java introuvable)",
        "jvm_status_missing": "✗ JVM Java {version} non téléchargée",
        "jvm_downloading": "Téléchargement de la JVM Java {version}...",
        "jvm_download_success": "JVM Java {version} téléchargée et configurée avec succès.",
        "jvm_download_error": "Erreur lors du téléchargement de la JVM : {error}",
        "maven_mode_label": "Origine de Maven :",
        "maven_mode_auto": "Automatique (sources/maven ou PATH système)",
        "maven_mode_local": "Maven personnalisé (dossier ou archive)",
        "local_maven_path_label": "Chemin Maven local :",
        "local_maven_placeholder": "Dossier Apache Maven ou archive .zip / .tar.gz",
        "btn_browse_maven_dir": "Parcourir Maven...",
        "maven_status_label": "Outil de compilation Maven :",
        "maven_status_ready_sys": "✓ Maven détecté (système)",
        "maven_status_ready_sources": "✓ Maven prêt (sources/maven)",
        "maven_status_local_ready": "✓ Maven local prêt",
        "maven_status_local_invalid": "✗ Maven local invalide (bin/mvn manquant)",
        "maven_status_missing": "✗ Apache Maven non détecté / non téléchargé",
        "btn_download_maven": "Télécharger Apache Maven",
        "maven_downloading": "Téléchargement d'Apache Maven...",
        "maven_download_success": "Apache Maven téléchargé et configuré avec succès dans sources/maven.",
        "maven_download_error": "Erreur lors du téléchargement de Maven : {error}",
        "wix_status_label": "Outil WiX Toolset (MSI) :",
        "wix_status_ready_sys": "✓ WiX Toolset détecté (système)",
        "wix_status_ready_sources": "✓ WiX Toolset prêt (sources/wix)",
        "wix_status_missing": "✗ WiX Toolset non détecté / non téléchargé",
        "btn_download_wix": "Télécharger WiX Toolset",
        "wix_downloading": "Téléchargement de WiX Toolset...",
        "wix_download_success": "WiX Toolset téléchargé et configuré avec succès dans sources/wix.",
        "wix_download_error": "Erreur lors du téléchargement de WiX Toolset : {error}",
        "build_disabled_no_jvm": "Veuillez d'abord télécharger la JVM Java dans l'onglet '1. Socle Technique' avant de lancer la construction.",
        "dlg_jvm_missing_title": "JVM Java manquante",
        "dlg_jvm_missing_msg": "La machine virtuelle Java {version} doit être téléchargée avant de lancer la construction.\nVoulez-vous la télécharger maintenant ?",
        "pref_folder_label": "Dossier de préférences utilisateur :",
        "pref_folder_hint": "Dossier créé sous $HOME/ pour stocker les préférences utilisateur (mémorisation de position de fenêtres, etc.).",
        "other_version_option": "Autre version spécifique...",
        "windows_package_type_label": "Type d'installateur Windows :",
        "opt_win_msi": "MSI (.msi) — Package Windows Installer standard",
        "opt_win_exe": "EXE (.exe) — Installateur exécutable autonome",
        "force_maven_label": "Forcer la recompilation Maven complète",
        "force_maven_hint": "Désactivé par défaut : réutilise intelligemment les binaires déjà compilés pour un empaquetage instantané.",
        "clean_temp_build_label": "Nettoyer l'espace de build après l'empaquetage",
        "clean_temp_build_hint": "Activé par défaut : supprime le dossier de compilation temporaire et libère l'espace disque une fois le paquet créé.",

        # Tab 2 : Application Identity
        "identity_title": "2. Identité de l'Application",
        "identity_subtitle": "Définissez les métadonnées et informations d'identification de l'installateur.",
        "app_name_label": "Nom de l'application :",
        "app_version_label": "Numéro de version :",
        "app_desc_label": "Description du logiciel :",
        "app_vendor_label": "Vendeur / Organisation :",
        "app_copyright_label": "Mention de Copyright :",
        "app_url_label": "Site web / URL du projet :",
        "deb_maintainer_label": "Mainteneur du paquet (.deb) :",

        # Tab 3 : Settings & UI Displays
        "settings_title": "3. Fichier de Configuration & Vues IHM",
        "settings_subtitle": "Intégrez vos paramètres de configuration EPICS/Phoebus (settings.ini) et vos interfaces (.bob).",
        "settings_ini_label": "Fichier de configuration (settings.ini) :",
        "btn_edit_settings": "Éditer settings.ini...",
        "btn_generate_default_settings": "Générer settings.ini par défaut",
        "ui_dir_label": "Dossier des interfaces (.bob) :",
        "ui_dir_hint": "Dossier racine contenant vos fichiers d'écrans (.bob), synoptiques et images associés.",
        "btn_clear_ui_dir": "Vider le dossier UI",
        "home_display_label": "Vue d'accueil principale (.bob) :",
        "home_display_hint": "Écran d'accueil ouvert automatiquement au lancement de Phoebus (définit org.phoebus.ui/home_display).",
        "home_display_placeholder": "Ex: main.bob, index.bob ou accueil.bob",

        # Tab 4 : Phoebus Modules
        "modules_title": "4. Modules & Extensions Phoebus",
        "modules_subtitle": "Sélectionnez les modules applicatifs à embarquer dans le paquet final.",
        "btn_select_all": "Tout inclure",
        "btn_select_minimal": "Sélection minimale",
        "btn_select_standard": "Sélection standard",
        "btn_deselect_optional": "Tout désélectionner",
        "module_core_badge": "[Requis]",
        "modules_no_sources_placeholder": "Les sources Phoebus pour la version {version} ne sont pas encore téléchargées.\nVeuillez d'abord télécharger les sources pour afficher et configurer les modules disponibles.",
        "btn_download_sources_now": "Télécharger les sources maintenant",
        "build_disabled_no_sources": "Veuillez d'abord télécharger les sources Phoebus dans l'onglet '1. Socle Technique' avant de lancer la construction.",
        "dlg_sources_missing_title": "Sources Phoebus manquantes",
        "dlg_sources_missing_msg": "Les sources Phoebus ({version}) doivent être téléchargées avant de lancer la construction.\nVoulez-vous les télécharger maintenant ?",

        # Tab 5 : Logo
        "logo_title": "5. Logo de l'application",
        "logo_subtitle": "L'icône sera utilisée pour le paquet jpackage et le lanceur système. Format requis : {req_ext}.",
        "logo_path_label": "Chemin du logo :",
        "logo_none_status": "Aucun logo personnalisé (icône par défaut Phoebus).",
        "logo_valid_status": "Logo valide : {name} ({dims}) — vignette Phoebus site_logo.png (64x64) prête",
        "logo_invalid_status": "Format non conforme : {format} (attendu : {req_ext})",

        # Tab 6 : Splash Screen
        "splash_title": "6. Écran de démarrage (Splash Screen)",
        "splash_subtitle": "Image d'arrière-plan affichée lors du chargement initial de Phoebus. Format requis : .png (480x300 px).",
        "splash_path_label": "Chemin du splash :",
        "splash_none_status": "Aucun splash personnalisé (écran par défaut utilisé).",
        "splash_valid_status": "Splash conforme : {name} ({dims} px)",
        "splash_invalid_status": "Dimensions non conformes : {dims} (attendu : 480x300 px)",
        "splash_preview_unavailable": "Aperçu indisponible",
        "splash_default_preview": "Splash par défaut Phoebus",

        # Tab 7 : Build & Summary
        "build_title": "7. Construction & Synthèse",
        "build_subtitle": "Vérifiez les paramètres ci-dessous et lancez la génération du paquet d'installation.",
        "summary_box_title": "Synthèse du projet avant construction",
        "dest_box_title": "Dossier de destination du paquet final",
        "dest_dir_label": "Dossier de destination :",
        "btn_launch_build": "Lancer la construction",
        "btn_building": "Construction en cours...",
        "btn_stop_build": "Arrêter",
        "btn_clean_cache": "Purger le cache",
        "btn_refresh_summary": "Actualiser le résumé",
        "status_ready": "Prêt",
        "status_building": "Compilation et packaging en cours...",
        "status_stopping": "Arrêt en cours...",
        "status_success": "Construction terminée avec succès.",
        "status_error": "Erreur lors de la construction.",
        "status_interrupted": "Construction interrompue.",
        "console_title": "Journal d'exécution :",
        "summary_header": "RÉCAPITULATIF DE LA CONFIGURATION",

        # Common Buttons
        "btn_browse": "Parcourir...",
        "btn_open_folder": "Ouvrir dossier",
        "btn_default": "Rétablir défaut",
        "btn_cancel": "Annuler",
        "btn_close": "Fermer",
        "btn_save": "Enregistrer",
        "btn_prev": "Précédent",
        "btn_next": "Suivant",
        "btn_create": "Créer",
        "btn_ok": "OK",
        "btn_yes": "Oui",
        "btn_no": "Non",
        "btn_discard": "Ne pas enregistrer",

        # Modals & Dialogs
        "dlg_new_project_title": "Nouveau projet Phoebus",
        "dlg_new_project_prompt": "Nom du nouveau projet :",
        "dlg_confirm_title": "Confirmation",
        "dlg_info_title": "Information",
        "dlg_confirm_build": "Lancer la construction de l'installateur natif pour {app_name} (version {version}) ?",
        "dlg_confirm_stop": "Voulez-vous interrompre le processus de compilation en cours ?",
        "dlg_confirm_clear_ui": "Voulez-vous supprimer tous les fichiers du dossier UI du projet :\n\n{path}/*\n\nCette action est irréversible.",
        "dlg_confirm_clean_title": "Purger le cache de compilation",
        "dlg_confirm_clean_msg": "Voulez-vous supprimer les fichiers temporaires dans le dossier de compilation '{path}' ?\n\nEspace estimé à libérer : {size}\n(Vos configurations dans configs/ restent intactes).",
        "dlg_clean_success_title": "Nettoyage terminé",
        "dlg_clean_success_msg": "Le cache de compilation a été purgé avec succès.\n\nEspace libéré : {size}",
        "dlg_clean_empty": "Le dossier de build est déjà vide (aucun fichier temporaire à supprimer).",
        "module_deps_label": "Dépendances requises : {deps}",
        "dlg_build_log_hint": "Journal détaillé de build enregistré dans : {path}",
        "dlg_build_success_title": "Construction réussie",
        "dlg_build_success_msg": "L'installateur natif a été généré avec succès dans le dossier :\n\n{result}\n\nJournal : {log_file}",
        "dlg_build_error_title": "Erreur de construction",
        "dlg_build_error_msg": "La construction a échoué :\n\n{result}\n\nJournal détaillé : {log_file}",
        "dlg_build_cancelled_title": "Construction interrompue",
        "dlg_build_cancelled_msg": "Le processus de compilation a été interrompu par l'utilisateur.",
        "dlg_network_error_title": "Connexion réseau requise",
        "dlg_network_error_msg": "{err}\n\nVeuillez vérifier votre accès réseau et relancer l'application.",

        # Settings & Workspace Dialogs
        "dlg_settings_title": "Paramètres de l'application",
        "lbl_workspace_dir": "Répertoire de travail (Workspace) :",
        "lbl_workspace_hint": "Dossier où sont stockés les configurations de projets, les sources et les artéfacts.",
        "btn_default_workspace": "Emplacement par défaut",
        "chk_migrate_data": "Copier les projets existants vers le nouvel emplacement",
        "dlg_workspace_changed": "Le répertoire de travail a été modifié avec succès :\n\n{path}",
        "dlg_first_run_title": "Bienvenue dans Phoebus Builder",
        "first_run_welcome": "Bienvenue dans Phoebus Builder !\n\nVeuillez choisir l'emplacement de votre répertoire de travail (Workspace) où seront enregistrés vos projets, sources et configurations :",
        "dlg_select_workspace_placeholder": "Cliquez sur Parcourir pour choisir votre répertoire de travail...",
        "dlg_workspace_required": "Veuillez sélectionner un répertoire de travail pour enregistrer vos projets et sources.",
        "btn_start_app": "Commencer",

        # System Prerequisites
        "dlg_prereq_title": "Prérequis système manquants",
        "dlg_prereq_intro": "Des outils indispensables sont manquants sur votre système :",
        "dlg_prereq_mvn_win": "Apache Maven ('mvn.cmd') est introuvable dans le PATH.",
        "dlg_prereq_mvn_linux": "Apache Maven ('mvn') est introuvable. Installez-le avec :\n   • Fedora / RHEL : sudo dnf install maven\n   • Debian / Ubuntu : sudo apt install maven",
        "dlg_prereq_tar": "L'utilitaire 'tar' est manquant.",
        "dlg_prereq_fakeroot": "L'outil 'fakeroot' est manquant. Installez-le avec : sudo apt install fakeroot",
        "dlg_prereq_dpkg": "L'outil 'dpkg-deb' est manquant. Installez-le avec : sudo apt install dpkg",
        "dlg_prereq_rpmbuild": "L'outil 'rpmbuild' est manquant. Installez-le avec : sudo dnf install rpm-build",

        # Configuration Validation
        "dlg_val_err_title": "Erreur de configuration",
        "dlg_val_app_name": "Le nom de l'application (APP_NAME) ne peut pas être vide.",
        "dlg_val_app_version": "La version de l'application (APP_VERSION) ne peut pas être vide.",
        "dlg_val_phoebus_branch": "La version de Phoebus doit être renseignée (ex: v5.0.2).",
        "dlg_val_java_version": "La version Java doit être renseignée (ex: 21 ou 25).",
        "dlg_val_local_sources_missing": "Le chemin des sources locales Phoebus spécifié n'existe pas.",
        "dlg_val_local_sources_invalid": "Le répertoire des sources locales ne contient pas les fichiers pom.xml requis pour Phoebus.",
        "dlg_val_local_jdk_missing": "Le chemin du JDK local spécifié n'existe pas.",
        "dlg_val_local_jdk_invalid": "Le JDK local ne contient pas l'exécutable requis jpackage.",
        "dlg_val_local_maven_missing": "Le chemin de Maven local spécifié n'existe pas.",
        "dlg_val_local_maven_invalid": "Le dossier Maven local ne contient pas l'exécutable bin/mvn.",

        # Files & Projects Management
        "dlg_settings_need_file": "Veuillez d'abord générer ou sélectionner un fichier settings.ini.",
        "dlg_settings_generated_title": "Génération de settings.ini",
        "dlg_settings_generated": "Fichier de configuration généré dans :\n\n{path}",
        "dlg_ui_already_empty": "Le dossier UI est déjà vide :\n\n{path}",
        "dlg_ui_cleared_title": "Dossier UI vidé",
        "dlg_ui_cleared": "Le dossier UI a été vidé avec succès :\n\n{path}",
        "dlg_project_saved_title": "Projet enregistré",
        "dlg_project_saved": "Configuration enregistrée avec succès dans le projet :\n\n{path}",
        "dlg_invalid_project_name": "Nom de projet invalide.",
        "dlg_export_title": "Exporter le projet",
        "dlg_export_filter": "Archive de projet (*.zip)",
        "dlg_export_success": "Projet '{name}' exporté avec succès vers :\n\n{path}",
        "dlg_export_error": "Échec de l'exportation du projet :\n\n{err}",
        "dlg_import_title": "Importer un projet (.zip)",
        "dlg_import_filter": "Archive de projet (*.zip)",
        "dlg_import_prompt": "Nom du projet importé :",
        "dlg_import_overwrite": "Écraser le projet s'il existe déjà",
        "dlg_import_overwrite_confirm": "Le projet '{name}' existe déjà. Cochez la case ci-dessus pour l'écraser.",
        "dlg_import_invalid_zip": "L'archive ZIP sélectionnée n'est pas un projet Phoebus valide (config.json introuvable).",
        "dlg_import_success": "Projet '{name}' importé et activé avec succès !",
        "dlg_import_error": "Échec de l'importation du projet :\n\n{err}",
        "dlg_duplicate_title": "Dupliquer le projet",
        "dlg_duplicate_prompt": "Nom du nouveau projet :",
        "dlg_duplicate_exists": "Un projet nommé '{name}' existe déjà.",
        "dlg_duplicate_error": "Échec de la duplication du projet :\n\n{err}",
        "dlg_delete_title": "Supprimer le projet",
        "dlg_delete_confirm": "Êtes-vous sûr de vouloir supprimer définitivement le projet '{name}' ?\n\nTous les fichiers du projet seront effacés.",
        "dlg_delete_only_project": "Impossible de supprimer le seul projet actif.",
        "dlg_build_busy": "Une compilation est déjà en cours d'exécution.",

        # Image Validation
        "dlg_img_invalid_format_title": "Format d'image non valide",
        "dlg_img_invalid_format_msg": "Le fichier '{filename}' est au format {current_ext}.\n\nPour {label}, le format requis est : {req_ext}.",
        "dlg_img_invalid_dims_title": "Dimensions d'image non valides",
        "dlg_img_invalid_dims_msg": "L'image '{filename}' a pour dimensions : {w}x{h} px.\n\nPour {label}, la résolution requise est : {expected_w}x{expected_h} px.",

        # Settings Editor
        "editor_title": "Éditeur de Préférences — {filename}",
        "editor_save_title": "Enregistrement",
        "editor_save_msg": "Modifications enregistrées dans :\n\n{filename}",
        "editor_save_err": "Échec de l'enregistrement du fichier :\n\n{err}",
        "editor_close_title": "Enregistrer les modifications",
        "editor_close_msg": "Voulez-vous enregistrer les modifications apportées à '{filename}' avant de fermer ?",
        "editor_saved_status": "Enregistré",
        "editor_search_label": "Rechercher :",
        "editor_btn_find_next": "Suivant",
        "editor_btn_find_prev": "Précédent",
        "dlg_btn_select_dir": "Sélectionner ce dossier",
        "dlg_btn_open_file": "Ouvrir",
        "dlg_lbl_look_in": "Dossier :",
        "dlg_lbl_file_name": "Nom :",
        "dlg_lbl_file_type": "Type de fichier :",
    },

    "en": {
        # Header & Title
        "app_title": "Phoebus Builder",
        "app_subtitle": "Custom Phoebus Native Installer Creator & Builder",
        "project_bar_label": "Active Project:",
        "btn_save_project": "Save",
        "btn_new_project": "New...",
        "btn_open_project": "Open...",
        "btn_export_project": "Export (.zip)...",
        "btn_import_project": "Import (.zip)...",
        "btn_project_actions": "Actions",
        "action_export_project": "Export project (.zip)...",
        "action_import_project": "Import project (.zip)...",
        "action_duplicate_project": "Duplicate project...",
        "action_open_project_folder": "Open project folder",
        "action_delete_project": "Delete project...",
        "status_project_saved": "✓ Saved at {time}",
        "btn_app_settings": "⚙ Settings",
        "language_label": "Language:",

        # Tabs
        "tab_tech": "1. Core Stack",
        "tab_identity": "2. App Identity",
        "tab_settings": "3. Settings & UI",
        "tab_modules": "4. Phoebus Modules",
        "tab_logo": "5. Logo",
        "tab_splash": "6. Splash Screen",
        "tab_build": "7. Build & Package",

        # Tab 1 : Core Stack
        "tech_title": "1. Core Stack & Phoebus / Java Versions",
        "tech_subtitle": "Select official Phoebus release and Java virtual machine version (Adoptium Temurin).",
        "sources_mode_label": "Phoebus Sources Origin:",
        "sources_mode_github": "Remote GitHub Repository (Releases)",
        "sources_mode_local": "Local Sources (Directory or Archive)",
        "local_sources_path_label": "Local Sources Path:",
        "local_sources_placeholder": "Phoebus root folder or .zip / .tar.gz archive",
        "btn_browse_sources_dir": "Folder...",
        "btn_browse_sources_archive": "Archive...",
        "phoebus_version_label": "Official Phoebus Release:",
        "custom_tag_label": "Custom GitHub Tag:",
        "custom_tag_placeholder": "Ex: v5.0.2 or branch name",
        "btn_download_sources": "Download Phoebus Sources",
        "sources_status_label": "Phoebus Sources:",
        "sources_status_ready": "✓ Sources ready ({version})",
        "sources_status_local_ready": "✓ Local sources ready",
        "sources_status_local_invalid": "✗ Invalid local sources (pom.xml not found)",
        "sources_status_missing": "✗ Sources not downloaded for this version",
        "sources_downloading": "Downloading sources ({version})...",
        "sources_download_success": "Sources downloaded and extracted successfully for version {version}.",
        "sources_download_error": "Error downloading sources: {error}",
        "jvm_mode_label": "JVM (Java) Origin:",
        "jvm_mode_adoptium": "Download Adoptium Temurin",
        "jvm_mode_local": "Local JDK (Directory, Archive or System)",
        "java_version_label": "JVM Version (Java):",
        "local_jdk_path_label": "Local JDK Path:",
        "local_jdk_placeholder": "JDK directory (with bin/java and bin/jpackage) or archive",
        "btn_browse_jdk_dir": "Browse JDK...",
        "btn_detect_system_jdk": "Detect JAVA_HOME",
        "btn_download_jvm": "Download Adoptium JVM",
        "jvm_status_label": "Java Virtual Machine:",
        "jvm_status_ready": "✓ Java {version} JVM ready",
        "jvm_status_local_ready": "✓ Local JDK ready ({version})",
        "jvm_status_local_missing_jpackage": "✗ Incomplete JDK (jpackage missing in bin/)",
        "jvm_status_local_invalid": "✗ Invalid JDK (bin/java not found)",
        "jvm_status_missing": "✗ Java {version} JVM not downloaded",
        "jvm_downloading": "Downloading Java {version} JVM...",
        "jvm_download_success": "Java {version} JVM downloaded and configured successfully.",
        "jvm_download_error": "Error downloading Java JVM: {error}",
        "maven_mode_label": "Maven Origin:",
        "maven_mode_auto": "Automatic (sources/maven or system PATH)",
        "maven_mode_local": "Custom Maven (Directory or Archive)",
        "local_maven_path_label": "Local Maven Path:",
        "local_maven_placeholder": "Apache Maven directory or .zip / .tar.gz archive",
        "btn_browse_maven_dir": "Browse Maven...",
        "maven_status_label": "Maven Build Tool:",
        "maven_status_ready_sys": "✓ Maven detected (system)",
        "maven_status_ready_sources": "✓ Maven ready (sources/maven)",
        "maven_status_local_ready": "✓ Local Maven ready",
        "maven_status_local_invalid": "✗ Invalid local Maven (bin/mvn missing)",
        "maven_status_missing": "✗ Apache Maven not detected / not downloaded",
        "btn_download_maven": "Download Apache Maven",
        "maven_downloading": "Downloading Apache Maven...",
        "maven_download_success": "Apache Maven downloaded and configured successfully in sources/maven.",
        "maven_download_error": "Error downloading Maven: {error}",
        "wix_status_label": "WiX Toolset (MSI):",
        "wix_status_ready_sys": "✓ WiX Toolset detected (system)",
        "wix_status_ready_sources": "✓ WiX Toolset ready (sources/wix)",
        "wix_status_missing": "✗ WiX Toolset not detected / not downloaded",
        "btn_download_wix": "Download WiX Toolset",
        "wix_downloading": "Downloading WiX Toolset...",
        "wix_download_success": "WiX Toolset downloaded and configured successfully in sources/wix.",
        "wix_download_error": "Error downloading WiX Toolset: {error}",
        "build_disabled_no_jvm": "Please download the Java JVM in '1. Technical Stack' tab before starting the build.",
        "dlg_jvm_missing_title": "Java JVM Missing",
        "dlg_jvm_missing_msg": "Java {version} JVM must be downloaded before starting the build.\nWould you like to download it now?",
        "pref_folder_label": "User Preference Subfolder:",
        "pref_folder_hint": "Folder created under $HOME/ to store user preferences (window positions, history, etc.).",
        "other_version_option": "Other specific version...",
        "windows_package_type_label": "Windows Installer Package Type:",
        "opt_win_msi": "MSI (.msi) — Standard Windows Installer package",
        "opt_win_exe": "EXE (.exe) — Standalone executable installer",
        "force_maven_label": "Force full Maven compilation",
        "force_maven_hint": "Disabled by default: reuses compiled binaries for instant packaging.",
        "clean_temp_build_label": "Clean build workspace after packaging",
        "clean_temp_build_hint": "Enabled by default: automatically deletes temporary compilation folder and frees disk space once package is generated.",

        # Tab 2 : App Identity
        "identity_title": "2. Application Identity",
        "identity_subtitle": "Customize metadata and branding identification for your native installer.",
        "app_name_label": "Application Name:",
        "app_version_label": "Version Number:",
        "app_desc_label": "Software Description:",
        "app_vendor_label": "Vendor / Organization:",
        "app_copyright_label": "Copyright Notice:",
        "app_url_label": "Project Website / URL:",
        "deb_maintainer_label": "Package Maintainer (.deb):",

        # Tab 3 : Settings & UI
        "settings_title": "3. Settings Configuration & UI Displays",
        "settings_subtitle": "Embed your EPICS/Phoebus configuration settings (settings.ini) and UI displays (.bob).",
        "settings_ini_label": "Configuration File (settings.ini):",
        "btn_edit_settings": "Edit settings.ini...",
        "btn_generate_default_settings": "Generate Default settings.ini",
        "ui_dir_label": "UI Displays Directory (.bob):",
        "ui_dir_hint": "Root directory containing your UI display files (.bob), screens, and associated graphics.",
        "btn_clear_ui_dir": "Clear UI Folder",
        "home_display_label": "Main Home Display (.bob):",
        "home_display_hint": "Startup display file automatically opened on launch (configures org.phoebus.ui/home_display).",
        "home_display_placeholder": "E.g. main.bob, index.bob or home.bob",

        # Tab 4 : Phoebus Modules
        "modules_title": "4. Phoebus Modules & Extensions",
        "modules_subtitle": "Select the application modules to include in the final package.",
        "btn_select_all": "Select All",
        "btn_select_minimal": "Minimal Selection",
        "btn_select_standard": "Standard Selection",
        "btn_deselect_optional": "Deselect All",
        "module_core_badge": "[Required]",
        "modules_no_sources_placeholder": "Phoebus sources for version {version} are not downloaded yet.\nPlease download sources first to view and configure available modules.",
        "btn_download_sources_now": "Download sources now",
        "build_disabled_no_sources": "Please download Phoebus sources in '1. Technical Stack' tab before starting the build.",
        "dlg_sources_missing_title": "Phoebus Sources Missing",
        "dlg_sources_missing_msg": "Phoebus sources ({version}) must be downloaded before starting the build.\nWould you like to download them now?",

        # Tab 5 : Logo
        "logo_title": "5. Application Logo",
        "logo_subtitle": "Icon used for jpackage native bundle and system launcher. Required format: {req_ext}.",
        "logo_path_label": "Logo file path:",
        "logo_none_status": "No custom logo (default Phoebus icon used).",
        "logo_valid_status": "Valid logo: {name} ({dims}) — Phoebus site_logo.png (64x64) ready",
        "logo_invalid_status": "Invalid format: {format} (expected: {req_ext})",

        # Tab 6 : Splash Screen
        "splash_title": "6. Startup Splash Screen",
        "splash_subtitle": "Background image displayed during initial Phoebus startup. Required format: .png (480x300 px).",
        "splash_path_label": "Splash file path:",
        "splash_none_status": "No custom splash screen (default Phoebus splash used).",
        "splash_valid_status": "Valid splash screen: {name} ({dims} px)",
        "splash_invalid_status": "Invalid dimensions: {dims} (expected: 480x300 px)",
        "splash_preview_unavailable": "Preview unavailable",
        "splash_default_preview": "Default Phoebus Splash",

        # Tab 7 : Build & Logs
        "build_title": "7. Build & Summary",
        "build_subtitle": "Review the configuration parameters below and launch native package generation.",
        "summary_box_title": "Project Summary Before Build",
        "dest_box_title": "Final Package Output Location",
        "dest_dir_label": "Output Directory:",
        "btn_launch_build": "Launch Build",
        "btn_building": "Building in progress...",
        "btn_stop_build": "Stop Build",
        "btn_clean_cache": "Clean Build Cache",
        "btn_refresh_summary": "Refresh Summary",
        "status_ready": "Ready",
        "status_building": "Building and packaging in progress...",
        "status_stopping": "Stopping...",
        "status_success": "Build completed successfully.",
        "status_error": "Build error occurred.",
        "status_interrupted": "Build cancelled.",
        "console_title": "Execution Log :",
        "summary_header": "CONFIGURATION SUMMARY",

        # Common Buttons
        "btn_browse": "Browse...",
        "btn_open_folder": "Open Folder",
        "btn_default": "Reset Default",
        "btn_cancel": "Cancel",
        "btn_close": "Close",
        "btn_save": "Save",
        "btn_prev": "Previous",
        "btn_next": "Next",
        "btn_create": "Create",
        "btn_ok": "OK",
        "btn_yes": "Yes",
        "btn_no": "No",
        "btn_discard": "Don't Save",

        # Modals & Dialogs
        "dlg_new_project_title": "New Phoebus Project",
        "dlg_new_project_prompt": "New project name:",
        "dlg_confirm_title": "Confirmation",
        "dlg_info_title": "Information",
        "dlg_confirm_build": "Launch native installer construction for {app_name} (version {version})?",
        "dlg_confirm_stop": "Are you sure you want to stop the current build?",
        "dlg_confirm_clear_ui": "Do you really want to delete all files in the project UI folder:\n\n{path}/*\n\nThis action cannot be undone.",
        "dlg_confirm_clean_title": "Clean Build Cache",
        "dlg_confirm_clean_msg": "Do you want to delete temporary build files in '{path}'?\n\nEstimated disk space to free: {size}\n(Your project configurations in configs/ will remain untouched).",
        "dlg_clean_success_title": "Cleanup Complete",
        "dlg_clean_success_msg": "Build cache was successfully purged.\n\nFreed disk space: {size}",
        "dlg_clean_empty": "The build directory is already empty.",
        "module_deps_label": "Required dependencies: {deps}",
        "dlg_build_log_hint": "Detailed build log saved in: {path}",
        "dlg_build_success_title": "Build Successful",
        "dlg_build_success_msg": "Native installer package was successfully created in:\n\n{result}\n\nBuild log: {log_file}",
        "dlg_build_error_title": "Build Error",
        "dlg_build_error_msg": "Build failed with error:\n\n{result}\n\nDetailed log: {log_file}",
        "dlg_build_cancelled_title": "Build Cancelled",
        "dlg_build_cancelled_msg": "The build process was stopped by the user.",
        "dlg_network_error_title": "Network Connection Required",
        "dlg_network_error_msg": "{err}\n\nPlease check your network access and restart the application.",

        # Settings & Workspace Dialogs
        "dlg_settings_title": "Application Settings",
        "lbl_workspace_dir": "Workspace Directory:",
        "lbl_workspace_hint": "Directory where project configurations, sources, and artifacts are stored.",
        "btn_default_workspace": "Default Location",
        "chk_migrate_data": "Copy existing projects to new location",
        "dlg_workspace_changed": "Workspace directory successfully changed:\n\n{path}",
        "dlg_first_run_title": "Welcome to Phoebus Builder",
        "first_run_welcome": "Welcome to Phoebus Builder!\n\nPlease select your workspace directory where your projects, sources, and configurations will be stored:",
        "dlg_select_workspace_placeholder": "Click Browse to select your workspace directory...",
        "dlg_workspace_required": "Please select a workspace directory to store your projects and sources.",
        "btn_start_app": "Get Started",

        # System Prerequisites
        "dlg_prereq_title": "Missing System Prerequisites",
        "dlg_prereq_intro": "Required tools are missing to build the package:",
        "dlg_prereq_mvn_win": "Apache Maven ('mvn.cmd') is missing in PATH.",
        "dlg_prereq_mvn_linux": "Apache Maven ('mvn') is missing. Install it with:\n   • Fedora / RHEL : sudo dnf install maven\n   • Debian / Ubuntu : sudo apt install maven",
        "dlg_prereq_tar": "Archive utility 'tar' is missing.",
        "dlg_prereq_fakeroot": "Packaging tool 'fakeroot' is missing. Install with: sudo apt install fakeroot",
        "dlg_prereq_dpkg": "Debian package tool 'dpkg-deb' is missing. Install with: sudo apt install dpkg",
        "dlg_prereq_rpmbuild": "RPM package builder 'rpmbuild' is missing. Install with: sudo dnf install rpm-build",

        # Configuration Validation
        "dlg_val_err_title": "Configuration Error",
        "dlg_val_app_name": "Application name (APP_NAME) cannot be empty.",
        "dlg_val_app_version": "Application version (APP_VERSION) cannot be empty.",
        "dlg_val_phoebus_branch": "Phoebus version must be specified (e.g. v5.0.2).",
        "dlg_val_java_version": "Java version must be specified (e.g. 21 or 25).",
        "dlg_val_local_sources_missing": "The specified local Phoebus sources path does not exist.",
        "dlg_val_local_sources_invalid": "The local sources directory does not contain required Phoebus pom.xml files.",
        "dlg_val_local_jdk_missing": "The specified local JDK path does not exist.",
        "dlg_val_local_jdk_invalid": "The local JDK is missing the required jpackage executable.",
        "dlg_val_local_maven_missing": "The specified local Maven path does not exist.",
        "dlg_val_local_maven_invalid": "The local Maven directory is missing the bin/mvn executable.",

        # Files & Projects Management
        "dlg_settings_need_file": "Please generate or select a settings.ini file first.",
        "dlg_settings_generated_title": "settings.ini Generation",
        "dlg_settings_generated": "Configuration file generated in:\n\n{path}",
        "dlg_ui_already_empty": "UI directory is already empty:\n\n{path}",
        "dlg_ui_cleared_title": "UI Directory Cleared",
        "dlg_ui_cleared": "UI directory has been cleared successfully:\n\n{path}",
        "dlg_project_saved_title": "Project Saved",
        "dlg_project_saved": "Project saved successfully in:\n\n{path}",
        "dlg_invalid_project_name": "Invalid project name.",
        "dlg_export_title": "Export Project",
        "dlg_export_filter": "Project Archive (*.zip)",
        "dlg_export_success": "Project '{name}' successfully exported to:\n\n{path}",
        "dlg_export_error": "Failed to export project:\n\n{err}",
        "dlg_import_title": "Import Project (.zip)",
        "dlg_import_filter": "Project Archive (*.zip)",
        "dlg_import_prompt": "Name for imported project:",
        "dlg_import_overwrite": "Overwrite project if it already exists",
        "dlg_import_overwrite_confirm": "Project '{name}' already exists. Check the box above to overwrite.",
        "dlg_import_invalid_zip": "The selected ZIP archive is not a valid Phoebus project (config.json not found).",
        "dlg_import_success": "Project '{name}' imported and loaded successfully!",
        "dlg_import_error": "Failed to import project:\n\n{err}",
        "dlg_duplicate_title": "Duplicate Project",
        "dlg_duplicate_prompt": "Name for the new project:",
        "dlg_duplicate_exists": "A project named '{name}' already exists.",
        "dlg_duplicate_error": "Failed to duplicate project:\n\n{err}",
        "dlg_delete_title": "Delete Project",
        "dlg_delete_confirm": "Are you sure you want to permanently delete project '{name}'?\n\nAll files in this project will be deleted.",
        "dlg_delete_only_project": "Cannot delete the only active project.",
        "dlg_build_busy": "A build is already running.",

        # Image Validation
        "dlg_img_invalid_format_title": "Invalid Image Format",
        "dlg_img_invalid_format_msg": "File '{filename}' is in {current_ext} format.\n\nFor {label}, required format is: {req_ext}.",
        "dlg_img_invalid_dims_title": "Invalid Image Dimensions",
        "dlg_img_invalid_dims_msg": "Image '{filename}' has dimensions: {w}x{h} px.\n\nFor {label}, required resolution is: {expected_w}x{expected_h} px.",

        # Settings Editor
        "editor_title": "Preferences Editor — {filename}",
        "editor_save_title": "Save File",
        "editor_save_msg": "Modifications saved in:\n\n{filename}",
        "editor_save_err": "Failed to save file:\n\n{err}",
        "editor_close_title": "Save Changes",
        "editor_close_msg": "Do you want to save changes to '{filename}' before closing?",
        "editor_saved_status": "Saved",
        "editor_search_label": "Search:",
        "editor_btn_find_next": "Next",
        "editor_btn_find_prev": "Previous",
        "dlg_btn_select_dir": "Select Folder",
        "dlg_btn_open_file": "Open",
        "dlg_lbl_look_in": "Directory:",
        "dlg_lbl_file_name": "Name:",
        "dlg_lbl_file_type": "File type:",
    }
}


if QTranslator is not None:
    class QtDictTranslator(QTranslator):
        """Native Qt QTranslator implementation driven by the TRANSLATIONS dictionary."""
        def __init__(self, lang_code: str = "fr", parent=None):
            super().__init__(parent)
            self.lang_code = lang_code

        def translate(self, context: str, source_text: str, disambiguation: Optional[str] = None, n: int = -1) -> Optional[str]:
            trans = TRANSLATIONS.get(self.lang_code, {})
            if source_text in trans:
                return trans[source_text]
            return None


_QTBASE_TRANSLATOR = None


def get_language() -> str:
    """Returns the current language code ('fr' or 'en')."""
    return _CURRENT_LANG


def set_language(lang: str) -> None:
    """Sets the active language and installs/replaces the native Qt translator and Qt base strings."""
    global _CURRENT_LANG, _ACTIVE_TRANSLATOR, _QTBASE_TRANSLATOR
    if lang.lower() in ("fr", "en"):
        _CURRENT_LANG = lang.lower()

    if QCoreApplication is not None and QTranslator is not None:
        app = QCoreApplication.instance()
        if app is not None:
            if _ACTIVE_TRANSLATOR is not None:
                app.removeTranslator(_ACTIVE_TRANSLATOR)
            _ACTIVE_TRANSLATOR = QtDictTranslator(_CURRENT_LANG, app)
            app.installTranslator(_ACTIVE_TRANSLATOR)

            if _QTBASE_TRANSLATOR is not None:
                app.removeTranslator(_QTBASE_TRANSLATOR)
                _QTBASE_TRANSLATOR = None

            try:
                from PySide6.QtCore import QLibraryInfo
                trans_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
                qtbase_trans = QTranslator(app)
                if qtbase_trans.load(f"qtbase_{_CURRENT_LANG}", trans_path):
                    _QTBASE_TRANSLATOR = qtbase_trans
                    app.installTranslator(_QTBASE_TRANSLATOR)
            except Exception:
                pass


def t(key: str, /, **kwargs: Any) -> str:
    """Translates a key based on active language, with variable formatting."""
    lang_dict = TRANSLATIONS.get(_CURRENT_LANG, TRANSLATIONS["en"])
    text = lang_dict.get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
