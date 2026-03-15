"""
Generate an expanded synthetic dataset (sales, weather, events) so the model has
many more weeks to train and test on. Uses the same dish/category structure as
sample_sales_upload.csv; adds weekday/weekend and event-driven variation so the
model can learn from context.

Usage:
  python generate_synthetic_dataset.py --weeks 12
  python generate_synthetic_dataset.py --weeks 16 --start 2025-06-09 --out-dir data/raw

Then run ingest and train:
  python ingest_uploads.py --sales data/raw/uploads/sales_synthetic_12weeks.csv --weather data/raw/weather/weather.csv --events data/raw/events/events.csv
  python train_model.py
"""
import argparse
import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
UPLOADS_DIR = RAW_DIR / "uploads"

# Same dishes as sample_sales_upload.csv (dish_id, dish_name, category, base qty_sold, price)
DISHES = [
    (1, "Paneer Tikka", "Dairy", 2.3, 12.50),
    (2, "Tomato Soup", "Vegetables", 1.1, 8.00),
    (3, "Onion Rings", "Vegetables", 5.0, 6.50),
    (4, "Chicken Curry", "Meat", 3.5, 15.00),
    (5, "Mutton Biryani", "Meat", 2.1, 18.00),
    (6, "Grilled Salmon", "Fish", 5.1, 22.00),
    (7, "Egg Fried Rice", "Meat", 4.3, 10.00),
    (8, "Basmati Rice", "Other", 3.8, 5.00),
    (9, "Sugar Cookie", "Other", 2.5, 3.50),
]


def generate_sales(
    start_date: str,
    end_date: str,
    events_df: pd.DataFrame,
    restaurant_id: int = 1,
    seed: int = 42,
) -> pd.DataFrame:
    """Daily sales per dish with weekday and event-driven variation."""
    random.seed(seed)
    events_df = events_df.set_index("date")
    dates = pd.date_range(start_date, end_date, freq="D")
    rows = []
    for d in dates:
        day = d.dayofweek
        is_weekend = day >= 5
        weekday_mult = 1.0 + (0.15 if is_weekend else -0.05)
        ds = d.strftime("%Y-%m-%d")
        ev_count = events_df.loc[ds, "events_count"] if ds in events_df.index else 0
        ev_att = events_df.loc[ds, "expected_attendance_total"] if ds in events_df.index else 0
        event_mult = 1.0 + 0.02 * (ev_count / 5) + 0.00001 * min(ev_att, 10000)
        noise = random.gauss(1.0, 0.12)
        mult = weekday_mult * event_mult * max(0.5, noise)
        for dish_id, dish_name, category, base_qty, price in DISHES:
            qty = round(base_qty * mult + random.gauss(0, 0.15), 2)
            qty = max(0.1, qty)
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "dish_id": dish_id,
                "dish_name": dish_name,
                "category": category,
                "qty_sold": qty,
                "restaurant_id": restaurant_id,
                "price": price,
            })
    return pd.DataFrame(rows)


def generate_weather(start_date: str, end_date: str, seed: int = 42) -> pd.DataFrame:
    """Synthetic daily weather: temp and precip with seasonal + random variation."""
    random.seed(seed)
    dates = pd.date_range(start_date, end_date, freq="D")
    base = 20.0
    amp = 5.0
    rows = []
    for i, d in enumerate(dates):
        day_of_year = d.timetuple().tm_yday
        seasonal = base + amp * (0.5 + 0.5 * (day_of_year / 365) * 3.14159)
        tmax = seasonal + random.gauss(2, 3)
        tmin = tmax - random.uniform(6, 10)
        precip = random.choices([0.0, random.uniform(2, 15)], weights=[0.7, 0.3])[0]
        precip = round(precip, 4)
        rows.append({"date": d.strftime("%Y-%m-%d"), "tmax_c": round(tmax, 4), "tmin_c": round(tmin, 4), "precip_mm": precip})
    return pd.DataFrame(rows)


def generate_events(start_date: str, end_date: str, seed: int = 42) -> pd.DataFrame:
    """Synthetic events: weekday vs weekend, occasional big days (same logic as generate_synthetic_events)."""
    random.seed(seed)
    dates = pd.date_range(start_date, end_date, freq="D")
    rows = []
    for d in dates:
        day = d.dayofweek
        is_weekend = day >= 5
        is_friday = day == 4
        if is_weekend or is_friday:
            lo_e, hi_e = 4, 10
            lo_a, hi_a = 2000, 7000
        else:
            lo_e, hi_e = 1, 4
            lo_a, hi_a = 400, 2000
        t = (d.day % 3) / 3.0
        events_count = int(lo_e + (hi_e - lo_e) * (0.4 + t * 0.4))
        attendance = int(lo_a + (hi_a - lo_a) * (0.4 + t * 0.4))
        if is_weekend and day == 5 and 14 <= d.day <= 21:
            events_count = int(events_count * 1.8)
            attendance = int(attendance * 1.8)
        rows.append({"date": d.strftime("%Y-%m-%d"), "events_count": events_count, "expected_attendance_total": attendance})
    return pd.DataFrame(rows)


