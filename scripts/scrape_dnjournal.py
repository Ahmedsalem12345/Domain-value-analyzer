#!/usr/bin/env python3
"""Collect free domain sales data from DNJournal archives.

Sources:
  - DNJournal bi-weekly sales reports (2023-2026 by default).
  - Uniregistry 2015 previously-unreported sales Excel file.

Output: data/sales/dnjournal_sales.csv
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

ARCHIVE_BASE = "https://dnjournal.com/archive/"
UNIREGISTRY_URL = (
    "https://dnjournal.com/archive/domainsales/2015/"
    "2015-Uniregistry-Previously-Unreported-Sales.xlsx"
)
YEARS = [2023, 2024, 2025, 2026]
SLEEP_SECONDS = 1.0
MIN_PRICE = 100
MAX_PRICE = 100_000_000

PRICE_RE = re.compile(r"(?:(?:€|£)\s*[\d,.]+\s*=\s*)?\$\s*([\d,.]+)", re.IGNORECASE)


def normalize_price(raw: str) -> int | None:
    raw = raw.replace(",", "")
    m = PRICE_RE.search(raw)
    if not m:
        return None
    try:
        val = int(float(m.group(1)))
    except ValueError:
        return None
    if MIN_PRICE <= val <= MAX_PRICE:
        return val
    return None


def is_domain(token: str) -> bool:
    token = token.strip("*#_()[]{} \n\t<>'\"").rstrip(".,")
    if not token or " " in token or "@" in token:
        return False
    if token.lower().startswith(("http://", "https://")):
        return False
    if token.count(".") < 1 or token.count(".") > 2:
        return False
    # Reject things like .jpg / .png
    if token.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".pdf", ".htm", ".html")):
        return False
    return True


def extract_pairs_from_report(html: str, report_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = []
    for line in text.splitlines():
        line = line.strip().replace("**", "")
        if line:
            lines.append(line)

    records = []
    i = 0
    while i < len(lines) - 1:
        candidate = lines[i]
        if is_domain(candidate):
            domain = candidate.lower().rstrip(".,")
            for j in range(i + 1, min(i + 8, len(lines))):
                price = normalize_price(lines[j])
                if price is not None:
                    records.append(
                        {
                            "domain": domain,
                            "price": price,
                            "currency": "USD",
                            "date": "",
                            "source": "dnjournal",
                            "venue": "",
                            "tld": domain.split(".")[-1],
                            "report_url": report_url,
                        }
                    )
                    i = j
                    break
        i += 1
    return records


def collect_report_urls(years: list[int]) -> list[str]:
    urls = []
    for year in years:
        if year == 2026:
            archive_url = f"{ARCHIVE_BASE}domainsales-archive.htm"
        else:
            archive_url = f"{ARCHIVE_BASE}domainsales-archive-{year}.htm"
        print(f"Collecting report URLs from {archive_url} ...")
        resp = requests.get(
            archive_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(rf"domainsales/{year}/\d{{4}}\.htm$", href):
                urls.append(urljoin(archive_url, href))
        time.sleep(SLEEP_SECONDS)
    # Stable order, current first
    return sorted(set(urls), reverse=True)


def fetch_report(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    return resp.text


def scrape_reports(urls: list[str]) -> list[dict]:
    seen = set()
    records = []
    for idx, url in enumerate(urls, 1):
        print(f"  [{idx}/{len(urls)}] {url}")
        try:
            html = fetch_report(url)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue
        pairs = extract_pairs_from_report(html, url)
        new = [r for r in pairs if r["domain"] not in seen]
        for r in new:
            seen.add(r["domain"])
        records.extend(new)
        print(f"    +{len(new)} new (total {len(records)})")
        time.sleep(SLEEP_SECONDS)
    return records


def load_uniregistry_sales() -> list[dict]:
    print(f"Downloading Uniregistry 2015 sales from {UNIREGISTRY_URL} ...")
    resp = requests.get(UNIREGISTRY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    xlsx_path = Path("/tmp/dnjournal_uniregistry_2015.xlsx")
    xlsx_path.write_bytes(resp.content)

    df = pd.read_excel(xlsx_path)
    records = []
    for _, row in df.iterrows():
        domain = str(row.get("DomainName", "")).strip().lower()
        price = row.get("Price")
        if not domain or pd.isna(price):
            continue
        try:
            price = int(float(price))
        except (ValueError, TypeError):
            continue
        if MIN_PRICE <= price <= MAX_PRICE:
            records.append(
                {
                    "domain": domain,
                    "price": price,
                    "currency": "USD",
                    "date": "2015",
                    "source": "dnjournal_uniregistry",
                    "venue": "Uniregistry",
                    "tld": domain.split(".")[-1],
                    "report_url": UNIREGISTRY_URL,
                }
            )
    print(f"  +{len(records)} Uniregistry records")
    return records


def main():
    project_root = Path(__file__).resolve().parent.parent
    out_path = project_root / "data" / "sales" / "dnjournal_sales.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Step 1: Collecting DNJournal report URLs ...")
    report_urls = collect_report_urls(YEARS)
    print(f"Found {len(report_urls)} reports.")

    print("Step 2: Scraping reports ...")
    report_records = scrape_reports(report_urls)

    print("Step 3: Loading Uniregistry 2015 Excel ...")
    uniregistry_records = load_uniregistry_sales()

    # Combine and dedupe by domain (first occurrence wins)
    all_records = report_records + uniregistry_records
    seen = set()
    deduped = []
    for r in all_records:
        if r["domain"] in seen:
            continue
        seen.add(r["domain"])
        deduped.append(r)

    fieldnames = ["domain", "price", "currency", "date", "source", "venue", "tld"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in deduped:
            writer.writerow({k: r[k] for k in fieldnames})

    print(f"\nSaved {len(deduped)} unique records to {out_path}")
    sources = {}
    for r in deduped:
        sources[r["source"]] = sources.get(r["source"], 0) + 1
    print("By source:", sources)


if __name__ == "__main__":
    main()
