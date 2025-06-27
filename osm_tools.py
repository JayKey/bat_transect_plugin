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


def download_osm_roads_for_buffer(qgs_geometry, crs, iface, buffer_id, buffer_distance, excluded_highway_types=None, environment_preferences=None):
    print("Environment preferences:", environment_preferences)
    if excluded_highway_types is None:
        excluded_highway_types = []

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
            if isinstance(highway_value, list):
                return any(htype in excluded_highway_types for htype in highway_value)
            return highway_value in excluded_highway_types

        print("Excluded highway types:", excluded_highway_types)
        print("Sample highway values:", gdf_edges['highway'].unique())

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
            highway = row.get("highway", "")
            if isinstance(highway, list):
                highway = highway[0]
            elif highway is None:
                highway = ""

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
