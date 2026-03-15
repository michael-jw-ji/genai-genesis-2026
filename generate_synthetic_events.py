"""
Generate synthetic events (date, events_count, expected_attendance_total) so the model
can learn from event variation during training.

Pattern: weekday vs weekend (more events Fri–Sun), one or two "big" days per month so the
model sees a clear signal. Values match real Ticketmaster-style data when aggregated weekly.

Usage:
  python generate_synthetic_events.py --weeks 12
  python generate_synthetic_events.py --weeks 12 --start 2025-06-09 --output data/raw/events/events.csv
  python generate_synthetic_events.py --start 2025-06-09 --end 2025-06-22
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_EVENTS_DIR = ROOT / "data" / "raw" / "events"


def generate_synthetic_events(
    start_date: str,
    end_date: str,
    *,
    weekday_events: tuple[int, int] = (1, 4),
    weekday_attendance: tuple[int, int] = (400, 2000),
    weekend_events: tuple[int, int] = (4, 10),
    weekend_attendance: tuple[int, int] = (2000, 7000),
    big_day_boost: float = 1.8,
) -> pd.DataFrame:
    """
    Generate events_count and expected_attendance_total per day.
    Weekends (Sat/Sun) and Friday get higher counts; one Saturday gets a 'big day' boost.
    """
    dates = pd.date_range(start_date, end_date, freq="D")
    rows = []
    for d in dates:
        day = d.dayofweek  # 0=Mon .. 6=Sun
        is_weekend = day >= 5
        is_friday = day == 4
        if is_weekend or is_friday:
            lo_e, hi_e = weekend_events
            lo_a, hi_a = weekend_attendance
        else:
            lo_e, hi_e = weekday_events
            lo_a, hi_a = weekday_attendance
        # One Saturday per month gets a "big event day" boost (e.g. arena night)
        is_big_day = is_weekend and day == 5 and 14 <= d.day <= 21
        # Slight variation by day-of-month so not every Friday is identical
        t = (d.day % 3) / 3.0
        events_count = int(lo_e + (hi_e - lo_e) * (0.4 + t * 0.4))
        attendance = int(lo_a + (hi_a - lo_a) * (0.4 + t * 0.4))
        if is_big_day:
            events_count = int(events_count * big_day_boost)
            attendance = int(attendance * big_day_boost)
        rows.append((d.strftime("%Y-%m-%d"), events_count, attendance))

    return pd.DataFrame(rows, columns=["date", "events_count", "expected_attendance_total"])


def main() -> None:
    p = argparse.ArgumentParser(description="Generate synthetic events CSV for training (align with sales date range)")
    p.add_argument("--weeks", type=int, default=None, help="Number of weeks (overrides --end; use 12 to match expanded dataset)")
    p.add_argument("--start", default="2025-06-09", help="Start date (Monday of first week)")
    p.add_argument("--end", default="2025-06-22", help="End date (ignored if --weeks is set)")
    p.add_argument("--output", type=Path, default=RAW_EVENTS_DIR / "events.csv", help="Output CSV path")
    args = p.parse_args()

    if args.weeks is not None:
        start = pd.Timestamp(args.start)
        end = start + pd.Timedelta(days=args.weeks * 7 - 1)
        end_str = end.strftime("%Y-%m-%d")
    else:
        end_str = args.end
    df = generate_synthetic_events(args.start, end_str)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} rows to {args.output}")


if __name__ == "__main__":
    main()
