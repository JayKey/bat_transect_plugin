![WIP](https://img.shields.io/badge/status-WIP-yellow)

# 🦇 Bat Transects QGIS Plugin

A QGIS plugin for generating optimized road transects to assist in field surveys of bat activity — especially in coastal or rural areas.

This tool helps ecologists and researchers define 500-meter-long, drivable transects based on OpenStreetMap road networks, prioritized by proximity to bat habitats such as forests, water bodies, and wetlands.

---

## 🔧 Features

- 🗺️ Buffer generation around input point layers (e.g. sampling sites)
- 🚗 Downloading drivable roads within each buffer from OpenStreetMap (via `osmnx`)
- 🧠 Filtering and color-coding roads by type (`highway`)
- 🧭 Shortest path computation for each buffer with a minimum distance constraint (500 m)
- 🧪 Planned: Advanced options to fine-tune road inclusion/exclusion, transparency, and legend filtering

---

## 📦 Requirements

- QGIS 3.28+ (LTR recommended)
- Python modules:
  - `osmnx`
  - `networkx`
  - `shapely`

You can install these via the QGIS Python console or OSGeo4W shell:

```bash
python3 -m pip install osmnx networkx shapely
```

---

## 🚀 How to Use
1. Load a point layer representing bat sampling locations.
2. Click the Bat Transects toolbar button.
3. Set the buffer radius (default: 500 m) and generate buffer zones.
4. Roads within each buffer are downloaded and color-coded by type.
5. Optionally, use the "Find 500 m Route" button to create the shortest valid transect within each road network.

---

## ⚙️ Advanced Settings

Accessible via the **"Advanced"** tab in the plugin dialog:

### 🛣️ Exclude Road Types
You can choose to exclude selected road types from analysis. These may include:
- `footway` – pedestrian walkways
- `cycleway` – bike paths
- `path` – unclassified rural paths
- `pedestrian` – pedestrian-only zones (e.g., town centers)

This helps focus on roads that are realistically drivable or relevant for mobile surveys.

---

### 🌿 Environmental Proximity (Planned)

Enable environmental prioritization to prefer roads located close to key environmental features.

You can define a **maximum distance (in meters)** — only roads within this distance from selected features will be considered.

Planned environmental features include:

- **Forests**  
  Extracted from OpenStreetMap polygons tagged with `landuse=forest` or `natural=wood`.

- **Water bodies**  
  Includes lakes, rivers, and wetlands tagged with `natural=water`, `water=lake`, or `wetland=*`.

- **Caves**  
  Points tagged with `natural=cave_entrance`, if available in OSM.

- **Abandoned buildings**  
  Extracted from OSM features tagged with `building=ruins` or `abandoned=*`.

This allows prioritizing transects located in ecologically interesting or target-rich environments.

You can also set the **maximum distance (in meters)** for a road to be considered "near" such features.

---

## 🧪 Example Use Cases
- Designing transects for acoustic bat monitoring (e.g. with detectors on moving vehicles)
- Mapping field survey routes in coastal and inland habitats
- Exploring road connectivity in low-density areas during migration periods

---

## 📄 License
MIT License.
Free to use and modify — contributions welcome!

---

Happy fieldwork — and don’t forget your headlamp. 🔦🦇