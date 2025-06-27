import networkx as nx
from shapely.geometry import LineString
from shapely.ops import linemerge
from qgis.core import (
    QgsFeature, QgsGeometry, QgsVectorLayer, QgsProject, QgsField, Qgis, QgsPointXY
)
from PyQt5.QtCore import QVariant
from qgis.core import QgsDistanceArea
from qgis.PyQt.QtGui import QColor

from shapely.geometry import LineString
from qgis.core import (
    QgsFeature, QgsGeometry, QgsVectorLayer, QgsProject, QgsField, QgsPointXY, Qgis
)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor
from math import radians, cos, sin, asin, sqrt


def find_min_500m_path_in_layer(layer, iface, prefer_score=True):
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

        #-----------------------------------------------------------------------------

        length = d.measureLength(QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in line]))

        # Pobierz score z atrybutów feature, domyślnie 0
        score = feat['score'] if 'score' in feat.fields().names() else 0.0
        try:
            score = float(score)
        except:
            score = 0.0

        # Jeśli preferujemy score, zmodyfikuj wagę
        if prefer_score and score > 0:
            weight = length / (1 + score)  # im wyższy score, tym mniejsza "kosztowa" długość
        else:
            weight = length

        G.add_edge(start, end, weight=weight, geometry=LineString(line))

        #-------------------------------------------------------------------------------

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

# ----------------------------------------------------------------------------------------------

def haversine_distance(p1, p2):
    lon1, lat1 = p1.x(), p1.y()
    lon2, lat2 = p2.x(), p2.y()
    R = 6371000
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * asin(sqrt(a))

def build_road_graph(road_layer):
    G = nx.Graph()
    for feat in road_layer.getFeatures():
        geom = feat.geometry()
        line = geom.asPolyline() or geom.asMultiPolyline()[0]
        if len(line) < 2:
            continue
        for i in range(len(line) - 1):
            p1 = tuple(line[i])
            p2 = tuple(line[i + 1])
            dist = QgsGeometry.fromPolylineXY([QgsPointXY(*p1), QgsPointXY(*p2)]).length()
            G.add_edge(p1, p2, weight=dist, geometry=LineString([p1, p2]))
    return G

def snap_to_graph(point, G, max_dist=50):
    nearest = min(G.nodes, key=lambda n: haversine_distance(point, QgsPointXY(*n)))
    if haversine_distance(point, QgsPointXY(*nearest)) > max_dist:
        return None
    return nearest

def shortest_path_geometry(G, p1, p2):
    try:
        nodes = nx.shortest_path(G, source=p1, target=p2, weight='weight')
    except nx.NetworkXNoPath:
        return []

    geometries = []
    for i in range(len(nodes) - 1):
        u = nodes[i]
        v = nodes[i + 1]
        edge_data = G.get_edge_data(u, v)
        if edge_data and 'geometry' in edge_data:
            geometries.append(edge_data['geometry'])
    return geometries

def connect_transects_via_osm(transect_layer, road_layer, iface):
    if not transect_layer or transect_layer.geometryType() != 1:
        iface.messageBar().pushMessage("Błąd", "Warstwa transektów musi zawierać linie!", level=Qgis.Critical)
        return

    G = build_road_graph(road_layer)

    transects = []
    for feat in transect_layer.getFeatures():
        geom = feat.geometry()
        line = geom.asPolyline() or geom.asMultiPolyline()[0]
        if len(line) < 2:
            continue
        start = QgsPointXY(*line[0])
        end = QgsPointXY(*line[-1])
        transects.append({
            'start': start,
            'end': end,
            'line': line,
            'id': feat.id()
        })

    if not transects:
        iface.messageBar().pushMessage("Brak danych", "Nie znaleziono transektów.", level=Qgis.Warning)
        return

    unvisited = transects[1:]
    current = transects[0]
    path_segments = []

    line_coords = [(pt.x(), pt.y()) for pt in current['line']]
    if line_coords[0] != (current['start'].x(), current['start'].y()):
        line_coords = list(reversed(line_coords))
    path_segments.append(LineString(line_coords))

    while unvisited:
        nearest = min(unvisited, key=lambda t: haversine_distance(current['end'], t['start']))

        try:
            p1 = snap_to_graph(current['end'], G, max_dist=1200)
            p2 = snap_to_graph(nearest['start'], G, max_dist=1200)

            if p1 is None or p2 is None or p1 not in G.nodes or p2 not in G.nodes:
                iface.messageBar().pushMessage("Brak połączenia",
                                               f"Brak drogi pomiędzy {current['id']} a {nearest['id']}",
                                               level=Qgis.Warning)
                return
            print(f"[DEBUG] current['end']: {current['end']}, snapped to: {p1}")
            print(f"[DEBUG] nearest['start']: {nearest['start']}, snapped to: {p2}")

        except ValueError:
            iface.messageBar().pushMessage("Błąd", "Nie można dopasować punktów do grafu OSM", level=Qgis.Critical)
            return

        print(f"[DEBUG] Próba połączenia transektów {current['id']} → {nearest['id']} przez {p1} → {p2}")
        road_path = shortest_path_geometry(G, p1, p2)
        if not road_path:
            iface.messageBar().pushMessage("Brak połączenia", f"Brak drogi pomiędzy {current['id']} a {nearest['id']}", level=Qgis.Warning)
            return

        path_segments.extend(road_path)

        next_line = [(pt.x(), pt.y()) for pt in nearest['line']]
        if next_line[0] != (nearest['start'].x(), nearest['start'].y()):
            next_line = list(reversed(next_line))
        path_segments.append(LineString(next_line))

        current = nearest
        unvisited.remove(nearest)

    output = QgsVectorLayer(f"LineString?crs={transect_layer.crs().authid()}", "Połączone transekty (OSM)", "memory")
    provider = output.dataProvider()
    provider.addAttributes([QgsField("length_m", QVariant.Double)])
    output.updateFields()

    for geom in path_segments:
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromWkt(geom.wkt))
        feat.setAttributes([geom.length])
        provider.addFeature(feat)

    output.updateExtents()
    symbol = output.renderer().symbol()
    symbol.setWidth(1.2)
    symbol.setColor(QColor("darkgreen"))
    output.triggerRepaint()
    QgsProject.instance().addMapLayer(output)

    iface.messageBar().pushMessage("OK", "Połączono transekty przez sieć OSM!", level=Qgis.Success)
