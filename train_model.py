 # train_forecast_model.py
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import joblib

DATA_DIR = Path("data_dir")
MODEL_DIR = Path("models_dir")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(DATA_DIR / "restaurant_inventory_waste_joined.csv")

df["date"] = pd.to_datetime(df["date"])
df["day_of_week"] = df["date"].dt.weekday

# Features and target
feature_cols = [
    "category",
    "day_of_week",
    "temp_max",
    "temp_min",
    "precipitation",
    "events_count",
    "expected_attendance_total",
]
target_col = "qty_used_kg"

# One‑hot encode category
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
