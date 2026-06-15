"""Retrain ML model on the combined real sales dataset."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from analyzer.ml_valuation import train

DEFAULT_SALES_CSV = ROOT / "data" / "sales" / "combined_real_sales_capped.csv"
MODEL_DIR = ROOT / "models"


def main():
    sales_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SALES_CSV
    print(f"Retraining on {sales_csv}")
    metrics = train(sales_csv=sales_csv, model_dir=MODEL_DIR, test_size=0.2)
    print(metrics)


if __name__ == "__main__":
    main()
