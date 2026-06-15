"""
Build a realistic expanded sales dataset by augmenting the 500 real
sales records with synthetic variants generated from retailstats moments.

For each real sale we extract the keyword(s), look up their retailstats
price distribution, then generate many plausible synthetic sales that
follow the same market segment but vary in SLD shape and TLD.
"""
from __future__ import annotations

import csv
import math
import random
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

ROOT = Path(__file__).parent.parent
RETAILSTATS = ROOT / "retailstats_20260427.csv"
REAL_SALES = ROOT / "data" / "sales" / "domainpro_sales.csv"
OUTPUT = ROOT / "data" / "sales" / "combined_sales_realistic.csv"

POSITIONS = ("exact", "start", "end", "middle")
POS_WEIGHTS = {"exact": 1.0, "start": 0.55, "end": 0.60, "middle": 0.25}

TLD_WEIGHTS = {
    "com": 55, "net": 6, "org": 6, "io": 8, "ai": 5, "co": 3,
    "co.uk": 2, "de": 2, "app": 2, "dev": 1, "me": 1, "tv": 1,
    "info": 1, "biz": 1, "xyz": 2, "us": 1, "online": 1, "site": 1,
    "shop": 1, "store": 1, "tech": 1, "club": 1,
}
TLDS = list(TLD_WEIGHTS.keys())
TLD_P = [w / sum(TLD_WEIGHTS.values()) for w in TLD_WEIGHTS.values()]

PREFIXES = ["my", "the", "web", "online", "pro", "best", "top", "new", "get", "go",
            "buy", "shop", "store", "app", "hq", "hub", "now", "smart", "easy",
            "fast", "max", "plus", "group", "global", "world", "digital", "cloud"]
SUFFIXES = PREFIXES + ["inc", "co", "llc", "corp", "io", "ai", "app", "tech",
                       "media", "lab", "hq", "box", "ly", "ify", "able"]


def load_retail_stats(path: Path) -> dict:
    data = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = row["keyword"].strip().lower()
            if not kw:
                continue
            rec = {"keyword": kw}
            for p in POSITIONS:
                for col in ("sale_count", "price_sum", "price_avg", "price_max", "price_stddev"):
                    key = f"{p}_{col}"
                    try:
                        rec[key] = float(row.get(key, 0) or 0)
                    except ValueError:
                        rec[key] = 0.0
            data[kw] = rec
    return data


def load_real_sales(path: Path) -> list[dict]:
    sales = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                price = int(float(row["price"]))
            except (ValueError, KeyError):
                continue
            domain = (row.get("domain") or "").lower().strip()
            if not domain or "." not in domain or price <= 0:
                continue
            tld = domain.rsplit(".", 1)[-1]
            sld = domain.rsplit(".", 1)[0]
            sales.append({
                "domain": domain,
                "sld": sld,
                "price": price,
                "tld": tld,
                "currency": row.get("currency", "USD"),
                "date": row.get("date", ""),
                "source": "dnjournal_real",
            })
    return sales


def find_keyword(sld: str, kw_data: dict):
    """Find the strongest keyword inside an SLD."""
    best = None
    best_len = 0
    for kw in kw_data:
        if len(kw) < 3:
            continue
        if kw in sld:
            # Prefer exact match or longer match
            if sld == kw:
                return kw, "exact"
            if sld.startswith(kw):
                return kw, "start"
            if sld.endswith(kw):
                return kw, "end"
            if len(kw) > best_len:
                best = kw
                best_len = len(kw)
    return best, "middle" if best else None


