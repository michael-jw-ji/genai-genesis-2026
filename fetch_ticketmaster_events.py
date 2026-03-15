"""
Fetch events from Ticketmaster Discovery API v2 and write the pipeline events CSV.

Uses Event Search: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
- Event Search: GET /discovery/v2/events.json with city, countryCode, postalCode, latlong,
  startDateTime, endDateTime, size, page, sort.
- Response: _embedded.events[] with dates.start.localDate and _embedded.venues[] (no capacity in search).
- Rate limit: 5000 calls/day, 5 req/s. Deep paging: size * page < 1000.

Output: data/raw/events/events.csv with columns date, events_count, expected_attendance_total.
Run before ingest_uploads.py or point --output at your events file.

Usage:
  Set TICKETMASTER_API_KEY in env, then:
  python fetch_ticketmaster_events.py --city "San Francisco" --country US
  python fetch_ticketmaster_events.py --postal-code 94102 --country US
  python fetch_ticketmaster_events.py --latlong "37.7749,-122.4194" --radius 25
  python fetch_ticketmaster_events.py --city Boston --country US --days 14 --output data/raw/events/events.csv
"""
import argparse
import os
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
RAW_EVENTS_DIR = ROOT / "data" / "raw" / "events"
DISCOVERY_BASE = "https://app.ticketmaster.com/discovery/v2"
# Discovery API: 5 req/s; deep paging max index 1000 (size * page < 1000)
RATE_LIMIT_DELAY = 0.21
MAX_PAGE_INDEX = 1000


def fetch_events_page(
    apikey: str,
    *,
    city: str | None = None,
    country: str | None = None,
    postal_code: str | None = None,
    latlong: str | None = None,
    radius: int = 25,
    start_datetime: str,
    end_datetime: str,
    page: int = 0,
    size: int = 200,
) -> dict:
    """Call Discovery API Event Search. See Discovery API v2 Event Search query parameters."""
    params = {
        "apikey": apikey,
        "startDateTime": start_datetime,
        "endDateTime": end_datetime,
        "size": size,
        "page": page,
        "sort": "date,asc",
    }
    if city:
        params["city"] = city
    if country:
        params["countryCode"] = country
    if postal_code:
        params["postalCode"] = postal_code
    if latlong:
        params["latlong"] = latlong
        params["radius"] = str(radius)
        params["unit"] = "miles"

    r = requests.get(
        f"{DISCOVERY_BASE}/events.json",
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def extract_date_and_attendance(event: dict) -> tuple[str | None, int]:
    """Return (localDate, estimated_attendance). Event Search response has dates.start.localDate; venues do not include capacity."""
    dates = event.get("dates", {}).get("start", {})
    local_date = dates.get("localDate")
    if not local_date:
        return None, 0
    attendance = 0
    venues = (event.get("_embedded") or {}).get("venues") or []
    if venues and "capacity" in venues[0]:
        try:
            attendance = int(venues[0]["capacity"])
        except (TypeError, ValueError):
            pass
    if attendance <= 0:
        attendance = 500
    return local_date, attendance


def fetch_events_in_range(
    apikey: str,
    start_date: str,
    end_date: str,
    *,
    city: str | None = None,
    country: str | None = None,
    postal_code: str | None = None,
    latlong: str | None = None,
    radius: int = 25,
    size: int = 200,
) -> dict[str, tuple[int, int]]:
    """Fetch all events in range; return dict date -> (events_count, expected_attendance_total). Enforces deep paging limit (size*page < 1000)."""
    start_dt = f"{start_date}T00:00:00Z"
    end_dt = f"{end_date}T23:59:59Z"

    by_date: dict[str, list[int]] = defaultdict(list)
    page = 0
    while True:
        if page * size >= MAX_PAGE_INDEX:
            break
        time.sleep(RATE_LIMIT_DELAY)
        data = fetch_events_page(
            apikey,
            city=city,
            country=country,
            postal_code=postal_code,
            latlong=latlong,
            radius=radius,
            start_datetime=start_dt,
            end_datetime=end_dt,
            page=page,
            size=size,
        )
        events = (data.get("_embedded") or {}).get("events") or []
        if not events:
            break
        for ev in events:
            local_date, attendance = extract_date_and_attendance(ev)
            if local_date:
                by_date[local_date].append(attendance)
        total_pages = data.get("page", {}).get("totalPages", 1)
        if page >= total_pages - 1:
            break
        page += 1

    return {
        d: (len(attendances), sum(attendances))
        for d, attendances in by_date.items()
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch Ticketmaster Discovery API events and write pipeline events CSV")
    p.add_argument("--apikey", default=os.environ.get("TICKETMASTER_API_KEY"), help="API key (or set TICKETMASTER_API_KEY)")
    p.add_argument("--city", help="City name (e.g. San Francisco)")
    p.add_argument("--postal-code", dest="postal_code", help="Postal/zip code (e.g. 94102)")
    p.add_argument("--country", default="US", help="Country code (default US)")
    p.add_argument("--latlong", help="Lat,long (e.g. 37.7749,-122.4194); overrides city/postal")
    p.add_argument("--radius", type=int, default=25, help="Radius in miles when using --latlong (default 25)")
    p.add_argument("--days", type=int, default=30, help="Number of days from today to fetch (default 30)")
    p.add_argument("--start-date", dest="start_date", help="Start date YYYY-MM-DD (overrides --days; use with --end-date to match sample CSV)")
    p.add_argument("--end-date", dest="end_date", help="End date YYYY-MM-DD")
    p.add_argument("--output", type=Path, default=RAW_EVENTS_DIR / "events.csv", help="Output CSV path")
    args = p.parse_args()

    if not args.apikey:
        p.error("Set TICKETMASTER_API_KEY or pass --apikey")

    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            p.error("Provide both --start-date and --end-date")
        if not args.latlong and not args.city and not args.postal_code:
            p.error("Provide --city, --postal-code, or --latlong (used for API call; past dates may return no events)")
        start_date = args.start_date
        end_date = args.end_date
        by_date = fetch_events_in_range(
            args.apikey,
            start_date,
            end_date,
            city=args.city,
            country=args.country,
            postal_code=args.postal_code,
            latlong=args.latlong,
            radius=args.radius,
        )
    else:
        if not args.latlong and not args.city and not args.postal_code:
            p.error("Provide --city, --postal-code, or --latlong")
        today = pd.Timestamp.utcnow().normalize()
        start_date = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (today + pd.Timedelta(days=args.days)).strftime("%Y-%m-%d")
        by_date = fetch_events_in_range(
            args.apikey,
            start_date,
            end_date,
            city=args.city,
            country=args.country,
            postal_code=args.postal_code,
            latlong=args.latlong,
            radius=args.radius,
        )

    # Full date range so pipeline merge with weather has one row per day
    dates = pd.date_range(start_date, end_date, freq="D").strftime("%Y-%m-%d")
    rows = [
        (d, by_date.get(d, (0, 0))[0], by_date.get(d, (0, 0))[1])
        for d in dates
    ]
    df = pd.DataFrame(rows, columns=["date", "events_count", "expected_attendance_total"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} rows to {args.output}")


if __name__ == "__main__":
    main()
