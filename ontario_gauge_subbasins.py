#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ontario gauge sub-basin extractor using Google Earth Engine HydroATLAS Level-12.

- Loads a CSV of gauges (lat/lon/id)
- For each gauge, builds a buffer (km) and intersects with WWF/HydroATLAS Level 12
- export_mode 'client'  : download features client-side, write zipped shapefile per gauge, then a combined ZIP
- export_mode 'ee_drive': queue Earth Engine table exports to Google Drive
"""
import os
import io
import sys
import json
import time
import math
import zipfile
import argparse
from typing import List, Optional

import ee
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape as shp_shape

DATASET_ID = "WWF/HydroATLAS/v1/Basins/level12"

def init_ee(project: Optional[str] = None):
    try:
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
    except Exception:
        print("Earth Engine not initialized. Starting authentication flow...")
        ee.Authenticate()
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()

def ensure_dir(p: str):
    if not os.path.exists(p):
        os.makedirs(p, exist_ok=True)

def get_subbasins_fc(lon: float, lat: float, buffer_km: float) -> ee.FeatureCollection:
    pt = ee.Geometry.Point([lon, lat])
    roi = pt.buffer(buffer_km * 1000.0)
    fc = ee.FeatureCollection(DATASET_ID).filterBounds(roi)
    return fc

def fc_to_geodataframe(fc: ee.FeatureCollection) -> gpd.GeoDataFrame:
    """Download features to client and convert to GeoDataFrame (EPSG:4326)."""
    info = fc.getInfo()  # Caution: can be heavy for big collections
    feats = info.get("features", [])
    if not feats:
        return gpd.GeoDataFrame(columns=["geometry"], geometry=[] , crs="EPSG:4326")
    geoms = []
    props = []
    for f in feats:
        geoms.append(shp_shape(f["geometry"]))
        props.append(f.get("properties", {}))
    gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")
    return gdf

def write_shapefile_zip(gdf: gpd.GeoDataFrame, out_zip_path: str, layer_name: str):
    """Write GeoDataFrame to a shapefile and zip it."""
    tmp_dir = out_zip_path.replace(".zip", "")
    ensure_dir(tmp_dir)
    shp_path = os.path.join(tmp_dir, f"{layer_name}.shp")
    gdf.to_file(shp_path, driver="ESRI Shapefile")
    # Zip the folder
    with zipfile.ZipFile(out_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(tmp_dir):
            for fn in files:
                full = os.path.join(root, fn)
                arcname = os.path.relpath(full, start=tmp_dir)
                zf.write(full, arcname)
    # Cleanup
    for root, dirs, files in os.walk(tmp_dir, topdown=False):
        for fn in files:
            os.remove(os.path.join(root, fn))
        for d in dirs:
            os.rmdir(os.path.join(root, d))
    os.rmdir(tmp_dir)

def queue_ee_drive_export(fc: ee.FeatureCollection, description: str, folder: Optional[str] = None):
    """Start an EE export task to Google Drive for the given FeatureCollection."""
    task = ee.batch.Export.table.toDrive(
        collection=fc,
        description=description,
        fileFormat="SHP",
        folder=folder
    )
    task.start()
    print(f"Started EE export task for '{description}'. Task ID: {task.id}")

def process_gauge_row(row, args, combined_paths: List[str]) -> None:
    lat = float(row[args.lat_col])
    lon = float(row[args.lon_col])
    gid = str(row[args.id_col])

    print(f"Processing gauge {gid} at ({lat:.5f}, {lon:.5f}) ...")
    fc = get_subbasins_fc(lon, lat, args.buffer_km)

    if args.export_mode == "client":
        gdf = fc_to_geodataframe(fc)
        if gdf.empty:
            print(f"  No sub-basins found for gauge {gid}. Skipping.")
        else:
            out_zip = os.path.join(args.out_dir, f"gauge_{gid}_subbasins.zip")
            write_shapefile_zip(gdf, out_zip, layer_name=f"gauge_{gid}_subbasins")
            combined_paths.append(out_zip)
            print(f"  Wrote: {out_zip}")
    else:
        # Earth Engine Drive export
        desc = f"gauge_{gid}_subbasins"
        queue_ee_drive_export(fc, description=desc, folder=args.drive_folder)

def build_combined_zip(zip_paths: List[str], out_dir: str):
    if not zip_paths:
        print("No per-gauge ZIPs to combine.")
        return
    combined = os.path.join(out_dir, "all_gauge_subbasins.zip")
    with zipfile.ZipFile(combined, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in zip_paths:
            zf.write(p, os.path.basename(p))
    print(f"Combined ZIP written: {combined}")

def main():
    parser = argparse.ArgumentParser(description="Extract HydroATLAS L12 sub-basins within a buffer around gauges.")
    parser.add_argument("--gauges_csv", required=True, help="Path to CSV with gauges.")
    parser.add_argument("--lat_col", default="LATITUDE", help="Latitude column name in CSV.")
    parser.add_argument("--lon_col", default="LONGITUDE", help="Longitude column name in CSV.")
    parser.add_argument("--id_col", default="STATION_NUMBER", help="Gauge ID column name in CSV.")
    parser.add_argument("--buffer_km", type=float, default=25.0, help="Buffer radius in kilometers.")
    parser.add_argument("--export_mode", choices=["client", "ee_drive"], default="client", help="Export mode.")
    parser.add_argument("--out_dir", default="outputs", help="Output folder for client mode.")
    parser.add_argument("--drive_folder", default=None, help="Google Drive folder for EE export mode.")
    parser.add_argument("--ee_project", default=None, help="Optional GCP project for EE Initialize.")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N gauges (debugging).")
    parser.add_argument("--sleep_sec", type=float, default=0.0, help="Sleep between gauges (seconds).")
    args = parser.parse_args()

    ensure_dir(args.out_dir)
    init_ee(project=args.ee_project)

    # Load gauges
    df = pd.read_csv(args.gauges_csv)
    for col in [args.lat_col, args.lon_col, args.id_col]:
        if col not in df.columns:
            raise KeyError(f"Column '{col}' not found in CSV.")

    # Iterate
    combined_paths: List[str] = []
    it = df.itertuples(index=False)
    count = 0
    for row in it:
        # Convert row to Series-like mapping
        row_dict = row._asdict() if hasattr(row, "_asdict") else dict(zip(df.columns, row))
        process_gauge_row(row_dict, args, combined_paths)
        count += 1
        if args.limit and count >= args.limit:
            print(f"Reached limit={args.limit}. Stopping.")
            break
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    # Build combined zip (client mode only)
    if args.export_mode == "client":
        build_combined_zip(combined_paths, args.out_dir)
    else:
        print("All EE export tasks have been started. Monitor the Earth Engine Tasks panel.")

if __name__ == "__main__":
    main()
