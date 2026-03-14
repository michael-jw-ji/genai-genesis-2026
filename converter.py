import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")

# Read CSV sales dataset
sales_raw = pd.read_csv(DATA_DIR / "Sales Dataset.csv")  # adjust name if needed

# Rename columns to the schema we use later
sales = sales_raw.rename(columns={
    "System Date": "date",
    "Food ID": "dish_id",
    "Food Name": "dish_name",
    "Food Category": "category",   # or "FoodTypeName" if that’s better
    "Quantity": "qty_sold",
    "Restaurant Name": "restaurant_id",
    "Total Price": "price",        # optional
})

# Parse date column
sales["date"] = pd.to_datetime(sales["date"])

# Save normalized version as sales.csv for the main pipeline
sales.to_csv(DATA_DIR / "sales.csv", index=False)

print("Wrote normalized sales.csv to", DATA_DIR)
