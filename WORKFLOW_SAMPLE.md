# Full workflow using sample_sales_upload.csv

Run these in order from the project root.

---

## 0a. (Recommended) Expanded synthetic dataset for training

The sample has only ~2 weeks; the model needs more data to train and test. Generate 12 (or more) weeks of synthetic sales, weather, and events with the same dish/category structure and sensible variation (weekday vs weekend, event-driven demand):

```bash
python generate_synthetic_dataset.py --weeks 12
```

- Writes **data/raw/uploads/sales_synthetic_12weeks.csv**, **data/raw/weather/weather.csv**, **data/raw/events/events.csv**.
- Then run step 1 with those files (see below). Result: **restaurant_inventory_waste_joined.csv** with 12 weeks × 5 categories = 60 rows (train/test split in step 2).

Optional: `--weeks 16`, `--start 2025-06-09`, `--seed 123`.

---

## 0b. (Optional) Events only for the pipeline

**Synthetic events (recommended for training):** So the model sees event variation. Aligns with sample weeks (2025-06-09 to 2025-06-22). Weekdays fewer events, Fri–Sun more; one Saturday is a "big" day.

```bash
python generate_synthetic_events.py
```

Writes **data/raw/events/events.csv**. Use it in step 1 so the joined CSV has non-zero `events_count` and `expected_attendance_total`.

**Match sample week with Ticketmaster (zeros only):** The sample sales run **2025-06-10** through **2025-06-16**. The pipeline’s first week starts **Monday 2025-06-09**. To align events with that week, use:

```bash
python fetch_ticketmaster_events.py --start-date 2025-06-09 --end-date 2025-06-16 --city Toronto --country CA --output data/raw/events/events.csv
```

- For that past date range the API returns no events, so the CSV has zeros. Timelines then match the joined CSV.

**Live Toronto events (next 30 days):** For current/future dates:

```bash
python fetch_ticketmaster_events.py --city Toronto --country CA --days 30
```

- Requires `.env` with `TICKETMASTER_API_KEY` (Consumer Key from developer portal).
- Then use **data/raw/events/events.csv** in step 1 (e.g. `--events data/raw/events/events.csv`).

---

## 1. Ingest uploads (sales + weather + events) and build joined CSV

**Using the expanded synthetic dataset (recommended):**

```bash
python ingest_uploads.py --sales data/raw/uploads/sales_synthetic_12weeks.csv --weather data/raw/weather/weather.csv --events data/raw/events/events.csv
```

**Using the small sample (2 weeks):**

```bash
python ingest_uploads.py --sales sample_sales_upload.csv --weather data/raw/weather/weather.csv --events data/raw/events/events.csv
```

- Writes **data/processed/sales.csv** from the sample.
- Writes **data/raw/weather/weather.csv** and **data/raw/events/events.csv** (same as input).
- Expects **data/raw/waste/food_wastage_data.csv** to exist (it does).
- Runs **dataset_creator.py** and writes **data/processed/restaurant_inventory_waste_joined.csv** (weekly).

---

## 2. Train the model

```bash
python train_model.py
```

- Reads **data/processed/restaurant_inventory_waste_joined.csv**.
- Builds lagged features, trains Random Forest, saves **models_dir/forecast_qty_used_rf.joblib** and **models_dir/forecast_feature_cols.joblib**.

---

## 3. Run the agent pipeline (forecast + optimize + summary)

```bash
python run_agent_pipeline.py
```

- Uses the trained model and **data/processed/restaurant_inventory_waste_joined.csv** as history for lags.
- Builds weekly features for the date range in the script (e.g. 2026-03-14 to 2026-03-20), predicts qty_used_kg, runs optimizer, prints summary.

---

## Summary order

| Step | Script | What it does |
|------|--------|----------------|
| 1 | `ingest_uploads.py` | Sample sales + weather + events → normalized files + **restaurant_inventory_waste_joined.csv** |
| 2 | `train_model.py` | Joined CSV → trained model + feature list in **models_dir/** |
| 3 | `run_agent_pipeline.py` | Model + history → forecast for a date range and print plan summary |

Note: **sample_sales_upload.csv** only has 7 days (2025-06-10 to 2025-06-16), so the joined CSV has one week (5 rows: one per category). For a useful model you’ll want more weeks of sales (and matching weather/events) before step 2.
