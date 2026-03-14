 # train_forecast_model.py
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import joblib

ROOT = Path(__file__).resolve().parent
PROCESSED_DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models_dir"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(PROCESSED_DATA_DIR / "restaurant_inventory_waste_joined.csv")

df["week_start"] = pd.to_datetime(df["week_start"])
df["week_of_year"] = df["week_start"].dt.isocalendar().week.astype(int)
df["month"] = df["week_start"].dt.month
df["restaurant_id"] = pd.to_numeric(df["restaurant_id"], errors="coerce").fillna(0).astype(int)

# Lagged features: previous week's usage and received (same restaurant + category)
lag_df = df[["restaurant_id", "category", "week_start", "qty_used_kg", "qty_received_kg"]].copy()
lag_df["week_start"] = lag_df["week_start"] + pd.Timedelta(days=7)
lag_df = lag_df.rename(columns={"qty_used_kg": "qty_used_kg_prev_week", "qty_received_kg": "qty_received_kg_prev_week"})
df = df.merge(lag_df, on=["restaurant_id", "category", "week_start"], how="left")
df["qty_used_kg_prev_week"] = df["qty_used_kg_prev_week"].fillna(0.0)
df["qty_received_kg_prev_week"] = df["qty_received_kg_prev_week"].fillna(0.0)

# Features: context + previous week usage/prep (all known at forecast time)
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
target_col = "qty_used_kg"

df_model = pd.get_dummies(df[feature_cols], columns=["category"])
X = df_model
y = df[target_col]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestRegressor(
    n_estimators=300,
    max_depth=8,
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
print("MAE qty_used_kg:", mae)

# Save model + columns for use in the agent
joblib.dump(model, MODEL_DIR / "forecast_qty_used_rf.joblib")
joblib.dump(list(X.columns), MODEL_DIR / "forecast_feature_cols.joblib")
