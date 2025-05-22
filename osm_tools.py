import osmnx as ox
import networkx as nx
from shapely.geometry import Polygon
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsFeature, QgsField,
    QgsGeometry, Qgis,
    QgsRendererCategory, QgsLineSymbol, QgsCategorizedSymbolRenderer
)
from PyQt5.QtCore import QVariant

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

def download_osm_roads_for_buffer(qgs_geometry, crs, iface, buffer_id):
    # Zamiana QGIS geometry -> Shapely
    shapely_geom = qgs_geometry.asPolygon()
    if not shapely_geom:
        shapely_geom = qgs_geometry.asMultiPolygon()[0]
    polygon = Polygon(shapely_geom[0])

    try:
        G = ox.graph_from_polygon(polygon, network_type='all', simplify=True, truncate_by_edge=False)
        gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)

        # Tworzenie warstwy tymczasowej QGIS
        temp_layer = QgsVectorLayer("LineString?crs=" + crs.authid(), f"Drogi transektu {buffer_id}", "memory")
        provider = temp_layer.dataProvider()
        provider.addAttributes([QgsField("highway", QVariant.String)])
        temp_layer.updateFields()

        features = []

        # Lista typów dróg, które chcemy pominąć
        excluded_highway_types = []
        #excluded_highway_types = ['footway', 'cycleway', 'path', 'pedestrian']

        # Filtrowanie niechcianych typów
        gdf_edges = gdf_edges[~gdf_edges['highway'].isin(excluded_highway_types)]

        for _, row in gdf_edges.iterrows():
            print("DEBUG highway:", row.get("highway"))
            highway = row.get("highway", "")
            if isinstance(highway, list):  # OSM może mieć listy
                highway = highway[0]
            elif highway is None:
                highway = ""

            geom = QgsGeometry.fromWkt(row["geometry"].wkt)
            feat = QgsFeature()
            feat.setGeometry(geom)
            feat.setAttributes([str(highway)])
            features.append(feat)

        provider.addFeatures(features)
        temp_layer.updateExtents()

        # Stylizacja według typu drogi
        categories = []
        for road_type, color in road_styles.items():
            symbol = QgsLineSymbol.createSimple({"color": color, "width": "0.8"})
            category = QgsRendererCategory(road_type, symbol, road_type)
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer("highway", categories)
        #renderer.updateCategories(temp_layer) # usuwa nieuzywane kategroie
        temp_layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(temp_layer)
        iface.messageBar().pushMessage("OSM", f"Dodano drogi do bufora {buffer_id}", level=Qgis.Info)

    except Exception as e:
        iface.messageBar().pushMessage("OSM Error", str(e), level=Qgis.Critical)
