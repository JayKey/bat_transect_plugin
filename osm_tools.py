# osm_tools.py
import osmnx as ox
import networkx as nx
from shapely.geometry import Polygon
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsFeature, QgsField,
    QgsGeometry, Qgis,
    QgsRendererCategory, QgsLineSymbol, QgsCategorizedSymbolRenderer
)
from PyQt5.QtCore import QVariant

from shapely.geometry import shape
from shapely.ops import transform
import pyproj
from qgis.core import QgsSpatialIndex, QgsFeatureRequest
from collections.abc import Iterable


# Typy dróg i kolory
road_styles = {
    'motorway': '255,0,0',
    'primary': '255,128,0',
    'secondary': '255,200,0',
    'tertiary': '255,0,255',
    'residential': '200,200,200',
    'track': '0,255,0',
    'path': '0,128,255',
    'service': '160,160,160',
    'unclassified': '100,100,100',
    'footway': '100,100,255'
}

def flatten(value):
    """
    Rekurencyjnie spłaszcza dowolnie zagnieżdżoną strukturę listową,
    ignorując stringi i bajty jako iterowalne.
    """
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        result = []
        for item in value:
            result.extend(flatten(item))
        return result
    else:
        return [value]


def download_osm_roads_for_buffer(qgs_geometry, crs, iface, buffer_id, buffer_distance, excluded_highway_types=None, environment_preferences=None):
    print("Environment preferences:", environment_preferences)
    if excluded_highway_types is None:
        excluded_highway_types = []
    excluded_highway_types = [str(v) for v in excluded_highway_types]

    # Mapowanie typów środowiskowych na fragmenty nazw warstw
    layer_map = {
        'forest': 'lasy',
        'water': 'woda',
        'cave': 'jaskinie',
        'abandoned': 'pustostany'
    }

    env_layers = {}
    if environment_preferences:
        for key, name in layer_map.items():
            if environment_preferences.get(key):
                for layer in QgsProject.instance().mapLayers().values():
                    if name.lower() in layer.name().lower():
                        env_layers[key] = layer
                        break

    # Konwersja QGIS geometry -> Shapely
    shapely_geom = qgs_geometry.asPolygon()
    if not shapely_geom:
        shapely_geom = qgs_geometry.asMultiPolygon()[0]
    polygon = Polygon(shapely_geom[0])

    # Wyznaczenie centrum bufora
    centroid = polygon.centroid
    center_latlon = (polygon.centroid.y, polygon.centroid.x)

    try:
        # Pobieramy graf w oparciu o punkt + dystans
        G = ox.graph_from_point(center_latlon, dist=buffer_distance, network_type='all', simplify=True, truncate_by_edge=False)
        gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)

        # Przycinamy do faktycznego bufora
        gdf_edges = gdf_edges[gdf_edges.intersects(polygon)]

        # Filtrujemy drogi
        def should_exclude(highway_value):
            try:
                flat_values = flatten(highway_value)  # używa globalnej wersji
            except Exception as e:
                print(f"[ERROR flattening] value={highway_value} → {e}")
                return False
            print(f"flat_values={flat_values}")

            for val in flat_values:
                if val in excluded_highway_types:
                    return True

            return False

        print("Excluded highway types:", excluded_highway_types)
        print("Sample highway values:", gdf_edges['highway'].unique())

        iface.messageBar().pushMessage("OSM", f"Petla na drogi", level=Qgis.Info)
        print("excluded_highway_types (final):", excluded_highway_types)
        for i, val in enumerate(gdf_edges['highway']):
            try:
                _ = should_exclude(val)
            except Exception as e:
                print(f"[ERROR] row {i} → highway={val} (type={type(val)}) → {e}")
            else:
                print(f"[OK] row {i} → highway={val} (type={type(val)})")

        gdf_edges = gdf_edges[~gdf_edges['highway'].apply(should_exclude)]

        # Tworzenie tymczasowej warstwy
        temp_layer = QgsVectorLayer("LineString?crs=" + crs.authid(), f"Drogi transektu {buffer_id}", "memory")
        provider = temp_layer.dataProvider()
        provider.addAttributes([
            QgsField("highway", QVariant.String),
            QgsField("score", QVariant.Double)
        ])
        temp_layer.updateFields()

        # Tworzymy indeksy przestrzenne dla warstw środowiskowych
        env_indexes = {}
        for key, layer in env_layers.items():
            env_indexes[key] = QgsSpatialIndex(layer.getFeatures())

        features = []
        for _, row in gdf_edges.iterrows():
            highway_raw = row.get("highway", "")

            try:
                flat_values = flatten(highway_raw)
                if not flat_values:
                    highway = ""
                else:
                    highway = str(flat_values[0])
            except Exception as e:
                print(f"[ERROR] Failed to flatten highway value: {highway_raw} → {e}")
                highway = "unknown"

            print(f"[DEBUG] highway_raw={highway_raw} → flattened={flat_values} → used highway={highway}")

            geom = QgsGeometry.fromWkt(row["geometry"].wkt)
            score = 0.0

            # Liczymy score: bliskość do warstw środowiskowych
            for key, layer in env_layers.items():
                index = env_indexes[key]
                nearest_ids = index.nearestNeighbor(geom.boundingBox().center(), 1)
                if nearest_ids:
                    nearest_feat = next(layer.getFeatures(QgsFeatureRequest(nearest_ids[0])))
                    dist = geom.distance(nearest_feat.geometry())
                    if dist < 100:  # próg 100 m
                        score += 1 / (dist + 1)  # im bliżej, tym większy score

            feat = QgsFeature()
            feat.setGeometry(geom)
            feat.setAttributes([str(highway), score])
            features.append(feat)

        provider.addFeatures(features)
        temp_layer.updateExtents()

        iface.messageBar().pushMessage("OSM", f"Stylizacja", level=Qgis.Info)
        # Stylizacja
        categories = []
        for road_type, color in road_styles.items():
            symbol = QgsLineSymbol.createSimple({"color": color, "width": "0.8"})
            category = QgsRendererCategory(road_type, symbol, road_type)
            categories.append(category)
        renderer = QgsCategorizedSymbolRenderer("highway", categories)
        temp_layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(temp_layer)
        iface.messageBar().pushMessage("OSM", f"Added roads for buffer {buffer_id}", level=Qgis.Info)

    except Exception as e:
        iface.messageBar().pushMessage("OSM Error", str(e), level=Qgis.Critical)
