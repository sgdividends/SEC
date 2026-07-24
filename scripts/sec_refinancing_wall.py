#!/usr/bin/env python3
"""
sec_refinancing_wall.py
Pulls aggregate corporate debt-maturity data from SEC EDGAR's XBRL Frames
API, sums it across all reporting companies per quarter, and caches the
result to CSV. This is a SAMPLE proxy (not every filer uses these exact
tags), intended to track directional trend, not an exact total.
"""

import time
import datetime as dt
from pathlib import Path

import requests
import pandas as pd

# SEC REQUIRES a real identifying User-Agent. Replace with YOUR name/email.
# Requests without this get blocked.
HEADERS = {"User-Agent": "YourName research-script yourname@example.com"}

BASE_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json"
CACHE_PATH = Path("data/sec_edgar/refinancing_wall.csv")

# Standard XBRL tags companies use for their debt maturity ladder,
# broken out by "year N from now" bucket.
TAGS = {
    "year1_wall": "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "year2_wall": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "year3_wall": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    "year4_wall": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    "year5_wall": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
}


def last_completed_quarter_periods(n_quarters=8):
    """
    Returns the last N completed-calendar-quarter period codes in SEC's
    'CYyyyyQq I' instant format, skipping the most recent quarter since
    filings for it likely aren't complete yet (10-Qs have a ~45 day lag).
    """
    today = dt.date.today()
    q = (today.month - 1) // 3 + 1
    year, quarter = today.year, q - 1
    if quarter == 0:
        year, quarter = year - 1, 4

    periods = []
    for _ in range(n_quarters):
        periods.append(f"CY{year}Q{quarter}I")
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return periods


def fetch_frame_sum(tag: str, period: str) -> float:
    url = BASE_URL.format(tag=tag, period=period)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return None  # no data filed yet for this tag/period combo
    resp.raise_for_status()
    data = resp.json()
    values = [row["val"] for row in data.get("data", []) if row.get("val") is not None]
    return sum(values) if values else None


def build_dataframe() -> pd.DataFrame:
    periods = last_completed_quarter_periods()
    rows = []
    for period in periods:
        row = {"period": period}
        for col_name, tag in TAGS.items():
            row[col_name] = fetch_frame_sum(tag, period)
            time.sleep(0.25)  # stay well under SEC's 10 req/sec limit
        rows.append(row)
        print(f"  {period}: {row}")
    df = pd.DataFrame(rows)
    df["total_5yr_wall"] = df[list(TAGS.keys())].sum(axis=1, skipna=True)
    return df


def update_cache(df_new: pd.DataFrame) -> pd.DataFrame:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_PATH.exists():
        df_old = pd.read_csv(CACHE_PATH)
        merged = pd.concat([df_old, df_new]).drop_duplicates(
            subset="period", keep="last"
        )
    else:
        merged = df_new
    merged.to_csv(CACHE_PATH, index=False)
    return merged


def main():
    print(f"[{dt.datetime.now()}] Fetching SEC EDGAR refinancing-wall frames...")
    df = build_dataframe()
    merged = update_cache(df)
    print(f"\nCache updated: {CACHE_PATH} ({len(merged)} quarters on file)")


if __name__ == "__main__":
    main()
