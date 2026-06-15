"""Combine real domain sales from multiple sources into one training file.

By default the script merges DNJournal retail sales with Zachwill auction sales
>= $5,000.  This gives a more realistic price distribution than DNJournal alone
(whose Top-100 charts inflate everyday domains) while avoiding the extreme
low-price bias of the full auction dump.

For experimentation, --dnjournal-only and --with-zachwill are also available.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent

DNJOURNAL_SOURCES = [
    ROOT / "data" / "sales" / "domainpro_sales.csv",
    ROOT / "data" / "sales" / "dnjournal_ytd_sales.csv",
]
ZACHWILL_RAW = ROOT / "data" / "sales" / "zachwill_domain_sales.csv"
ZACHWILL_BALANCED = ROOT / "data" / "sales" / "zachwill_domain_sales_balanced.csv"
OUTPUT = ROOT / "data" / "sales" / "combined_real_sales.csv"
CAP_OUTPUT = ROOT / "data" / "sales" / "combined_real_sales_capped.csv"
PRICE_CAP = 2_000_000


def normalize_source(path: Path) -> str:
    name = path.stem
    if "zachwill" in name:
        return "zachwill_sampled"
    if "dnjournal_ytd" in name:
        return "dnjournal_ytd"
    return "dnjournal"


def load_and_normalize(path: Path, source_label: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["domain"] = df["domain"].astype(str).str.lower().str.strip()
    df = df[df["domain"].str.contains(".", regex=False)]
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df[df["price"] > 0]
    df["tld"] = df["domain"].str.rsplit(".", n=1).str[-1]
    df["source"] = source_label if source_label else normalize_source(path)
    if "currency" not in df.columns:
        df["currency"] = "USD"
    if "venue" not in df.columns:
        df["venue"] = ""
    if "date" not in df.columns:
        df["date"] = ""
    return df[["domain", "price", "currency", "date", "source", "venue", "tld"]]


def combine(sources: list[Path]) -> pd.DataFrame:
    all_rows = [load_and_normalize(p) for p in sources]
    combined = pd.concat(all_rows, ignore_index=True)
    # Keep highest price per domain (real sources are more trustworthy)
    combined = combined.sort_values("price", ascending=False).drop_duplicates("domain")
    combined = combined.sort_values("price", ascending=False).reset_index(drop=True)
    return combined


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Combine real domain sales")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dnjournal-only",
        action="store_true",
        help="Use only DNJournal sources (premium-only, may overestimate)",
    )
    group.add_argument(
        "--with-zachwill",
        action="store_true",
        help="Include a balanced sample of the public Zachwill auction data",
    )
    args = parser.parse_args(argv)

    if args.dnjournal_only:
        sources = list(DNJOURNAL_SOURCES)
    elif args.with_zachwill:
        sources = list(DNJOURNAL_SOURCES) + [ZACHWILL_BALANCED]
    else:
        # Default: DNJournal + Zachwill auction sales >= $5,000
        zach = pd.read_csv(ZACHWILL_RAW)
        zach = zach[zach["price"] >= 5_000]
        zach_path = ROOT / "data" / "sales" / "zachwill_domain_sales_highvalue.csv"
        zach[["date", "domain", "price", "venue", "length", "dot_com", "hyphen", "numbers"]].to_csv(
            zach_path, index=False
        )
        sources = list(DNJOURNAL_SOURCES) + [zach_path]

    combined = combine(sources)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT, index=False)
    print(f"Saved {len(combined)} unique real sales to {OUTPUT}")
    print(combined["source"].value_counts())
    print("\nPrice stats:")
    print(combined["price"].describe())

    # Also write the capped version used for training.
    capped = combined.copy()
    capped["price"] = capped["price"].clip(upper=PRICE_CAP)
    capped.to_csv(CAP_OUTPUT, index=False)
    print(f"\nSaved capped version to {CAP_OUTPUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
