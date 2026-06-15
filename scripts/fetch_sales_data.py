#!/usr/bin/env python3
"""Fetch publicly reported domain sales from DomainPro.io and save a clean CSV."""

import csv
import os
import sys
from pathlib import Path

import requests

API_URL = "https://www.domainpro.io/api/sales"
BATCH_SIZE = 500
MAX_PRICE = 10_000_000  # drop obviously malformed prices (e.g. foreign-currency bugs)


def fetch_all_sales(limit_per_call=BATCH_SIZE):
    """Iterate DomainPro API offsets until all sales are downloaded."""
    all_sales = []
    offset = 0
    while True:
        params = {"offset": offset, "limit": limit_per_call}
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("sales", [])
        if not batch:
            break
        all_sales.extend(batch)
        print(f"  fetched {len(all_sales)} / {data.get('total', '?')} ...", end="\r")
        if len(all_sales) >= data.get("total", len(all_sales)):
            break
        offset += limit_per_call
    print()
    return all_sales


def _recover_price(price):
    """DomainPro encodes some foreign-currency sales as original*100000+usd.

    Example: 2070623812 -> original 20706, USD 23812.
    """
    if price > 1_000_000:
        usd_part = int(price) % 100_000
        original_part = int(price) // 100_000
        if 0 < usd_part <= MAX_PRICE and original_part > 0:
            return usd_part
        return None
    return int(price)


def clean_sales(raw_sales):
    """Remove malformed/duplicate rows and recover concatenated prices."""
    seen = set()
    cleaned = []
    for row in raw_sales:
        price = row.get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        price = _recover_price(price)
        if price is None or price > MAX_PRICE:
            continue
        domain = str(row.get("domain", "")).strip().lower()
        if not domain or "." not in domain:
            continue
        date = str(row.get("date", "")).strip()
        key = (domain, price, date)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "domain": domain,
            "price": int(price),
            "currency": str(row.get("currency", "USD")).upper(),
            "date": date,
            "source": str(row.get("source", "")).strip().lower(),
            "venue": str(row.get("venue", "")).strip(),
            "tld": str(row.get("tld", domain.split(".")[-1])).lower(),
        })
    return cleaned


def save_csv(sales, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["domain", "price", "currency", "date", "source", "venue", "tld"],
        )
        writer.writeheader()
        writer.writerows(sales)
    return path


def main():
    project_root = Path(__file__).resolve().parent.parent
    out_path = project_root / "data" / "sales" / "domainpro_sales.csv"

    print(f"Fetching sales from {API_URL} ...")
    raw = fetch_all_sales()
    print(f"Raw rows: {len(raw)}")

    cleaned = clean_sales(raw)
    print(f"Clean rows: {len(cleaned)}")

    save_csv(cleaned, out_path)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
