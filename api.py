from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from io import StringIO
from pathlib import Path

import joblib
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models_dir"
RAW_DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DATA_DIR = ROOT / "data" / "processed"

MODEL = joblib.load(MODEL_DIR / "forecast_qty_used_rf.joblib")
FEATURE_COLS = joblib.load(MODEL_DIR / "forecast_feature_cols.joblib")

# Category to kg per portion mapping (from dataset_creator.py)
KG_PER_PORTION = {
    "Meat": 0.25,
    "Vegetables": 0.15,
    "Dairy": 0.10,
    "Fish": 0.22,
    "Other": 0.20,
}

REQUIRED_COLS = [
    "date",
    "dish_id",
    "dish_name",
    "category",
    "qty_sold",
    "restaurant_id",
    "price",
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_kg_per_portion(category: str) -> float:
    """Get kg per portion for a category."""
    return KG_PER_PORTION.get(category, KG_PER_PORTION["Other"])


@app.post("/api/upload-sales")
async def upload_sales(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be utf-8 encoded")

    df = pd.read_csv(StringIO(text))

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )

    # Convert date and calculate week_start (Monday of each week)
    df["date"] = pd.to_datetime(df["date"])
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="d")
    
    # Calculate qty_used_kg from qty_sold using kg_per_portion
    df["kg_per_portion"] = df["category"].apply(get_kg_per_portion)
    df["qty_used_kg"] = df["qty_sold"] * df["kg_per_portion"]

    # Aggregate daily sales to weekly by restaurant, week_start, and category
    weekly = (
        df.groupby(["restaurant_id", "week_start", "category"], as_index=False)
        .agg(
            qty_used_kg=("qty_used_kg", "sum"),
            qty_sold=("qty_sold", "sum"),
        )
    )

    # Load weather data and aggregate to weekly
    try:
        weather = pd.read_csv(RAW_DATA_DIR / "weather" / "weather.csv")
        weather["date"] = pd.to_datetime(weather["date"])
        weather["week_start"] = weather["date"] - pd.to_timedelta(weather["date"].dt.weekday, unit="d")
        weather = weather.rename(columns={
            "tmax_c": "temp_max",
            "tmin_c": "temp_min",
            "precip_mm": "precipitation",
        })
        weather_week = weather.groupby("week_start", as_index=False).agg(
            temp_max=("temp_max", "mean"),
            temp_min=("temp_min", "mean"),
            precipitation=("precipitation", "sum"),
        )
    except FileNotFoundError:
        # Use defaults if weather file not found
        weather_week = pd.DataFrame(columns=["week_start", "temp_max", "temp_min", "precipitation"])

    # Load events data and aggregate to weekly
    try:
        events = pd.read_csv(RAW_DATA_DIR / "events" / "events.csv")
        events["date"] = pd.to_datetime(events["date"])
        events["week_start"] = events["date"] - pd.to_timedelta(events["date"].dt.weekday, unit="d")
        events_week = events.groupby("week_start", as_index=False).agg(
            events_count=("events_count", "sum"),
            expected_attendance_total=("expected_attendance_total", "sum"),
        )
    except FileNotFoundError:
        # Use defaults if events file not found
        events_week = pd.DataFrame(columns=["week_start", "events_count", "expected_attendance_total"])

    # Merge weather and events
    if not weather_week.empty and not events_week.empty:
        ctx_week = weather_week.merge(events_week, on="week_start", how="outer")
    elif not weather_week.empty:
        ctx_week = weather_week.copy()
        ctx_week["events_count"] = 0
        ctx_week["expected_attendance_total"] = 0
    elif not events_week.empty:
        ctx_week = events_week.copy()
        ctx_week["temp_max"] = 20.0  # default
        ctx_week["temp_min"] = 10.0  # default
        ctx_week["precipitation"] = 0.0
    else:
        # No context data available - use defaults
        ctx_week = pd.DataFrame({
            "week_start": weekly["week_start"].unique(),
            "temp_max": 20.0,
            "temp_min": 10.0,
            "precipitation": 0.0,
            "events_count": 0,
            "expected_attendance_total": 0,
        })

    # Merge context into weekly data
    weekly = weekly.merge(ctx_week, on="week_start", how="left")
    weekly["temp_max"] = weekly["temp_max"].fillna(20.0)
    weekly["temp_min"] = weekly["temp_min"].fillna(10.0)
    weekly["precipitation"] = weekly["precipitation"].fillna(0.0)
    weekly["events_count"] = weekly["events_count"].fillna(0)
    weekly["expected_attendance_total"] = weekly["expected_attendance_total"].fillna(0)

    # Add time features
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    weekly["week_of_year"] = weekly["week_start"].dt.isocalendar().week.astype(int)
    weekly["month"] = weekly["week_start"].dt.month
    
    # Convert restaurant_id to numeric
    weekly["restaurant_id"] = pd.to_numeric(weekly["restaurant_id"], errors="coerce").fillna(0).astype(int)

    # Calculate lagged features (previous week's usage and received)
    # For simplicity, we'll use 0 if no previous week data is available
    weekly_sorted = weekly.sort_values(["restaurant_id", "category", "week_start"])
    weekly_sorted["qty_used_kg_prev_week"] = weekly_sorted.groupby(["restaurant_id", "category"])["qty_used_kg"].shift(1).fillna(0.0)
    # For qty_received_kg_prev_week, we'll estimate it from qty_used_kg_prev_week with a default waste rate
    weekly_sorted["qty_received_kg_prev_week"] = weekly_sorted["qty_used_kg_prev_week"] / 0.8  # assuming 20% waste rate

    # Build feature matrix matching train_model.py
    feature_cols = [
        "restaurant_id",
        "category",
        "week_of_year",
        "month",
        "qty_used_kg_prev_week",
        "qty_received_kg_prev_week",
        "temp_max",
        "temp_min",
        "precipitation",
        "events_count",
        "expected_attendance_total",
    ]
    
    feature_df = pd.get_dummies(weekly_sorted[feature_cols], columns=["category"])
    
    # Align with model's expected feature columns
    for col in FEATURE_COLS:
        if col not in feature_df.columns:
            feature_df[col] = 0.0
    feature_df = feature_df[FEATURE_COLS]

    # Make predictions
    preds = MODEL.predict(feature_df)
    weekly_sorted["predicted_qty_used_kg"] = preds

    # Map predictions back to daily level for display
    # For each daily row, find its weekly prediction
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="d")
    df["week_start"] = pd.to_datetime(df["week_start"])
    
    # Create a mapping from (restaurant_id, week_start, category) to predicted_qty_used_kg
    pred_map = weekly_sorted.set_index(["restaurant_id", "week_start", "category"])["predicted_qty_used_kg"].to_dict()
    
    # For daily rows, we'll use the weekly prediction proportionally
    # Calculate the proportion of weekly qty_used_kg that this daily row represents
    weekly_totals = df.groupby(["restaurant_id", "week_start", "category"])["qty_used_kg"].transform("sum")
    df["daily_proportion"] = df["qty_used_kg"] / weekly_totals.replace(0, np.nan)
    df["daily_proportion"] = df["daily_proportion"].fillna(0.0)  # if weekly total is 0, proportion is 0
    
    # Get weekly prediction and scale by daily proportion
    df["weekly_pred"] = df.apply(
        lambda row: pred_map.get((row["restaurant_id"], row["week_start"], row["category"]), 0.0),
        axis=1
    )
    df["predicted_qty_used_kg"] = df["weekly_pred"] * df["daily_proportion"]

    # Prepare response with daily-level data
    preview_cols = [
        "date",
        "dish_name",
        "category",
        "qty_sold",
        "predicted_qty_used_kg",
    ]

    rows = (
        df[preview_cols]
        .head(200)  # avoid huge payloads
        .to_dict(orient="records")
    )

    return {"rows": rows}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)


