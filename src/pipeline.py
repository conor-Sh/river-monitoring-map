import requests
import pandas as pd
import geopandas as gpd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # project root, so it runs from anywhere
OUT = ROOT / "data" / "processed"

BASE = "https://environment.data.gov.uk/flood-monitoring"
METRE_UNITS = {"mASD", "mAOD", "m"} 

def get_stations(lat, long, dist):
    # all level stations within dist km of a point
    params = {"parameter": "level", "lat": lat, "long": long, "dist": dist}
    r = requests.get(f"{BASE}/id/stations", params=params, timeout=30)
    r.raise_for_status()
    return pd.DataFrame(r.json()["items"])

def pick_measure(measures):
    """Return the best metre-based level measure (a dict), or None."""
    # each station has several measures, some in volts, so we have to choose one
    if not isinstance(measures, list):
        return None
    candidates = [m for m in measures
                  if m.get("parameter") == "level"
                  and m.get("unitName") in METRE_UNITS]
    if not candidates:
        return None
    # prefer plain stage, then height, then downstream
    order = {"Stage": 0, "Height": 1, "Downstream Stage": 2}
    candidates.sort(key=lambda m: order.get(m.get("qualifier"), 9))
    return candidates[0]

def get_readings(measure_id, station_ref, limit=700):
    # 700 readings at 15 min intervals is roughly a week
    r = requests.get(f"{measure_id}/readings",
                     params={"_sorted": "", "_limit": limit}, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["items"])
    if df.empty:
        return df
    df["stationReference"] = station_ref   # tag rows so we can join back later
    df["dateTime"] = pd.to_datetime(df["dateTime"])
    return df[["stationReference", "dateTime", "value"]]

def main():
    stations = get_stations(53.4, -2.98333, 10)   # Liverpool
    stations = stations.drop_duplicates("stationReference")
    print(len(stations), "stations returned")

    units = pd.Series([(m.get("qualifier"), m.get("unitName"))
                       for ms in stations["measures"] if isinstance(ms, list)
                       for m in ms])
    print(units.value_counts())

    # keep one usable measure per station, drop stations without one
    stations["measure"] = stations["measures"].apply(pick_measure)
    stations = stations.dropna(subset=["measure"]).copy()
    stations["measure_id"] = stations["measure"].apply(lambda m: m["@id"])
    stations["unit"] = stations["measure"].apply(lambda m: m["unitName"])
    stations["type"] = stations["measure"].apply(lambda m: m.get("qualifier"))   # Stage vs Tidal Level
    # labels aren't unique (two Redbourns), so add the reference
    stations["name"] = stations["label"] + " (" + stations["stationReference"] + ")"
    print(len(stations), "stations with a metre-based level measure")

    all_readings = [get_readings(row.measure_id, row.stationReference)
                    for row in stations.itertuples()]
    non_empty = [d for d in all_readings if not d.empty]
    if not non_empty:
        raise SystemExit("No readings returned. Check the area or units.")
    readings = pd.concat(non_empty).dropna(subset=["value"])

    # most recent reading per station
    latest = (readings.sort_values("dateTime")
              .groupby("stationReference").tail(1)
              .rename(columns={"value": "latest_level"}))

    # each station's usual level over the week
    stats = readings.groupby("stationReference")["value"].agg(["median", "std"]).reset_index()
    latest = latest.merge(stats, on="stationReference")
    # raw levels aren't comparable between stations (different datums),
    # so look at how far each one is from its own normal
    latest["level_vs_median"] = latest["latest_level"] - latest["median"]

    merged = (stations[["stationReference", "name", "riverName", "town",
                        "catchmentName", "unit", "type", "easting", "northing"]]
              .merge(latest[["stationReference", "latest_level",
                             "level_vs_median", "dateTime"]],
                     on="stationReference", how="left"))

    # easting/northing are British National Grid (27700), convert to lat/long for web maps
    gdf = gpd.GeoDataFrame(
        merged,
        geometry=gpd.points_from_xy(merged["easting"], merged["northing"]),
        crs="EPSG:27700",
    ).to_crs(4326)

    OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT / "stations.geojson", driver="GeoJSON")   #