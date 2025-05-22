import networkx as nx
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from qgis.core import (
    QgsFeature, QgsGeometry, QgsVectorLayer, QgsProject, QgsField
)
from PyQt5.QtCore import QVariant
from qgis.core import Qgis
from qgis.core import QgsPointXY

def find_min_500m_path_in_layer(layer, iface):
    if layer is None or layer.geometryType() != 1:
        iface.messageBar().pushMessage("Błąd", "Warstwa musi zawierać linie!", level=Qgis.Critical)
        return

    G = nx.Graph()
    edge_geoms = {}

    for feat in layer.getFeatures():
        geom = feat.geometry()
        if not geom:
            continue

        line = geom.asPolyline()
        if not line:
            line = geom.asMultiPolyline()[0]
        if len(line) < 2:
            continue

        start = tuple(line[0])
        end = tuple(line[-1])
        length = QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in line]).length()

        G.add_edge(start, end, weight=length, geometry=LineString(line))
        edge_geoms[(start, end)] = LineString(line)

    # Szukamy ścieżek >= 500 m
    min_path = None
    min_length = float('inf')

    for source in G.nodes():
        for target in G.nodes():
            if source == target:
                continue
            try:
                path = nx.shortest_path(G, source=source, target=target, weight='weight')
                length = sum(
                    G.edges[path[i], path[i+1]]['weight']
                    for i in range(len(path) - 1)
                )
                if length >= 500 and length < min_length:
                    min_length = length
                    min_path = path
            except nx.NetworkXNoPath:
                continue

    if not min_path:
        iface.messageBar().pushMessage("Brak trasy", "Nie znaleziono żadnej trasy ≥ 500 m", level=Qgis.Warning)
        return

    # Tworzymy geometrię z wybranej ścieżki
    segments = []
    for i in range(len(min_path) - 1):
        edge = G.edges[min_path[i], min_path[i+1]]
        segments.append(edge['geometry'])

    merged = linemerge(segments)

    # Dodajemy jako nową warstwę
    output_layer = QgsVectorLayer("LineString?crs=" + layer.crs().authid(), "Trasa ≥ 500 m", "memory")
    provider = output_layer.dataProvider()
    provider.addAttributes([QgsField("length_m", QVariant.Double)])
    output_layer.updateFields()

    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromWkt(merged.wkt))
    feat.setAttributes([min_length])
    provider.addFeature(feat)

    output_layer.updateExtents()
    QgsProject.instance().addMapLayer(output_layer)
    iface.messageBar().pushMessage("OK", f"Znaleziono trasę: {int(min_length)} m", level=Qgis.Success)
