"""
Scrape DNJournal YTD Top 100 sales charts from the Wayback Machine.
Combines multiple years into a single CSV of real domain sales.
"""
from __future__ import annotations

import csv
import re
import urllib.request
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "data" / "sales" / "dnjournal_ytd_sales.csv"

# Wayback snapshots of DNJournal YTD sales charts
CHART_URLS = [
    "https://web.archive.org/web/20241231172736/https://www.dnjournal.com/ytd-sales-charts.htm",
    "https://web.archive.org/web/20231230000000/https://www.dnjournal.com/ytd-sales-charts.htm",
    "https://web.archive.org/web/20221230000000/https://www.dnjournal.com/ytd-sales-charts.htm",
    "https://web.archive.org/web/20211230000000/https://www.dnjournal.com/ytd-sales-charts.htm",
    "https://web.archive.org/web/20201230000000/https://www.dnjournal.com/ytd-sales-charts.htm",
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="ignore")


def parse_chart(html: str, year: str) -> list[dict]:
    """Extract domain/price pairs from a DNJournal YTD chart page."""
    sales = []
    # DNJournal chart rows are <tr> with 4-5 <td> cells:
    # rank | domain | price | venue | date
    # Strip scripts/styles, then match each row.
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(tds) < 3:
            continue
        # First cell should contain rank like "1." or "5. tie"
        rank_text = re.sub(r"<[^>]+>", "", tds[0]).strip()
        if not re.match(r"\d+\.\s*(?:tie)?", rank_text, re.I):
            continue
        # Second cell = domain
        domain_cell = tds[1]
        domain = re.sub(r"<[^>]+>", "", domain_cell).strip().lower()
        domain = re.sub(r"\s+", "", domain)
        # Third cell = price
        price_cell = tds[2]
        price_text = re.sub(r"<[^>]+>", "", price_cell).strip()
        # Extract first USD amount
        m = re.search(r"\$?([\d,]+)", price_text)
        if not m:
            continue
        price_str = m.group(1).replace(",", "")
        try:
            price_val = int(price_str)
        except ValueError:
            continue
        if price_val < 100:
            continue
        if not re.match(r"^[a-z0-9][a-z0-9\-\.]*\.[a-z]{2,}$", domain):
            continue
        tld = domain.rsplit(".", 1)[-1]
        sales.append({
            "domain": domain,
            "price": price_val,
            "currency": "USD",
            "date": f"{year}-12-31",
            "source": "dnjournal_ytd",
            "venue": "",
            "tld": tld,
        })
    return sales


def main():
    all_sales = []
    for url in CHART_URLS:
        # Infer year from URL
        m = re.search(r"/web/(\d{4})", url)
        year = m.group(1) if m else "2024"
        print(f"Fetching {year} chart...")
        try:
            html = fetch(url)
            sales = parse_chart(html, year)
            print(f"  -> {len(sales)} sales extracted")
            all_sales.extend(sales)
        except Exception as e:
            print(f"  -> failed: {e}")

    # Deduplicate by domain, keep highest price
    best = {}
    for s in all_sales:
        d = s["domain"]
        if d not in best or s["price"] > best[d]["price"]:
            best[d] = s

    deduped = list(best.values())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["domain", "price", "currency", "date", "source", "venue", "tld"])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"\nSaved {len(deduped)} unique YTD sales to {OUTPUT}")


if __name__ == "__main__":
    main()
