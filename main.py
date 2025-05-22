from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import Qgis

from . import resources
from . import osm_tools
from . import routing_tools
from .bat_transects_dialog import BatTransectsDialog

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes,
    QgsFeature,
    QgsVectorLayer,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorDataProvider,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsCoordinateTransform,
    QgsUnitTypes,
)
from PyQt5.QtCore import QVariant
from qgis.core import QgsFillSymbol, QgsSimpleFillSymbolLayer

class BatTransectsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.route_action = None

    def initGui(self):
        # Ładujemy ikonę z resources.qrc (np. ":/icon.png")
        icon = QIcon(":/icon.png")

        # Tworzymy akcję z ikoną i nazwą
        self.action = QAction(icon, "Bat Transects", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        # Dodajemy ikonę do paska narzędzi QGIS
        self.iface.addToolBarIcon(self.action)

        # Dodajemy ikonę + nazwę do menu „Wtyczki”
        self.iface.addPluginToMenu("&Bat Transects", self.action)

        # Przycisk: wyznacz trasę 500 m
        route_icon = QIcon(":/icon.png")  # albo inna ikona
        self.route_action = QAction(route_icon, "Wyznacz trasę 500 m", self.iface.mainWindow())
        self.route_action.triggered.connect(self.run_route_search)
        self.iface.addToolBarIcon(self.route_action)
        self.iface.addPluginToMenu("&Bat Transects", self.route_action)

    def unload(self):
        # Usuwanie przy wyłączaniu wtyczki
        self.iface.removePluginMenu("&Bat Transects", self.action)
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&Bat Transects", self.route_action)
        self.iface.removeToolBarIcon(self.route_action)

    def run(self):
        self.dialog = BatTransectsDialog()

        # Załaduj listę punktowych warstw z projektu
        layers = [layer for layer in QgsProject.instance().mapLayers().values() if
                  layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry]
        self.dialog.layerComboBox.clear()
        for layer in layers:
            self.dialog.layerComboBox.addItem(layer.name(), layer)

        self.dialog.bufferLineEdit.setText("500")  # domyślny promień
        self.dialog.generateButton.clicked.connect(self.generate_transects)

        self.dialog.show()

    def generate_transects(self):
        layer = self.dialog.layerComboBox.currentData()
        buffer_distance = float(self.dialog.bufferLineEdit.text())

        if layer is None or buffer_distance <= 0:
            self.iface.messageBar().pushMessage("Błąd", "Brak warstwy lub nieprawidłowy bufor.", level=Qgis.Critical)
            return

        source_crs = layer.crs()
        map_crs = QgsCoordinateReferenceSystem("EPSG:3857")  # układ metryczny
        transform_to_buffer = QgsCoordinateTransform(source_crs, map_crs, QgsProject.instance())
        transform_back = QgsCoordinateTransform(map_crs, source_crs, QgsProject.instance())

        # Czy CRS jest już metryczny?
        crs_is_metric = source_crs.mapUnits() == QgsUnitTypes.DistanceMeters

        buffer_layer = QgsVectorLayer("Polygon?crs=" + source_crs.authid(), "Bufory transektów", "memory")
        provider = buffer_layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int)])
        buffer_layer.updateFields()

        for i, feature in enumerate(layer.getFeatures()):
            geom = feature.geometry()
            if geom.isEmpty():
                continue

            if not crs_is_metric:
                geom.transform(transform_to_buffer)

            buffer_geom = geom.buffer(buffer_distance, 16)

            if not crs_is_metric:
                buffer_geom.transform(transform_back)

            new_feature = QgsFeature()
            new_feature.setGeometry(buffer_geom)
            new_feature.setAttributes([i + 1])
            provider.addFeature(new_feature)
            osm_tools.download_osm_roads_for_buffer(buffer_geom, source_crs, self.iface, i + 1)

        buffer_layer.updateExtents()

        symbol = QgsFillSymbol.createSimple({
            'color': '255,0,0,100',  # czerwony, przezroczystość 100 (z 255)
            'outline_color': '255,0,0',
            'outline_width': '0.5'
        })
        buffer_layer.renderer().setSymbol(symbol)

        QgsProject.instance().addMapLayer(buffer_layer)

        self.iface.messageBar().pushMessage("Sukces", "Dodano warstwę buforów.", level=Qgis.Success)

        self.dialog.close()

    def run_route_search(self):
        layer = self.iface.activeLayer()
        routing_tools.find_min_500m_path_in_layer(layer, self.iface)