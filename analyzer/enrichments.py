"""
Domain Enrichment Services — Spam detection and price estimation.
"""
import logging
from config import NICHE_PROFITABILITY, TLD_MULTIPLIERS as _TLD_MULT, tld_for_lookup

logger = logging.getLogger("analyzer.enrichments")


def detect_spam_domain(domain: str) -> dict:
    """
    Detect if domain was used for spam or PBN.
    Only flags genuine spam indicators — NOT legitimate high-value industry keywords.

    NOTE: casino, poker, gambling, adult content are proven premium domain markets
    (avg sale prices $55k–$841k per the retail sales database).  They are NOT spam.
    Only flag domains whose keywords are exclusively associated with fraud/counterfeits.
    """
    spam_score = 0
    flags = []

    name = domain.split('.')[0].lower()
    # Also check hyphen-stripped form so "essay-writer.com" matches "essaywriter"
    name_stripped = name.replace('-', '').replace('_', '')

    # Genuine spam/fraud indicators ONLY (not premium industry keywords)
    spam_keywords = [
        "viagra", "cialis", "xanax", "oxycontin", "tramadol",   # counterfeit pharma
        "ponzi", "payday",                                        # predatory finance
        "essaywriter", "homeworkhelp", "ghostwriter",             # academic fraud (compound)
        "maleenhancement", "enlargement",                         # counterfeit supplements
    ]

    # Stack signals from all matched keywords (don't stop at first)
    for kw in spam_keywords:
        if kw in name or kw in name_stripped:
            spam_score += 15
            flags.append(f"spam_keyword:{kw}")

    if len(name) > 20:
        spam_score += 5
        flags.append("long_domain")

    # Threshold of 15 = a single confirmed spam keyword is enough to flag
    return {
        "spam_score": min(spam_score, 100),
        "flags": flags,
        "is_spammy": spam_score >= 15
    }


