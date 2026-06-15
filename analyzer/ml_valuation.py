"""Machine-learning valuation module for domain names.

Trains a price regressor and an investment-grade classifier from historical
sales data, then exposes a lightweight `predict()` function that can be
plugged into the existing analysis pipeline.

The module is intentionally self-contained so it can be retrained on better
data (e.g. a NameBio CSV export) without touching the rest of the project.
"""

from __future__ import annotations

import json
import math
import pickle
from pathlib import Path
from typing import Iterable, Optional

import operator

import ahocorasick
import numpy as np
import pandas as pd

from config import TLD_MULTIPLIERS
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

# scikit-learn >= 1.3 ships HistGradientBoostingRegressor/Classifier
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

import wordninja


_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parent

DEFAULT_RETAILSTATS = str(_PROJECT_ROOT / "retailstats_20260427.csv")
DEFAULT_SALES_CSV = str(_PROJECT_ROOT / "data" / "sales" / "domainpro_sales.csv")
DEFAULT_MODEL_DIR = str(_PROJECT_ROOT / "models")

# Load system English word list if available for dictionary features.
_ENGLISH_WORDS: set = set()
for _dict_path in ("/usr/share/dict/words", "/usr/dict/words"):
    try:
        with open(_dict_path, "r", encoding="utf-8", errors="ignore") as _f:
            _ENGLISH_WORDS = {line.strip().lower() for line in _f if line.strip()}
        break
    except FileNotFoundError:
        continue

# Investment-grade breakpoints are learned from training-set price quantiles.
# We store them alongside the model so prediction stays consistent.
GRADE_LABELS = ["PASS", "HOLD", "BUY", "GEM"]


class _KeywordMatcher:
    """Fast Aho-Corasick matcher for retail-stats keywords against SLDs."""

    def __init__(self, stats: pd.DataFrame):
        self.stats = stats
        self.automaton = ahocorasick.Automaton()
        for idx, keyword in enumerate(stats["keyword"]):
            self.automaton.add_word(keyword, idx)
        self.automaton.make_automaton()

    def matches(self, sld: str) -> pd.DataFrame:
        """Return the rows of stats whose keyword occurs in sld."""
        indices = {idx for _, idx in self.automaton.iter(sld)}
        if not indices:
            return self.stats.iloc[0:0]
        return self.stats.iloc[sorted(indices)]


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


# Caches: retail-stats is large (~6 MB) and artifacts are a pickle file.
# Loading either of them for every single domain is the main bottleneck in
# batch analysis, so we keep them in memory after the first load.
_RETAIL_STATS_CACHE: dict[str, pd.DataFrame] = {}
_ARTIFACTS_CACHE: dict | None = None


def load_retail_stats(path: str | Path) -> pd.DataFrame:
    """Load the retail-stats CSV produced by the existing KPS engine."""
    path = Path(path)
    key = str(path)
    if key in _RETAIL_STATS_CACHE:
        return _RETAIL_STATS_CACHE[key]
    if not path.exists():
        raise FileNotFoundError(f"Retail stats not found: {path}")
    df = pd.read_csv(path)
    df["keyword"] = df["keyword"].astype(str).str.lower().str.strip()
    _RETAIL_STATS_CACHE[key] = df
    return df


def _sld_and_tld(domain: str):
    domain = domain.lower().strip()
    if "//" in domain:
        domain = domain.split("//", 1)[1]
    domain = domain.split("/")[0]
    if "." not in domain:
        return domain, ""
    sld, tld = domain.rsplit(".", 1)
    return sld, tld


def _segment_words(sld: str) -> list[str]:
    """Segment an SLD into probable words."""
    try:
        return [w for w in wordninja.split(sld) if w]
    except Exception:
        return []


