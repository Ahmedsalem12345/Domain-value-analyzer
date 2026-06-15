#!/usr/bin/env python3
"""Retrain the ML valuation models from the latest sales CSV."""

from pathlib import Path
import sys

# Allow importing analyzer package when running from scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer.ml_valuation import train


if __name__ == "__main__":
    metrics = train()
    print("\nTraining complete. Metrics saved to models/ml_valuation_metrics.json")
