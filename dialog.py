# -*- coding: utf-8 -*-

import csv
import os
import re

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsMemoryProviderUtils,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import plugin_hub

if hasattr(Qt, "AlignmentFlag"):
    QT_ALIGN_TOP = Qt.AlignmentFlag.AlignTop
    QT_ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft
    QT_ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    QT_KEEP_ASPECT_RATIO = Qt.AspectRatioMode.KeepAspectRatio
    QT_SMOOTH_TRANSFORMATION = Qt.TransformationMode.SmoothTransformation
else:
    QT_ALIGN_TOP = Qt.AlignTop
    QT_ALIGN_LEFT = Qt.AlignLeft
    QT_ALIGN_CENTER = Qt.AlignCenter
    QT_KEEP_ASPECT_RATIO = Qt.KeepAspectRatio
    QT_SMOOTH_TRANSFORMATION = Qt.SmoothTransformation

if hasattr(QDialogButtonBox, "ButtonRole"):
    BTN_ACCEPT_ROLE = QDialogButtonBox.ButtonRole.AcceptRole
    BTN_REJECT_ROLE = QDialogButtonBox.ButtonRole.RejectRole
else:
    BTN_ACCEPT_ROLE = QDialogButtonBox.AcceptRole
    BTN_REJECT_ROLE = QDialogButtonBox.RejectRole


class CsvImporterDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.csv_path = None
        self.csv_headers = []
        self.csv_rows = []
        self.preview_layer = None
        self.osm_layer = None

        self.lang = "it"  # default

        self.setWindowTitle("CSV Importer XY — GeoPackage & Mappa")
        self.setMinimumWidth(850)
        self.setMinimumHeight(650)
        self.setStyleSheet(plugin_hub.FAMILY_STYLE)

        self.plugin_dir = os.path.dirname(__file__)

        self._build_ui()
        self._update_texts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab_import = QWidget()
        self._build_import_tab()
        self.tabs.addTab(self.tab_import, "Importazione")

        self.tab_help = QWidget()
        self._build_help_tab()
        self.tabs.addTab(self.tab_help, "Guida / Help")

        self.tab_info = QWidget()
        self._build_info_tab()
        self.tabs.addTab(self.tab_info, "Info Autori")

        btn_box = QDialogButtonBox()
        self.import_btn = btn_box.addButton(
            "Importa e Salva in GeoPackage...", BTN_ACCEPT_ROLE
        )
        self.import_btn.setEnabled(False)
        self.cancel_btn = btn_box.addButton("Annulla", BTN_REJECT_ROLE)
        btn_box.accepted.connect(self._on_import_clicked)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _build_import_tab(self):
        layout = QHBoxLayout(self.tab_import)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.file_group = QGroupBox("1. File CSV e Codifica")
        file_layout = QVBoxLayout(self.file_group)

        file_h = QHBoxLayout()
        self.file_line = QLineEdit()
        self.file_line.setPlaceholderText("Nessun file selezionato…")
        self.file_line.setReadOnly(True)
        file_h.addWidget(self.file_line)

        self.browse_btn = QPushButton("Sfoglia…")
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.clicked.connect(self._browse_csv)
        file_h.addWidget(self.browse_btn)
        file_layout.addLayout(file_h)

        enc_h = QHBoxLayout()
        self.enc_label = QLabel("Codifica:")
        enc_h.addWidget(self.enc_label)
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(
            ["utf-8", "latin1", "windows-1252", "utf-8-sig"]
        )
        self.encoding_combo.currentTextChanged.connect(self._reload_csv)
        enc_h.addWidget(self.encoding_combo)

        self.status_icon = QLabel("⚫ In attesa")
        self.status_icon.setStyleSheet("color: gray; font-weight: bold;")
        enc_h.addWidget(self.status_icon)
        enc_h.addStretch()
        file_layout.addLayout(enc_h)

        left_layout.addWidget(self.file_group)

        self.coords_group = QGroupBox("2. Colonne delle coordinate")
        self.coords_form = QFormLayout(self.coords_group)
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        self.x_combo.currentIndexChanged.connect(self._update_preview_map)
        self.y_combo.currentIndexChanged.connect(self._update_preview_map)
        self.x_label = QLabel("Colonna X (Lon/Est):")
        self.y_label = QLabel("Colonna Y (Lat/Nord):")
        self.coords_form.addRow(self.x_label, self.x_combo)
        self.coords_form.addRow(self.y_label, self.y_combo)
        left_layout.addWidget(self.coords_group)

        self.crs_group = QGroupBox("3. Sistema di riferimento (CRS)")
        crs_layout = QVBoxLayout(self.crs_group)
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.crs_widget.crsChanged.connect(self._update_preview_map)
        crs_layout.addWidget(self.crs_widget)
        left_layout.addWidget(self.crs_group)

        self.name_group = QGroupBox("4. Nome del layer")
        name_layout = QHBoxLayout(self.name_group)
        self.layer_name_edit = QLineEdit("CSV_Layer")
        name_layout.addWidget(self.layer_name_edit)
        left_layout.addWidget(self.name_group)

        left_layout.addStretch()

        self.right_panel = QGroupBox("Anteprima Mappa")
        right_layout = QVBoxLayout(self.right_panel)
        self.map_canvas = QgsMapCanvas(self)
        self.map_canvas.setCanvasColor(QColor("white"))
        self.map_canvas.enableAntiAliasing(True)
        right_layout.addWidget(self.map_canvas)

        urlWithParams = (
            "type=xyz&url=https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
            "&zmax=19&zmin=0&crs=EPSG3857"
        )
        self.osm_layer = QgsRasterLayer(urlWithParams, "OpenStreetMap", "wms")
        if self.osm_layer.isValid():
            QgsProject.instance().addMapLayer(self.osm_layer, False)
            self.map_canvas.setLayers([self.osm_layer])
            self.map_canvas.setDestinationCrs(
                QgsCoordinateReferenceSystem("EPSG:3857")
            )
            self.map_canvas.setExtent(self.osm_layer.extent())

        layout.addWidget(left_panel, 1)
        layout.addWidget(self.right_panel, 1)

    def _build_help_tab(self):
        from qgis.PyQt.QtWidgets import QScrollArea

        layout = QVBoxLayout(self.tab_help)
        self.help_text = QLabel()
        self.help_text.setWordWrap(True)
        self.help_text.setAlignment(QT_ALIGN_TOP | QT_ALIGN_LEFT)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.help_text)
        layout.addWidget(scroll)

    def _build_info_tab(self):
        main_layout = QVBoxLayout(self.tab_info)

        # --- Lang Switcher ---
        lang_layout = QHBoxLayout()
        lang_layout.addStretch()
        self.btn_it = QPushButton(" Italiano")
        self.btn_en = QPushButton(" English")

        it_icon_path = os.path.join(self.plugin_dir, "IT.svg")
        en_icon_path = os.path.join(self.plugin_dir, "UK.svg")
        if os.path.exists(it_icon_path):
            self.btn_it.setIcon(QIcon(it_icon_path))
        if os.path.exists(en_icon_path):
            self.btn_en.setIcon(QIcon(en_icon_path))

        self.btn_it.clicked.connect(lambda: self._set_lang("it"))
        self.btn_en.clicked.connect(lambda: self._set_lang("en"))
        lang_layout.addWidget(self.btn_it)
        lang_layout.addWidget(self.btn_en)
        main_layout.addLayout(lang_layout)

        # --- Description ---
        desc_group = QGroupBox()
        self.desc_group = desc_group
        desc_layout = QVBoxLayout(desc_group)
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        desc_layout.addWidget(self.desc_label)
        main_layout.addWidget(desc_group)

        # --- Cards (Sarino first, then Luca) ---
        cards_layout = QHBoxLayout()

        # Card Sarino
        sarino_group = QGroupBox("Dott. Sarino Alfonso Grande")
        self.sarino_group = sarino_group
        sarino_layout = QVBoxLayout(sarino_group)

        sarino_img = QLabel()
        logo_path = os.path.join(self.plugin_dir, "logo.jpg")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            sarino_img.setPixmap(
                pixmap.scaled(
                    150, 150, QT_KEEP_ASPECT_RATIO, QT_SMOOTH_TRANSFORMATION
                )
            )
        else:
            self.sarino_logo_missing = True
            sarino_img.setText("Logo Mancante")
        sarino_img.setAlignment(QT_ALIGN_CENTER)
        sarino_layout.addWidget(sarino_img)

        self.sarino_info = QLabel()
        self.sarino_info.setAlignment(QT_ALIGN_CENTER)
        self.sarino_info.setOpenExternalLinks(True)
        sarino_layout.addWidget(self.sarino_info)
        sarino_layout.addStretch()

        # Card Luca
        luca_group = QGroupBox("Geometra Luca Casti")
        self.luca_group = luca_group
        luca_layout = QVBoxLayout(luca_group)

        luca_img = QLabel()
        qr_path = os.path.join(self.plugin_dir, "1770729804841.jpg")
        if os.path.exists(qr_path):
            pixmap = QPixmap(qr_path)
            luca_img.setPixmap(
                pixmap.scaled(
                    150, 150, QT_KEEP_ASPECT_RATIO, QT_SMOOTH_TRANSFORMATION
                )
            )
        else:
            self.luca_qr_missing = True
            luca_img.setText("QR Code Mancante")
        luca_img.setAlignment(QT_ALIGN_CENTER)
        luca_layout.addWidget(luca_img)

        self.luca_info = QLabel()
        self.luca_info.setAlignment(QT_ALIGN_CENTER)
        self.luca_info.setOpenExternalLinks(True)
        luca_layout.addWidget(self.luca_info)
        luca_layout.addStretch()

        cards_layout.addWidget(sarino_group)
        cards_layout.addWidget(luca_group)

        main_layout.addLayout(cards_layout)

        # --- Other plugins of the family (drop-down) ---
        self.family_widget = plugin_hub.make_family_widget(
            "geocsv_mapper", lang=self.lang
        )
        main_layout.addWidget(self.family_widget)
        main_layout.addStretch()

    def _set_lang(self, lang):
        self.lang = lang
        self._update_texts()
        if hasattr(self, "family_widget"):
            self.family_widget.set_lang(lang)

    def _update_texts(self):
        t = {
            "it": {
                "win_title": "GeoCSV Mapper — GeoPackage & Mappa (v2.2.0)",
                "tab_import": "Importazione",
                "tab_help": "Guida",
                "tab_info": "Info Autori",
                "btn_import": "Importa e Salva in GeoPackage...",
                "btn_cancel": "Annulla",
                "grp_file": "1. File CSV e Codifica",
                "txt_nofile": "Nessun file selezionato…",
                "btn_browse": "Sfoglia…",
                "lbl_enc": "Codifica:",
                "lbl_wait": "⚫ In attesa",
                "lbl_ok": "🟢 Operativo",
                "lbl_err_enc": "🔴 Errore Codifica",
                "lbl_err": "🔴 Errore",
                "grp_coords": "2. Colonne delle coordinate",
                "lbl_x": "Colonna X (Lon/Est):",
                "lbl_y": "Colonna Y (Lat/Nord):",
                "grp_crs": "3. Sistema di riferimento (CRS)",
                "grp_name": "4. Nome del layer",
                "grp_map": "Anteprima Mappa",
                "grp_desc": "Informazioni sull'Applicativo",
                "txt_desc": (
                    "Questo plugin è uno strumento avanzato per "
                    "l'importazione massiva di punti tramite file CSV "
                    "in QGIS.<br><br>"
                    "Offre un potente parser per il riconoscimento "
                    "automatico sia delle coordinate decimali standard "
                    "sia dei formati sessagesimali più complessi (DMS). "
                    "Implementa un'anteprima rapida su cartografia "
                    "OpenStreetMap, verifica in tempo reale la codifica "
                    "del testo e supporta l'esportazione automatizzata "
                    "verso il formato moderno GeoPackage."
                ),
                "role_luca": (
                    "<b>Ruolo</b>: Ideatore e Consulente Tecnico<br>"
                    "<b>Email</b>: <a href='mailto:lucasti1988@gmail.com'>"
                    "lucasti1988@gmail.com</a><br>"
                    "<b>Cell</b>: 3474565539<br>"
                    "<b>LinkedIn</b>: <a href='https://linkedin.com/in/"
                    "luca-casti-326359357'>luca-casti</a>"
                ),
                "role_sarino": (
                    "<b>Ruolo</b>: Sviluppatore e Publisher<br>"
                    "<b>Email</b>: <a href='mailto:sino.grande@gmail.com'>"
                    "sino.grande@gmail.com</a><br>"
                    "<b>Sito Web</b>: <a href='https://sinocloud.it'>"
                    "sinocloud.it</a><br>"
                    "<b>GitHub</b>: <a href='https://github.com/sag1687'>"
                    "sag1687</a>"
                ),
                "qr_missing": "QR Code Mancante",
                "logo_missing": "Logo Mancante",
                "msg_err": "Errore",
                "msg_succ": "Success",
                "msg_gpkg_title": (
                    "Salva come GeoPackage (Annulla per mantenere solo "
                    "livello temporaneo)"),
                "msg_err_read": "Impossibile leggere il file CSV:",
                "msg_succ_gpkg": (
                    "Dati salvati e caricati da GeoPackage con "
                    "successo.\nPunti:"),
                "msg_err_gpkg": (
                    "Impossibile salvare in GeoPackage:\n{}\nVerrà caricato "
                    "il layer temporaneo."),
                "msg_succ_temp": "Layer temporaneo creato.\nPunti:",
                "txt_help": (
                    "<b>Guida all'uso di GeoCSV Mapper</b><br><br>"
                    "<b>1. File CSV e Codifica:</b><br>"
                    "Seleziona il file CSV tramite il pulsante "
                    "'Sfoglia...'. Scegli la codifica corretta se i "
                    "caratteri speciali non vengono letti "
                    "correttamente.<br><br>"
                    "<b>2. Colonne delle coordinate:</b><br>"
                    "Seleziona le colonne corrispondenti alle coordinate X "
                    "(Longitudine/Est) e Y (Latitudine/Nord). "
                    "Il plugin converte automaticamente sia formati decimali "
                    "che sessagesimali (DMS).<br><br>"
                    "<b>3. CRS e Mappa:</b><br>"
                    "Seleziona il corretto Sistema di Riferimento. "
                    "L'anteprima sulla mappa verificherà la corretta "
                    "posizione dei punti.<br><br>"
                    "<b>4. Importa:</b><br>"
                    "Clicca su 'Importa e Salva in GeoPackage...'. "
                    "Verrà richiesto dove salvare il file. Se annulli "
                    "il salvataggio, verrà creato un layer temporaneo."
                ),
            },
            "en": {
                "win_title": "GeoCSV Mapper — GeoPackage & Map (v2.2.0)",
                "tab_import": "Import",
                "tab_help": "Help",
                "tab_info": "About & Authors",
                "btn_import": "Import and Save to GeoPackage...",
                "btn_cancel": "Cancel",
                "grp_file": "1. CSV File & Encoding",
                "txt_nofile": "No file selected…",
                "btn_browse": "Browse…",
                "lbl_enc": "Encoding:",
                "lbl_wait": "⚫ Waiting",
                "lbl_ok": "🟢 Operational",
                "lbl_err_enc": "🔴 Encoding Error",
                "lbl_err": "🔴 Error",
                "grp_coords": "2. Coordinate Columns",
                "lbl_x": "X Column (Lon/East):",
                "lbl_y": "Y Column (Lat/North):",
                "grp_crs": "3. Coordinate Reference System (CRS)",
                "grp_name": "4. Layer Name",
                "grp_map": "Map Preview",
                "grp_desc": "Application Description",
                "txt_desc": (
                    "This plugin is an advanced tool for the bulk "
                    "import of points via CSV files in QGIS.<br><br>"
                    "It offers a powerful parser for automatic "
                    "recognition of both standard decimal coordinates "
                    "and complex sexagesimal formats (DMS). It features "
                    "a quick preview on OpenStreetMap cartography, "
                    "real-time text encoding verification, and "
                    "automated export support to the modern GeoPackage "
                    "format."
                ),
                "role_luca": (
                    "<b>Role</b>: Creator & Technical Consultant<br>"
                    "<b>Email</b>: <a href='mailto:lucasti1988@gmail.com'>"
                    "lucasti1988@gmail.com</a><br>"
                    "<b>Mobile</b>: 3474565539<br>"
                    "<b>LinkedIn</b>: <a href='https://linkedin.com/in/"
                    "luca-casti-326359357'>luca-casti</a>"
                ),
                "role_sarino": (
                    "<b>Role</b>: Developer & Publisher<br>"
                    "<b>Email</b>: <a href='mailto:sino.grande@gmail.com'>"
                    "sino.grande@gmail.com</a><br>"
                    "<b>Website</b>: <a href='https://sinocloud.it'>"
                    "sinocloud.it</a><br>"
                    "<b>GitHub</b>: <a href='https://github.com/sag1687'>"
                    "sag1687</a>"
                ),
                "qr_missing": "Missing QR Code",
                "logo_missing": "Missing Logo",
                "msg_err": "Error",
                "msg_succ": "Success",
                "msg_gpkg_title": (
                    "Save as GeoPackage (Cancel to keep only a temporary "
                    "layer)"),
                "msg_err_read": "Unable to read the CSV file:",
                "msg_succ_gpkg": (
                    "Data saved and loaded from GeoPackage "
                    "successfully.\nPoints:"),
                "msg_err_gpkg": (
                    "Failed to save GeoPackage:\n{}\nA temporary layer will "
                    "be loaded instead."),
                "msg_succ_temp": "Temporary layer created.\nPoints:",
                "txt_help": (
                    "<b>GeoCSV Mapper User Guide</b><br><br>"
                    "<b>1. CSV File & Encoding:</b><br>"
                    "Select the CSV file using the 'Browse...' button. "
                    "Choose the correct encoding if special characters "
                    "are not read properly.<br><br>"
                    "<b>2. Coordinate Columns:</b><br>"
                    "Select the columns corresponding to the X "
                    "(Longitude/East) and Y (Latitude/North) coordinates. "
                    "The plugin automatically parses both decimal and "
                    "sexagesimal (DMS) formats.<br><br>"
                    "<b>3. CRS & Map:</b><br>"
                    "Select the correct Coordinate Reference System. "
                    "The map preview will verify that points are placed "
                    "correctly.<br><br>"
                    "<b>4. Import:</b><br>"
                    "Click on 'Import and Save to GeoPackage...'. You "
                    "will be asked where to save the file. If you cancel "
                    "the save dialog, a temporary layer will be loaded "
                    "instead."
                ),
            },
        }

        c = t[self.lang]

        self.setWindowTitle(c["win_title"])
        self.tabs.setTabText(0, c["tab_import"])
        self.tabs.setTabText(1, c["tab_help"])
        self.tabs.setTabText(2, c["tab_info"])
        self.help_text.setText(c["txt_help"])
        self.import_btn.setText(c["btn_import"])
        self.cancel_btn.setText(c["btn_cancel"])

        self.file_group.setTitle(c["grp_file"])
        if not self.csv_path:
            self.file_line.setPlaceholderText(c["txt_nofile"])
        self.browse_btn.setText(c["btn_browse"])
        self.enc_label.setText(c["lbl_enc"])

        if (
            "attesa" in self.status_icon.text()
            or "Waiting" in self.status_icon.text()
        ):
            self.status_icon.setText(c["lbl_wait"])
        elif (
            "Operativo" in self.status_icon.text()
            or "Operational" in self.status_icon.text()
        ):
            self.status_icon.setText(c["lbl_ok"])
        elif (
            "Codifica" in self.status_icon.text()
            or "Encoding" in self.status_icon.text()
        ):
            self.status_icon.setText(c["lbl_err_enc"])
        elif (
            "Errore" in self.status_icon.text()
            or "Error" in self.status_icon.text()
        ):
            self.status_icon.setText(c["lbl_err"])

        self.coords_group.setTitle(c["grp_coords"])
        self.x_label.setText(c["lbl_x"])
        self.y_label.setText(c["lbl_y"])

        self.crs_group.setTitle(c["grp_crs"])
        self.name_group.setTitle(c["grp_name"])
        self.right_panel.setTitle(c["grp_map"])

        self.desc_group.setTitle(c["grp_desc"])
        self.desc_label.setText(c["txt_desc"])

        self.luca_info.setText(c["role_luca"])
        self.sarino_info.setText(c["role_sarino"])

    # ------------------------------------------------------------------ #
    #  Logic                                                               #
    # ------------------------------------------------------------------ #
    def _browse_csv(self):
        c = "Seleziona file CSV" if self.lang == "it" else "Select CSV file"
        path, _ = QFileDialog.getOpenFileName(
            self,
            c,
            "",
            (
                "File CSV (*.csv *.txt *.tsv);;Tutti i file (*)"
                if self.lang == "it"
                else "CSV Files (*.csv *.txt *.tsv);;All files (*)"
            ),
        )
        if not path:
            return

        self.csv_path = path
        self.file_line.setText(path)
        base = os.path.splitext(os.path.basename(path))[0]
        self.layer_name_edit.setText(base)

        self._reload_csv()

    def _reload_csv(self):
        if not self.csv_path:
            return

        enc = self.encoding_combo.currentText()
        try:
            with open(self.csv_path, newline="", encoding=enc) as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                headers = [
                    h.strip() for h in (reader.fieldnames or []) if h.strip()
                ]

                rows = []
                for i, row in enumerate(reader):
                    if i > 1000:  # Limit preview read
                        break
                    rows.append(
                        {k.strip(): v.strip() for k, v in row.items() if k}
                    )

            self.csv_headers = headers
            self.csv_rows = rows

            self._populate_combos()
            self._autoselect_xy()

            lbl_ok = "🟢 Operativo" if self.lang == "it" else "🟢 Operational"
            self.status_icon.setText(lbl_ok)
            self.status_icon.setStyleSheet(
                "color: #2e7d32; font-weight: bold;"
            )
            self.import_btn.setEnabled(True)

            self._update_preview_map()

        except UnicodeDecodeError:
            lbl_err = (
                "🔴 Errore Codifica"
                if self.lang == "it"
                else "🔴 Encoding Error"
            )
            self.status_icon.setText(lbl_err)
            self.status_icon.setStyleSheet(
                "color: #c62828; font-weight: bold;"
            )
            self.import_btn.setEnabled(False)
        except Exception:
            lbl_err = "🔴 Errore" if self.lang == "it" else "🔴 Error"
            self.status_icon.setText(lbl_err)
            self.status_icon.setStyleSheet(
                "color: #c62828; font-weight: bold;"
            )
            self.import_btn.setEnabled(False)

    def _populate_combos(self):
        self.x_combo.blockSignals(True)
        self.y_combo.blockSignals(True)
        self.x_combo.clear()
        self.y_combo.clear()
        for h in self.csv_headers:
            self.x_combo.addItem(h)
            self.y_combo.addItem(h)
        self.x_combo.blockSignals(False)
        self.y_combo.blockSignals(False)

    def _autoselect_xy(self):
        self.x_combo.blockSignals(True)
        self.y_combo.blockSignals(True)

        x_keywords = [
            "x",
            "lon",
            "longitude",
            "lng",
            "east",
            "est",
            "easting",
            "coord_x",
            "x_coord",
        ]
        y_keywords = [
            "y",
            "lat",
            "latitude",
            "north",
            "nord",
            "northing",
            "coord_y",
            "y_coord",
        ]

        lower = [h.lower() for h in self.csv_headers]

        def best_match(keywords):
            for kw in keywords:
                if kw in lower:
                    return lower.index(kw)
            for kw in keywords:
                for i, h in enumerate(lower):
                    if kw in h:
                        return i
            return 0

        self.x_combo.setCurrentIndex(best_match(x_keywords))
        self.y_combo.setCurrentIndex(best_match(y_keywords))

        self.x_combo.blockSignals(False)
        self.y_combo.blockSignals(False)

    def _update_preview_map(self):
        if not self.csv_rows:
            return

        x_field = self.x_combo.currentText()
        y_field = self.y_combo.currentText()
        crs = self.crs_widget.crs()

        if not x_field or not y_field or not crs.isValid():
            return

        if self.preview_layer:
            QgsProject.instance().removeMapLayer(self.preview_layer.id())

        self.preview_layer = QgsMemoryProviderUtils.createMemoryLayer(
            "preview", QgsFields(), QgsWkbTypes.Point, crs
        )

        self.preview_layer.startEditing()
        count = 0
        for row in self.csv_rows[:50]:
            x_val = row.get(x_field, "")
            y_val = row.get(y_field, "")
            x = self._parse_coordinate(x_val)
            y = self._parse_coordinate(y_val)
            if x is not None and y is not None:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                self.preview_layer.addFeature(feat)
                count += 1
        self.preview_layer.commitChanges()

        if count > 0:
            self.preview_layer.renderer().symbol().setColor(QColor(255, 0, 0))
            self.preview_layer.renderer().symbol().setSize(3)

            QgsProject.instance().addMapLayer(self.preview_layer, False)

            layers = [self.preview_layer]
            if self.osm_layer and self.osm_layer.isValid():
                layers.append(self.osm_layer)

            self.map_canvas.setLayers(layers)

            extent = self.preview_layer.extent()
            if self.map_canvas.mapSettings().destinationCrs() != crs:
                transform = QgsCoordinateTransform(
                    crs,
                    self.map_canvas.mapSettings().destinationCrs(),
                    QgsProject.instance(),
                )
                try:
                    extent = transform.transformBoundingBox(extent)
                except Exception:
                    pass

            extent.scale(1.5)
            self.map_canvas.setExtent(extent)
            self.map_canvas.refresh()

    def _parse_coordinate(self, val):
        if not val:
            return None
        val = str(val).strip().replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

        val_lower = val.lower().strip()
        dir_mult = 1

        m_end = re.search(
            r"(?:^|[^a-z0-9])\s*(nord|est|sud|ovest|west|n|e|s|w|o)\s*$",
            val_lower,
        )
        if m_end:
            d = m_end.group(1)
            if d in ["sud", "ovest", "west", "s", "w", "o"]:
                dir_mult = -1
            val_lower = val_lower[: m_end.start(1)] + val_lower[m_end.end(1) :]
        else:
            m_start = re.search(
                r"^\s*(nord|est|sud|ovest|west|n|e|s|w|o)\s*(?:$|[^a-z0-9])",
                val_lower,
            )
            if m_start:
                d = m_start.group(1)
                if d in ["sud", "ovest", "west", "s", "w", "o"]:
                    dir_mult = -1
                val_lower = (
                    val_lower[: m_start.start(1)] + val_lower[m_start.end(1) :]
                )

        nums = [float(n) for n in re.findall(r"[-+]?\d*\.\d+|\d+", val_lower)]
        if not nums:
            return None
        if len(nums) == 1:
            return nums[0] * dir_mult
        elif len(nums) == 2:
            deg = nums[0]
            sign = -1 if deg < 0 or str(val).strip().startswith("-") else 1
            return sign * (abs(deg) + nums[1] / 60.0) * dir_mult
        elif len(nums) >= 3:
            deg = nums[0]
            sign = -1 if deg < 0 or str(val).strip().startswith("-") else 1
            return (
                sign
                * (abs(deg) + nums[1] / 60.0 + nums[2] / 3600.0)
                * dir_mult
            )
        return None

    def _on_import_clicked(self):
        if not self.csv_path:
            return

        x_field = self.x_combo.currentText()
        y_field = self.y_combo.currentText()
        crs = self.crs_widget.crs()
        layer_name = self.layer_name_edit.text().strip() or "CSV_Layer"
        enc = self.encoding_combo.currentText()

        t = {
            "it": {
                "msg_err": "Errore",
                "msg_succ": "Successo",
                "msg_err_read": "Impossibile leggere il file CSV:",
                "msg_gpkg_title": (
                    "Salva come GeoPackage (Annulla per mantenere solo "
                    "livello temporaneo)"),
                "msg_succ_gpkg": (
                    "Dati salvati e caricati da GeoPackage con "
                    "successo.\nPunti:"),
                "msg_err_gpkg": (
                    "Impossibile salvare in GeoPackage:\n{}\nVerrà caricato "
                    "il layer temporaneo."),
                "msg_succ_temp": "Layer temporaneo creato.\nPunti:",
            },
            "en": {
                "msg_err": "Error",
                "msg_succ": "Success",
                "msg_err_read": "Unable to read the CSV file:",
                "msg_gpkg_title": (
                    "Save as GeoPackage (Cancel to keep only a temporary "
                    "layer)"),
                "msg_succ_gpkg": (
                    "Data saved and loaded from GeoPackage "
                    "successfully.\nPoints:"),
                "msg_err_gpkg": (
                    "Failed to save GeoPackage:\n{}\nA temporary layer will "
                    "be loaded instead."),
                "msg_succ_temp": "Temporary layer created.\nPoints:",
            },
        }[self.lang]

        try:
            with open(self.csv_path, newline="", encoding=enc) as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                fieldnames = [
                    fn.strip()
                    for fn in (reader.fieldnames or [])
                    if fn.strip()
                ]
                all_rows = [
                    {k.strip(): v.strip() for k, v in row.items() if k}
                    for row in reader
                ]
        except Exception as e:
            QMessageBox.critical(
                self, t["msg_err"], f"{t['msg_err_read']} {e}"
            )
            return

        qgs_fields = QgsFields()
        for fname in fieldnames:
            qgs_fields.append(QgsField(fname, QVariant.String))

        mem_layer = QgsMemoryProviderUtils.createMemoryLayer(
            layer_name, qgs_fields, QgsWkbTypes.Point, crs
        )
        mem_layer.startEditing()

        for row in all_rows:
            x_val = row.get(x_field, "")
            y_val = row.get(y_field, "")
            x = self._parse_coordinate(x_val)
            y = self._parse_coordinate(y_val)
            if x is not None and y is not None:
                feat = QgsFeature(qgs_fields)
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                attrs = [row.get(fn, "") for fn in fieldnames]
                feat.setAttributes(attrs)
                mem_layer.addFeature(feat)

        mem_layer.commitChanges()

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            t["msg_gpkg_title"],
            f"{layer_name}.gpkg",
            "GeoPackage (*.gpkg)",
        )

        if save_path:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = layer_name
            options.fileEncoding = "UTF-8"

            error, err_msg, new_filename, new_layer = (
                QgsVectorFileWriter.writeAsVectorFormatV3(
                    mem_layer,
                    save_path,
                    QgsProject.instance().transformContext(),
                    options,
                )
            )

            if error == QgsVectorFileWriter.NoError:
                final_layer = QgsVectorLayer(
                    f"{save_path}|layername={layer_name}", layer_name, "ogr"
                )
                if final_layer.isValid():
                    QgsProject.instance().addMapLayer(final_layer)
                    QMessageBox.information(
                        self,
                        t["msg_succ"],
                        f"{t['msg_succ_gpkg']} {final_layer.featureCount()}",
                    )
                    self.accept()
                    return
            else:
                QMessageBox.warning(
                    self, t["msg_err"], t["msg_err_gpkg"].format(err_msg)
                )

        QgsProject.instance().addMapLayer(mem_layer)
        QMessageBox.information(
            self,
            t["msg_succ"],
            f"{t['msg_succ_temp']} {mem_layer.featureCount()}",
        )
        self.accept()

    def closeEvent(self, event):
        if self.preview_layer:
            QgsProject.instance().removeMapLayer(self.preview_layer.id())
        if self.osm_layer:
            QgsProject.instance().removeMapLayer(self.osm_layer.id())
        super().closeEvent(event)