def update_sample_and_context(
    sample_week_start: str = "2026-03-09",
    context_weeks: int = 2,
    seed: int = 42,
) -> None:
    """Update sample_sales_upload.csv to the given week and append weather/events for sample + next week."""
    start = pd.Timestamp(sample_week_start)
    sample_end = start + pd.Timedelta(days=6)
    context_end = start + pd.Timedelta(days=context_weeks * 7 - 1)
    start_str = start.strftime("%Y-%m-%d")
    sample_end_str = sample_end.strftime("%Y-%m-%d")
    context_end_str = context_end.strftime("%Y-%m-%d")

    events_range = generate_events(start_str, context_end_str, seed=seed)
    weather_range = generate_weather(start_str, context_end_str, seed=seed)
    sales_sample = generate_sales(start_str, sample_end_str, events_range, seed=seed)

    sample_path = ROOT / "sample_sales_upload.csv"
    sales_sample.to_csv(sample_path, index=False)
    print(f"Sample sales: {start_str} to {sample_end_str} -> {sample_path}")

    weather_path = RAW_DIR / "weather" / "weather.csv"
    events_path = RAW_DIR / "events" / "events.csv"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "weather").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "events").mkdir(parents=True, exist_ok=True)

    for path, new_df, date_col in [
        (weather_path, weather_range, "date"),
        (events_path, events_range, "date"),
    ]:
        new_df = new_df.copy()
        new_df[date_col] = pd.to_datetime(new_df[date_col])
        if path.exists():
            existing = pd.read_csv(path)
            existing[date_col] = pd.to_datetime(existing[date_col])
            overlap_start, overlap_end = new_df[date_col].min(), new_df[date_col].max()
            existing = existing[(existing[date_col] < overlap_start) | (existing[date_col] > overlap_end)]
            combined = pd.concat([existing, new_df], ignore_index=True).sort_values(date_col)
        else:
            combined = new_df.sort_values(date_col)
        combined[date_col] = combined[date_col].dt.strftime("%Y-%m-%d")
        combined.to_csv(path, index=False)
        print(f"  Updated {path.name}: added {start_str} to {context_end_str}")

    print("Sample and context updated. Run forecast with sample_sales_upload.csv to see current week + next week prediction.")


def fill_weather_events_gap(
    gap_start: str = "2025-09-01",
    gap_end: str = "2026-03-08",
    seed: int = 42,
) -> None:
    """Fill the date gap in weather.csv and events.csv so data is continuous from file start to current."""
    weather_path = RAW_DIR / "weather" / "weather.csv"
    events_path = RAW_DIR / "events" / "events.csv"
    if not weather_path.exists() or not events_path.exists():
        print("Both data/raw/weather/weather.csv and data/raw/events/events.csv must exist.")
        return

    weather_gap = generate_weather(gap_start, gap_end, seed=seed)
    events_gap = generate_events(gap_start, gap_end, seed=seed)

    gap_start_dt = pd.to_datetime(gap_start)
    gap_end_dt = pd.to_datetime(gap_end)

    for path, gap_df in [(weather_path, weather_gap), (events_path, events_gap)]:
        date_col = "date"
        existing = pd.read_csv(path)
        existing[date_col] = pd.to_datetime(existing[date_col])
        before = existing[existing[date_col] < gap_start_dt]
        after = existing[existing[date_col] > gap_end_dt]
        gap_df = gap_df.copy()
        gap_df[date_col] = pd.to_datetime(gap_df[date_col])
        combined = pd.concat([before, gap_df, after], ignore_index=True).sort_values(date_col)
        combined[date_col] = combined[date_col].dt.strftime("%Y-%m-%d")
        combined.to_csv(path, index=False)
        print(f"  {path.name}: filled {gap_start} to {gap_end} ({len(gap_df)} days)")

    print("Gap filled. Weather and events are now continuous from start to current.")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate expanded synthetic sales, weather, and events for training.")
    p.add_argument("--weeks", type=int, default=12, help="Number of weeks of data (default 12)")
    p.add_argument("--start", default="2025-06-09", help="Start date (Monday of first week)")
    p.add_argument("--out-dir", type=Path, default=RAW_DIR, help="Base output directory (data/raw)")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--sample", action="store_true", help="Update sample_sales_upload.csv to most recent week and append weather/events for next-week prediction")
    p.add_argument("--fill-gap", action="store_true", help="Fill date gap in weather/events from 2025-09-01 to 2026-03-08 so data is continuous from start to current")
    args = p.parse_args()

    if args.sample:
        update_sample_and_context(sample_week_start="2026-03-09", context_weeks=2, seed=args.seed)
        return
    if args.fill_gap:
        fill_weather_events_gap(gap_start="2025-09-01", gap_end="2026-03-08", seed=args.seed)
        return

    start = pd.Timestamp(args.start)
    end = start + pd.Timedelta(days=args.weeks * 7 - 1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    events_df = generate_events(start_str, end_str, seed=args.seed)
    weather_df = generate_weather(start_str, end_str, seed=args.seed)
    sales_df = generate_sales(start_str, end_str, events_df, seed=args.seed)

    out = args.out_dir
    (out / "uploads").mkdir(parents=True, exist_ok=True)
    (out / "weather").mkdir(parents=True, exist_ok=True)
    (out / "events").mkdir(parents=True, exist_ok=True)

    sales_path = out / "uploads" / f"sales_synthetic_{args.weeks}weeks.csv"
    weather_path = out / "weather" / "weather.csv"
    events_path = out / "events" / "events.csv"

    sales_df.to_csv(sales_path, index=False)
    weather_df.to_csv(weather_path, index=False)
    events_df.to_csv(events_path, index=False)

    print(f"Generated {args.weeks} weeks ({start_str} to {end_str}):")
    print(f"  Sales:   {len(sales_df)} rows -> {sales_path}")
    print(f"  Weather: {len(weather_df)} rows -> {weather_path}")
    print(f"  Events:  {len(events_df)} rows -> {events_path}")
    print()
    print("Next:")
    print(f"  python ingest_uploads.py --sales {sales_path} --weather {weather_path} --events {events_path}")
    print("  python train_model.py")


if __name__ == "__main__":
    main()
