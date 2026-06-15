"""
Test Suite — Decision Engine + Pipeline + KPS Integration.

Tests validate:
  1. GeoRiskGate blocks weak geo markets
  2. Premium single-word domains get minimum BUY
  3. Decision Engine verdicts align with investment logic
  4. KPS Aho-Corasick produces correct results
  5. NameFitScore penalizes poor names
  6. Pipeline end-to-end correctness
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ━━━━━━━━━━━━ KPS SPEED ━━━━━━━━━━━━

def test_kps_uses_aho_corasick():
    from analyzer.retail_kps import _load
    from analyzer import retail_kps
    _load()
    assert retail_kps._AUTOMATON is not None, "Aho-Corasick automaton should be built"


def test_kps_speed():
    """KPS should process 100 domains in < 500ms (was 28s before AC)."""
    import time
    from analyzer.retail_kps import score_kps, _load
    _load()
    domains = ['insurance', 'casino', 'miamiplumbing', 'bestinsurance',
               'cloudhosting', 'smartfinance', 'devcell', 'fastcars',
               'bitcoinexchange', 'newyorkdentist'] * 10
    
    start = time.perf_counter()
    for d in domains:
        score_kps.cache_clear()
        score_kps(d)
    elapsed = time.perf_counter() - start
    
    assert elapsed < 0.5, f"KPS took {elapsed:.2f}s for 100 domains (max 0.5s)"


# ━━━━━━━━━━━━ KPS CORRECTNESS ━━━━━━━━━━━━

def test_kps_exact_match():
    from analyzer.retail_kps import score_kps
    r = score_kps("insurance")
    assert r["kps_tier"] in ("ultra", "premium"), f"insurance should be ultra/premium, got {r['kps_tier']}"
    assert r["best_match"]["match_type"] == "exact"


def test_kps_compound():
    from analyzer.retail_kps import score_kps
    r = score_kps("bestinsurance")
    assert len(r["tokens"]) >= 1, "bestinsurance should extract keywords"


def test_kps_no_match():
    from analyzer.retail_kps import score_kps
    # Single char can't match any keyword (min keyword len = 2)
    r = score_kps("z")
    assert r["kps_tier"] == "none"
    assert r["kps_score"] == 0


# ━━━━━━━━━━━━ NAME FIT ━━━━━━━━━━━━

def test_name_fit_short_clean():
    from analyzer.name_fit import score_name_fit
    r = score_name_fit("casino", "com")
    assert r["name_fit_score"] >= 80, f"casino.com should have high name fit, got {r['name_fit_score']}"


def test_name_fit_long_ugly():
    from analyzer.name_fit import score_name_fit
    r = score_name_fit("bestcheaponlineinsurancequotes", "xyz")
    assert r["name_fit_score"] < 40, f"Long ugly domain should have low name fit"


def test_name_fit_hyphen_penalty():
    from analyzer.name_fit import score_name_fit
    r = score_name_fit("my-best-shop", "com")
    assert "contains_hyphen" in r["name_fit_reasons"]


# ━━━━━━━━━━━━ DECISION ENGINE ━━━━━━━━━━━━

def test_geo_risk_gate_blocks_weak_geo():
    """omdurmaninsurance.com should NOT get BUY due to weak geo market."""
    from analyzer.pipeline import process_domain
    r = process_domain("omdurmaninsurance.com")
    assert r["Verdict"] in ("PASS", "HOLD"), \
        f"Weak geo should be PASS/HOLD, got {r['Verdict']}"
    assert "weak_geo_market" in r.get("RiskFlags", []), \
        "Should flag weak_geo_market"


def test_premium_single_word_gets_buy():
    """casino.com should get BUY or GEM — premium single-word .com."""
    from analyzer.pipeline import process_domain
    r = process_domain("casino.com")
    assert r["Verdict"] in ("BUY", "GEM"), \
        f"casino.com should be BUY/GEM, got {r['Verdict']}"


def test_taxi_gets_buy():
    """taxi.com should get at least BUY — proven KPS keyword."""
    from analyzer.pipeline import process_domain
    r = process_domain("taxi.com")
    assert r["Verdict"] in ("BUY", "GEM"), \
        f"taxi.com should be BUY/GEM, got {r['Verdict']}"


def test_gibberish_excluded():
    from analyzer.pipeline import process_domain
    r = process_domain("xzqwplm.com")
    assert r["Verdict"] == "EXCLUDED"


def test_trademark_excluded():
    from analyzer.pipeline import process_domain
    r = process_domain("openaihelp.com")
    assert r["Verdict"] == "EXCLUDED"


def test_low_value_stays_pass():
    """Weak domain with numbers and hyphens should not get promoted."""
    from analyzer.pipeline import process_domain
    r = process_domain("my-99-deals-online.com")
    assert r["Verdict"] in ("PASS", "HOLD", "EXCLUDED"), \
        f"my-99-deals-online.com should be PASS/HOLD/EXCLUDED, got {r['Verdict']}"


# ━━━━━━━━━━━━ DECISION ENGINE SCORES ━━━━━━━━━━━━

def test_opportunity_score_exists():
    from analyzer.pipeline import process_domain
    r = process_domain("miamiplumbing.com")
    assert "OpportunityScore" in r
    assert isinstance(r["OpportunityScore"], int)
    assert 0 <= r["OpportunityScore"] <= 100


def test_sell_through_exists():
    from analyzer.pipeline import process_domain
    r = process_domain("miamiplumbing.com")
    assert "SellThroughProbability" in r
    assert r["SellThroughProbability"] > 0


def test_risk_flags_list():
    from analyzer.pipeline import process_domain
    r = process_domain("omdurmaninsurance.com")
    assert isinstance(r.get("RiskFlags"), list)


def test_ranking_category_exists():
    from analyzer.pipeline import process_domain
    r = process_domain("casino.com")
    assert r.get("RankingCategory"), "Should have a ranking category"


def test_buyer_persona_exists():
    from analyzer.pipeline import process_domain
    r = process_domain("miamiplumbing.com")
    assert r.get("BuyerPersona"), "Should have a buyer persona"


# ━━━━━━━━━━━━ PIPELINE INTEGRATION ━━━━━━━━━━━━

def test_pipeline_all_fields():
    """Pipeline output should contain all required fields."""
    from analyzer.pipeline import process_domain
    r = process_domain("insurance.com")
    required = [
        "Domain", "Verdict", "TotalScore", "DomainType", "Reasoning",
        "CommercialIntent", "MarketDemand", "Clarity", "BuyerPool",
        "GeoNiche", "Liquidity", "PriceLow", "PriceHigh",
        "OpportunityScore", "SignalScore", "SellabilityScore",
        "RiskScore", "RiskFlags", "DecisionVerdict", "DecisionReason",
        "NameFitScore", "SellThroughProbability",
        "MaxAcquisitionPrice", "BuyerPersona", "RankingCategory",
    ]
    for field in required:
        assert field in r, f"Missing field: {field}"


def test_pipeline_excluded_has_no_scores():
    from analyzer.pipeline import process_domain
    r = process_domain("xzqwplm.com")
    assert r["Verdict"] == "EXCLUDED"
    assert "OpportunityScore" not in r or r.get("OpportunityScore") is None


# ━━━━━━━━━━━━ STRONG LOCAL SERVICE ━━━━━━━━━━━━

def test_miami_plumbing_strong():
    """Premium geo + strong niche should get BUY."""
    from analyzer.pipeline import process_domain
    r = process_domain("miamiplumbing.com")
    assert r["Verdict"] in ("BUY", "GEM")
    assert r.get("SellThroughProbability", 0) >= 10, "Strong local should have good STP"


def test_dentist_chicago_strong():
    from analyzer.pipeline import process_domain
    r = process_domain("dentistchicago.com")
    assert r["Verdict"] in ("BUY", "GEM")


def test_brandable_can_reach_gem_lane():
    """Excellent brandables should appear in the normal GEM view."""
    from analyzer.pipeline import process_domain
    r = process_domain("runwise.com")
    assert r["IsBrandable"] is True
    assert r["Verdict"] == "GEM"


def test_keyword_domain_still_gets_brandable_overlay():
    """Keyword-typed domains should not skip brandability analysis."""
    from analyzer.pipeline import process_domain
    r = process_domain("cloudnova.com")
    assert r["DomainType"] != "brandable"
    assert r["IsBrandable"] is True
    assert r["BrandableScore"] >= 58


def test_hot_keyword_compound_not_automatically_gem():
    """Insurance/legal/real-estate compounds need more than the hot keyword."""
    from analyzer.pipeline import process_domain
    r = process_domain("bestinsurance.com")
    assert r["Verdict"] != "GEM"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