def _domainize(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return s[:40]


def _pick_tld(preferred: str | None = None) -> str:
    if preferred and preferred in TLDS:
        # 40% chance to keep the original TLD
        if random.random() < 0.4:
            return preferred
    return random.choices(TLDS, weights=TLD_P, k=1)[0]


def generate_variants(real_sale: dict, kw_data: dict, n: int = 100) -> list[dict]:
    """Generate n synthetic variants around a real sale's keyword/price."""
    sld = real_sale["sld"]
    real_price = real_sale["price"]
    keyword, position = find_keyword(sld, kw_data)

    variants = []
    if not keyword:
        # No keyword found — fall back to shape-only variants with price noise
        for _ in range(min(n, 20)):
            variant_sld = _domainize(sld + random.choice(SUFFIXES) if random.random() < 0.5 else random.choice(PREFIXES) + sld)
            tld = _pick_tld(real_sale["tld"])
            price = max(100, int(random.lognormvariate(math.log(max(real_price, 100)), 0.4)))
            variants.append({
                "domain": f"{variant_sld}.{tld}",
                "price": price,
                "currency": "USD",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source": "augmented_shape",
                "tld": tld,
                "keyword": "",
                "position": "",
            })
        return variants

    rec = kw_data[keyword]
    pos = position or "exact"
    avg = rec.get(f"{pos}_price_avg", 0) or real_price
    std = rec.get(f"{pos}_price_stddev", 0)
    maxp = rec.get(f"{pos}_price_max", 0)

    # Blend real price with retailstats average for the target price distribution
    # Use real_price as anchor to preserve market segment
    target_mean = (real_price * 0.6 + avg * 0.4)
    sigma = max(0.3, min(0.8, (std / avg) if avg > 0 and std > 0 else 0.5))

    seen = set()
    attempts = 0
    while len(variants) < n and attempts < n * 30:
        attempts += 1
        # Generate SLD based on the real keyword position
        r = random.random()
        if r < 0.4:
            gen_pos = "exact"
            variant_sld = _domainize(keyword)
        elif r < 0.65:
            gen_pos = "start"
            variant_sld = _domainize(keyword + random.choice(SUFFIXES))
        elif r < 0.85:
            gen_pos = "end"
            variant_sld = _domainize(random.choice(PREFIXES) + keyword)
        else:
            gen_pos = "middle"
            variant_sld = _domainize(random.choice(PREFIXES) + keyword + random.choice(SUFFIXES))

        if not variant_sld or len(variant_sld) < 2:
            continue

        tld = _pick_tld(real_sale["tld"])
        domain = f"{variant_sld}.{tld}"
        if domain in seen:
            continue
        seen.add(domain)

        # Price: log-normal around target_mean, with realistic spread
        price = random.lognormvariate(math.log(max(target_mean, 100)), sigma)
        price *= random.uniform(0.8, 1.25)
        # Cap at 2x the real sale price or 3x keyword max to avoid absurd outliers
        cap = max(real_price * 2.5, maxp * 2) if maxp > 0 else real_price * 2.5
        price = min(price, cap)
        price = max(100, int(round(price)))

        variants.append({
            "domain": domain,
            "price": price,
            "currency": "USD",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "augmented_keyword",
            "tld": tld,
            "keyword": keyword,
            "position": gen_pos,
        })

    return variants


def main():
    print("Loading retail stats...")
    kw_data = load_retail_stats(RETAILSTATS)
    print(f"Loaded {len(kw_data)} keywords")

    print("Loading real sales...")
    real = load_real_sales(REAL_SALES)
    print(f"Loaded {len(real)} real sales")

    print("Generating augmented variants...")
    all_sales = []
    # Always include the real sales first
    for r in real:
        all_sales.append({
            "domain": r["domain"],
            "price": r["price"],
            "currency": r["currency"],
            "date": r["date"],
            "source": r["source"],
            "tld": r["tld"],
            "keyword": "",
            "position": "",
        })

    # Generate variants per real sale
    for i, r in enumerate(real):
        variants = generate_variants(r, kw_data, n=100)
        all_sales.extend(variants)
        if (i + 1) % 50 == 0:
            print(f"  processed {i+1}/{len(real)} real sales, total rows {len(all_sales)}")

    # Deduplicate by domain, keeping real ones first
    all_sales.sort(key=lambda x: 0 if x["source"] == "dnjournal_real" else 1)
    deduped = []
    seen = set()
    for s in all_sales:
        if s["domain"] in seen:
            continue
        seen.add(s["domain"])
        deduped.append(s)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(deduped).to_csv(OUTPUT, index=False)
    print(f"\nSaved {len(deduped):,} unique sales to {OUTPUT}")
    print("Source breakdown:")
    print(pd.Series([s["source"] for s in deduped]).value_counts())
    print("\nPrice stats:")
    prices = pd.Series([s["price"] for s in deduped])
    print(prices.describe())


if __name__ == "__main__":
    main()
