# agents_core.py
import pandas as pd
import numpy as np
from pathlib import Path
import joblib
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
RAW_DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models_dir"

CO2E_PER_KG_FOOD = 4.5

# Load model and feature columns
MODEL = joblib.load(MODEL_DIR / "forecast_qty_used_rf.joblib")
FEATURE_COLS = joblib.load(MODEL_DIR / "forecast_feature_cols.joblib")

# These should match your cat_stats used earlier
CATEGORY_RATES = {
    "Meat":   {"baseline": 0.25, "ai": 0.125},
    "Fish":   {"baseline": 0.25, "ai": 0.125},
    "Dairy":  {"baseline": 0.20, "ai": 0.10},
    "Vegetables": {"baseline": 0.20, "ai": 0.10},
    "Other":  {"baseline": 0.20, "ai": 0.10},
}

KG_PER_PORTION = {
    "Meat": 0.25,
    "Fish": 0.22,
    "Dairy": 0.10,
    "Vegetables": 0.15,
    "Other": 0.20,
}

def _kg_per_portion(category: str) -> float:
    return KG_PER_PORTION.get(category, KG_PER_PORTION["Other"])

# ---------- TOOL 1: build feature frame for future dates ----------

def build_features(restaurant_id: str, start_date: str, end_date: str, menu_categories):
    """
    menu_categories: list of dicts: [{"category": "Meat"}, {"category": "Vegetables"}, ...]
    Returns feature DF with one row per (week_start, category) for weeks in [start_date, end_date].
    """
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    # Week starts (Mondays) that fall in [start, end]
    week_starts = []
    d = start
    while d <= end:
        # Monday of this week
        weekday = d.weekday()
        week_start = d - timedelta(days=weekday)
        if week_start not in week_starts:
            week_starts.append(week_start)
        d += timedelta(days=1)

    # Load weekly history for lagged features
    history_path = PROCESSED_DATA_DIR / "restaurant_inventory_waste_joined.csv"
    if history_path.exists():
        history = pd.read_csv(history_path)
        history["week_start"] = pd.to_datetime(history["week_start"])
        history["restaurant_id"] = pd.to_numeric(history["restaurant_id"], errors="coerce").fillna(0).astype(int)
    else:
        history = pd.DataFrame(columns=["restaurant_id", "category", "week_start", "qty_used_kg", "qty_received_kg"])

    # Load daily weather/events and aggregate by week
    weather = pd.read_csv(RAW_DATA_DIR / "weather" / "weather.csv")
    weather["date"] = pd.to_datetime(weather["date"])
    weather["week_start"] = weather["date"] - pd.to_timedelta(weather["date"].dt.weekday, unit="d")
    weather = weather.rename(columns={"tmax_c": "temp_max", "tmin_c": "temp_min", "precip_mm": "precipitation"})

    events = pd.read_csv(RAW_DATA_DIR / "events" / "events.csv")
    events["date"] = pd.to_datetime(events["date"])
    events["week_start"] = events["date"] - pd.to_timedelta(events["date"].dt.weekday, unit="d")

    weather_week = weather.groupby("week_start", as_index=False).agg(
        temp_max=("temp_max", "mean"),
        temp_min=("temp_min", "mean"),
        precipitation=("precipitation", "sum"),
    )
    events_week = events.groupby("week_start", as_index=False).agg(
        events_count=("events_count", "sum"),
        expected_attendance_total=("expected_attendance_total", "sum"),
    )
    ctx_week = weather_week.merge(events_week, on="week_start", how="left")
    ctx_week["events_count"] = ctx_week["events_count"].fillna(0)
    ctx_week["expected_attendance_total"] = ctx_week["expected_attendance_total"].fillna(0)

    rows = []
    for ws in week_starts:
        for m in menu_categories:
            rows.append({"restaurant_id": restaurant_id, "week_start": ws, "category": m["category"]})

    df = pd.DataFrame(rows)
    df["week_start"] = pd.to_datetime(df["week_start"])
    df = df.merge(ctx_week, on="week_start", how="left")

    df["week_of_year"] = df["week_start"].dt.isocalendar().week.astype(int)
    df["month"] = df["week_start"].dt.month
    df["restaurant_id"] = df["restaurant_id"].apply(
        lambda x: int(str(x).replace("R", "")) if isinstance(x, str) and str(x).replace("R", "").isdigit() else 1
    )

    # Lagged: previous week's usage and received (same restaurant + category)
    if not history.empty and "qty_used_kg" in history.columns and "qty_received_kg" in history.columns:
        lag = history[["restaurant_id", "category", "week_start", "qty_used_kg", "qty_received_kg"]].copy()
        lag["week_start"] = lag["week_start"] + pd.Timedelta(days=7)
        lag = lag.rename(columns={"qty_used_kg": "qty_used_kg_prev_week", "qty_received_kg": "qty_received_kg_prev_week"})
        df = df.merge(lag, on=["restaurant_id", "category", "week_start"], how="left")
    df["qty_used_kg_prev_week"] = df["qty_used_kg_prev_week"].fillna(0.0) if "qty_used_kg_prev_week" in df.columns else 0.0
    df["qty_received_kg_prev_week"] = df["qty_received_kg_prev_week"].fillna(0.0) if "qty_received_kg_prev_week" in df.columns else 0.0
    return df

