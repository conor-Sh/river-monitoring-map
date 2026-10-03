import requests
import pandas as pd
import geopandas as pd

BASE = "https://environment.data.gov.uk/flood-monitoring"

def get_stations(lat, long, dist):
    params = {"parameter": "level", "lat": lat, "long": long, "dist": dist}
    r = requests.get(f"{BASE}/id/stations", params=params)
    r.raise_for_status()
    stations = pd.DataFrame(r.json()["items"])
    return stations

def get_readings(station_ref, limit=700):
    r = requests.get(
        f"{BASE}/id/stations/{station_ref}/readings",
        params={"parameter": "level", "_sorted": "", "_limit": limit},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json()["items"])
    if df.empty:
        return df
    df["stationReference"] = station_ref
    df["dateTime"] = pd.to_datetime(df["dateTime"])
    return df[["stationReference", "dateTime", "value"]]

def main():
    stations = get_stations(51.87967, -0.41748, 10)
    stations = stations.drop_duplicates("stationReference")

    all_readings = [get_readings(ref) for ref in stations["stationReference"]]
    readings = pd.concat([d for d in all_readings if not d.empty])
    readings = readings.dropna(subset=["value"])

    # Latest reading per station
    latest = (readings.sort_values("dateTime")
              .groupby("stationReference").tail(1)
              .rename(columns={"value": "latest_level"}))

    gdf = gpd.GeoDataFrame(
        stations[["stationReference", "label", "riverName", "town",
                  "catchmentName", "easting", "northing"]]
        .merge(latest[["stationReference", "latest_level", "dateTime"]],
               on="stationReference", how="left"),
        geometry=gpd.points_from_xy(stations["easting"], stations["northing"]),
        crs="EPSG:27700",
    ).to_crs(4326)

    gdf.to_file("data/processed/stations.geojson", driver="GeoJSON")
    readings.to_csv("data/processed/readings.csv", index=False)
    print(gdf[["label", "latest_level"]])

if __name__ == "__main__":
    main()