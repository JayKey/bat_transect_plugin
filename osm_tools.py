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
import geopandas as gpd


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

def download_osm_environment_layers(polygon):
    """
    Pobiera warstwy środowiskowe z OSM w granicach danego wielokąta.
    """
    bbox = polygon.bounds  # (minx, miny, maxx, maxy)

    tags = {
        "landuse": ["forest"],
        "natural": ["water", "cave_entrance"]
    }

    all_layers = {}

    for key, values in tags.items():
        for value in values:
            try:
                gdf = ox.geometries_from_bbox(bbox[3], bbox[1], bbox[2], bbox[0], {key: value})
                if not gdf.empty:
                    all_layers[f"{key}_{value}"] = gdf
            except Exception as e:
                print(f"[ERROR] Failed to download {key}={value} → {e}")

    return all_layers

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


def download_osm_roads_for_buffer(
        qgs_geometry, crs, iface, buffer_id, buffer_distance,
        excluded_highway_types=None, environment_preferences=None
):
    from shapely.geometry import Polygon as ShapelyPolygon

    if excluded_highway_types is None:
        excluded_highway_types = []
    excluded_highway_types = [str(v) for v in excluded_highway_types]

    # 1. Konwersja QGIS geometry -> Shapely Polygon
    shapely_geom = qgs_geometry.asPolygon()
    if not shapely_geom:
        shapely_geom = qgs_geometry.asMultiPolygon()[0]
    polygon = ShapelyPolygon(shapely_geom[0])

    # 2. Pobierz wybrane warstwy środowiskowe z OSM
    env_gdfs_all = download_osm_environment_layers(polygon)
    env_layers = {}
    env_indexes = {}
    for key, gdf in env_gdfs_all.items():
        env_type = key.split('_')[-1]
        if environment_preferences and not environment_preferences.get(env_type, False):
            continue  # Pomijaj nie wybrane

        gdf_qgs = QgsVectorLayer("Polygon?crs=EPSG:4326", key, "memory")
        prov = gdf_qgs.dataProvider()
        prov.addAttributes([QgsField("osm_id", QVariant.String)])
        gdf_qgs.updateFields()

        feats = []
        for _, row in gdf.iterrows():
            if row.geometry.is_valid:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
                feat.setAttributes([str(row.get("osmid", ""))])
                feats.append(feat)
        prov.addFeatures(feats)
        gdf_qgs.updateExtents()
        QgsProject.instance().addMapLayer(gdf_qgs)

        env_layers[env_type] = gdf_qgs
        env_indexes[env_type] = QgsSpatialIndex(gdf_qgs.getFeatures())

    # Pobierz max dystans z GUI, domyślnie 100
    max_distance = 100
    if environment_preferences and 'max_distance' in environment_preferences:
        try:
            max_distance = float(environment_preferences['max_distance'])
        except Exception:
            pass

    # 4. Pobieranie dróg
    centroid = polygon.centroid
    center_latlon = (centroid.y, centroid.x)
    G = ox.graph_from_point(center_latlon, dist=buffer_distance, network_type='all', simplify=True, truncate_by_edge=False)
    gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
    gdf_edges = gdf_edges[gdf_edges.intersects(polygon)]

    def flatten(value):
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            result = []
            for item in value:
                result.extend(flatten(item))
            return result
        else:
            return [value]

    def should_exclude(highway_value):
        try:
            flat_values = flatten(highway_value)
        except Exception as e:
            print(f"[ERROR flattening] value={highway_value} → {e}")
            return False
        for val in flat_values:
            if val in excluded_highway_types:
                return True
        return False

    gdf_edges = gdf_edges[~gdf_edges['highway'].apply(should_exclude)]

    # 5. Warstwa QGIS na drogi
    temp_layer = QgsVectorLayer("LineString?crs=" + crs.authid(), f"Drogi transektu {buffer_id}", "memory")
    provider = temp_layer.dataProvider()
    provider.addAttributes([
        QgsField("highway", QVariant.String),
        QgsField("score", QVariant.Double)
    ])
    temp_layer.updateFields()

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

        geom = QgsGeometry.fromWkt(row["geometry"].wkt)
        score = 0.0

        # 6. Score — bliskość do każdej wybranej warstwy środowiskowej
        for env_type, index in env_indexes.items():
            nearest_ids = index.nearestNeighbor(geom.boundingBox().center(), 1)
            if nearest_ids:
                layer = env_layers[env_type]
                nearest_feat = next(layer.getFeatures(QgsFeatureRequest(nearest_ids[0])))
                dist = geom.distance(nearest_feat.geometry())
                if dist < max_distance:
                    score += 1 / (dist + 1)  # im bliżej, tym wyższy score

        feat = QgsFeature()
        feat.setGeometry(geom)
        feat.setAttributes([str(highway), score])
        features.append(feat)

    provider.addFeatures(features)
    temp_layer.updateExtents()

    # 7. Stylizacja
    categories = []
    for road_type, color in road_styles.items():
        symbol = QgsLineSymbol.createSimple({"color": color, "width": "0.8"})
        category = QgsRendererCategory(road_type, symbol, road_type)
        categories.append(category)
    renderer = QgsCategorizedSymbolRenderer("highway", categories)
    temp_layer.setRenderer(renderer)

    QgsProject.instance().addMapLayer(temp_layer)
    iface.messageBar().pushMessage("OSM", f"Added roads for buffer {buffer_id}", level=Qgis.Info)

