#!/usr/bin/env python3
"""
Domain Value Analyzer V4 — Reference Domain Benchmark
Scores 9 reference domains through the FULL pipeline and produces a detailed comparison report.
"""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.pipeline import process_domain

# ── Reference Domains ──
REFERENCE_DOMAINS = [
    "casino.com",
    "insurance.com",
    "miamiplumbing.com",
    "dentistchicago.com",
    "realtorminnesota.com",
    "healthcareillinois.com",
    "airealestate.com",
    "bestinsurance.com",
    "xzqwplm.com",
]


def safe_get(d, key, default=""):
    """Safely get a value from dict, returning default for missing/None."""
    v = d.get(key, default)
    return v if v is not None else default


def fmt_price(val):
    """Format a price value."""
    if not val or val == 0:
        return "—"
    try:
        return f"${int(val):,}"
    except (ValueError, TypeError):
        return "—"


def fmt_pct(val):
    """Format a confidence/percentage."""
    if val is None or val == "":
        return "—"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "—"


def run_benchmark():
    results = []
    for domain in REFERENCE_DOMAINS:
        try:
            result = process_domain(domain)
            results.append(result)
        except Exception as e:
            results.append({
                "Domain": domain,
                "Verdict": "ERROR",
                "TotalScore": 0,
                "_error": str(e),
            })

    return results


def print_summary_table(results):
    """Print the main summary table."""
    print("\n" + "=" * 120)
    print("DOMAIN VALUE ANALYZER V4 — REFERENCE DOMAIN BENCHMARK")
    print("=" * 120)

    header = (
        f"{'Domain':<24} | {'Score':>5} | {'Verdict':<6} | "
        f"{'KPS':>4} | {'Tier':<7} | {'Keyword':<14} | "
        f"{'Conf':>5} | {'EvBonus':>7} | {'Price Avg':>12}"
    )
    print(header)
    print("-" * 120)

    for r in results:
        domain = safe_get(r, "Domain", "?")
        if "Verdict" not in r or r.get("Verdict") == "ERROR":
            print(f"{domain:<24} | ERROR: {r.get('_error', 'unknown')}")
            continue

        score = safe_get(r, "TotalScore", 0)
        verdict = safe_get(r, "Verdict", "?")
        kps = safe_get(r, "KeywordPowerScore", 0)
        tier = safe_get(r, "KPSTier", "none")
        keyword = safe_get(r, "KPSKeyword", "—")
        conf = fmt_pct(safe_get(r, "KPSConfidence", 0))
        ev_bonus = safe_get(r, "KPSEvidenceBonus", 0)
        price_low = safe_get(r, "PriceLow", 0)
        price_high = safe_get(r, "PriceHigh", 0)
        if price_low and price_high:
            price_avg = (price_low + price_high) / 2
            price_str = fmt_price(price_avg)
        else:
            price_str = "—"

        print(
            f"{domain:<24} | {score:>5} | {verdict:<6} | "
            f"{kps:>4} | {tier:<7} | {keyword:<14} | "
            f"{conf:>5} | {ev_bonus:>7} | {price_str:>12}"
        )

    print("-" * 120)


