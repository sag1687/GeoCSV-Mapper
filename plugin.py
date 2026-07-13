# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtGui import QIcon

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from .dialog import CsvImporterDialog


class CsvImporterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.menu_name = "GeoCSV Mapper"

    def initGui(self):
        from qgis.core import QgsApplication

        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            icon = QgsApplication.getThemeIcon(
                "/mActionAddDelimitedTextLayer.svg"
            )

        self.action = QAction(
            icon, "GeoCSV Mapper - Importa XY", self.iface.mainWindow()
        )
        self.action.setToolTip(
            "Importa un file CSV con colonne X/Y come layer temporaneo"
        )
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(self.menu_name, self.action)

    def unload(self):
        self.iface.removePluginVectorMenu(self.menu_name, self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.action:
            del self.action

    def run(self):
        dialog = CsvImporterDialog(self.iface)
        dialog.exec()
