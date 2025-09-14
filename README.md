# Sub-basin Extraction Near Gauges (Ontario) — Google Earth Engine + HydroATLAS

Extract **HydroATLAS Level‑12** sub‑basins intersecting a circular buffer around each gauge and export them as **Shapefiles (zipped)**, one per gauge plus an optional combined ZIP. Works locally (no Colab required).

## Features
- Reads a CSV of gauges with columns for **latitude**, **longitude**, and **station id**
- For each gauge:
  - Builds a buffer (km) around the point
  - Filters **WWF/HydroATLAS/v1/Basins/level12** within the buffer
  - Exports a **zipped shapefile** with all intersecting sub‑basins **and all their attributes**
- Optionally, also queue **Earth Engine table exports to Google Drive** (safer for large regions)
- Produces a **combined ZIP** of all per‑gauge shapefile ZIPs (client‑side mode)

> Note: Client‑side export (downloading features via `getInfo`) is convenient but can hit memory/timeout limits for large buffers or many gauges. Prefer `--export_mode ee_drive` for scale.

---

## Quickstart

```bash
# (optional) create venv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# First-time Earth Engine auth
python -c "import ee; ee.Authenticate(); ee.Initialize()"
# Or: earthengine authenticate

# Run (client-side shapefile zips + combined zip)
python ontario_gauge_subbasins.py   --gauges_csv "/path/to/GaugeData_WaterLevel_v1.csv"   --lat_col "LATITUDE" --lon_col "LONGITUDE" --id_col "STATION_NUMBER"   --buffer_km 25   --out_dir "outputs"   --export_mode client

# Run (queue EE exports to Google Drive — safer at scale)
python ontario_gauge_subbasins.py   --gauges_csv "/path/to/GaugeData_WaterLevel_v1.csv"   --lat_col "LATITUDE" --lon_col "LONGITUDE" --id_col "STATION_NUMBER"   --buffer_km 25   --drive_folder "GEE_Subbasins"   --export_mode ee_drive
```

### CSV expectations
- Must contain latitude/longitude columns, default names: `LATITUDE`, `LONGITUDE`.
- A unique ID column for naming outputs, default: `STATION_NUMBER`.

### Outputs (client mode)
- `outputs/gauge_<ID>_subbasins.zip` — zipped shapefile per gauge
- `outputs/all_gauge_subbasins.zip` — combined ZIP that contains all the per‑gauge ZIPs

### Outputs (ee_drive mode)
- Earth Engine export **tasks** are started, each producing a zipped shapefile in your **Google Drive** (folder `--drive_folder`).

---

## CLI

Run `python ontario_gauge_subbasins.py -h` for all options. Key flags:

- `--gauges_csv` (str, **required**): path to CSV file
- `--lat_col`, `--lon_col`, `--id_col` (defaults `LATITUDE`, `LONGITUDE`, `STATION_NUMBER`)
- `--buffer_km` (float, default 25): buffer radius in kilometers
- `--export_mode` (choices: `client`, `ee_drive`), default `client`
- `--out_dir` (client mode output folder, default `outputs`)
- `--drive_folder` (Drive folder name for EE exports, optional)
- `--ee_project` (optional GCP project id for `ee.Initialize(project=...)`)
- `--limit` (int, optional): process first N gauges (useful for testing)
- `--sleep_sec` (float, default 0): pause between gauges (throttle API calls)

---

## Notes
- **Dataset**: `WWF/HydroATLAS/v1/Basins/level12` (global Level‑12 basins).
- For very large buffers / many gauges, prefer `ee_drive` to avoid local memory/download issues.
- Shapefiles are written in **EPSG:4326**.
- You can safely use this for **Ontario** gauges; the script does not hard‑code a regional filter.

## License
MIT
