# main.py
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import Qgis

from .osm_tools import download_osm_environment_layers
from PyQt5.QtGui import QColor

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

from PyQt5.QtWidgets import QToolButton, QMenu

class BatTransectsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.route_action = None

    def initGui(self):
        # Ikona przycisku
        icon = QIcon(":/icon.png")

        # 🔹 Akcja główna – wykonuje wszystkie kroki
        self.action_run_all = QAction(QIcon(":/icon.png"), "Wyznacz trasę", self.iface.mainWindow())
        self.action_run_all.triggered.connect(self.run_all_steps)

        # 🔹 Akcja: Wyznacz transekty
        self.action_run_transect = QAction("Wyznacz bufory i znajdź drogi", self.iface.mainWindow())
        self.action_run_transect.triggered.connect(self.run)

        # 🔹 Akcja: Wyznacz ścieżkę 500 m
        self.action_find_500m = QAction("Wyznacz ścieżkę 500 m", self.iface.mainWindow())
        self.action_find_500m.triggered.connect(self.run_route_search)

        # 🔹 Akcja: Połącz po drogach OSM
        self.action_connect_osm = QAction("Połącz transekty", self.iface.mainWindow())
        self.action_connect_osm.triggered.connect(self.run_connect_transects)

        # 🔹 Menu rozwijane
        menu = QMenu()
        menu.addAction(self.action_run_transect)
        menu.addAction(self.action_find_500m)
        menu.addAction(self.action_connect_osm)

        # 🔹 Przyciski z menu i akcją główną
        self.button_main = QToolButton()
        self.button_main.setIcon(icon)
        self.button_main.setToolTip("Wyznacz trasę")
        self.button_main.setPopupMode(QToolButton.MenuButtonPopup)
        self.button_main.setDefaultAction(self.action_run_all)
        self.button_main.setMenu(menu)

        # 🔹 Dodanie przycisku do paska narzędzi QGIS
        self.iface.addToolBarWidget(self.button_main)

    def unload(self):
        # Usuwanie przy wyłączaniu wtyczki
        self.iface.removePluginMenu("&Bat Transects", self.action)
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&Bat Transects", self.route_action)
        self.iface.removeToolBarIcon(self.route_action)
        self.iface.removeToolBarIcon(self.connect_transects_action)
        self.iface.removePluginMenu("Bat Transect Plugin", self.connect_transects_action)

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
            if buffer_geom is None or buffer_geom.isEmpty():
                print(f"[DEBUG] Punkt {i + 1} → bufor pusty lub None!")
                continue

            if not crs_is_metric:
                buffer_geom.transform(transform_back)

            new_feature = QgsFeature()
            new_feature.setGeometry(buffer_geom)
            new_feature.setAttributes([i + 1])
            provider.addFeature(new_feature)

            excluded_types = []
            if self.dialog.checkMotorway.isChecked():
                excluded_types.append("motorway")
            if self.dialog.checkPrimary.isChecked():
                excluded_types.append("primary")
            if self.dialog.checkSecondary.isChecked():
                excluded_types.append("secondary")
            if self.dialog.checkTertiary.isChecked():
                excluded_types.append("tertiary")
            if self.dialog.checkResidential.isChecked():
                excluded_types.append("residential")
            if self.dialog.checkTrack.isChecked():
                excluded_types.append("track")
            if self.dialog.checkPath.isChecked():
                excluded_types.append("path")
            if self.dialog.checkService.isChecked():
                excluded_types.append("service")
            if self.dialog.checkUnclassified.isChecked():
                excluded_types.append("unclassified")
            if self.dialog.checkFootway.isChecked():
                excluded_types.append("footway")

            # Odczytujemy preferencje środowiskowe z UI
            environment_preferences = {
                'forest': self.dialog.checkForest.isChecked(),
                'water': self.dialog.checkWater.isChecked(),
                'cave': self.dialog.checkCave.isChecked(),
                'abandoned': self.dialog.checkAbandoned.isChecked(),
                'max_distance': self.dialog.lineEditMaxDistance.text()
            }

            osm_tools.download_osm_roads_for_buffer(
                buffer_geom,
                source_crs,
                self.iface,
                i + 1,
                buffer_distance,
                excluded_types,
                environment_preferences
            )
            print(f"[DEBUG] Wywołuję OSM download dla punktu {i + 1}, bufor: {buffer_geom.asWkt()[:100]}...")

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

    def run_connect_transects(self):
        transect_layer = self.iface.activeLayer()
        if not transect_layer:
            self.iface.messageBar().pushMessage("Błąd", "Nie wybrano warstwy transektów!", level=Qgis.Critical)
            return

        # Szukamy warstwy z drogami – po nazwie zawierającej "drogi" lub "roads"
        road_layer = None
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name().lower().startswith("drogi") or "roads" in layer.name().lower():
                road_layer = layer
                break

        if not road_layer:
            self.iface.messageBar().pushMessage("Błąd", "Nie znaleziono warstwy dróg (nazwa zaczynająca się od 'drogi').", level=Qgis.Critical)
            return

        routing_tools.connect_transects_via_osm(transect_layer, road_layer, self.iface)

    def run_all_steps(self):
        self.dialog = BatTransectsDialog()

        layers = [layer for layer in QgsProject.instance().mapLayers().values()
                  if layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry]

        self.dialog.layerComboBox.clear()
        for layer in layers:
            self.dialog.layerComboBox.addItem(layer.name(), layer)

        self.dialog.bufferLineEdit.setText("500")
        self.dialog.generateButton.clicked.connect(self.run_all_steps_generate)

        self.dialog.show()

    def run_all_steps_generate(self):
        layer = self.dialog.layerComboBox.currentData()
        try:
            buffer_distance = float(self.dialog.bufferLineEdit.text())
        except ValueError:
            self.iface.messageBar().pushMessage("Błąd", "Nieprawidłowa wartość bufora.", level=Qgis.Critical)
            return

        if layer is None or buffer_distance <= 0:
            self.iface.messageBar().pushMessage("Błąd", "Brak warstwy lub nieprawidłowy bufor.", level=Qgis.Critical)
            return

        self.generate_and_process(layer, buffer_distance)
        self.dialog.close()

    def generate_and_process(self, selected_layer, buffer_distance):
        source_crs = selected_layer.crs()
        map_crs = QgsCoordinateReferenceSystem("EPSG:3857")
        transform_to_buffer = QgsCoordinateTransform(source_crs, map_crs, QgsProject.instance())
        transform_back = QgsCoordinateTransform(map_crs, source_crs, QgsProject.instance())
        crs_is_metric = source_crs.mapUnits() == QgsUnitTypes.DistanceMeters
        print(f"[DEBUG] CRS warstwy: {source_crs.authid()}, metryczne: {crs_is_metric}")

        buffer_layer = QgsVectorLayer("Polygon?crs=" + source_crs.authid(), "Bufory transektów", "memory")
        provider = buffer_layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int)])
        buffer_layer.updateFields()

        for i, feature in enumerate(selected_layer.getFeatures()):
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

            osm_tools.download_osm_roads_for_buffer(buffer_geom, source_crs, self.iface, i + 1, buffer_distance)

        buffer_layer.updateExtents()
        symbol = QgsFillSymbol.createSimple(
            {'color': '255,0,0,100', 'outline_color': '255,0,0', 'outline_width': '0.5'})
        buffer_layer.renderer().setSymbol(symbol)
        QgsProject.instance().addMapLayer(buffer_layer)

        self.iface.messageBar().pushMessage("Sukces", "Dodano warstwę buforów.", level=Qgis.Success)

        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name().lower().startswith("trasa") or "transekt" in lyr.name().lower():
                routing_tools.find_min_500m_path_in_layer(lyr, self.iface)

        road_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if "drogi" in lyr.name().lower() or "roads" in lyr.name().lower():
                road_layer = lyr
                break