# ---------- TOOL 2: forecast qty_used_kg ----------

def forecast_qty_used(df_features: pd.DataFrame) -> pd.DataFrame:
    df = df_features.copy()

    base = df[["restaurant_id", "category", "week_of_year", "month", "qty_used_kg_prev_week", "qty_received_kg_prev_week",
               "temp_max", "temp_min", "precipitation", "events_count", "expected_attendance_total"]]

    base_dummies = pd.get_dummies(base, columns=["category"])
    for col in FEATURE_COLS:
        if col not in base_dummies.columns:
            base_dummies[col] = 0.0
    base_dummies = base_dummies[FEATURE_COLS]

    preds = MODEL.predict(base_dummies)
    df["predicted_qty_used_kg"] = preds
    return df

# ---------- TOOL 3: optimizer for order amounts & waste ----------

def optimize_inventory(df_forecast: pd.DataFrame) -> pd.DataFrame:
    df = df_forecast.copy()

    baseline_rates = df["category"].map(lambda c: CATEGORY_RATES.get(c, CATEGORY_RATES["Other"])["baseline"])
    ai_rates = df["category"].map(lambda c: CATEGORY_RATES.get(c, CATEGORY_RATES["Other"])["ai"])

    df["baseline_waste_rate"] = baseline_rates
    df["ai_waste_rate"] = ai_rates

    df["qty_received_baseline_kg"] = df["predicted_qty_used_kg"] / (1 - df["baseline_waste_rate"])
    df["waste_baseline_kg"] = df["qty_received_baseline_kg"] - df["predicted_qty_used_kg"]

    df["qty_received_ai_kg"] = df["predicted_qty_used_kg"] / (1 - df["ai_waste_rate"])
    df["waste_ai_kg"] = df["qty_received_ai_kg"] - df["predicted_qty_used_kg"]

    df["co2e_baseline_kg"] = df["waste_baseline_kg"] * CO2E_PER_KG_FOOD
    df["co2e_ai_kg"] = df["waste_ai_kg"] * CO2E_PER_KG_FOOD
    df["co2e_reduced_kg"] = df["co2e_baseline_kg"] - df["co2e_ai_kg"]

    return df

# ---------- TOOL 4: natural-language summary ----------

def summarize_plan(df_plan: pd.DataFrame) -> str:
    total_waste_base = df_plan["waste_baseline_kg"].sum()
    total_waste_ai = df_plan["waste_ai_kg"].sum()
    total_co2_saved = df_plan["co2e_reduced_kg"].sum()

    return (
        f"Over the selected period, the baseline plan wastes "
        f"{total_waste_base:.1f} kg of food. With the AI plan, "
        f"waste drops to {total_waste_ai:.1f} kg, saving approximately "
        f"{total_co2_saved:.1f} kg CO2e."
    )
