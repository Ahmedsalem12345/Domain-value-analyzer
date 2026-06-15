"""
Retrain the domain valuation ML model on the expanded combined sales dataset.
Saves new artifacts to models/ and reports metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from analyzer.ml_valuation import train

SALES_CSV = ROOT / "data" / "sales" / "combined_sales_large.csv"
MODEL_DIR = ROOT / "models"


def main():
    print(f"Retraining ML model on {SALES_CSV}")
    metrics = train(
        sales_csv=SALES_CSV,
        model_dir=MODEL_DIR,
        test_size=0.2,
    )
    print("\nTraining complete. Metrics:")
    print(metrics)


if __name__ == "__main__":
    main()
