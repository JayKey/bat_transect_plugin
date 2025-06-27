
# 📍 Jak działa `ox.graph_from_point()` w osmnx

Funkcja `graph_from_point()` z biblioteki `osmnx` służy do pobierania sieci dróg (lub innych sieci OSM) w określonej odległości od podanego punktu geograficznego.

---

## ✅ Składnia

```python
ox.graph_from_point(center_point, dist=1000, network_type='all', simplify=True)
```

- `center_point`: Krotka `(lat, lon)` — punkt środkowy (np. centroid bufora).
- `dist`: Promień (w metrach) — jak daleko od punktu szukać dróg.
- `network_type`: Typ sieci (`'drive'`, `'walk'`, `'all'`, `'bike'`, itd.).
- `simplify`: Czy upraszczać geometrię (usuwać zbędne węzły).

---

## 📌 Przykład w kontekście QGIS

Załóżmy, że mamy bufor jako `QgsGeometry`, zamieniamy go na Shapely i liczymy centroid:

```python
polygon = Polygon(qgs_geometry.asPolygon()[0])  # lub .asMultiPolygon()[0]
centroid = polygon.centroid
center_latlon = (centroid.y, centroid.x)
```

Następnie pobieramy sieć dróg:

```python
G = ox.graph_from_point(center_latlon, dist=1000, network_type='all', simplify=True)
```

I konwertujemy do GeoDataFrame:

```python
gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
```

Teraz mamy wszystkie drogi w promieniu 1000 metrów od środka bufora.

---

## ℹ️ Kiedy używać `graph_from_point()` zamiast `graph_from_polygon()`?

| Sytuacja | Rekomendacja |
|----------|--------------|
| Poligon zawiera dużo skrzyżowań i dobrze zdefiniowaną siatkę dróg | ✅ `graph_from_polygon()` |
| Poligon jest wąski, punktowy, lub na trasie bez skrzyżowań | ✅ `graph_from_point()` (lepsze pokrycie) |
| Chcesz objąć dokładny obszar geometrii | `graph_from_polygon()` |
| Chcesz mieć kontrolę przez `dist` (metry od środka) | `graph_from_point()` |

---

## 🧪 Porównanie działania

| Parametr | `graph_from_polygon()` | `graph_from_point()` |
|----------|------------------------|-----------------------|
| Trzeba mieć pełny poligon | ✅ | ❌ |
| Można używać z centroidem | ❌ | ✅ |
| Czy uwzględnia drogi "przechodzące" przez | ❌ (jeśli brak węzła w polu) | ✅ |
| Czy uwzględnia drogi ciągłe (np. odcinki bez skrzyżowań) | Często ❌ | ✅ |

---

## 📎 Źródło dokumentacji

https://osmnx.readthedocs.io/en/stable/osmnx.html#osmnx.graph.graph_from_point

---

Happy mapping! 🗺️