def estimate_historical_price(domain: str, score: int,
                               domain_type: str = "low_value",
                               niche_name: str = "-",
                               kps_result: dict = None) -> dict:
    """
    Estimate domain resale value using KPS comparable sale data as the primary
    anchor, with score/type/niche as secondary adjustments.

    When KPS provides real transaction data, we anchor to those actual market
    prices rather than guessing from score tiers alone.

    NOTE on TLD handling
    --------------------
    The ``score`` parameter is the TotalScore returned by market_scorer, which
    already has the TLD multiplier baked in (axes_sum * tld_mult).  Using that
    score directly for the score-based tier lookup is therefore correct —
    it naturally yields a lower score_base for weak-TLD domains.

    The TLD multiplier is then applied ONCE to the KPS-anchored component
    (because KPS data comes from real domain sales that are mostly .com, so
    the anchor needs TLD-normalisation).  It is NOT applied to the score_base
    component a second time — doing so would double-penalise non-.com domains.
    """
    kps_result = kps_result or {}
    best_m     = kps_result.get("best_match") or {}
    kps_avg    = best_m.get("avg_price", 0)
    kps_cnt    = best_m.get("sale_count", 0)
    kps_max    = best_m.get("max_price", 0)
    kps_mtype  = best_m.get("match_type", "")
    kps_tier   = kps_result.get("kps_tier", "none")

    # ── TLD multiplier (resolved once, used below) ──
    tld_key  = tld_for_lookup(domain)
    tld_mult = _TLD_MULT.get(tld_key, 0.30)

    # ── KPS-anchored estimate (primary when data is available) ──
    # KPS prices are TLD-neutral (sourced from .com comparable sales).
    # Apply TLD multiplier here so the anchor reflects actual market value
    # for this domain's extension.
    kps_base = 0
    confidence = "low"

    if kps_avg > 0 and kps_cnt >= 3:
        if kps_mtype == "exact":
            # Most reliable: this exact keyword category has sold at this price
            kps_base   = kps_avg * tld_mult
            confidence = "high" if kps_cnt >= 10 else "medium"
        elif kps_mtype in ("prefix", "suffix"):
            # Comparable compound: use avg as a directional anchor
            kps_base   = kps_avg * 0.7 * tld_mult
            confidence = "medium" if kps_cnt >= 20 else "low"
        elif kps_mtype == "middle":
            kps_base   = kps_avg * 0.4 * tld_mult
            confidence = "low"

    # ── Score-based estimate (fallback / blending) ──
    # The score is already TLD-adjusted, so the tier jump naturally captures
    # the TLD impact. Do NOT multiply by tld_mult again here.
    if score >= 85:      score_base = 5000
    elif score >= 75:    score_base = 2500
    elif score >= 65:    score_base = 1200
    elif score >= 50:    score_base = 400
    elif score >= 35:    score_base = 120
    else:                score_base = 30

    # Domain type multiplier
    type_mult = {
        "local_service": 1.8, "seo_keyword": 1.5, "global_service": 1.2,
        "brandable": 1.0,     "content_media": 0.8, "low_value": 0.4,
    }.get(domain_type, 0.5)
    score_base *= type_mult

    # Niche boost on score-base
    prof = NICHE_PROFITABILITY.get(niche_name)
    if prof:
        tier = prof["profit_tier"]
        if tier == 1:   score_base *= 2.0
        elif tier == 2: score_base *= 1.5
        elif tier == 3: score_base *= 1.2
    elif kps_tier in ("ultra", "premium"):
        # Dynamic niche: no hardcoded entry but KPS proves high-value keyword
        score_base *= 1.5
    elif kps_tier == "high" or (kps_avg > 0 and kps_avg >= 2000):
        score_base *= 1.3

    # ── Blend KPS anchor with score base (confidence-aware) ──
    # Both components are now TLD-normalised — kps_base has tld_mult already
    # applied above, and score_base inherits TLD from the input score.
    if kps_base > 0:
        kps_confidence = kps_result.get("kps_confidence", 0) if kps_result else 0
        kps_weight = min(1.0, 0.8 * kps_confidence)
        fallback_weight = 1.0 - kps_weight
        estimated = (kps_base * kps_weight) + (score_base * fallback_weight)
    else:
        estimated = score_base

    # ── Length influence & Ultra-Short Premium Override ──
    name = domain.split('.')[0].lower()
    is_pure_alpha = name.isalpha()
    is_pure_num = name.isdigit()
    is_mixed_alnum = name.isalnum() and not is_pure_alpha and not is_pure_num
    is_ultra_short = len(name) <= 4 and name.isalnum()

    if is_ultra_short:
        # Base floor values for .com (tld_mult handles .net, .org, etc)
        short_base = 0
        if is_pure_alpha:
            if len(name) == 1: short_base = 2_000_000
            elif len(name) == 2: short_base = 500_000
            elif len(name) == 3: short_base = 15_000
            elif len(name) == 4: short_base = 500
        elif is_pure_num:
            if len(name) == 1: short_base = 3_000_000
            elif len(name) == 2: short_base = 1_000_000
            elif len(name) == 3: short_base = 40_000
            elif len(name) == 4: short_base = 3_000
        elif is_mixed_alnum:
            # Mixed alphanumeric short names (ai2, x5, g7, etc.) — lower floor
            if len(name) == 2: short_base = 50_000
            elif len(name) == 3: short_base = 3_000
            elif len(name) == 4: short_base = 300

        # Override score-based estimate if the floor is higher
        short_val = short_base * tld_mult
        if short_val > estimated:
            estimated = short_val
            confidence = "high" if not is_mixed_alnum else "medium"
    elif len(name) <= 4:    estimated *= 2.0
    elif len(name) <= 6:  estimated *= 1.3
    elif len(name) >= 18: estimated *= 0.6

    # ── Price ceiling guard: proportional to match quality ──
    # Ceiling is based on the TLD-adjusted kps_max.
    kps_max_adj = kps_max * tld_mult if kps_max > 0 else 0
    ceiling_pct = {"exact": 0.80, "prefix": 0.60, "suffix": 0.60, "middle": 0.40}.get(kps_mtype, 0.60)
    
    # Do not apply KPS ceiling to ultra-short premiums (their value is structural, not keyword-bound)
    if not is_ultra_short and kps_max_adj > 0 and estimated > kps_max_adj * ceiling_pct:
        estimated = kps_max_adj * ceiling_pct

    # Narrow range: 0.7x–1.5x (was 0.5x–2.5x = unrealistic 5x spread)
    low  = int(estimated * 0.7)
    high = int(estimated * 1.5)

    # ── Confidence override based on KPS tier ──
    if kps_tier in ("ultra", "premium") and kps_cnt >= 10:
        confidence = "high"
    elif kps_tier in ("ultra", "premium") and kps_cnt >= 3:
        confidence = "medium"

    return {
        "estimated_value": int(estimated),
        "low_estimate":    low,
        "high_estimate":   high,
        "confidence":      confidence,
        "kps_anchored":    kps_base > 0,
    }