def print_detailed_breakdown(results):
    """Print detailed breakdown for each domain."""
    print("\n" + "=" * 100)
    print("DETAILED BREAKDOWN")
    print("=" * 100)

    for r in results:
        domain = safe_get(r, "Domain", "?")
        print(f"\n{'─' * 80}")
        print(f"  {domain}")
        print(f"{'─' * 80}")

        if r.get("Verdict") == "ERROR":
            print(f"  ERROR: {r.get('_error', 'unknown')}")
            continue

        # Core scores
        total = safe_get(r, "TotalScore", 0)
        verdict = safe_get(r, "Verdict", "?")
        dtype = safe_get(r, "DomainType", "?")
        dtype_label = safe_get(r, "DomainTypeLabel", dtype)
        print(f"  Total Score: {total}  |  Verdict: {verdict}  |  Type: {dtype} ({dtype_label})")

        # 6 Axes
        commercial = safe_get(r, "CommercialIntent", 0)
        demand = safe_get(r, "MarketDemand", 0)
        clarity = safe_get(r, "Clarity", 0)
        buyers = safe_get(r, "BuyerPool", 0)
        geo_niche = safe_get(r, "GeoNiche", 0)
        liquidity = safe_get(r, "Liquidity", 0)
        print(f"\n  6 Axes:")
        print(f"    Commercial Intent : {commercial:>3} / 25")
        print(f"    Market Demand     : {demand:>3} / 20")
        print(f"    Clarity           : {clarity:>3} / 15")
        print(f"    Buyer Pool        : {buyers:>3} / 15")
        print(f"    Geo + Niche       : {geo_niche:>3} / 15")
        print(f"    Liquidity         : {liquidity:>3} / 10")
        axes_sum = commercial + demand + clarity + buyers + geo_niche + liquidity
        print(f"    ─────────────────────────────────")
        print(f"    Axes Total        : {axes_sum:>3} / 100")

        # KPS Details
        kps = safe_get(r, "KeywordPowerScore", 0)
        kps_tier = safe_get(r, "KPSTier", "none")
        kps_keyword = safe_get(r, "KPSKeyword", "—")
        kps_match = safe_get(r, "KPSMatchType", "—")
        kps_avg_price = safe_get(r, "KPSAvgPrice", 0)
        kps_sale_count = safe_get(r, "KPSSaleCount", 0)
        kps_max_price = safe_get(r, "KPSMaxPrice", 0)
        kps_conf = safe_get(r, "KPSConfidence", 0)
        kps_ev_bonus = safe_get(r, "KPSEvidenceBonus", 0)
        kps_kw_matched = safe_get(r, "KPSKeywordsMatched", [])
        print(f"\n  KPS Details:")
        print(f"    KPS Score         : {kps}")
        print(f"    KPS Tier          : {kps_tier}")
        print(f"    Best Keyword      : {kps_keyword}  (match: {kps_match})")
        print(f"    Avg Price         : {fmt_price(kps_avg_price)}")
        print(f"    Sale Count        : {kps_sale_count}")
        print(f"    Max Price         : {fmt_price(kps_max_price)}")
        print(f"    Confidence        : {fmt_pct(kps_conf)}")
        print(f"    Evidence Bonus    : {kps_ev_bonus}")
        print(f"    Keywords Matched  : {kps_kw_matched}")

        # Penalties
        penalties = safe_get(r, "Penalties", 0)
        penalty_reasons = safe_get(r, "PenaltyReasons", "")
        print(f"\n  Penalties: {penalties}  {f'({penalty_reasons})' if penalty_reasons else ''}")

        # Brandable
        brand_score = safe_get(r, "BrandableScore", 0)
        is_brand = safe_get(r, "IsBrandable", False)
        print(f"  Brandable: {'Yes' if is_brand else 'No'}  (score: {brand_score})")

        # Price
        price_low = safe_get(r, "PriceLow", 0)
        price_high = safe_get(r, "PriceHigh", 0)
        kps_anchored = safe_get(r, "KPSAnchored", False)
        print(f"  Price Range: {fmt_price(price_low)} – {fmt_price(price_high)}  {'(KPS-anchored)' if kps_anchored else ''}")

        # Niche / Geo
        niche = safe_get(r, "NicheName", "—")
        niche_tier = safe_get(r, "NicheTier", "—")
        geo = safe_get(r, "GeoName", "")
        is_geo = safe_get(r, "IsGeo", False)
        print(f"  Niche: {niche} (tier: {niche_tier})  |  Geo: {geo if geo else '—'} (found: {is_geo})")


