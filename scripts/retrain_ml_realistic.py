"""Retrain ML model on the realistic augmented dataset."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from analyzer.ml_valuation import train

SALES_CSV = ROOT / "data" / "sales" / "combined_sales_realistic.csv"
MODEL_DIR = ROOT / "models"


def main():
    print(f"Retraining on {SALES_CSV}")
    metrics = train(sales_csv=SALES_CSV, model_dir=MODEL_DIR, test_size=0.2)
    print(metrics)


if __name__ == "__main__":
    main()
