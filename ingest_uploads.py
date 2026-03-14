"""
Convert restaurant uploads into the format expected by the pipeline,
then build the weekly joined CSV (restaurant_inventory_waste_joined.csv).

Expected upload columns:
  Sales:    date, restaurant_id, category, qty_sold, dish_id, dish_name
  Weather:  date, tmax_c, tmin_c, precip_mm
  Events:   date, events_count, expected_attendance_total
  Waste:    Type of Food, Quantity of Food (optional; uses default if missing)

Usage:
  Place uploads in data/raw/uploads/ (or set UPLOADS_DIR), then:
  python ingest_uploads.py

  Or pass paths:
  python ingest_uploads.py --sales path/sales.csv --weather path/weather.csv --events path/events.csv [--waste path/waste.csv]
"""
import argparse
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = ROOT / "data" / "raw" / "uploads"
RAW_DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DATA_DIR = ROOT / "data" / "processed"

# Optional column renames if restaurant uses different headers
SALES_RENAME = {
    "Date": "date",
    "System Date": "date",
    "Restaurant Name": "restaurant_id",
    "Food ID": "dish_id",
    "Food Name": "dish_name",
    "Food Category": "category",
    "Quantity": "qty_sold",
}
WEATHER_RENAME = {
    "temp_max": "tmax_c",
    "temp_min": "tmin_c",
    "precipitation": "precip_mm",
}
EVENTS_RENAME = {}
WASTE_RENAME = {
    "Type of Food": "Type of Food",
    "Quantity of Food": "Quantity of Food",
}


def normalize_sales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={k: v for k, v in SALES_RENAME.items() if k in df.columns})
    needed = ["date", "restaurant_id", "category", "qty_sold"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"Sales upload missing column: {c}")
    if "dish_id" not in df.columns:
        df["dish_id"] = range(len(df))
    if "dish_name" not in df.columns:
        df["dish_name"] = df.get("category", "item")
    df = df[["date", "dish_id", "dish_name", "category", "qty_sold", "restaurant_id"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def normalize_weather(df: pd.DataFrame) -> pd.DataFrame:
    # Accept either tmax_c or temp_max; we write tmax_c, tmin_c, precip_mm for dataset_creator
    if "temp_max" in df.columns and "tmax_c" not in df.columns:
        df = df.rename(columns={"temp_max": "tmax_c", "temp_min": "tmin_c", "precipitation": "precip_mm"})
    for c in ["date", "tmax_c", "tmin_c", "precip_mm"]:
        if c not in df.columns:
            raise ValueError(f"Weather upload missing column: {c}")
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "tmax_c", "tmin_c", "precip_mm"]].copy()


def normalize_events(df: pd.DataFrame) -> pd.DataFrame:
    if "date" not in df.columns:
        raise ValueError("Events upload missing column: date")
    if "events_count" not in df.columns:
        df["events_count"] = 0
    if "expected_attendance_total" not in df.columns:
        df["expected_attendance_total"] = 0
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "events_count", "expected_attendance_total"]].copy()


def main():
    p = argparse.ArgumentParser(description="Convert uploads to pipeline format and build joined CSV.")
    p.add_argument("--sales", type=Path, default=UPLOADS_DIR / "sales.csv", help="Sales CSV path")
    p.add_argument("--weather", type=Path, default=UPLOADS_DIR / "weather.csv", help="Weather CSV path")
    p.add_argument("--events", type=Path, default=UPLOADS_DIR / "events.csv", help="Events CSV path")
    p.add_argument("--waste", type=Path, default=None, help="Waste CSV path (optional)")
    args = p.parse_args()

    # 1) Normalize and write sales -> processed/sales.csv
    sales = pd.read_csv(args.sales)
    sales = normalize_sales(sales)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    sales.to_csv(PROCESSED_DATA_DIR / "sales.csv", index=False)
    print("Wrote", PROCESSED_DATA_DIR / "sales.csv")

    # 2) Normalize and write weather -> raw/weather/weather.csv
    weather = pd.read_csv(args.weather)
    weather = normalize_weather(weather)
    (RAW_DATA_DIR / "weather").mkdir(parents=True, exist_ok=True)
    weather.to_csv(RAW_DATA_DIR / "weather" / "weather.csv", index=False)
    print("Wrote", RAW_DATA_DIR / "weather" / "weather.csv")

    # 3) Events -> raw/events/events.csv (or create default if missing)
    if args.events.exists():
        events = pd.read_csv(args.events)
        events = normalize_events(events)
    else:
        dates = pd.date_range(sales["date"].min(), sales["date"].max(), freq="D")
        events = pd.DataFrame({"date": dates, "events_count": 0, "expected_attendance_total": 0})
    (RAW_DATA_DIR / "events").mkdir(parents=True, exist_ok=True)
    events.to_csv(RAW_DATA_DIR / "events" / "events.csv", index=False)
    print("Wrote", RAW_DATA_DIR / "events" / "events.csv")

    # 4) Waste -> raw/waste/food_wastage_data.csv (optional)
    if args.waste and args.waste.exists():
        waste = pd.read_csv(args.waste)
        (RAW_DATA_DIR / "waste").mkdir(parents=True, exist_ok=True)
        waste.to_csv(RAW_DATA_DIR / "waste" / "food_wastage_data.csv", index=False)
        print("Wrote", RAW_DATA_DIR / "waste" / "food_wastage_data.csv")
    elif not (RAW_DATA_DIR / "waste" / "food_wastage_data.csv").exists():
        raise FileNotFoundError("No waste file provided and no default at data/raw/waste/food_wastage_data.csv")

    # 5) Run dataset_creator to build weekly joined CSV
    import subprocess
    subprocess.run(["python", str(ROOT / "dataset_creator.py")], check=True, cwd=str(ROOT))
    print("Done. Joined CSV:", PROCESSED_DATA_DIR / "restaurant_inventory_waste_joined.csv")


if __name__ == "__main__":
    main()
