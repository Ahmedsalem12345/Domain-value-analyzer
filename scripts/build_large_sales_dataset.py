"""
Build a large domain sales training dataset by combining:
  1. Existing real sales from data/sales/domainpro_sales.csv
  2. Scraped public sales from Domain Name Wire
  3. Synthetic but realistic sales generated from retailstats keyword data

The synthetic portion uses real per-position price statistics (avg/max/stddev)
from retailstats_20260427.csv so the resulting prices follow actual market
patterns rather than arbitrary guesses.
"""
from __future__ import annotations

import csv
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from datetime import datetime

import pandas as pd

random.seed(42)

ROOT = Path(__file__).parent.parent
RETAILSTATS = ROOT / "retailstats_20260427.csv"
REAL_SALES = ROOT / "data" / "sales" / "domainpro_sales.csv"
OUTPUT = ROOT / "data" / "sales" / "combined_sales_large.csv"

# Realistic TLD distribution (relative weights)
TLD_WEIGHTS = {
    "com": 55,
    "net": 6,
    "org": 6,
    "io": 8,
    "ai": 5,
    "co": 3,
    "co.uk": 2,
    "de": 2,
    "ai": 5,
    "app": 2,
    "dev": 1,
    "me": 1,
    "tv": 1,
    "info": 1,
    "biz": 1,
    "xyz": 2,
    "us": 1,
    "online": 1,
    "site": 1,
    "shop": 1,
    "store": 1,
    "tech": 1,
    "club": 1,
}

TLDS = list(TLD_WEIGHTS.keys())
TLD_P = [w / sum(TLD_WEIGHTS.values()) for w in TLD_WEIGHTS.values()]

POSITIONS = ("exact", "start", "end", "middle")

# Short generic words used to build prefix/suffix/middle combos
_GENERIC = [
    "my", "the", "web", "online", "pro", "best", "top", "new", "get", "go",
    "buy", "shop", "store", "app", "hq", "hub", "now", "24", "365", "usa",
    "global", "world", "smart", "easy", "fast", "max", "plus", "group", "inc",
    "co", "net", "io", "ai", "tech", "media", "digital", "cloud", "data",
    "auto", "home", "real", "green", "eco", "cyber", "meta", "nano", "crypto",
    "ai", "vr", "ar", "block", "chain", "nft", "defi", "web3", "sol", "neo",
]


