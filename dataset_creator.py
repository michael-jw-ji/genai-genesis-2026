import pandas as pd
from pathlib import Path

# ---------- CONFIG ----------
ROOT = Path(__file__).resolve().parent
RAW_DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DATA_DIR = ROOT / "data" / "processed"
OUT_PATH = PROCESSED_DATA_DIR / "restaurant_inventory_waste_joined.csv"
CO2E_PER_KG_FOOD = 4.5  # kg CO2e per kg wasted food

KG_PER_PORTION = {
    "Meat": 0.25,
    "Vegetables": 0.15,
    "Dairy": 0.10,
    "Fish": 0.22,
    "Other": 0.20,
}

# ---------- LOAD RAW DATA ----------

# Normalized sales CSV you just created
sales = pd.read_csv(PROCESSED_DATA_DIR / "sales.csv")

# Trevin Hannibal food wastage data
waste_raw = pd.read_csv(RAW_DATA_DIR / "waste" / "food_wastage_data.csv")

# Weather CSV (your Toronto weather file, already renamed)
weather = pd.read_csv(RAW_DATA_DIR / "weather" / "weather.csv")

# Events CSV (can be synthetic, just needs date, events_count, expected_attendance_total)
events = pd.read_csv(RAW_DATA_DIR / "events" / "events.csv")

# ---------- CLEAN / NORMALIZE ----------

# SALES
sales = sales[["date", "dish_id", "dish_name", "category", "qty_sold", "restaurant_id"]].copy()
sales["date"] = pd.to_datetime(sales["date"])

# FOOD WASTE
waste = waste_raw.rename(
    columns={
        "Type of Food": "category",
        "Quantity of Food": "waste_qty_raw",
    }
)[["category", "waste_qty_raw"]].copy()
waste = waste.dropna(subset=["category", "waste_qty_raw"])

# WEATHER
weather = weather.rename(columns={
    "weathercode": "weather_code",
    "tmax_c": "temp_max",
    "tmin_c": "temp_min",
    "precip_mm": "precipitation",
})
weather = weather[["date", "temp_max", "temp_min", "precipitation"]].copy()
weather["date"] = pd.to_datetime(weather["date"])

# EVENTS
events = events[["date", "events_count", "expected_attendance_total"]].copy()
events["date"] = pd.to_datetime(events["date"])

# ---------- DERIVE CATEGORY WASTE RATES ----------

cat_stats = (
    waste.groupby("category")["waste_qty_raw"]
    .agg(["mean", "max"])
    .reset_index()
    .rename(columns={"mean": "avg_waste_qty", "max": "max_waste_qty"})
)

cat_stats["baseline_waste_rate"] = (
    cat_stats["avg_waste_qty"] / cat_stats["max_waste_qty"]
).clip(lower=0.05, upper=0.4)

cat_stats["ai_waste_rate"] = cat_stats["baseline_waste_rate"] * 0.5

# Map waste categories to sales categories so every sales category gets rates
# (waste has "Dairy Products", "Fruits", "Baked Goods" etc.; sales has "Dairy", "Fish", "Other")
WASTE_TO_SALES_CATEGORY = {
    "Dairy Products": "Dairy",
    "Fruits": "Other",
    "Baked Goods": "Other",
    "Meat": "Meat",
    "Vegetables": "Vegetables",
}
cat_stats["sales_category"] = cat_stats["category"].map(WASTE_TO_SALES_CATEGORY)
# For unmapped waste categories, treat as Other
cat_stats["sales_category"] = cat_stats["sales_category"].fillna("Other")
# One row per sales category: take first (or mean) when multiple waste types map to same sales category
cat_stats = (
    cat_stats.groupby("sales_category", as_index=False)[["baseline_waste_rate", "ai_waste_rate"]]
    .mean()
)
cat_stats = cat_stats.rename(columns={"sales_category": "category"})
# Ensure Fish and any other missing sales categories get default rates (use overall average)
all_sales_cats = pd.DataFrame({"category": ["Dairy", "Fish", "Meat", "Other", "Vegetables"]})
default_rate = cat_stats["baseline_waste_rate"].mean()
cat_stats = all_sales_cats.merge(cat_stats, on="category", how="left")
cat_stats["baseline_waste_rate"] = cat_stats["baseline_waste_rate"].fillna(default_rate)
cat_stats["ai_waste_rate"] = cat_stats["ai_waste_rate"].fillna(default_rate * 0.5)

