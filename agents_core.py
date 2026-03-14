# agents_core.py
import pandas as pd
import numpy as np
from pathlib import Path
import joblib
from datetime import datetime, timedelta

DATA_DIR = Path("data_dir")
MODEL_DIR = Path("models_dir")

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
    Returns feature DF with one row per (date, category).
    """
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    weather = pd.read_csv(DATA_DIR / "weather.csv")
    weather["date"] = pd.to_datetime(weather["date"]).dt.date
    weather = weather.rename(columns={
        "tmax_c": "temp_max",
        "tmin_c": "temp_min",
        "precip_mm": "precipitation",
    })

    events = pd.read_csv(DATA_DIR / "events.csv")
    events["date"] = pd.to_datetime(events["date"]).dt.date

    ctx = weather.merge(events, on="date", how="left")

    rows = []
    d = start
    while d <= end:
        for m in menu_categories:
            rows.append(
                {
                    "restaurant_id": restaurant_id,
                    "date": d,
                    "category": m["category"],
                }
            )
        d += timedelta(days=1)

    df = pd.DataFrame(rows)
    df = df.merge(ctx, on="date", how="left")

    df["day_of_week"] = pd.to_datetime(df["date"]).dt.weekday
    return df

# ---------- TOOL 2: forecast qty_used_kg ----------

def forecast_qty_used(df_features: pd.DataFrame) -> pd.DataFrame:
    df = df_features.copy()

    base = df[["category", "day_of_week", "temp_max", "temp_min",
               "precipitation", "events_count", "expected_attendance_total"]]

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