def _keyword_features(sld: str, matcher: _KeywordMatcher) -> dict:
    """Aggregate keyword-level signals from the retail-stats table."""
    feats = {}
    sld = sld.lower()
    stats = matcher.matches(sld)

    positions = {
        "exact": stats["keyword"] == sld,
        "start": stats["keyword"].apply(lambda k: sld.startswith(k)),
        "end": stats["keyword"].apply(lambda k: sld.endswith(k)),
        "middle": stats["keyword"].apply(lambda k: k in sld and not sld.startswith(k) and not sld.endswith(k)),
    }

    best_signal = 0.0
    best_avg_price = 0.0
    best_max_price = 0.0
    best_total_sales = 0

    for pos, mask in positions.items():
        sub = stats[mask]
        if sub.empty:
            feats[f"{pos}_match"] = 0
            feats[f"{pos}_count"] = 0
            feats[f"{pos}_max_price"] = 0.0
            feats[f"{pos}_avg_price"] = 0.0
            feats[f"{pos}_total_volume"] = 0.0
        else:
            feats[f"{pos}_match"] = 1
            feats[f"{pos}_count"] = int(sub[f"{pos}_sale_count"].sum())
            feats[f"{pos}_max_price"] = float(sub[f"{pos}_price_max"].max())
            feats[f"{pos}_avg_price"] = float(sub[f"{pos}_price_avg"].max())
            feats[f"{pos}_total_volume"] = float(sub[f"{pos}_price_sum"].sum())
            # Update best single match (strongest signal)
            signal = (
                math.log1p(feats[f"{pos}_count"])
                * math.log1p(feats[f"{pos}_avg_price"])
                * {"exact": 1.0, "start": 0.55, "end": 0.60, "middle": 0.25}[pos]
            )
            if signal > best_signal:
                best_signal = signal
                best_avg_price = feats[f"{pos}_avg_price"]
                best_max_price = feats[f"{pos}_max_price"]
                best_total_sales = feats[f"{pos}_count"]

    feats["any_match"] = int(any(feats[f"{p}_match"] for p in positions))
    feats["best_signal"] = float(best_signal)
    feats["best_avg_price"] = float(best_avg_price)
    feats["best_max_price"] = float(best_max_price)
    feats["best_total_sales"] = int(best_total_sales)
    feats["log_best_avg_price"] = math.log1p(best_avg_price)
    feats["log_best_max_price"] = math.log1p(best_max_price)
    return feats


def _char_features(sld: str) -> dict:
    """Basic hand-crafted features from the SLD string."""
    letters = [c for c in sld if c.isalpha()]
    vowels = [c for c in letters if c in "aeiou"]
    digits = [c for c in sld if c.isdigit()]

    # max run of identical characters
    max_run = 1
    cur = 1
    for i in range(1, len(sld)):
        if sld[i] == sld[i - 1]:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 1

    words = _segment_words(sld)
    word_lengths = [len(w) for w in words]

    # Number at start/end of SLD (e.g. 123abc vs abc123)
    prefix_num = 0
    suffix_num = 0
    if digits:
        import re
        m = re.match(r"^(\d+)", sld)
        if m:
            prefix_num = int(m.group(1))
        m = re.search(r"(\d+)$", sld)
        if m:
            suffix_num = int(m.group(1))

    # Dictionary coverage of segmented words
    if _ENGLISH_WORDS:
        dict_hits = sum(1 for w in words if w in _ENGLISH_WORDS)
        dict_ratio = dict_hits / len(words) if words else 0.0
    else:
        dict_ratio = 0.0

    return {
        "sld_length": len(sld),
        "domain_length": len(sld) + 1,  # placeholder; recomputed with tld below
        "num_words": len(words),
        "avg_word_len": np.mean(word_lengths) if word_lengths else 0.0,
        "max_word_len": max(word_lengths) if word_lengths else 0,
        "has_numbers": int(len(digits) > 0),
        "has_hyphen": int("-" in sld),
        "vowel_ratio": len(vowels) / len(letters) if letters else 0.0,
        "digit_ratio": len(digits) / len(sld) if sld else 0.0,
        "max_char_run": max_run,
        "char_entropy": _char_entropy(sld),
        "prefix_number": prefix_num,
        "suffix_number": suffix_num,
        "dict_word_ratio": dict_ratio,
    }


def _char_entropy(s: str) -> float:
    """Shannon entropy of character distribution (higher = more random)."""
    if not s:
        return 0.0
    counts = pd.Series(list(s)).value_counts(normalize=True)
    return float(-(counts * np.log2(counts)).sum())


