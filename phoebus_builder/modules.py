"""
Module for managing and filtering Phoebus application modules in phoebus-product/pom.xml.
Allows customizing and slimming down the packaged Phoebus product according to project requirements.
Supports bilingual labels (French / English).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Iterable
import xml.etree.ElementTree as ET


@dataclass
class PhoebusModuleInfo:
    artifact_id: str
    label: str
    description: str
    category: str
    label_en: str = ""
    description_en: str = ""
    category_en: str = ""
    is_core: bool = False  # Mandatory core module required to run Phoebus
    default_enabled: bool = True
    depends_on: List[str] = field(default_factory=list)

    def get_label(self, lang: str = "fr") -> str:
        return self.label_en if lang == "en" and self.label_en else self.label

    def get_description(self, lang: str = "fr") -> str:
        return self.description_en if lang == "en" and self.description_en else self.description

    def get_category(self, lang: str = "fr") -> str:
        return self.category_en if lang == "en" and self.category_en else self.category


# Complete categorized list of all phoebus-product modules
PHOEBUS_MODULES: List[PhoebusModuleInfo] = [
    # --- CORE STACK & PV PROTOCOLS ---
    PhoebusModuleInfo(
        artifact_id="core-launcher",
        label="Lanceur Principal (Core Launcher)",
        description="Moteur de démarrage et cycle de vie de l'application (Indispensable)",
        category="Socle & Protocoles PV",
        label_en="Core Launcher",
        description_en="Application bootstrap and runtime lifecycle (Mandatory)",
        category_en="Core Stack & PV Protocols",
        is_core=True,
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-ca",
        label="Protocole Channel Access (CA)",
        description="Connecteur EPICS Channel Access (EPICS v3 / ca://)",
        category="Socle & Protocoles PV",
        label_en="Channel Access Protocol (CA)",
        description_en="EPICS Channel Access network connector (EPICS v3 / ca://)",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-pva",
        label="Protocole PVAccess (PVA)",
        description="Connecteur EPICS PVAccess (EPICS v4/v7 / pva://)",
        category="Socle & Protocoles PV",
        label_en="PVAccess Protocol (PVA)",
        description_en="EPICS PVAccess network connector (EPICS v4/v7 / pva://)",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-mqtt",
        label="Protocole MQTT",
        description="Connecteur de données IoT MQTT (mqtt://)",
        category="Socle & Protocoles PV",
        label_en="MQTT Protocol",
        description_en="IoT MQTT data connector (mqtt://)",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-opva",
        label="Protocole OPC-UA",
        description="Connecteur standard industriel OPC Unified Architecture (opc://)",
        category="Socle & Protocoles PV",
        label_en="OPC-UA Protocol",
        description_en="OPC Unified Architecture industrial connector (opc://)",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-tango",
        label="Protocole Tango Controls",
        description="Connecteur système de contrôle Tango (tango://)",
        category="Socle & Protocoles PV",
        label_en="Tango Controls Protocol",
        description_en="Tango Control System connector (tango://)",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="core-pv-jackie",
        label="Protocole Jackie (Pure Java CA)",
        description="Implémentation Java alternative Channel Access",
        category="Socle & Protocoles PV",
        label_en="Jackie Protocol (Pure Java CA)",
        description_en="Alternative pure Java Channel Access implementation",
        category_en="Core Stack & PV Protocols",
        default_enabled=True,
    ),

    # --- DISPLAY BUILDER (UI / OPERATOR INTERFACES) ---
    PhoebusModuleInfo(
        artifact_id="app-display-runtime",
        label="Display Builder Runtime",
        description="Moteur d'exécution et d'affichage des interfaces .bob",
        category="IHM & Display Builder",
        label_en="Display Builder Runtime",
        description_en="Runtime execution engine for .bob UI screens",
        category_en="UI & Display Builder",
        is_core=True,
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-representation-javafx",
        label="Rendu Graphique JavaFX Display",
        description="Composants graphiques natifs JavaFX pour l'affichage des interfaces",
        category="IHM & Display Builder",
        label_en="JavaFX Display Rendering",
        description_en="Native JavaFX graphics components for UI rendering",
        category_en="UI & Display Builder",
        is_core=True,
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-fonts",
        label="Polices Graphiques Display",
        description="Gestionnaire des polices vectorielles pour les vues d'interfaces",
        category="IHM & Display Builder",
        label_en="Display Font Manager",
        description_en="Vector font manager for display screens",
        category_en="UI & Display Builder",
        is_core=True,
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-editor",
        label="Éditeur Graphique d'Interfaces (.bob)",
        description="Permet de modifier et concevoir des vues .bob directement dans Phoebus",
        category="IHM & Display Builder",
        label_en="UI Graphic Editor (.bob)",
        description_en="Design and edit .bob display files directly in Phoebus",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime", "app-display-representation-javafx", "app-display-fonts"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-navigation",
        label="Navigation & Arborescence Interfaces",
        description="Outils de navigation entre pages et panneaux d'interfaces",
        category="IHM & Display Builder",
        label_en="Display Navigation & Breadcrumbs",
        description_en="Navigation tools and display hierarchy panels",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-adapters",
        label="Adaptateurs Display Builder",
        description="Ponts de communication et menus contextuels pour les widgets",
        category="IHM & Display Builder",
        label_en="Display Builder Adapters",
        description_en="Context menus and widget communication bridges",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-thumbwheel",
        label="Widget Molette (Thumbwheel)",
        description="Widget potentiomètre / roue codeuse pour ajuster des valeurs",
        category="IHM & Display Builder",
        label_en="Thumbwheel Widget",
        description_en="Thumbwheel potentiometer widget for fine value adjustments",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-linearmeter",
        label="Widget Vu-mètre Linéaire",
        description="Jauge linéaire de niveau pour valeurs analogiques",
        category="IHM & Display Builder",
        label_en="Linear Meter Widget",
        description_en="Linear level gauge for analog values",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-waterfallplot",
        label="Widget Graphique Cascade (Waterfall Plot)",
        description="Widget d'affichage de spectres et profils d'ondes en cascade",
        category="IHM & Display Builder",
        label_en="Waterfall Plot Widget",
        description_en="Waterfall spectrum and time-profile plot widget",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime", "app-databrowser"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-convert-medm",
        label="Convertisseur MEDM (.adl -> .bob)",
        description="Permet d'importer et convertir d'anciens écrans EPICS MEDM",
        category="IHM & Display Builder",
        label_en="MEDM Converter (.adl -> .bob)",
        description_en="Import and convert legacy EPICS MEDM screens",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime", "app-display-editor"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-display-convert-edm",
        label="Convertisseur EDM (.edl -> .bob)",
        description="Permet d'importer et convertir d'anciens écrans EPICS EDM",
        category="IHM & Display Builder",
        label_en="EDM Converter (.edl -> .bob)",
        description_en="Import and convert legacy EPICS EDM screens",
        category_en="UI & Display Builder",
        default_enabled=True,
        depends_on=["app-display-runtime", "app-display-editor"],
    ),

    # --- PLOTS, TRENDS & ARCHIVING ---
    PhoebusModuleInfo(
        artifact_id="app-databrowser",
        label="Data Browser (Courbes & Historique)",
        description="Outil de visualisation graphique des PVs en temps réel et archivées",
        category="Courbes & Archivage",
        label_en="Data Browser (Plots & History)",
        description_en="Real-time and archived PV graphing and trending tool",
        category_en="Plots & Archiving",
        default_enabled=True,
        depends_on=["app-rtplot"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-rtplot",
        label="Moteur de Tracé Temps Réel (RTPlot)",
        description="Moteur de tracé haute performance pour graphiques dynamiques",
        category="Courbes & Archivage",
        label_en="Real-Time Plot Engine (RTPlot)",
        description_en="High-performance plotting engine for dynamic charts",
        category_en="Plots & Archiving",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-trends-archive-reader",
        label="Lecteur d'Archivage (Archive Reader)",
        description="Connecteur aux services d'archivage EPICS Archiver Appliance",
        category="Courbes & Archivage",
        label_en="Archive Reader",
        description_en="Connector for EPICS Archiver Appliance services",
        category_en="Plots & Archiving",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-trends-archive-datasource",
        label="Source de Données d'Archivage",
        description="Source de données intégrée pour le lecteur d'archives",
        category="Courbes & Archivage",
        label_en="Archive Data Source",
        description_en="Integrated data source for archive readers",
        category_en="Plots & Archiving",
        default_enabled=True,
        depends_on=["app-trends-archive-reader"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-trends-rich-adapters",
        label="Adaptateurs Riches de Tendances",
        description="Intégration du menu contextuel vers le Data Browser",
        category="Courbes & Archivage",
        label_en="Rich Trend Adapters",
        description_en="Context menu integration targeting Data Browser",
        category_en="Plots & Archiving",
        default_enabled=True,
        depends_on=["app-databrowser"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-databrowser-json",
        label="Export/Import JSON Data Browser",
        description="Support des configurations de courbes au format JSON",
        category="Courbes & Archivage",
        label_en="JSON Data Browser Import/Export",
        description_en="Support for JSON plot configurations",
        category_en="Plots & Archiving",
        default_enabled=True,
        depends_on=["app-databrowser"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-databrowser-timescale",
        label="Connecteur TimescaleDB",
        description="Support de l'archivage dans des bases temporelles TimescaleDB",
        category="Courbes & Archivage",
        label_en="TimescaleDB Connector",
        description_en="Archiving support in TimescaleDB time-series databases",
        category_en="Plots & Archiving",
        default_enabled=True,
        depends_on=["app-databrowser"],
    ),

    # --- ALARM MANAGEMENT ---
    PhoebusModuleInfo(
        artifact_id="app-alarm-ui",
        label="Interface Table des Alarmes",
        description="Vue hiérarchique et tableau de suivi des alarmes actives",
        category="Alarmes",
        label_en="Alarm Table UI",
        description_en="Hierarchical tree and table for active alarm tracking",
        category_en="Alarms",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-alarm-datasouce",
        label="Source de Données d'Alarmes (Kafka)",
        description="Connecteur au serveur d'alarmes Phoebus via Apache Kafka",
        category="Alarmes",
        label_en="Alarm Data Source (Kafka)",
        description_en="Connector to Phoebus Alarm Server via Apache Kafka",
        category_en="Alarms",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-alarm-logging-ui",
        label="Historique & Journal des Alarmes",
        description="Interface de consultation des logs d'alarmes (Elasticsearch)",
        category="Alarmes",
        label_en="Alarm Logging UI",
        description_en="Alarm history query UI (Elasticsearch)",
        category_en="Alarms",
        default_enabled=True,
        depends_on=["app-alarm-ui", "app-alarm-datasouce"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-alarm-freetts-annunciator",
        label="Synthèse Vocale des Alarmes (FreeTTS)",
        description="Annonce sonore et vocale des alertes et alarmes critiques",
        category="Alarmes",
        label_en="Alarm Speech Annunciator (FreeTTS)",
        description_en="Voice annunciator for critical alarms and alerts",
        category_en="Alarms",
        default_enabled=True,
        depends_on=["app-alarm-ui"],
    ),

    # --- SCANS & SEQUENCES ---
    PhoebusModuleInfo(
        artifact_id="app-scan-ui",
        label="Client Scan (Balayages & Expériences)",
        description="Interface de contrôle et de surveillance du serveur de balayage Scan Server",
        category="Scans & Séquences",
        label_en="Scan Client (Experiment Scans)",
        description_en="Scan Server monitoring and control UI",
        category_en="Scans & Sequences",
        default_enabled=True,
    ),

    # --- SAVE & RESTORE ---
    PhoebusModuleInfo(
        artifact_id="save-and-restore",
        label="Save & Restore (Snapshots PV)",
        description="Capture et réapplication de clichés de réglages de points de consigne",
        category="Save & Restore",
        label_en="Save & Restore (PV Snapshots)",
        description_en="Capture and restore machine setpoint snapshots",
        category_en="Save & Restore",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="save-and-restore-logging",
        label="Journalisation Save & Restore",
        description="Enregistrement d'audit des restaurations de clichés",
        category="Save & Restore",
        label_en="Save & Restore Audit Logging",
        description_en="Audit logging of snapshot restore operations",
        category_en="Save & Restore",
        default_enabled=True,
        depends_on=["save-and-restore"],
    ),

    # --- ELECTRONIC LOGBOOK ---
    PhoebusModuleInfo(
        artifact_id="app-logbook-inmemory",
        label="Logbook Mémoire Locale",
        description="Cahier de notes stocké temporairement en mémoire locale",
        category="Logbook",
        label_en="Local Memory Logbook",
        description_en="Note log stored temporarily in local memory",
        category_en="Logbook",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-logbook-olog-ui",
        label="Interface OLog Web",
        description="Client de connexion au service de cahier électronique OLog",
        category="Logbook",
        label_en="OLog Web UI",
        description_en="Client UI for OLog electronic logbook service",
        category_en="Logbook",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-logbook-elog",
        label="Interface PSI ELOG",
        description="Client de connexion au service de cahier électronique ELOG",
        category="Logbook",
        label_en="PSI ELOG UI",
        description_en="Client UI for PSI ELOG electronic logbook service",
        category_en="Logbook",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-logbook-olog-client",
        label="Client REST OLog",
        description="Bibliothèque cliente pour les requêtes OLog",
        category="Logbook",
        label_en="OLog REST Client",
        description_en="Client library for OLog REST API queries",
        category_en="Logbook",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-logbook-olog-client-es",
        label="Client OLog Elasticsearch",
        description="Connecteur OLog vers index Elasticsearch",
        category="Logbook",
        label_en="OLog Elasticsearch Client",
        description_en="OLog direct connector to Elasticsearch",
        category_en="Logbook",
        default_enabled=True,
    ),

    # --- TOOLS & DIAGNOSTICS ---
    PhoebusModuleInfo(
        artifact_id="app-pvtable",
        label="Tableau de Variables (PV Table)",
        description="Grille de surveillance et d'édition rapide d'une liste de PVs",
        category="Outils & Diagnostics",
        label_en="PV Table",
        description_en="Grid monitoring and fast editing tool for PV lists",
        category_en="Tools & Diagnostics",
        default_enabled=True,
        depends_on=["core-pv-ca"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-pvtree",
        label="Arbre de Dépendances (PV Tree)",
        description="Visualisation hiérarchique de l'arbre des liens entre enregistrements EPICS",
        category="Outils & Diagnostics",
        label_en="PV Tree",
        description_en="Hierarchical tree view of EPICS record links",
        category_en="Tools & Diagnostics",
        default_enabled=True,
        depends_on=["core-pv-ca"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-probe",
        label="Sonde PV (Probe)",
        description="Inspection détaillée en direct de la valeur, statut et métadonnées d'une PV",
        category="Outils & Diagnostics",
        label_en="PV Probe",
        description_en="Live detailed inspection of PV value, status and metadata",
        category_en="Tools & Diagnostics",
        default_enabled=True,
        depends_on=["core-pv-ca"],
    ),
    PhoebusModuleInfo(
        artifact_id="app-filebrowser",
        label="Explorateur de Fichiers Intégré",
        description="Navigateur de fichiers et dossiers dans la barre latérale",
        category="Outils & Diagnostics",
        label_en="Integrated File Browser",
        description_en="Sidebar directory and file navigator",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-imageviewer",
        label="Visualiseur d'Images (AreaDetector)",
        description="Affichage de flux de caméras et matrices 2D EPICS AreaDetector",
        category="Outils & Diagnostics",
        label_en="Image Viewer (AreaDetector)",
        description_en="Display camera streams and EPICS AreaDetector 2D arrays",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-3d-viewer",
        label="Visualiseur 3D STL/OBJ",
        description="Visualisation de modèles 3D mécaniques intégrés",
        category="Outils & Diagnostics",
        label_en="3D Viewer (STL/OBJ)",
        description_en="Embedded mechanical 3D model viewer",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-console",
        label="Console Système & Sortie Standard",
        description="Fenêtre d'affichage des logs et flux console de Phoebus",
        category="Outils & Diagnostics",
        label_en="System Console",
        description_en="Log and standard output display window",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-errlog",
        label="Journal des Erreurs (Error Log)",
        description="Vue des alertes et exceptions Java survenues pendant l'exécution",
        category="Outils & Diagnostics",
        label_en="Error Log",
        description_en="View of Java warnings and runtime exceptions",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-diag",
        label="Outils de Diagnostic Phoebus",
        description="Informations mémoire JVM, threads et statut système",
        category="Outils & Diagnostics",
        label_en="Diagnostic Tools",
        description_en="JVM memory metrics, active threads and system health",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-perfmon",
        label="Moniteur de Performances (PerfMon)",
        description="Graphique de consommation CPU et mémoire de Phoebus",
        category="Outils & Diagnostics",
        label_en="Performance Monitor (PerfMon)",
        description_en="Phoebus CPU and memory consumption charts",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-email-ui",
        label="Envoi par Email",
        description="Permet d'envoyer des captures d'écran et rapports par e-mail",
        category="Outils & Diagnostics",
        label_en="Email Sending UI",
        description_en="Send display screenshots and reports via email",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-credentials-management",
        label="Gestionnaire d'Identifiants",
        description="Stockage sécurisé des identifiants et mots de passe",
        category="Outils & Diagnostics",
        label_en="Credentials Management",
        description_en="Secure password and credentials vault",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-channel-views",
        label="Vues ChannelFinder",
        description="Interface de recherche et filtrage de canaux",
        category="Outils & Diagnostics",
        label_en="ChannelFinder Views",
        description_en="Channel search and filtering directory UI",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-channel-channelfinder",
        label="Connecteur ChannelFinder Directory",
        description="Client de communication avec le service d'annuaire ChannelFinder",
        category="Outils & Diagnostics",
        label_en="ChannelFinder Directory Connector",
        description_en="REST communication client for ChannelFinder directory",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-eslog",
        label="Journalisation Elasticsearch",
        description="Export direct des logs vers un cluster Elasticsearch",
        category="Outils & Diagnostics",
        label_en="Elasticsearch Logging",
        description_en="Direct log streaming to Elasticsearch clusters",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-utility-preference-manager",
        label="Gestionnaire de Préférences (Preference Manager)",
        description="Interface graphique de consultation et d'édition des préférences de l'application",
        category="Outils & Diagnostics",
        label_en="Preference Manager",
        description_en="Graphical interface to view and edit application preferences",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
    PhoebusModuleInfo(
        artifact_id="app-update",
        label="Mise à Jour Automatique",
        description="Mécanisme de mise à jour intégrée de Phoebus",
        category="Outils & Diagnostics",
        label_en="Auto Update",
        description_en="Built-in application auto-update mechanism",
        category_en="Tools & Diagnostics",
        default_enabled=True,
    ),
]


class PhoebusPomManager:
    """Manager for filtering and editing phoebus-product/pom.xml dependencies."""

    @staticmethod
    def get_module_map() -> Dict[str, PhoebusModuleInfo]:
        """Returns artifactId -> PhoebusModuleInfo dictionary."""
        return {m.artifact_id: m for m in PHOEBUS_MODULES}

    @classmethod
    def get_dependencies(cls, artifact_id: str) -> List[str]:
        """Returns direct dependencies for a module."""
        mod = cls.get_module_map().get(artifact_id)
        return list(mod.depends_on) if mod else []

    @classmethod
    def get_dependents(cls, artifact_id: str) -> List[str]:
        """Returns modules that directly depend on the given module."""
        return [m.artifact_id for m in PHOEBUS_MODULES if artifact_id in m.depends_on]

    @classmethod
    def resolve_dependencies(cls, enabled_modules: Iterable[str]) -> List[str]:
        """
        Recursively resolves all module dependencies ensuring no missing required module.
        Returns a sorted list of artifactIds with all transitive dependencies included.
        """
        mod_map = cls.get_module_map()
        resolved: Set[str] = set()
        queue = list(enabled_modules)

        # Always include core modules
        for m in PHOEBUS_MODULES:
            if m.is_core:
                queue.append(m.artifact_id)

        while queue:
            aid = queue.pop(0)
            if aid not in resolved and aid in mod_map:
                resolved.add(aid)
                for dep_id in mod_map[aid].depends_on:
                    if dep_id not in resolved and dep_id not in queue:
                        queue.append(dep_id)

        return [m.artifact_id for m in PHOEBUS_MODULES if m.artifact_id in resolved]

    @staticmethod
    def get_all_module_ids() -> List[str]:
        """Returns list of all managed artifactIds."""
        return [m.artifact_id for m in PHOEBUS_MODULES]

    @staticmethod
    def get_default_enabled_module_ids() -> List[str]:
        """Returns list of default enabled module artifactIds."""
        return [m.artifact_id for m in PHOEBUS_MODULES if m.default_enabled or m.is_core]

    @staticmethod
    def get_minimal_ui_module_ids() -> List[str]:
        """Returns ultra-lightweight minimal UI configuration (Displays .bob + PV protocols only)."""
        minimal = {
            "core-launcher",
            "core-pv-ca",
            "core-pv-pva",
            "app-display-runtime",
            "app-display-representation-javafx",
            "app-display-fonts",
            "app-display-editor",
            "app-display-adapters",
            "app-display-thumbwheel",
            "app-display-linearmeter",
            "app-console",
            "app-errlog",
        }
        return [m.artifact_id for m in PHOEBUS_MODULES if m.artifact_id in minimal]

    @staticmethod
    def get_standard_module_ids() -> List[str]:
        """Returns standard configuration (UI + DataBrowser + Probe + PVTable)."""
        standard = {
            "core-launcher",
            "core-pv-ca",
            "core-pv-pva",
            "app-display-runtime",
            "app-display-representation-javafx",
            "app-display-fonts",
            "app-display-editor",
            "app-display-navigation",
            "app-display-adapters",
            "app-display-thumbwheel",
            "app-display-linearmeter",
            "app-display-waterfallplot",
            "app-databrowser",
            "app-rtplot",
            "app-trends-archive-reader",
            "app-trends-archive-datasource",
            "app-trends-rich-adapters",
            "app-databrowser-json",
            "app-probe",
            "app-pvtable",
            "app-pvtree",
            "app-filebrowser",
            "app-utility-preference-manager",
            "app-console",
            "app-errlog",
            "app-diag",
            "app-logbook-inmemory",
        }
        return [m.artifact_id for m in PHOEBUS_MODULES if m.artifact_id in standard]

    @staticmethod
    def discover_modules_from_pom(pom_file: Optional[Path] = None) -> List[PhoebusModuleInfo]:
        """
        Parses phoebus-product pom.xml.
        - If pom_file is present and contains dependencies:
          Filters the known catalog to ONLY return modules actually declared in that version's pom.xml,
          plus any new/unknown modules discovered in the POM.
        - If pom_file is None or does not exist (sources not yet downloaded):
          Returns the complete known catalog as default fallback.
        """
        known_ids = {m.artifact_id: m for m in PHOEBUS_MODULES}
        if not pom_file or not pom_file.exists():
            return list(PHOEBUS_MODULES)

        try:
            if pom_file.stat().st_size == 0:
                return list(PHOEBUS_MODULES)
        except OSError:
            return list(PHOEBUS_MODULES)

        ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
        try:
            tree = ET.parse(pom_file)
            root = tree.getroot()
        except Exception:
            return list(PHOEBUS_MODULES)

        ns = {"mvn": "http://maven.apache.org/POM/4.0.0"}
        dependencies_node = root.find("mvn:dependencies", ns)
        if dependencies_node is None:
            dependencies_node = root.find("dependencies")

        if dependencies_node is None:
            return list(PHOEBUS_MODULES)

        pom_artifact_ids: Set[str] = set()
        discovered: List[PhoebusModuleInfo] = []
        mandatory = {"core-launcher", "phoebus-target", "app-log-configuration"}

        for dep in list(dependencies_node):
            art_node = dep.find("mvn:artifactId", ns) if "mvn" in ns else dep.find("artifactId")
            if art_node is None:
                art_node = dep.find("artifactId")

            if art_node is not None and art_node.text:
                artifact_id = art_node.text.strip()
                pom_artifact_ids.add(artifact_id)
                if artifact_id not in known_ids and artifact_id not in mandatory:
                    clean_name = artifact_id.replace("app-", "").replace("core-", "").replace("-", " ").title()
                    discovered.append(
                        PhoebusModuleInfo(
                            artifact_id=artifact_id,
                            label=f"{clean_name} ({artifact_id})",
                            description=f"Nouveau module détecté depuis le pom.xml de cette version",
                            category="Nouveaux modules détectés",
                            label_en=f"{clean_name} ({artifact_id})",
                            description_en=f"Discovered module from this version's pom.xml",
                            category_en="Discovered New Modules",
                            default_enabled=True
                        )
                    )

        if not pom_artifact_ids:
            return list(PHOEBUS_MODULES)

        # Retain only modules from the catalog that are actually present in this version's pom.xml
        catalog_present = [m for m in PHOEBUS_MODULES if m.artifact_id in pom_artifact_ids]

        return catalog_present + discovered

    @staticmethod
    def filter_product_pom(pom_file: Path, enabled_modules: Set[str], managed_modules: Optional[Set[str]] = None) -> Path:
        """
        Parses phoebus-product pom.xml, filters <dependency> tags based on enabled_modules
        while preserving core-launcher and phoebus-target, then writes back the file.
        """
        if not pom_file.exists():
            raise FileNotFoundError(f"pom.xml file not found: {pom_file}")

        # Register default namespace to prevent ns0: prefix in output XML
        ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
        tree = ET.parse(pom_file)
        root = tree.getroot()

        # Maven XML namespace
        ns = {"mvn": "http://maven.apache.org/POM/4.0.0"}
        dependencies_node = root.find("mvn:dependencies", ns)
        if dependencies_node is None:
            dependencies_node = root.find("dependencies")

        if dependencies_node is None:
            raise ValueError(f"<dependencies> section not found in {pom_file}")

        # Always preserved infrastructure dependencies
        mandatory_artifacts = {"core-launcher", "phoebus-target", "app-log-configuration"}

        managed_artifact_ids = managed_modules or {m.artifact_id for m in PHOEBUS_MODULES}

        removed_count = 0
        kept_count = 0

        # Reverse iteration for safe child node removal
        for dep in list(dependencies_node):
            art_node = dep.find("mvn:artifactId", ns) if "mvn" in ns else dep.find("artifactId")
            if art_node is None:
                art_node = dep.find("artifactId")

            if art_node is not None and art_node.text:
                artifact_id = art_node.text.strip()

                if artifact_id in mandatory_artifacts:
                    kept_count += 1
                    continue

                if artifact_id in managed_artifact_ids:
                    if artifact_id in enabled_modules:
                        kept_count += 1
                    else:
                        dependencies_node.remove(dep)
                        removed_count += 1
                else:
                    # Keep unmanaged third-party dependencies
                    kept_count += 1

        tree.write(pom_file, encoding="utf-8", xml_declaration=True)
        return pom_file