def load_retail_stats(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["keyword"] = df["keyword"].astype(str).str.lower().str.strip()
    # Keep only rows with at least some market evidence
    df = df[df[[f"{p}_sale_count" for p in POSITIONS]].sum(axis=1) > 0]
    return df


def _domainize(s: str) -> str:
    """Convert a phrase into a valid SLD-ish string."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s[:40]


def _pick_tld() -> str:
    return random.choices(TLDS, weights=TLD_P, k=1)[0]


def _price_with_noise(avg: float, std: float, maxp: float, position: str) -> float:
    """Generate a realistic sale price from retailstats moments."""
    if avg <= 0 or math.isnan(avg):
        return 0.0
    # Position discount (matches how the KPS engine weights positions)
    pos_mult = {"exact": 1.0, "start": 0.55, "end": 0.60, "middle": 0.25}[position]
    base = avg * pos_mult
    # Use a tighter, more realistic log-normal spread. Domain prices are
    # volatile, but training on wildly noisy synthetic data hurts accuracy.
    cv = (std / avg) if avg > 0 and std > 0 else 0.5
    sigma = max(0.25, min(0.75, cv * 0.5))
    noise = random.lognormvariate(mu=math.log(max(base, 50)), sigma=sigma)
    price = noise * random.uniform(0.85, 1.15)
    # Hard global cap to prevent unrealistic $20M+ synthetic outliers
    global_cap = 200_000
    # Cap at 1.2x max historical observation per keyword/position
    cap = min(global_cap, maxp * 1.2 if maxp > 0 else global_cap)
    price = min(price, cap)
    return max(100.0, round(price, 2))


def generate_synthetic_sales(df: pd.DataFrame, target: int = 50_000) -> list[dict]:
    """Generate realistic sales from retailstats keywords."""
    rows = df.to_dict("records")
    # Weight by total sales volume so high-value keywords appear more often
    weights = []
    for r in rows:
        total_sales = sum(int(float(r.get(f"{p}_sale_count", 0) or 0)) for p in POSITIONS)
        weights.append(max(1, total_sales))

    synthetic = []
    attempts = 0
    seen = set()
    while len(synthetic) < target and attempts < target * 20:
        attempts += 1
        row = random.choices(rows, weights=weights, k=1)[0]
        kw = row["keyword"].strip()
        if not kw or " " in kw or len(kw) < 2:
            continue

        # Choose a position weighted by observed sale counts
        counts = {p: int(float(row.get(f"{p}_sale_count", 0) or 0)) for p in POSITIONS}
        total = sum(counts.values())
        if total == 0:
            continue
        pos = random.choices(POSITIONS, weights=[counts[p] for p in POSITIONS], k=1)[0]

        avg = float(row.get(f"{pos}_price_avg", 0) or 0)
        std = float(row.get(f"{pos}_price_stddev", 0) or 0)
        maxp = float(row.get(f"{pos}_price_max", 0) or 0)
        if avg <= 0:
            continue

        tld = _pick_tld()
        if pos == "exact":
            sld = _domainize(kw)
        elif pos == "start":
            sld = _domainize(kw + random.choice(_GENERIC))
        elif pos == "end":
            sld = _domainize(random.choice(_GENERIC) + kw)
        else:  # middle
            sld = _domainize(random.choice(_GENERIC) + kw + random.choice(_GENERIC))

        if not sld or len(sld) < 2:
            continue
        domain = f"{sld}.{tld}"
        if domain in seen:
            continue
        seen.add(domain)

        price = _price_with_noise(avg, std, maxp, pos)
        if price < 100:
            continue

        synthetic.append({
            "domain": domain,
            "price": int(price),
            "currency": "USD",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "retailstats_synthetic",
            "venue": "",
            "tld": tld,
            "position": pos,
            "keyword": kw,
        })

    return synthetic


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
            sales.append({
                "domain": domain,
                "price": price,
                "currency": row.get("currency", "USD"),
                "date": row.get("date", ""),
                "source": row.get("source", "domainpro"),
                "venue": row.get("venue", ""),
                "tld": tld,
                "position": "",
                "keyword": "",
            })
    return sales


def scrape_dnw() -> list[dict]:
    """Best-effort scrape of Domain Name Wire domain sales articles."""
    import urllib.request

    def fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")

    sales = []
    seen = set()
    for page in range(1, 8):
        url = f"https://domainnamewire.com/category/domain-sales/page/{page}/"
        try:
            html = fetch(url)
        except Exception:
            continue
        links = re.findall(r'<a[^>]+href="(https://domainnamewire.com/\d{4}/\d{2}/\d{2}/[^"]+)"[^>]*>', html)
        for link in set(links):
            try:
                art = fetch(link)
            except Exception:
                continue
            patterns = [
                r"([a-z0-9][a-z0-9\-]*\.[a-z]{2,})\s+(?:sold|for)\s+(?:about|around|approximately)?\s*\$?([\d,]+)",
                r"\$([\d,]+)\s+(?:for|paid for)\s+([a-z0-9][a-z0-9\-]*\.[a-z]{2,})",
                r"([a-z0-9][a-z0-9\-]*\.[a-z]{2,})\s+for\s+\$?([\d,]+)",
            ]
            for pat in patterns:
                for m in re.finditer(pat, art, re.I):
                    if pat.startswith("\\$"):
                        price, domain = m.groups()
                    else:
                        domain, price = m.groups()
                    price = int(price.replace(",", ""))
                    domain = domain.lower().strip()
                    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
                    if 100 <= price <= 10_000_000 and domain not in seen and "." in domain and len(domain) <= 60:
                        seen.add(domain)
                        sales.append({
                            "domain": domain,
                            "price": price,
                            "currency": "USD",
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "source": "dnw_scraped",
                            "venue": "",
                            "tld": tld,
                            "position": "",
                            "keyword": "",
                        })
    return sales


def main():
    print("Loading retailstats...")
    stats = load_retail_stats(RETAILSTATS)
    print(f"Retailstats rows: {len(stats)}")

    print("Loading real sales...")
    real = load_real_sales(REAL_SALES)
    print(f"Real sales: {len(real)}")

    # DNW scraping skipped for speed; see scrape_dnw() if you want to re-enable.
    dnw = []
    print(f"DNW scraped: {len(dnw)} (skipped)")

    target_synthetic = 50_000
    print(f"Generating {target_synthetic:,} synthetic sales from retailstats...")
    synthetic = generate_synthetic_sales(stats, target=target_synthetic)
    print(f"Synthetic generated: {len(synthetic)}")

    combined = real + dnw + synthetic
    # Deduplicate by domain, preferring real sources
    source_rank = {"dnjournal": 0, "domainpro": 0, "dnw_scraped": 1, "retailstats_synthetic": 2}
    combined.sort(key=lambda r: source_rank.get(r["source"], 9))
    deduped = []
    seen = set()
    for r in combined:
        if r["domain"] in seen:
            continue
        seen.add(r["domain"])
        deduped.append(r)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(deduped).to_csv(OUTPUT, index=False)
    print(f"Saved {len(deduped):,} unique sales to {OUTPUT}")
    print(f"Source breakdown:")
    for src, cnt in pd.Series([r["source"] for r in deduped]).value_counts().items():
        print(f"  {src}: {cnt:,}")


if __name__ == "__main__":
    main()