# ---------- MAP DISHES TO KG USED ----------

def get_kg_per_portion(cat: str) -> float:
    return KG_PER_PORTION.get(cat, KG_PER_PORTION["Other"])

sales["kg_per_portion"] = sales["category"].apply(get_kg_per_portion)
sales["qty_used_kg"] = sales["qty_sold"] * sales["kg_per_portion"]

# ---------- AGGREGATE TO INVENTORY VIEW ----------

inv_used = (
    sales.groupby(["restaurant_id", "date", "category"], as_index=False)["qty_used_kg"]
    .sum()
)

inv = inv_used.merge(
    cat_stats[["category", "baseline_waste_rate"]],
    on="category",
    how="left",
)

inv["qty_received_kg"] = inv["qty_used_kg"] / (1 - inv["baseline_waste_rate"])
inv["qty_wasted_baseline_kg"] = inv["qty_received_kg"] - inv["qty_used_kg"]

<<<<<<< Updated upstream
=======
# AI-based waste/CO2 are computed at inference time in the agent (optimize_inventory),
# not stored in the training dataset.

>>>>>>> Stashed changes
# ---------- JOIN WEATHER + EVENTS ----------

ctx = weather.merge(events, on="date", how="left")
ctx["events_count"] = ctx["events_count"].fillna(0)
ctx["expected_attendance_total"] = ctx["expected_attendance_total"].fillna(0)
inv_ctx = inv.merge(ctx, on="date", how="left")

<<<<<<< Updated upstream
# ---------- CO2 (baseline only) ----------

inv_ctx["co2e_baseline_kg"] = inv_ctx["qty_wasted_baseline_kg"] * CO2E_PER_KG_FOOD

# ---------- AGGREGATE TO WEEKLY (one row per restaurant, week_start, category) ----------

inv_ctx["date"] = pd.to_datetime(inv_ctx["date"])
inv_ctx["week_start"] = inv_ctx["date"] - pd.to_timedelta(inv_ctx["date"].dt.weekday, unit="d")

agg = inv_ctx.groupby(["restaurant_id", "week_start", "category"], as_index=False).agg(
    qty_received_kg=("qty_received_kg", "sum"),
    qty_used_kg=("qty_used_kg", "sum"),
    qty_wasted_baseline_kg=("qty_wasted_baseline_kg", "sum"),
    baseline_waste_rate=("baseline_waste_rate", "mean"),
    co2e_baseline_kg=("co2e_baseline_kg", "sum"),
    temp_max=("temp_max", "mean"),
    temp_min=("temp_min", "mean"),
    precipitation=("precipitation", "sum"),
    events_count=("events_count", "sum"),
    expected_attendance_total=("expected_attendance_total", "sum"),
)

# ---------- SAVE FINAL TRAINING DATASET (weekly) ----------

=======
# ---------- CO2 (baseline only; AI is computed in agent) ----------

inv_ctx["co2e_baseline_kg"] = inv_ctx["qty_wasted_baseline_kg"] * CO2E_PER_KG_FOOD

# ---------- SAVE FINAL TRAINING DATASET ----------
# Only features + target + baseline reference. AI metrics live in the agent pipeline.
>>>>>>> Stashed changes
final_cols = [
    "restaurant_id",
    "week_start",
    "category",
    "qty_received_kg",
    "qty_used_kg",
    "qty_wasted_baseline_kg",
    "baseline_waste_rate",
    "co2e_baseline_kg",
    "temp_max",
    "temp_min",
    "precipitation",
    "events_count",
    "expected_attendance_total",
]

final_df = agg[final_cols].sort_values(["restaurant_id", "week_start", "category"])
final_df["week_start"] = final_df["week_start"].dt.strftime("%Y-%m-%d")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
final_df.to_csv(OUT_PATH, index=False)

print(f"Saved weekly training dataset to: {OUT_PATH}")