def extract_features(domains: Iterable[str], stats: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Turn a list of domain names into a feature DataFrame."""
    if stats is None:
        stats = load_retail_stats(DEFAULT_RETAILSTATS)
    matcher = _KeywordMatcher(stats)

    rows = []
    for domain in domains:
        sld, tld = _sld_and_tld(domain)
        feats = {"domain": domain, "sld": sld, "tld": tld}
        feats.update(_char_features(sld))
        feats["domain_length"] = len(domain)
        feats.update(_keyword_features(sld, matcher))
        feats["tld_multiplier"] = float(TLD_MULTIPLIERS.get(tld.lower(), 1.0))
        rows.append(feats)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def _build_preprocessor(feature_df: pd.DataFrame):
    """Build a sklearn preprocessor for the feature columns."""
    text_col = "sld"
    categorical_cols = ["tld"]
    numeric_cols = [c for c in feature_df.columns if c not in ["domain", "sld", "tld"]]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value=0))]), numeric_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_cols),
            (
                "char_ngram",
                Pipeline(
                    [
                        ("vect", CountVectorizer(analyzer="char", ngram_range=(2, 4), max_features=100)),
                        ("dense", FunctionTransformer(operator.methodcaller("toarray"), accept_sparse=True)),
                    ]
                ),
                text_col,
            ),
        ],
        remainder="drop",
    )
    return preprocessor, numeric_cols


def _assign_grade(price: float, quantiles: list[float]) -> str:
    """Map a price to a grade using precomputed quantile breakpoints."""
    for threshold, label in zip(quantiles, GRADE_LABELS):
        if price <= threshold:
            return label
    return GRADE_LABELS[-1]


def train(
    sales_csv: str | Path = DEFAULT_SALES_CSV,
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    test_size: float = 0.2,
) -> dict:
    """Train and save the valuation models.

    Returns a metrics dict with cross-validation scores and test-set errors.
    """
    sales_csv, model_dir = Path(sales_csv), Path(model_dir)
    if not sales_csv.exists():
        raise FileNotFoundError(f"Sales CSV not found: {sales_csv}")

    sales = pd.read_csv(sales_csv)
    sales = sales.dropna(subset=["domain", "price"])
    sales["price"] = pd.to_numeric(sales["price"], errors="coerce")
    sales = sales[sales["price"] > 0]

    print(f"Training on {len(sales)} sales records ...")

    # Weight real retail sales (DNJournal) more heavily than auction data so
    # premium-domain signals are not drowned out by low-price drop auctions.
    if "source" in sales.columns:
        source_weights = {
            "dnjournal": 10.0,
            "dnjournal_ytd": 10.0,
            "domainpro": 5.0,
            "zachwill_sampled": 1.0,
            "zachwill_highvalue": 2.0,
            "zachwill_market": 1.0,
        }
        sample_weight = sales["source"].map(source_weights).fillna(1.0).values
    else:
        sample_weight = np.ones(len(sales))

    stats = load_retail_stats(DEFAULT_RETAILSTATS)
    features = extract_features(sales["domain"], stats=stats)
    X = features.copy()
    y_price = sales["price"].values
    y_log = np.log1p(y_price)

    preprocessor_reg, numeric_cols = _build_preprocessor(X)
    preprocessor_clf, _ = _build_preprocessor(X)

    # Split for final regression evaluation
    X_train, X_test, y_log_train, y_log_test, sw_train, sw_test = train_test_split(
        X, y_log, sample_weight,
        test_size=test_size, random_state=42
    )

    # ---------------- Regression model ----------------
    # Trained on the full (possibly mixed) dataset to learn realistic price
    # levels across both retail sales and auction data.
    regressor = Pipeline(
        [
            ("preprocess", preprocessor_reg),
            (
                "model",
                HistGradientBoostingRegressor(
                    max_iter=150,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42,
                ),
            ),
        ]
    )
    regressor.fit(X_train, y_log_train, model__sample_weight=sw_train)

    y_log_pred = regressor.predict(X_test)
    y_pred = np.expm1(y_log_pred)
    y_test = np.expm1(y_log_test)
    metrics = {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "regression": {
            "rmse_log": float(np.sqrt(np.mean((y_log_pred - y_log_test) ** 2))),
            "mae_log": float(np.mean(np.abs(y_log_pred - y_log_test))),
            "rmse_usd": float(np.sqrt(np.mean((y_pred - y_test) ** 2))),
            "mae_usd": float(np.mean(np.abs(y_pred - y_test))),
        },
    }

    # ---------------- Classification model ----------------
    # Grade thresholds are computed from DNJournal retail sales only so
    # GEM/BUY/HOLD/PASS stay anchored to real public retail transactions.
    # The classifier itself is trained on the full dataset using those labels.
    if "source" in sales.columns:
        grade_sales = sales[sales["source"].isin(["dnjournal", "dnjournal_ytd"])].copy()
    else:
        grade_sales = sales.copy()

    g_y_price = grade_sales["price"].values
    quantiles = [np.percentile(g_y_price, q) for q in [33, 60, 85]]
    # Assign retail-grade labels to every row in the full training set
    y_grade = pd.Series(y_price).apply(lambda p: _assign_grade(p, quantiles)).values

    (
        gX_train, gX_test,
        gy_train, gy_test,
        gsw_train, gsw_test,
    ) = train_test_split(
        X, y_grade, sample_weight,
        test_size=test_size, random_state=42, stratify=y_grade
    )

    classifier = Pipeline(
        [
            ("preprocess", preprocessor_clf),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_iter=150,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42,
                ),
            ),
        ]
    )
    classifier.fit(gX_train, gy_train, model__sample_weight=gsw_train)

    grade_pred = classifier.predict(gX_test)
    metrics["classification"] = {
        "accuracy": float(np.mean(grade_pred == gy_test)),
        "classes": list(classifier.classes_),
    }

    # ---------------- Persist artifacts ----------------
    model_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "regressor": regressor,
        "classifier": classifier,
        "quantiles": quantiles,
        "grade_labels": GRADE_LABELS,
        "numeric_cols": numeric_cols,
    }
    with open(model_dir / "ml_valuation_artifacts.pkl", "wb") as f:
        pickle.dump(artifacts, f)

    # Clear the in-memory cache so the newly trained model is used immediately.
    global _ARTIFACTS_CACHE
    _ARTIFACTS_CACHE = None

    with open(model_dir / "ml_valuation_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Models saved to {model_dir}")
    print(json.dumps(metrics, indent=2))
    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def load_artifacts(model_dir: str | Path = DEFAULT_MODEL_DIR) -> dict:
    """Load previously trained models (cached after first call)."""
    global _ARTIFACTS_CACHE
    if _ARTIFACTS_CACHE is not None:
        return _ARTIFACTS_CACHE
    path = Path(model_dir) / "ml_valuation_artifacts.pkl"
    if not path.exists():
        raise FileNotFoundError(f"No trained model found at {path}. Run train() first.")
    with open(path, "rb") as f:
        _ARTIFACTS_CACHE = pickle.load(f)
    return _ARTIFACTS_CACHE


def predict(domain: str, artifacts: Optional[dict] = None) -> dict:
    """Return ML-based valuation for a single domain.

    Output keys:
        - ml_price_estimate: predicted USD sale price
        - ml_grade: predicted investment grade (PASS/HOLD/BUY/GEM)
        - ml_grade_proba: dict of class probabilities
        - ml_investment_score: probability of BUY or GEM combined
    """
    if artifacts is None:
        artifacts = load_artifacts()

    regressor = artifacts["regressor"]
    classifier = artifacts["classifier"]

    stats = load_retail_stats(DEFAULT_RETAILSTATS)
    X = extract_features([domain], stats=stats)

    log_price = regressor.predict(X)[0]
    price_estimate = max(0.0, float(np.expm1(log_price)))

    grade = classifier.predict(X)[0]
    proba = dict(zip(classifier.classes_, classifier.predict_proba(X)[0].tolist()))
    investment_score = float(proba.get("BUY", 0.0) + proba.get("GEM", 0.0))

    return {
        "ml_price_estimate": round(price_estimate, 2),
        "ml_grade": grade,
        "ml_grade_proba": proba,
        "ml_investment_score": round(investment_score, 4),
    }


def batch_predict(domains: Iterable[str], artifacts: Optional[dict] = None) -> pd.DataFrame:
    """Predict price and grade for many domains at once."""
    if artifacts is None:
        artifacts = load_artifacts()

    regressor = artifacts["regressor"]
    classifier = artifacts["classifier"]

    stats = load_retail_stats(DEFAULT_RETAILSTATS)
    X = extract_features(domains, stats=stats)

    log_prices = regressor.predict(X)
    prices = np.expm1(log_prices)
    grades = classifier.predict(X)
    probas = classifier.predict_proba(X)

    out = pd.DataFrame({"domain": X["domain"], "ml_price_estimate": prices, "ml_grade": grades})
    classes = list(classifier.classes_)
    for i, cls in enumerate(classes):
        out[f"proba_{cls}"] = probas[:, i]
    out["ml_investment_score"] = out.get("proba_BUY", 0) + out.get("proba_GEM", 0)
    return out


if __name__ == "__main__":
    # Quick CLI test: train, then show a few predictions
    metrics = train()
    sample = ["mindmesh.com", "totalrx.com", "minicrossword.com", "ai.com", "xyzabc123.com"]
    print("\nSample predictions:")
    for d in sample:
        print(d, predict(d))
