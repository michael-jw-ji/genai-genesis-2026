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

# Waste rates: baseline (current) vs AI-optimized (match agents_core.py)
CATEGORY_RATES = {
    "Meat": {"baseline": 0.25, "ai": 0.125},
    "Fish": {"baseline": 0.25, "ai": 0.125},
    "Dairy": {"baseline": 0.20, "ai": 0.10},
    "Vegetables": {"baseline": 0.20, "ai": 0.10},
    "Other": {"baseline": 0.20, "ai": 0.10},
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

    # Compute baseline vs AI waste and savings by category (for "You can save X kg ..." message)
    def waste_kg(row: pd.Series) -> tuple:
        rates = CATEGORY_RATES.get(row["category"], CATEGORY_RATES["Other"])
        pred = row["predicted_qty_used_kg"]
        recv_base = pred / (1 - rates["baseline"])
        waste_base = recv_base - pred
        recv_ai = pred / (1 - rates["ai"])
        waste_ai = recv_ai - pred
        return waste_base - waste_ai  # savings kg

    weekly_sorted["savings_kg"] = weekly_sorted.apply(waste_kg, axis=1)
    savings_by_cat = weekly_sorted.groupby("category", as_index=False)["savings_kg"].sum()
    savings_by_category = dict(zip(savings_by_cat["category"], savings_by_cat["savings_kg"].round(2)))
    total_savings = savings_by_cat["savings_kg"].sum()
    savings_parts = [f"{v} kg {k}" for k, v in savings_by_category.items() if v > 0]
    savings_message = (
        f"You can save {total_savings:.1f} kg total"
        + (" (" + ", ".join(savings_parts) + ")." if savings_parts else ".")
    )

    # Optional: predict next week if we have weather/events for it (for "prediction for the next week")
    next_week_forecast = None
    max_week = weekly_sorted["week_start"].max()
    next_week_start = max_week + pd.Timedelta(days=7)
    ctx_week["week_start"] = pd.to_datetime(ctx_week["week_start"])
    ctx_next = ctx_week[ctx_week["week_start"] == next_week_start].drop_duplicates(subset=["week_start"])
    if not ctx_next.empty:
        upload_week_usage = weekly_sorted[weekly_sorted["week_start"] == max_week][
            ["restaurant_id", "category", "qty_used_kg"]
        ].copy()
        upload_week_usage = upload_week_usage.rename(columns={"qty_used_kg": "qty_used_kg_prev_week"})
        next_df = upload_week_usage.copy()
        next_df["week_start"] = next_week_start
        next_df["qty_received_kg_prev_week"] = next_df["qty_used_kg_prev_week"] / 0.8
        next_df = next_df.merge(
            ctx_next[["week_start", "temp_max", "temp_min", "precipitation", "events_count", "expected_attendance_total"]],
            on="week_start",
            how="left",
        )
        next_df["week_of_year"] = next_week_start.isocalendar().week
        next_df["month"] = next_week_start.month
        next_df["temp_max"] = next_df["temp_max"].fillna(20.0)
        next_df["temp_min"] = next_df["temp_min"].fillna(10.0)
        next_df["precipitation"] = next_df["precipitation"].fillna(0.0)
        next_df["events_count"] = next_df["events_count"].fillna(0)
        next_df["expected_attendance_total"] = next_df["expected_attendance_total"].fillna(0)
        feature_df_next = pd.get_dummies(next_df[feature_cols], columns=["category"])
        for col in FEATURE_COLS:
            if col not in feature_df_next.columns:
                feature_df_next[col] = 0.0
        feature_df_next = feature_df_next[FEATURE_COLS]
        preds_next = MODEL.predict(feature_df_next)
        next_df["predicted_qty_used_kg"] = preds_next
        next_by_cat = next_df.groupby("category", as_index=False)["predicted_qty_used_kg"].sum()
        row = ctx_next.iloc[0]
        next_week_forecast = {
            "week_start": next_week_start.strftime("%Y-%m-%d"),
            "by_category": dict(zip(next_by_cat["category"], next_by_cat["predicted_qty_used_kg"].round(2).tolist())),
            "weather": {
                "temp_max": round(float(row["temp_max"]), 1),
                "temp_min": round(float(row["temp_min"]), 1),
                "precipitation": round(float(row["precipitation"]), 1),
            },
            "events": {
                "events_count": int(row["events_count"]),
                "expected_attendance_total": int(row["expected_attendance_total"]),
            },
        }

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
    # For partial weeks (fewer than 7 days in upload), scale so we show per-day average
    # instead of cramming a full week's prediction onto one day (which made June 16 look wrong).
    days_per_week = df.groupby(["restaurant_id", "week_start"]).agg(
        days_in_week=("date", "nunique")
    ).reset_index()
    df = df.merge(days_per_week, on=["restaurant_id", "week_start"], how="left")
    df["predicted_qty_used_kg"] = (
        df["weekly_pred"] * df["daily_proportion"] * (df["days_in_week"].clip(upper=7) / 7)
    )

    # Prepare response: actual and predicted in kg; include kg_per_portion for frontend units
    df["actual_qty_used_kg"] = df["qty_used_kg"]  # qty_sold * kg_per_portion
    preview_cols = [
        "date",
        "dish_name",
        "category",
        "qty_sold",
        "kg_per_portion",
        "actual_qty_used_kg",
        "predicted_qty_used_kg",
    ]

    rows = (
        df[preview_cols]
        .head(200)  # avoid huge payloads
        .to_dict(orient="records")
    )

    out = {
        "rows": rows,
        "savings_by_category": savings_by_category,
        "savings_message": savings_message,
    }
    if next_week_forecast is not None:
        out["next_week_forecast"] = next_week_forecast
    return out


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)