def print_analysis(results):
    """Print analysis and verdict on scoring calibration."""
    print("\n" + "=" * 100)
    print("ANALYSIS & VERDICT")
    print("=" * 100)

    # Filter out errors
    valid = [r for r in results if r.get("Verdict") != "ERROR"]
    errors = [r for r in results if r.get("Verdict") == "ERROR"]

    if errors:
        print(f"\n  ⚠️  ERRORS: {len(errors)} domain(s) failed to process:")
        for e in errors:
            print(f"    - {e.get('Domain', '?')}: {e.get('_error', 'unknown')}")

    if not valid:
        print("\n  ❌ No valid results to analyze.")
        return

    # ── Score Distribution ──
    scores = [(r.get("Domain", "?"), r.get("TotalScore", 0)) for r in valid]
    scores.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  📊 Score Distribution (sorted):")
    for domain, score in scores:
        bar = "█" * (score // 2) + "░" * (50 - score // 2)
        print(f"    {domain:<24} {score:>3}  {bar}")

    score_values = [s for _, s in scores]
    score_range = max(score_values) - min(score_values)
    print(f"\n    Range: {score_range} points  (min: {min(score_values)}, max: {max(score_values)})")

    # ── High-value vs Low-value separation ──
    premium_domains = ["casino.com", "insurance.com"]
    mid_domains = ["bestinsurance.com", "airealestate.com"]
    geo_service_domains = ["miamiplumbing.com", "dentistchicago.com", "realtorminnesota.com", "healthcareillinois.com"]
    junk_domain = "xzqwplm.com"

    premium_scores = [r.get("TotalScore", 0) for r in valid if r.get("Domain") in premium_domains]
    mid_scores = [r.get("TotalScore", 0) for r in valid if r.get("Domain") in mid_domains]
    geo_scores = [r.get("TotalScore", 0) for r in valid if r.get("Domain") in geo_service_domains]
    junk_result = next((r for r in valid if r.get("Domain") == junk_domain), None)

    print(f"\n  📈 Category Averages:")
    if premium_scores:
        print(f"    Premium single-word (casino, insurance): avg {sum(premium_scores)/len(premium_scores):.1f}")
    if mid_scores:
        print(f"    Mid-tier compound (bestinsurance, airealestate): avg {sum(mid_scores)/len(mid_scores):.1f}")
    if geo_scores:
        print(f"    Geo+Service (miamiplumbing, etc.): avg {sum(geo_scores)/len(geo_scores):.1f}")
    if junk_result:
        print(f"    Gibberish (xzqwplm): {junk_result.get('TotalScore', 0)}")

    # ── Calibration Checks ──
    print(f"\n  🔍 Calibration Checks:")

    # 1. Score separation
    if premium_scores and junk_result:
        separation = min(premium_scores) - junk_result.get("TotalScore", 0)
        status = "✅" if separation >= 30 else "⚠️" if separation >= 15 else "❌"
        print(f"    {status} Premium vs Gibberish separation: {separation} points (want ≥30)")

    # 2. Verdicts
    print(f"\n    Verdicts:")
    for r in valid:
        domain = r.get("Domain", "?")
        verdict = r.get("Verdict", "?")
        score = r.get("TotalScore", 0)
        print(f"      {domain:<24} → {verdict:<6} ({score} pts)")

    # 3. KPS Confidence
    print(f"\n    KPS Confidence:")
    for r in valid:
        domain = r.get("Domain", "?")
        conf = r.get("KPSConfidence", 0)
        keyword = r.get("KPSKeyword", "—")
        tier = r.get("KPSTier", "none")
        match = r.get("KPSMatchType", "—")
        print(f"      {domain:<24} conf={conf:.2f}  keyword={keyword:<14} tier={tier:<7} match={match}")

    # 4. Evidence bonus cap check
    print(f"\n    Evidence Bonus (should be capped by confidence):")
    for r in valid:
        domain = r.get("Domain", "?")
        ev = r.get("KPSEvidenceBonus", 0)
        conf = r.get("KPSConfidence", 0)
        print(f"      {domain:<24} ev_bonus={ev:>3}  confidence={conf:.2f}")

    # 5. Multi-keyword domain recognition
    print(f"\n    Multi-keyword Domain Recognition:")
    for r in valid:
        domain = r.get("Domain", "?")
        dtype = r.get("DomainType", "?")
        niche = r.get("NicheName", "—")
        geo = r.get("GeoName", "")
        is_geo = r.get("IsGeo", False)
        kw_matched = r.get("KPSKeywordsMatched", [])
        print(f"      {domain:<24} type={dtype:<15} niche={niche:<20} geo={geo:<12} found={is_geo}  kw={kw_matched}")

    # ── Overall Assessment ──
    print(f"\n  🏁 Overall Assessment:")

    issues = []

    # Check 1: Score distribution
    if score_range < 30:
        issues.append("Score range is too narrow (<30 points). Scores may not differentiate well.")
    else:
        print(f"    ✅ Score range is healthy ({score_range} points spread)")

    # Check 2: Premium > junk
    if premium_scores and junk_result:
        if min(premium_scores) <= junk_result.get("TotalScore", 0):
            issues.append("Premium domains don't score higher than gibberish!")
        else:
            print(f"    ✅ Premium domains score higher than gibberish")

    # Check 3: Verdicts make sense
    for r in valid:
        domain = r.get("Domain", "?")
        verdict = r.get("Verdict", "?")
        score = r.get("TotalScore", 0)
        if domain in premium_domains and verdict not in ("GEM", "BUY"):
            issues.append(f"{domain} (premium) got verdict '{verdict}' — expected GEM or BUY")
        if domain == junk_domain and verdict not in ("PASS", "HOLD", "EXCLUDED"):
            issues.append(f"{domain} (gibberish) got verdict '{verdict}' — expected PASS or EXCLUDED")

    if not any(i for i in issues if "verdict" in i.lower() or "premium" in i.lower()):
        print(f"    ✅ Verdicts are reasonable for all domains")

    # Check 4: KPS confidence
    for r in valid:
        domain = r.get("Domain", "?")
        conf = r.get("KPSConfidence", 0)
        if domain in premium_domains and conf < 0.5:
            issues.append(f"{domain} has low KPS confidence ({conf:.2f}) — expected high for premium keyword")
        if domain == junk_domain and conf > 0.3:
            issues.append(f"{domain} has high KPS confidence ({conf:.2f}) — expected low/zero for gibberish")

    if not any(i for i in issues if "confidence" in i.lower()):
        print(f"    ✅ KPS confidence looks properly calibrated")

    # Check 5: Evidence bonus capped
    for r in valid:
        ev = r.get("KPSEvidenceBonus", 0)
        conf = r.get("KPSConfidence", 0)
        if ev > 0 and conf == 0:
            issues.append(f"{r.get('Domain', '?')} has evidence bonus ({ev}) but zero confidence — should be capped to 0")

    if not any(i for i in issues if "evidence" in i.lower()):
        print(f"    ✅ Evidence bonus properly scaled by confidence")

    # Check 6: Geo+Service domains recognized
    for r in valid:
        domain = r.get("Domain", "?")
        if domain in ["miamiplumbing.com", "dentistchicago.com"]:
            dtype = r.get("DomainType", "?")
            if dtype != "local_service":
                issues.append(f"{domain} classified as '{dtype}' — expected 'local_service'")

    if not any(i for i in issues if "local_service" in i):
        print(f"    ✅ Geo+Service domains properly recognized as local_service")

    if issues:
        print(f"\n  ⚠️  Issues Found ({len(issues)}):")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    else:
        print(f"\n    🎉 No issues found — scoring appears well-calibrated!")


def main():
    print("Running benchmark on 9 reference domains...")
    results = run_benchmark()
    print_summary_table(results)
    print_detailed_breakdown(results)
    print_analysis(results)
    print("\n" + "=" * 100)
    print("BENCHMARK COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
