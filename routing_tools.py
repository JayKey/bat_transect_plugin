import networkx as nx
from shapely.geometry import LineString
from shapely.ops import linemerge
from qgis.core import (
    QgsFeature, QgsGeometry, QgsVectorLayer, QgsProject, QgsField, Qgis, QgsPointXY
)
from PyQt5.QtCore import QVariant
from qgis.core import QgsDistanceArea
from qgis.PyQt.QtGui import QColor


def find_min_500m_path_in_layer(layer, iface):
    if layer is None or layer.geometryType() != 1:
        iface.messageBar().pushMessage("Błąd", "Warstwa musi zawierać linie!", level=Qgis.Critical)
        return

    G = nx.Graph()
    edge_geoms = {}

    # Wspólna warstwa --------------------------------------------------------------------------
    if not hasattr(find_min_500m_path_in_layer, "combined_layer"):
        find_min_500m_path_in_layer.combined_layer = QgsVectorLayer("LineString?crs=" + layer.crs().authid(),
                                                                    "Wszystkie trasy", "memory")
        prov = find_min_500m_path_in_layer.combined_layer.dataProvider()
        prov.addAttributes([QgsField("length_m", QVariant.Double)])
        find_min_500m_path_in_layer.combined_layer.updateFields()
        QgsProject.instance().addMapLayer(find_min_500m_path_in_layer.combined_layer)

    combined_layer = find_min_500m_path_in_layer.combined_layer

    symbol = combined_layer.renderer().symbol()
    symbol.setWidth(1.2)  # grubość linii w mm
    symbol.setColor(QColor("orange"))  # kolor linii
    combined_layer.triggerRepaint()
    # End of Wspólna warstwa -------------------------------------------------------------------

    iface.messageBar().pushMessage(
        "DEBUG",
        f"Węzły: {len(G.nodes())}, krawędzie: {len(G.edges())}",
        level=Qgis.Info
    )

    print("[DEBUG] Buduję graf...")
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if not geom:
            continue

        line = geom.asPolyline()
        if not line:
            line = geom.asMultiPolyline()[0]
        if len(line) < 2:
            print("[DEBUG] Pominięto geometrię z <2 punktami")
            continue

        start = tuple(line[0])
        end = tuple(line[-1])
        d = QgsDistanceArea()
        d.setEllipsoid('WGS84')
        length = d.measureLength(QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in line]))

        print(f"[DEBUG] CRS warstwy: {layer.crs().authid()}")
        print(f"[DEBUG] Surowa długość (QGIS): {length:.2f}")

        if length > 300:
            iface.messageBar().pushMessage(
                "DEBUG", f"Krawędź {start}–{end} ma długość {int(length)} m", level=Qgis.Info
            )

        print(f"[DEBUG] Krawędź: {start} → {end}, długość: {length:.2f} m")
        G.add_edge(start, end, weight=length, geometry=LineString(line))
        edge_geoms[(start, end)] = LineString(line)
        edge_geoms[(end, start)] = LineString(list(reversed(line)))

    print(f"[DEBUG] Węzły: {len(G.nodes())}, Krawędzie: {len(G.edges())}")

    min_path = None
    min_length = float('inf')
    nodes = list(G.nodes())

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            source = nodes[i]
            target = nodes[j]

            found_paths = 0

            try:
                for path in nx.all_simple_paths(G, source=source, target=target, cutoff=10):
                    found_paths += 1
                    length = sum(
                        G.edges[path[k], path[k + 1]]['weight']
                        for k in range(len(path) - 1)
                    )
                    print(f"[DEBUG] Path {source} → {target} przez {len(path)} punktów: {length:.2f} m")
                    if 500 <= length < min_length:
                        min_length = length
                        min_path = path

                iface.messageBar().pushMessage(
                    "DEBUG", f"Liczba sprawdzonych ścieżek: {found_paths}", level=Qgis.Info
                )
            except nx.NetworkXNoPath:
                continue

    if not min_path:
        iface.messageBar().pushMessage("Brak trasy", "Nie znaleziono ścieżki ≥ 500 m", level=Qgis.Warning)
        print("[DEBUG] Nie znaleziono żadnej ścieżki ≥ 500 m")
        return

    segments = []
    for i in range(len(min_path) - 1):
        edge = G.edges[min_path[i], min_path[i + 1]]
        segments.append(edge['geometry'])

    merged = linemerge(segments)

    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromWkt(merged.wkt))
    feat.setAttributes([min_length])
    combined_layer.dataProvider().addFeature(feat)
    combined_layer.updateExtents()
    combined_layer.triggerRepaint()

    iface.messageBar().pushMessage("OK", f"Znaleziono trasę: {int(min_length)} m", level=Qgis.Success)
