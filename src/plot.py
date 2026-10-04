from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUTS = ROOT / "outputs"
OUTS.mkdir(exist_ok=True)

stations = gpd.read_file(PROC / "stations.geojson")
readings = pd.read_csv(PROC / "readings.csv", parse_dates=["dateTime"])

# River stations only, with names
river = stations[stations["type"] == "Stage"][["stationReference", "name"]]
df = readings.merge(river, on="stationReference")

# Show each station relative to its own median so they share a scale
df["change_m"] = df["value"] - df.groupby("stationReference")["value"].transform("median")

fig, ax = plt.subplots(figsize=(10, 5))
for name, g in df.groupby("name"):
    ax.plot(g["dateTime"], g["change_m"], label=name, linewidth=1)
ax.set_title("River level change from 7-day median")
ax.set_ylabel("Level minus station median (m)")
ax.set_xlabel("Date/time (UTC)")
ax.legend(fontsize=7)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(OUTS / "timeseries.png", dpi=200)