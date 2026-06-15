"""
Market Scorer V4 — Domain Valuation Through Investor Logic.

This is NOT a calculator. It simulates a real domainer's buying decision.
The single question: "Can this domain realistically be sold for profit?"

6 Axes:
  1. Commercial Intent (0-25) — Is there money here?
  2. Market Demand    (0-20) — Is the market active?
  3. Clarity          (0-15) — Does the domain explain itself?
  4. Buyer Pool       (0-15) — How many potential buyers?
  5. Geo + Niche      (0-15) — Geographic + industry value
  6. Liquidity        (0-10) — How fast can you sell?
"""
import re
import logging
from config import (
    NICHE_PROFITABILITY, NICHE_TIER_SCORES, PENALTIES,
    TRANSACTIONAL_KEYWORDS, CONTENT_KEYWORDS, DOMAIN_TYPES,
    SCORE_THRESHOLDS, DOMAIN_TYPES_AR, RESELL_SPEED_AR,
    TLD_MULTIPLIERS, tld_for_lookup,
)
from analyzer.word_data import (
    TIER1_WORDS, ALL_WORDS, ALL_GEO,
    detect_geo, try_split_compound,
    get_singular,
    get_geo_market_quality,
)
from analyzer.geo_service import detect_niche, detect_personal_name
from analyzer.retail_kps import score_kps, kps_commercial, kps_demand, TREND_KEYWORDS, COMMERCIAL_KEYWORDS

logger = logging.getLogger("analyzer.market_scorer")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   UTILITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━



def _parse_float(val, default=0.0):
    try:
        return float(str(val).replace('$', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return default


def _parse_int(val, default=0):
    try:
        return int(float(str(val).replace(',', '').strip()))
    except (ValueError, TypeError):
        return default


def _name_contains_any(name, word_set):
    """Check if domain name contains any word from a set (substring, min 4 chars)."""
    for w in word_set:
        if len(w) >= 4 and w in name:
            return True
    return False


def _find_matching_keywords(name, word_set):
    """Return all matching keywords from a set found in the name."""
    return [w for w in word_set if len(w) >= 4 and w in name]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   STEP 1: DOMAIN TYPE DETECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_domain_type(name, niche_info, geo_info, extra_data, kps_result=None):
    """
    Classify the domain into ONE type. This controls how everything is evaluated.

    Types:
      - seo_keyword:    keyword-rich, targeting search traffic (bestcarinsurance)
      - local_service:  geo + service combination (miamidentist)
      - global_service: service/product without geo (cloudhosting)
      - brandable:      short, memorable, no clear keyword (zentrova, stripe)
      - content_media:  informational / content site (technews, healthtips)
      - low_value:      unclear, no signal, gibberish-adjacent
    """
    has_geo = geo_info["geo_found"]
    has_niche = niche_info.get("niche", "-") != "-"
    niche_tier = niche_info.get("niche_tier", "none")
    cpc = _parse_float(extra_data.get("cpc", 0))
    has_cpc = cpc > 0.5
    has_sv = _parse_int(extra_data.get("sv", 0)) > 100

    has_transactional = _name_contains_any(name, TRANSACTIONAL_KEYWORDS)
    has_content = _name_contains_any(name, CONTENT_KEYWORDS)

    # Trending tech/market keywords — domains embedding these are treated as
    # global_service or brandable, NOT low_value, even without niche/geo data.
    has_trend_kw = any(kw in name for kw in TREND_KEYWORDS if len(kw) >= 2)

    is_single_word = name in ALL_WORDS or name in ALL_GEO
    compound = try_split_compound(name)
    is_compound = compound is not None

    # ── Dynamic KPS & Market Signals ──
    # Use KPS/CPC data to discover value in ANY industry, not just hardcoded niches.
    has_strong_kps = False
    if kps_result:
        k_tier = kps_result.get("kps_tier", "none")
        k_avg = (kps_result.get("best_match") or {}).get("avg_price", 0)
        k_count = (kps_result.get("best_match") or {}).get("sale_count", 0)
        # If a keyword has sold well historically, it IS a valid commercial niche.
        if k_tier in ("ultra", "premium", "high") or (k_avg >= 800 and k_count >= 2):
            has_strong_kps = True
            
    is_dynamic_commercial = has_strong_kps or cpc >= 2.0

    # ── Plural/singular awareness ──
    name_singular   = get_singular(name)
    name_is_plural  = (name_singular != name)
    singular_in_kws = (name_singular in TIER1_WORDS or name_singular in ALL_WORDS)

    if name_is_plural and singular_in_kws and not has_geo:
        if has_cpc or has_sv or has_niche or is_dynamic_commercial:
            return "seo_keyword"
        if name_singular in TIER1_WORDS:
            return "seo_keyword"

    # ── Dynamic Discovery ──
    reg = _parse_int(extra_data.get("reg", 0))
    rdt = _parse_int(extra_data.get("rdt", 0))
    is_market_popular = False
    if not is_single_word and not is_compound:
        if len(name) <= 12 and (rdt >= 20 or reg >= 10):
            is_market_popular = True

    is_short_clean = len(name) <= 7 and _is_clean_name(name)

    # ── Decision tree ──

    # Local service: geo + niche/service keyword OR geo + dynamic commercial signal
    if has_geo and (has_niche or is_dynamic_commercial):
        return "local_service"

    if is_short_clean and not name_is_plural and (reg >= 5 or rdt >= 5):
        return "brandable"

    # SEO keyword: strong commercial signals + niche OR dynamic market signal
    if (has_niche and has_transactional) or (is_dynamic_commercial and has_transactional):
        return "seo_keyword"

    if (has_niche and has_cpc and niche_tier in ("tier1", "tier2", "tier3")) or is_dynamic_commercial:
        return "seo_keyword"

    # Content/media
    if has_content and (is_compound or is_single_word):
        return "content_media"

    # Global service: niche present, no geo
    if has_niche and (is_compound or is_single_word) and not has_geo:
        return "global_service"

    # Brandable: short + clean + NOT a plural
    if is_short_clean and not name_is_plural:
        return "brandable"

    if is_single_word and len(name) <= 8 and not name_is_plural:
        return "brandable"

    # SEO fallback: compound + data signals
    if is_compound and (has_cpc or has_sv):
        return "seo_keyword"

    if has_content:
        return "content_media"

    if has_niche:
        return "global_service"

    if is_compound or (is_single_word and len(name) <= 12) or is_market_popular:
        return "brandable"

    if _is_clean_name(name) and len(name) <= 10:
        return "brandable"

    if len(name) <= 6 and (reg >= 2 or rdt >= 2):
        return "brandable"

    # Trending technology/market keywords salvage otherwise undifferentiated names.
    # "aitools", "solarnova", "cryptobase" should never be low_value.
    if has_trend_kw and len(name) <= 16:
        return "global_service"

    return "low_value"


def _is_clean_name(name):
    """Check if name looks clean and pronounceable."""
    if len(name) < 3:
        return True
    # Real dictionary words are always clean, regardless of vowel pattern.
    # This prevents false negatives on words like "rhythm", "crypt", "lynx".
    if name in ALL_WORDS or name in TIER1_WORDS:
        return True
    vowels = sum(1 for c in name if c in 'aeiouy')
    ratio = vowels / len(name)
    if ratio < 0.15 or ratio > 0.85:
        return False
    # No crazy consonant clusters
    max_cons = max((len(r) for r in re.findall(r'[^aeiouy]+', name)), default=0)
    return max_cons < 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   STEP 2: AXIS SCORING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def score_commercial_intent(name, domain_type, niche_info, extra_data,
                             kps_result=None, coherence=None):
    """
    Axis 1: Commercial Intent (0-25)
    "Are people trying to BUY something here?"

    V5 changes:
    - Niche boost is GATED on coherence_score. Stuffed/incoherent names
      get zero boost regardless of category.
    - Hardcoded NICHE_PROFITABILITY tier no longer grants its own boost
      independent of evidence. The boost path now requires evidence:
      KPS or CPC. (The old engine awarded +3 for tier1 even with zero
      evidence, which is the source of the law/insurance/health bias.)
    - Transactional keyword stacking is capped (was unbounded by length).
    """
    cpc = _parse_float(extra_data.get("cpc", 0))

    if kps_result is None:
        kps_result = score_kps(name)

    kps_score = kps_result.get("kps_score", 0)
    coherence_score = (coherence or {}).get("coherence_score", 100)
    is_stuffed = (coherence or {}).get("is_keyword_stuffed", False)
    is_incoherent = (coherence or {}).get("is_incoherent", False)

    # ── Evidence-driven niche boost (replaces tier-driven boost) ──
    # The boost is awarded based on EVIDENCE, not category labels.
    # A new sector with strong KPS gets the same boost as Insurance/Legal
    # with the same KPS. A category label alone is no longer sufficient.
    niche_boost = 0
    if kps_score >= 80:
        niche_boost = 4
    elif kps_score >= 50:
        niche_boost = 3
    elif kps_score >= 25:
        niche_boost = 2
    elif cpc >= 10.0:
        niche_boost = 1

    # Hardcoded niche tier ONLY adds +1 ceiling — never the primary driver.
    # This recognizes known categories without elevating them above evidence.
    niche = niche_info.get("niche", "-")
    prof = NICHE_PROFITABILITY.get(niche)
    if prof and niche_boost > 0:
        if prof["profit_tier"] <= 2:
            niche_boost = min(niche_boost + 1, 4)

    # ── Coherence gate: forfeit boost on broken names ──
    if is_stuffed:
        niche_boost = 0
    elif is_incoherent:
        niche_boost = min(niche_boost, 1)
    elif coherence_score < 60:
        niche_boost = max(0, int(niche_boost * coherence_score / 60))

    score = kps_commercial(kps_score, kps_result.get("kps_confidence", 1.0), cpc, niche_boost)

    # Transactional keyword secondary signal — capped, and forfeit on stuffing
    if not is_stuffed and coherence_score >= 50:
        tx_keywords = _find_matching_keywords(name, TRANSACTIONAL_KEYWORDS)
        if tx_keywords:
            score = min(25, score + min(2, len(tx_keywords)))  # cap reduced 3→2

    # Floor guarantees by domain type when KPS is absent — only on coherent names
    if kps_score == 0 and coherence_score >= 60:
        if domain_type == "local_service" and score < 8:
            score = max(score, 8)
        elif domain_type == "seo_keyword" and score < 6:
            score = max(score, 6)

    return min(25, score)


def score_market_demand(name, domain_type, niche_info, extra_data, kps_result=None):
    """
    Axis 2: Market Demand (0-20)
    "Is this a live market with money flowing?"

    PRIMARY signal: KPS sale count — how many real domains with this keyword sold.
    SECONDARY signals: SV (reduced weight), domain age, REG, RDT.
    """
    if kps_result is None:
        kps_result = score_kps(name)

    sv  = _parse_int(extra_data.get("sv",  0))
    rdt = _parse_int(extra_data.get("rdt", 0))
    reg = _parse_int(extra_data.get("reg", 0))
    aby = _parse_int(extra_data.get("aby", 0))

    return kps_demand(kps_result, sv=sv, rdt=rdt, reg=reg, aby=aby)


def score_clarity(name, domain_type, niche_info, geo_info, extra_data=None, kps_result=None):
    """
    Axis 3: Clarity (0-15)
    "Does the domain instantly explain what it is?"

    A clear domain sells itself. An unclear domain needs a sales pitch.
    """
    score = 0

    is_single_word = name in TIER1_WORDS
    is_known_word  = name in ALL_WORDS
    is_geo         = name in ALL_GEO
    compound       = try_split_compound(name)
    has_niche      = niche_info.get("niche", "-") != "-"

    # ── Plural/Singular awareness ──
    # "lawyers.com" is an SEO keyword → singular "lawyer" is in TIER1 but the
    # plural form signals search intent ("best lawyers near me").
    # "car.com" is brandable → singular premium single word.
    # We detect this and adjust scoring accordingly.
    name_singular  = get_singular(name)
    name_is_plural = (name_singular != name)  # True when name is a plural form
    singular_is_tier1 = name_singular in TIER1_WORDS
    singular_is_known = name_singular in ALL_WORDS

    # Perfect clarity: single common word everyone knows
    if is_single_word:
        score = 14  # "fire.com", "cloud.com" — everyone gets it

    # Plural of a Tier-1 word — clear, strong SEO signal.
    # We must rescue "Category Killers" (plurals of commercial/transactional words).
    # "loans.com" or "hotels.com" are often MORE valuable than their singulars.
    elif name_is_plural and singular_is_tier1:
        if _name_contains_any(name_singular, COMMERCIAL_KEYWORDS) or _name_contains_any(name_singular, TRANSACTIONAL_KEYWORDS):
            score = 14  # Category Killers: "loans", "hotels", "cars"
        else:
            score = 11  # "tables.com", "clouds.com" — clear + SEO intent

    # Geographic name — universally understood
    elif is_geo and geo_info.get("geo_type") == "pure":
        score = 13  # "miami.com" — crystal clear

    # Known word — clear but maybe less universal
    elif is_known_word:
        score = 11  # "falcon.com" — clear concept

    # Plural of a known word — clear with SEO intent
    elif name_is_plural and singular_is_known:
        score = 10  # "apartments.com" — clear + search intent

    # Compound with clear meaning
    elif compound:
        w1, w2 = compound
        both_common = w1 in TIER1_WORDS and w2 in TIER1_WORDS
        if both_common:
            score = 12  # "goldmine.com" — instantly clear
        else:
            score = 9   # "birchwood.com" — mostly clear

    # Geo + niche compound (not in word lists but detectable)
    elif geo_info["geo_found"] and has_niche:
        score = 13  # "miamidentist" — perfectly clear

    # Has niche keywords — somewhat clear
    elif has_niche:
        score = 8   # "dentalcare" — clear category

    # Content keywords present
    elif _name_contains_any(name, CONTENT_KEYWORDS):
        score = 7

    # Can detect transactional intent
    elif _name_contains_any(name, TRANSACTIONAL_KEYWORDS):
        score = 7

    # Brandable but unclear concept
    elif domain_type == "brandable":
        # Clarity for brandables is purely structural — not market signals.
        # REG/RDT live exclusively in Buyer Pool to avoid double-counting.
        if len(name) <= 5:
            score = 7   # Short brandables have implicit clarity
        elif len(name) <= 7:
            score = 5
        else:
            score = 4   # "zentrova" — nice name but what is it?

    else:
        score = 1  # Unclear

    # KPS coverage boost — if the KPS engine parsed the domain into meaningful
    # keywords that cover most of the SLD, the domain IS clear to an investor
    # even if it's not in any word list or compound dictionary.
    # Example: "parallelai" → KPS finds [parallel, ai] with 100% coverage → clear.
    if score < 9 and kps_result:
        kps_coverage = kps_result.get("coverage_ratio", 0.0)
        kps_matches  = kps_result.get("kps_keywords_matched", [])
        kps_tier     = kps_result.get("kps_tier", "none")
        if kps_coverage >= 0.8 and len(kps_matches) >= 2:
            if kps_tier in ("ultra", "premium"):
                score = max(score, 11)
            elif kps_tier == "high":
                score = max(score, 10)
            elif kps_tier == "mid":
                score = max(score, 9)
        elif kps_coverage >= 0.6 and kps_matches:
            if kps_tier in ("ultra", "premium"):
                score = max(score, 9)
            elif kps_tier in ("high", "mid"):
                score = max(score, 8)

    # Length penalty on clarity: long + unclear = worse
    if len(name) > PENALTIES["LONG_UNCLEAR_THRESHOLD"] and score < 8:
        score = max(0, score - 3)

    # Length bonus on clarity: short + clear = better
    if len(name) <= 5 and score >= 8:
        score = min(15, score + 2)
    elif len(name) <= 7 and score >= 8:
        score = min(15, score + 1)

    return min(15, score)


def score_buyer_pool(name, domain_type, niche_info, geo_info, extra_data, kps_result=None):
    """
    Axis 4: Buyer Pool (0-15)
    "How many potential buyers exist for this domain?"

    Local service domains have the most buyers (every dentist in Miami).
    Random brandable names have the fewest (need the right startup).

    REG is the PRIMARY signal here (taken in multiple TLDs = proven buyer interest).
    RDT contributes a small secondary boost (max +2) to avoid double-counting with
    Commercial Intent and Liquidity axes.
    """
    score = 0
    niche = niche_info.get("niche", "-")
    prof = NICHE_PROFITABILITY.get(niche)
    reg = _parse_int(extra_data.get("reg", 0))
    rdt = _parse_int(extra_data.get("rdt", 0))

    if domain_type == "local_service":
        score = 13
        if prof and prof["buyer_density"] >= 8:
            score = 15
        elif kps_result and kps_result.get("total_keyword_sales", 0) >= 50:
            score = 15
        elif not prof and _parse_float(extra_data.get("cpc", 0)) >= 4.0:
            # Dynamic niche: CPC proves active buyer market
            score = 14

    elif domain_type == "seo_keyword":
        score = 10
        if prof and prof["buyer_density"] >= 7:
            score = 12
        elif kps_result and kps_result.get("total_keyword_sales", 0) >= 30:
            score = 12

    elif domain_type == "global_service":
        score = 8
        if prof and prof["buyer_density"] >= 6:
            score = 10
        elif kps_result and kps_result.get("total_keyword_sales", 0) >= 20:
            score = 10

    elif domain_type == "content_media":
        score = 7

    elif domain_type == "brandable":
        if name in TIER1_WORDS and len(name) <= 6:
            score = 12
        elif name in TIER1_WORDS:
            score = 9
        elif name in ALL_WORDS:
            score = 7
        else:
            # REG is the authoritative buyer-pool signal for non-dictionary brandables
            if reg >= 10:
                score = 11
            elif reg >= 5:
                score = 9
            elif reg >= 3:
                score = 7
            elif len(name) <= 5 and _is_clean_name(name):
                # Rescue short pronounceable startup names even without REG
                score = 6
            elif reg >= 1:
                score = 5
            else:
                score = 3

    elif domain_type == "low_value":
        score = 1

    # REG boost (PRIMARY signal for this axis — only applied once, here)
    # Already baked into brandable logic above; apply globally for other types
    if domain_type != "brandable":
        if reg >= 10:
            score = min(15, score + 3)
        elif reg >= 5:
            score = min(15, score + 2)
        elif reg >= 2:
            score = min(15, score + 1)

    # RDT — tiered secondary boost (primary home is Commercial Intent & Signal)
    if rdt >= 100:
        score = min(15, score + 4)
    elif rdt >= 50:
        score = min(15, score + 3)
    elif rdt >= 10:
        score = min(15, score + 2)
    elif rdt >= 3:
        score = min(15, score + 1)

    # KPS boost: high total keyword sales = many participants in this market
    if kps_result:
        tks = kps_result.get("total_keyword_sales", 0)
        if tks >= 200:
            score = min(15, score + 3)
        elif tks >= 50:
            score = min(15, score + 2)
        elif tks >= 20:
            score = min(15, score + 1)

    return min(15, score)


def score_geo_niche(name, domain_type, niche_info, geo_info, extra_data,
                     kps_result=None, coherence=None):
    """
    Axis 5: Geo + Niche (0-15)
    "Geographic and industry value combined."

    V5 changes:
    - Niche-only path no longer awards 8 pts purely for being "tier1".
      It now requires SOME evidence (KPS/CPC/REG) before granting points.
    - Dynamic sector path widens the funnel — any keyword with strong KPS
      data (regardless of category) can trigger this path. This is what
      lets non-traditional gems surface.
    - Coherence gate caps points on broken structures.

    Two dimensions:
      1. Niche quality  (tier1–tier5)
      2. Market quality (1=English-native premium → 4=negligible .com market)
    """
    score = 0
    has_geo = geo_info["geo_found"]
    niche = niche_info.get("niche", "-")
    niche_tier = niche_info.get("niche_tier", "none")
    geo_name = geo_info.get("geo_name", "")
    cpc = _parse_float(extra_data.get("cpc", 0))
    coherence_score = (coherence or {}).get("coherence_score", 100)
    is_stuffed = (coherence or {}).get("is_keyword_stuffed", False)
    is_incoherent = (coherence or {}).get("is_incoherent", False)

    # ── Geo + Niche combo (the jackpot — if the market is real) ──
    if has_geo and niche != "-":
        market_q = get_geo_market_quality(geo_name)  # 1=best … 4=weakest

        # 2-D scoring matrix: niche tier × market quality
        # Rows = niche tier, Cols = market quality 1/2/3/4
        _MATRIX = {
            "tier1": {1: 15, 2: 13, 3:  9, 4:  5},
            "tier2": {1: 14, 2: 12, 3:  8, 4:  4},
            "tier3": {1: 12, 2: 10, 3:  7, 4:  3},
            "tier4": {1:  9, 2:  7, 3:  5, 4:  2},
            "tier5": {1:  7, 2:  5, 3:  3, 4:  2},
        }
        row = _MATRIX.get(niche_tier, {1: 5, 2: 4, 3: 3, 4: 2})
        score = row.get(market_q, row.get(3, 3))  # default to quality=3 bucket

    # ── Niche only (no geo) — REQUIRES evidence to score above generic ──
    # Previous engine: tier1 → 8 automatically (this is the law/insurance bias).
    # V5: niche category alone earns minimal recognition. Real points come
    # from KPS/CPC evidence — which any industry can provide.
    elif niche != "-":
        kps_tier_local = kps_result.get("kps_tier", "none") if kps_result else "none"
        kps_avg_local = (kps_result.get("best_match") or {}).get("avg_price", 0) if kps_result else 0
        has_evidence = (
            kps_tier_local in ("ultra", "premium", "high")
            or kps_avg_local >= 1500
            or cpc >= 15.0
        )
        if niche_tier == "tier1" and has_evidence:
            score = 8
        elif niche_tier == "tier1":
            score = 4   # category recognized but no evidence yet
        elif niche_tier == "tier2" and has_evidence:
            score = 6
        elif niche_tier == "tier2":
            score = 3
        elif niche_tier == "tier3" and has_evidence:
            score = 4
        elif niche_tier == "tier3":
            score = 2
        else:
            score = min(2, NICHE_TIER_SCORES.get(niche_tier, 0))

    # ── Geo + Dynamic Niche (geo detected, no hardcoded niche, but KPS/CPC proves value) ──
    elif has_geo and niche == "-":
        market_q = get_geo_market_quality(geo_name)
        kps_tier_local = kps_result.get("kps_tier", "none") if kps_result else "none"
        kps_avg_local = (kps_result.get("best_match") or {}).get("avg_price", 0) if kps_result else 0

        if kps_tier_local in ("ultra", "premium") or kps_avg_local >= 2000:
            # Dynamic high-value keyword + geo = good combo
            _dyn_row = {1: 12, 2: 10, 3: 7, 4: 3}
            score = _dyn_row.get(market_q, 5)
        elif kps_tier_local in ("high", "mid") or cpc >= 4.0:
            _dyn_row = {1: 9, 2: 7, 3: 5, 4: 2}
            score = _dyn_row.get(market_q, 4)
        elif cpc >= 2.0:
            _dyn_row = {1: 6, 2: 4, 3: 3, 4: 1}
            score = _dyn_row.get(market_q, 3)
        else:
            # Geo without any niche or CPC signal — minimal value
            geo_tier = geo_info.get("geo_tier", 3)
            if geo_info.get("geo_type") == "pure":
                if geo_tier == 1 and market_q <= 2:
                    score = 6
                elif geo_tier == 1:
                    score = 4
                elif geo_tier == 2 and market_q <= 2:
                    score = 3
                else:
                    score = 1
            else:
                score = 1

    # ── Dynamic Sector Value (No Geo, No Niche — pure keyword play) ──
    # If the domain has NO niche AND NO geo, but has strong KPS/CPC data,
    # it belongs to a profitable sector not in our hardcoded niches.
    # Award points based on real market evidence instead of giving 0.
    if score <= 1 and not has_geo:
        kps_tier_local = kps_result.get("kps_tier", "none") if kps_result else "none"
        kps_avg_local = (kps_result.get("best_match") or {}).get("avg_price", 0) if kps_result else 0

        if kps_tier_local in ("ultra", "premium"):
            score = 8
        elif kps_tier_local == "high" or kps_avg_local >= 2000:
            score = 6
        elif kps_tier_local == "mid":
            score = 5
        elif cpc >= 15.0:
            score = 3

    # CPC validates the niche value — heavily dampened to avoid CPC-bias.
    # Only extreme CPC (>$20) adds a small bonus.
    if cpc >= 20.0 and score > 0:
        score = min(15, score + 1)

    # ── COHERENCE GATE: forfeit niche/geo points on broken names ──
    # This is what stops "xqz-insurance-blah" from getting a high geo+niche
    # score just because "insurance" is a tier1 keyword.
    if is_stuffed:
        score = min(score, 2)
    elif is_incoherent:
        score = min(score, 4)
    elif coherence_score < 60 and score > 5:
        score = max(5, int(score * coherence_score / 60))

    return min(15, score)


def score_liquidity(name, domain_type, niche_info, geo_info, extra_data, kps_result=None):
    """
    Axis 6: Liquidity (0-10)
    "How EASY is it to sell this domain?"

    Fast flip: local service domain with high CPC
    Mid-term: good keyword domain in active niche
    Hard sell: brandable with no clear market

    Returns: (score, speed_label)
    """
    score = 0
    cpc = _parse_float(extra_data.get("cpc", 0))
    niche = niche_info.get("niche", "-")
    prof = NICHE_PROFITABILITY.get(niche)

    if domain_type == "local_service":
        # Base liquidity depends on market quality — you can only sell to buyers
        # that actually exist in that geo's domain investment community.
        geo_name  = geo_info.get("geo_name", "") if geo_info else ""
        market_q  = get_geo_market_quality(geo_name)
        # quality 1 = fast flip;  quality 4 = hard to find any buyer
        base_liq  = {1: 9, 2: 7, 3: 5, 4: 3}.get(market_q, 6)
        if prof and prof["resell_ease"] >= 7:
            score = min(10, base_liq + 1)
        elif prof and prof["resell_ease"] >= 5:
            score = base_liq
        elif cpc >= 4.0:
            # Dynamic niche: no NICHE_PROFITABILITY entry but CPC proves market
            score = min(10, base_liq + 1)
        else:
            score = max(1, base_liq - 1)

    elif domain_type == "seo_keyword":
        score = 6
        if cpc >= 8.0:
            score = 9  # High CPC = active market = easy sell
        elif cpc >= 4.0:
            score = 7

    elif domain_type == "global_service":
        score = 5
        if prof and prof["resell_ease"] >= 6:
            score = 7
        elif cpc >= 4.0:
            # Dynamic niche: CPC proves active advertiser market
            score = 7
        elif cpc >= 2.0:
            score = 6

    elif domain_type == "content_media":
        score = 4

    elif domain_type == "brandable":
        # Brandable is the hardest to sell — you need the right buyer
        if name in TIER1_WORDS and len(name) <= 5:
            score = 8  # Premium single words sell themselves
        elif name in TIER1_WORDS and len(name) <= 7:
            score = 6
        elif name in ALL_WORDS:
            score = 4
        elif len(name) <= 5 and _is_clean_name(name):
            # Rescue: Short, highly pronounceable Web3/Startup CVCV names
            score = 6
        elif len(name) <= 6 and _is_clean_name(name):
            score = 4
        else:
            score = 2  # Invented names — very hard sell

    else:
        score = 1

    # Domain age improves liquidity (proven asset) — stronger vintage tiers
    aby = _parse_int(extra_data.get("aby", 0))
    if 1990 <= aby <= 2000:
        score = min(10, score + 3)   # Pre-dot-com bust: genuine web pioneer
    elif aby <= 2003:
        score = min(10, score + 2)   # Early internet era
    elif aby <= 2007:
        score = min(10, score + 1)   # Pre-social-media era

    # KPS: high keyword sales volume = active market = easier to sell
    # RDT is NOT repeated here — it lives in Buyer Pool to prevent double-counting.
    if kps_result:
        tks = kps_result.get("total_keyword_sales", 0)
        if tks >= 100:
            score = min(10, score + 2)
        elif tks >= 30:
            score = min(10, score + 1)

    # Resell speed classification
    if score >= 8:
        speed = "Fast"
    elif score >= 5:
        speed = "Medium"
    else:
        speed = "Slow"

    return min(10, score), speed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   STEP 3: PENALTIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_penalties(name, domain_name, domain_type, clarity_score,
                         extra_data=None, coherence=None, geo_info=None):
    """
    Penalties: things that hurt resale value.
    V5 — UNIVERSAL penalties (was: brandable-only for hyphens/digits).

    A hyphen or digit hurts resale across ALL domain types, not just
    brandables. Previously "car-insurance.com" got full SEO axes despite
    its hyphen because penalties only applied to the brandable scorer.
    """
    if extra_data is None:
        extra_data = {}
    if geo_info is None:
        geo_info = {}
    total = 0
    reasons = []

    # Personal name — hard to sell to non-named person
    if detect_personal_name(domain_name):
        total += PENALTIES["PERSONAL_NAME"]
        reasons.append("Personal name (-10)")

    # Long + unclear — the worst combo
    threshold = PENALTIES["LONG_UNCLEAR_THRESHOLD"]
    if len(name) > threshold and clarity_score < 8:
        total += PENALTIES["LONG_UNCLEAR"]
        reasons.append(f"Long ({len(name)} chars) + unclear (-8)")

    # Hyphen penalty — universal (was only in brandable scorer).
    # One hyphen in a geo+service compound is excused (e.g. "los-angeles-cleaners")
    n_hyphens = name.count('-')
    is_geo_compound = geo_info.get("geo_found", False)
    if n_hyphens >= 2:
        total += PENALTIES.get("MULTI_HYPHEN", -10)
        reasons.append(f"Multiple hyphens (-{abs(PENALTIES.get('MULTI_HYPHEN', -10))})")
    elif n_hyphens == 1 and not is_geo_compound:
        total += PENALTIES.get("HYPHEN", -5)
        reasons.append("Hyphen in non-geo name (-5)")

    # Digit penalty — universal. Skip if the number is a meaningful brand pattern.
    n_digits = sum(1 for c in name if c.isdigit())
    if n_digits >= 3:
        total += PENALTIES.get("MANY_DIGITS", -10)
        reasons.append(f"Many digits (-{abs(PENALTIES.get('MANY_DIGITS', -10))})")
    elif n_digits >= 1 and len(name) > 6:
        total += PENALTIES.get("DIGITS_IN_LONG", -5)
        reasons.append("Digits in long name (-5)")

    # NOTE: coherence structural_penalty is intentionally NOT re-applied here.
    # The 6 scoring axes are already coherence-gated (axis scores are reduced for
    # incoherent/stuffed names). Applying structural_penalty on top would triple-count
    # the same structural flaw (axis reduction + here + decision_engine risk flags).
    # We do surface a warning in reasons so the UI can show what coherence flagged.
    if coherence:
        if coherence.get("is_keyword_stuffed"):
            reasons.append("Keyword stuffing detected (coherence gate)")
        elif coherence.get("is_incoherent"):
            reasons.append("Incoherent keyword structure (coherence gate)")

    return total, reasons


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   STEP 4: REASONING ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_reasoning(domain, domain_type, scores, niche_info, geo_info,
                       extra_data, resell_speed, total, verdict, kps_result=None):
    """
    Generate a human-like explanation of why this domain is valuable or not.
    Written as if a 10-year domain investor is explaining his decision.
    """
    name = domain.split('.')[0].lower()
    niche = niche_info.get("niche", "-")
    geo_name = geo_info.get("geo_name", "")
    cpc = _parse_float(extra_data.get("cpc", 0))
    sv = _parse_int(extra_data.get("sv", 0))
    prof = NICHE_PROFITABILITY.get(niche)

    parts = []

    # ── Domain type context ──
    type_label = DOMAIN_TYPES.get(domain_type, domain_type)

    if domain_type == "local_service":
        parts.append(f"{type_label} domain")
        if geo_name and niche != "-":
            parts.append(f"targeting {niche.lower()} businesses in {geo_name.title()}")
        elif geo_name and kps_result and (kps_result.get("best_match") or {}).get("keyword"):
            kw = kps_result["best_match"]["keyword"]
            parts.append(f"targeting '{kw}'-related businesses in {geo_name.title()}")
        if prof and prof["buyer_density"] >= 7:
            parts.append("— large pool of potential buyers")
        elif cpc >= 4.0:
            parts.append("— active advertiser market indicates strong buyer pool")
        else:
            parts.append("— moderate buyer pool")

    elif domain_type == "seo_keyword":
        parts.append(f"{type_label} domain")
        if niche != "-":
            parts.append(f"in the {niche} vertical")
        elif kps_result and (kps_result.get("best_match") or {}).get("keyword"):
            kw = kps_result["best_match"]["keyword"]
            parts.append(f"anchored by proven keyword '{kw}'")
        if cpc >= 8:
            parts.append(f"with strong advertiser spending (${cpc:.0f} CPC)")
        elif cpc >= 2:
            parts.append(f"with moderate CPC (${cpc:.2f})")

    elif domain_type == "global_service":
        parts.append(f"{type_label} domain")
        if niche != "-":
            parts.append(f"in {niche}")
        elif kps_result and (kps_result.get("best_match") or {}).get("keyword"):
            kw = kps_result["best_match"]["keyword"]
            parts.append(f"in the '{kw}' sector")

    elif domain_type == "brandable":
        parts.append(f"{type_label} domain")
        reg = _parse_int(extra_data.get("reg", 0))
        rdt = _parse_int(extra_data.get("rdt", 0))
        aby = _parse_int(extra_data.get("aby", 0))

        if name in TIER1_WORDS:
            parts.append(f"— '{name}' is a strong, universal English word")
        elif name in ALL_WORDS:
            parts.append(f"— '{name}' is a recognized word with brand potential")
        else:
            compound = try_split_compound(name)
            if compound:
                parts.append(f"— compound of '{compound[0]}' + '{compound[1]}'")
            elif len(name) <= 6:
                parts.append("— short and memorable")

        # Mention strong professional signals
        if reg >= 10 or rdt >= 10 or (1990 <= aby <= 2000):
            parts.append("| 💎 Professional Grade: Strong historical/market footprint (REG/RDT/Age)")

    elif domain_type == "content_media":
        parts.append(f"{type_label} domain")
        if niche != "-":
            parts.append(f"for {niche} content")

    else:
        parts.append("Low-value domain — no clear market positioning")

    # ── KPS (Keyword Power Score) — lead signal ──
    if kps_result is None:
        kps_result = {}
    kps_score = kps_result.get("kps_score", 0)
    kps_tier  = kps_result.get("kps_tier", "none")
    best_m    = kps_result.get("best_match") or {}
    kps_kw    = best_m.get("keyword", "")
    kps_avg   = best_m.get("avg_price", 0)
    kps_cnt   = best_m.get("sale_count", 0)
    kps_mx    = best_m.get("max_price", 0)
    kps_mtype = best_m.get("match_type", "")

    pos_label = {"exact": "exact match", "prefix": "prefix",
                 "suffix": "suffix", "middle": "embedded"}.get(kps_mtype, "")

    if kps_tier in ("ultra", "premium") and kps_kw:
        parts.append(
            f"| 🏆 KPS [{kps_tier.upper()}]: '{kps_kw}' ({pos_label}) — "
            f"avg sale ${kps_avg:,.0f} / {kps_cnt} real txns, ceiling ${kps_mx:,.0f}"
        )
    elif kps_tier == "high" and kps_kw:
        parts.append(
            f"| 💰 KPS [HIGH]: '{kps_kw}' ({pos_label}) — "
            f"avg sale ${kps_avg:,.0f} across {kps_cnt} transactions"
        )
    elif kps_tier == "mid" and kps_kw:
        parts.append(
            f"| KPS [MID]: '{kps_kw}' ({pos_label}) avg ${kps_avg:,.0f}"
        )

    # Compound bonus mention
    if kps_result.get("compound_bonus", 0) > 0:
        cp = kps_result.get("compound_partner")
        if cp:
            parts.append(
                f"| Power compound: +'{cp['keyword']}' "
                f"({cp['match_type']}, avg ${cp['avg_price']:,.0f})"
            )

    # Spam penalty mention
    if kps_result.get("spam_penalty", 0) < 0:
        parts.append("| ⚠️ Keyword stuffing penalty applied")

    # ── CPC as secondary commercial signal ──
    if scores["CommercialIntent"] >= 18:
        parts.append("| High commercial intent confirmed")
    elif cpc >= 4.0:
        parts.append(f"| CPC support signal: ${cpc:.2f}")

    # ── Demand signals ──
    if sv >= 10000:
        parts.append(f"| Search demand: {sv:,}/mo")
    elif sv >= 1000:
        parts.append(f"| Search volume: {sv:,}/mo")

    # ── RDT (related domains) ──
    rdt = _parse_int(extra_data.get("rdt", 0))
    if rdt >= 5:
        parts.append(f"| 🔥 Keyword in {rdt} related domains — exceptional popularity")
    elif rdt >= 2:
        parts.append(f"| ✅ Keyword in {rdt} related domains")
    elif rdt >= 1:
        parts.append("| ✅ Keyword used in related domains")

    # ── Liquidity ──
    if resell_speed == "Fast":
        parts.append("| Quick flip potential")
    elif resell_speed == "Slow":
        parts.append("| Would need patience to sell")

    # ── TLD Impact ──
    tld = tld_for_lookup(domain)
    tld_mult = TLD_MULTIPLIERS.get(tld, 0.4)
    if tld_mult < 1.0:
        parts.append(f"| 📉 TLD Penalty: .{tld} extension reduces market liquidity and value")

    # ── Verdict reasoning ──
    if verdict == "GEM":
        parts.append("→ STRONG BUY — multiple value signals align, high confidence")
    elif verdict == "BUY":
        parts.append("→ Worth acquiring — solid fundamentals for resale")
    elif verdict == "HOLD":
        parts.append("→ Borderline — research further before committing money")
    else:
        parts.append("→ Skip — insufficient market signals for profitable resale")

    return ". ".join(parts)


def generate_target_buyer(domain_type, niche_info, geo_info, kps_result=None):
    """Describe who would buy this domain."""
    niche = niche_info.get("niche", "-")
    geo_name = geo_info.get("geo_name", "")
    kps_kw = (kps_result.get("best_match") or {}).get("keyword", "") if kps_result else ""

    if domain_type == "local_service":
        if geo_name and niche != "-":
            return f"{niche} businesses in {geo_name.title()}"
        elif geo_name and kps_kw:
            return f"'{kps_kw}'-related businesses in {geo_name.title()}"
        elif niche != "-":
            return f"Local {niche.lower()} businesses"
        return "Local service businesses"

    elif domain_type == "seo_keyword":
        if niche != "-":
            return f"{niche} companies, affiliate marketers, SEO agencies"
        elif kps_kw:
            return f"'{kps_kw}' industry businesses, affiliate marketers, SEO agencies"
        return "SEO-focused businesses, affiliate marketers"

    elif domain_type == "global_service":
        if niche != "-":
            return f"{niche} startups and companies"
        elif kps_kw:
            return f"'{kps_kw}' sector startups and companies"
        return "Service-oriented businesses"

    elif domain_type == "brandable":
        return "Startups, rebranding companies, new ventures"

    elif domain_type == "content_media":
        if niche != "-":
            return f"{niche} publishers, bloggers, media companies"
        return "Content creators, publishers, media companies"

    return "Unclear target buyer"


def generate_reasoning_ar(domain, domain_type, scores, niche_info, geo_info,
                          extra_data, resell_speed, total, verdict, kps_result=None):
    """
    Arabic version of the reasoning engine.
    """
    name = domain.split('.')[0].lower()
    niche = niche_info.get("niche", "-")
    geo_name = geo_info.get("geo_name", "")
    cpc = _parse_float(extra_data.get("cpc", 0))
    sv = _parse_int(extra_data.get("sv", 0))
    if kps_result is None:
        kps_result = {}
    
    parts = []

    # 1. نوع النطاق
    type_label = DOMAIN_TYPES_AR.get(domain_type, domain_type)
    if domain_type == "local_service":
        parts.append(f"نطاق {type_label}")
        if geo_name and niche != "-":
            parts.append(f"يستهدف مجال الـ {niche} في مدينة {geo_name}")
        parts.append("مما يوفر قاعدة عملاء محتملين جيدة")
        
    elif domain_type == "seo_keyword":
        parts.append(f"نطاق {type_label}")
        if niche != "-":
            parts.append(f"في تخصص {niche}")
        elif kps_result and (kps_result.get("best_match") or {}).get("keyword"):
            kw = kps_result["best_match"]["keyword"]
            parts.append(f"مُرتكز على كلمة مُثبتة '{kw}'")
        if cpc >= 8:
            parts.append(f"مع تكلفة نقرة قوية (${cpc:.0f} CPC)")
        elif cpc >= 2:
            parts.append(f"مع تكلفة نقرة متوسطة (${cpc:.2f})")
            
    elif domain_type == "brandable":
        parts.append(f"نطاق {type_label}")
        if name in TIER1_WORDS or name in ALL_WORDS:
            parts.append(f"- كلمة '{name}' معروفة ولها إمكانيات تجارية")
        elif len(name) <= 6:
            parts.append("- اسم قصير وسهل التذكر")

    elif domain_type == "content_media":
        parts.append(f"نطاق {type_label}")
        if niche != "-":
            parts.append(f"لمحتوى الـ {niche}")
    else:
        parts.append("نطاق ذو قيمة منخفضة - لا يوجد توجه واضح للسوق")

    # 2. مؤشر قوة الكلمة المفتاحية (KPS)
    kps_score = kps_result.get("kps_score", 0)
    kps_tier  = kps_result.get("kps_tier", "none")
    best_m    = kps_result.get("best_match") or {}
    kps_kw    = best_m.get("keyword", "")
    kps_avg   = best_m.get("avg_price", 0)
    kps_cnt   = best_m.get("sale_count", 0)
    ar_pos    = {"exact": "مطابقة تامة", "prefix": "بادئة", "suffix": "لاحقة", "middle": "مضمّنة"}.get(best_m.get("match_type", ""), "")

    if kps_tier in ("ultra", "premium") and kps_kw:
        parts.append(
            f"| 🏆 KPS [{kps_tier}]: '{kps_kw}' ({ar_pos}) — "
            f"متوسط سعر ${kps_avg:,.0f} في {kps_cnt} صفقة فعلية"
        )
    elif kps_tier == "high" and kps_kw:
        parts.append(f"| 💰 KPS: '{kps_kw}' ({ar_pos}) — متوسط ${kps_avg:,.0f} في {kps_cnt} صفقة")
    elif kps_tier == "mid" and kps_kw:
        parts.append(f"| KPS: '{kps_kw}' ({ar_pos}) متوسط ${kps_avg:,.0f}")

    if kps_result.get("compound_bonus", 0) > 0:
        cp = kps_result.get("compound_partner")
        if cp:
            parts.append(f"| مركّب قوي: +'{cp['keyword']}' (متوسط ${cp['avg_price']:,.0f})")

    if kps_result.get("spam_penalty", 0) < 0:
        parts.append("| ⚠️ خصم: تكديس كلمات مفتاحية")

    # الإشارات التجارية
    if scores["CommercialIntent"] >= 18:
        parts.append("| نية تجارية عالية")

    if sv >= 1000:
        parts.append(f"| حجم بحث {sv:,}/شهر")

    # 3. الأدلة من السوق (Related Domains)
    rdt = _parse_int(extra_data.get("rdt", 0))
    if rdt >= 5:
        parts.append(f"| 🔥 الكلمة مستخدمة في {rdt} نطاقات أخرى - شعبية استثنائية")
    elif rdt >= 1:
        parts.append("| ✅ الكلمة مستخدمة في نطاقات مشابهة - إشارة إيجابية")

    # 4. السيولة وسرعة البيع
    speed_ar = RESELL_SPEED_AR.get(resell_speed, "بطيء")
    if resell_speed == "Fast":
        parts.append(f"| إمكانية بيع سريعة ({speed_ar})")
    else:
        parts.append(f"| سرعة البيع المتوقعة: {speed_ar}")

    # 4b. تأثير امتداد النطاق (TLD)
    tld = tld_for_lookup(domain)
    tld_mult = TLD_MULTIPLIERS.get(tld, 0.4)
    if tld_mult < 1.0:
        parts.append(f"| 📉 خصم الامتداد: امتداد .{tld} يقلل من سيولة وقيمة النطاق")

    # 5. الخلاصة
    if verdict == "GEM":
        parts.append("← شراء مؤكد - مؤشرات القيمة متوافقة وبثقة عالية")
    elif verdict == "BUY":
        parts.append("← يستحق الاقتناء - أساسيات صلبة لإعادة البيع")
    elif verdict == "HOLD":
        parts.append("← منطقة حيادية - يفضل البحث أكثر قبل الاستثمار")
    else:
        parts.append("← تجاهل - لا توجد مؤشرات كافية للربح")

    return " . ".join(parts)


def generate_target_buyer_ar(domain_type, niche_info, geo_info, kps_result=None):
    """Arabic target buyer description."""
    niche = niche_info.get("niche", "-")
    geo_name = geo_info.get("geo_name", "")
    kps_kw = (kps_result.get("best_match") or {}).get("keyword", "") if kps_result else ""

    if domain_type == "local_service":
        if geo_name and niche != "-":
            return f"أصحاب أعمال الـ {niche} في مدينة {geo_name}"
        elif geo_name and kps_kw:
            return f"أصحاب أعمال '{kps_kw}' في مدينة {geo_name}"
        return "أصحاب الأعمال المحلية"

    elif domain_type == "seo_keyword":
        if niche != "-":
            return f"شركات الـ {niche}، المسوقين بالعمولة، وكالات الـ SEO"
        elif kps_kw:
            return f"شركات قطاع '{kps_kw}'، المسوقين بالعمولة، وكالات الـ SEO"
        return "شركات التسويق، المسوقين بالعمولة، وكالات الـ SEO"

    elif domain_type == "global_service":
        if niche != "-":
            return f"الشركات الناشئة في مجال الـ {niche}"
        elif kps_kw:
            return f"الشركات الناشئة في قطاع '{kps_kw}'"
        return "الشركات الناشئة والخدمية"

    elif domain_type == "brandable":
        return "الشركات الناشئة، رواد الأعمال، المشاريع الجديدة"

    elif domain_type == "content_media":
        return "كبار الناشرين، المدونين، شركات الإعلام"

    return "مشتري غير محدد"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   MAIN SCORING FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def score_domain(domain_name, extra_data=None):
    """
    Main scoring function — V4 Market Intelligence.

    Simulates a real investor making a buying decision:
    1. Classify the domain type
    2. Score 6 market axes
    3. Apply penalties
    4. Generate human reasoning
    5. Return structured output
    """
    if extra_data is None:
        extra_data = {}

    parts = domain_name.lower().split('.')
    name = parts[0]
    tld = tld_for_lookup(domain_name)

    # ── Step 1: Detect context ──
    geo_info = detect_geo(name)
    niche_info = detect_niche(domain_name)

    # ── Step 1b: Keyword Power Score (computed once, shared across axes) ──
    kps_result = score_kps(name)

    # ── Step 1c: Coherence Gate (universal — runs before scoring) ──
    # The gate decides which keyword bonuses are legitimate vs. false positives.
    # Stuffed/incoherent names will have their niche/keyword boosts forfeited
    # downstream. This is the central fix for the "law/insurance/health bias".
    from analyzer.coherence_gate import evaluate_coherence
    coherence = evaluate_coherence(domain_name, kps_result=kps_result, geo_info=geo_info)

    # ── Step 2: Classify domain type ──
    domain_type = detect_domain_type(name, niche_info, geo_info, extra_data, kps_result)

    # ── Step 3: Score all 6 axes (coherence-aware) ──
    commercial = score_commercial_intent(name, domain_type, niche_info, extra_data,
                                         kps_result, coherence=coherence)
    demand = score_market_demand(name, domain_type, niche_info, extra_data, kps_result)
    clarity = score_clarity(name, domain_type, niche_info, geo_info, extra_data, kps_result)
    buyers = score_buyer_pool(name, domain_type, niche_info, geo_info, extra_data, kps_result)
    geo_niche = score_geo_niche(name, domain_type, niche_info, geo_info, extra_data,
                                kps_result, coherence=coherence)
    liquidity, resell_speed = score_liquidity(name, domain_type, niche_info, geo_info, extra_data, kps_result)

    # ── Step 4: Penalties (universal hyphen/digit + coherence) ──
    penalties, penalty_reasons = calculate_penalties(
        name, domain_name, domain_type, clarity, extra_data,
        coherence=coherence, geo_info=geo_info,
    )

    # ── Step 5a: Evidence Bonus ──
    # Age is already scored inside score_liquidity (its axis home).
    # No standalone age bonus here to avoid double-counting.
    evidence_bonus = 0

    # ── Step 5c: Ultra-Premium Short Domain Bonus ──
    # 1-4 letter/number domains are universally liquid and valuable regardless of meaning.
    is_pure_alpha = name.isalpha()
    is_pure_num = name.isdigit()
    is_mixed_alnum = name.isalnum() and not is_pure_alpha and not is_pure_num
    if len(name) <= 4 and name.isalnum():
        short_bonus = 0
        if is_pure_alpha:
            if len(name) <= 2: short_bonus = 85
            elif len(name) == 3: short_bonus = 50
            elif len(name) == 4: short_bonus = 15
        elif is_pure_num:
            if len(name) <= 2: short_bonus = 85
            elif len(name) == 3: short_bonus = 60
            elif len(name) == 4: short_bonus = 25
        elif is_mixed_alnum:
            # Mixed short names (ai2, x5, g7) — real but lower value than pure forms
            if len(name) == 2: short_bonus = 40
            elif len(name) == 3: short_bonus = 20
            elif len(name) == 4: short_bonus = 8
        evidence_bonus += short_bonus

    # ── Step 5b: KPS Evidence Bonus ──
    # Proven high-value keywords elevate the total directly, correcting for axes
    # that lack signals (no niche/geo) on single-word or pure keyword domains.
    kps_evidence_bonus = 0
    _kps_s    = kps_result.get("kps_score", 0)
    _kps_tier = kps_result.get("kps_tier", "none")
    _kps_best = kps_result.get("best_match") or {}
    _kps_mtype = _kps_best.get("match_type", "")
    _kps_avg   = _kps_best.get("avg_price", 0)

    if _kps_mtype == "exact":
        # Single-word domain matching a proven keyword — strongest possible signal
        # Caps reduced to prevent too many domains hitting the 100 ceiling
        if _kps_tier == "ultra":
            if _kps_avg >= 500_000:  kps_evidence_bonus = 12   # ai, voice, chat
            elif _kps_avg >= 100_000: kps_evidence_bonus = 10  # casino, jobs, mortgage
            elif _kps_avg >= 50_000:  kps_evidence_bonus = 7   # poker, invest
            else:                     kps_evidence_bonus = 5   # strong ultra tier
        elif _kps_tier == "premium":
            kps_evidence_bonus = 3
        elif _kps_tier == "high":
            kps_evidence_bonus = 1
        elif _kps_tier == "mid" and _kps_avg >= 50_000:
            # Mid-tier KPS but very high avg sale price — still strong evidence
            kps_evidence_bonus = 5

    elif _kps_mtype in ("prefix", "suffix"):
        # Keyword-anchored compound — solid secondary evidence
        if _kps_tier == "ultra":
            kps_evidence_bonus = 6
        elif _kps_tier == "premium":
            kps_evidence_bonus = 3
        elif _kps_tier == "high":
            kps_evidence_bonus = 1
        elif _kps_tier == "mid" and _kps_avg >= 10_000:
            kps_evidence_bonus = 1

    # Middle-embedded keywords get no direct bonus (too weak positionally)

    # ── Tier1 word floor bonus (short premium dictionary words with no KPS entry) ──
    # Real single-word domains like "spark", "bloom", "cloud" are inherently valuable.
    # When KPS has no sale data for them (kps_evidence_bonus == 0), give a floor boost
    # so they are not invisibly penalised for being absent from the CSV.
    if kps_evidence_bonus == 0 and len(name) <= 6 and name in TIER1_WORDS:
        kps_evidence_bonus = 3  # recognises the word is premium even without CSV data

    # ── Cap evidence bonus by confidence ──
    kps_confidence = kps_result.get("kps_confidence", 0)
    kps_evidence_bonus = round(kps_evidence_bonus * kps_confidence)  # round(), not int()

    # ── Cap evidence bonus by coherence ──
    # A keyword sale-history bonus is meaningless on an unsellable name.
    # "xqz-insurance-blah" has the same retail data as "insurance.com" but
    # the bonus is wasted on the broken structure. Gate the bonus accordingly.
    _coh_score = coherence.get("coherence_score", 100)
    if coherence.get("is_keyword_stuffed"):
        kps_evidence_bonus = 0
    elif coherence.get("is_incoherent"):
        kps_evidence_bonus = round(kps_evidence_bonus * 0.3)
    elif _coh_score < 60:
        kps_evidence_bonus = round(kps_evidence_bonus * _coh_score / 60)

    # ── Step 6: Compute total score ──
    # Apply TLD multiplier ONLY to the 6 positive axes — NOT to penalties or bonuses.
    # Applying it to the full sum (including negatives) would flip the sign of penalties:
    # a -18 penalty on .xyz (mult=0.3) becomes only -5.4, rewarding bad domains.
    axes_sum = commercial + demand + clarity + buyers + geo_niche + liquidity
    tld_mult = TLD_MULTIPLIERS.get(tld, 0.30)
    # Blended TLD multiplier: half of the axes score is TLD-independent (content quality),
    # half is penalized for non-.com. A strong keyword domain on .ai still reflects its
    # intrinsic value; the TLD discount is real but no longer catastrophic.
    tld_adjusted_axes = axes_sum * (0.5 + 0.5 * tld_mult)
    raw_total = tld_adjusted_axes + penalties + evidence_bonus + kps_evidence_bonus

    # ── Diminishing returns curve (prevents ceiling clustering) ──
    # Scores below 70 are unchanged (linear region).
    # Scores 70-100 are compressed concavely so mid-GEM domains spread out
    # rather than bunching near 100. Formula: 30 * (excess/30)**1.5 maps
    # 0→0, 30→30 with sublinear growth (e.g. excess=10 → 6, excess=20 → 16).
    if raw_total > 70:
        excess = max(0.0, raw_total - 70)
        # Exponent 1.25 (was 1.5): less aggressive compression so strong domains
        # can still reach the 85-100 range instead of clustering just above 70.
        compressed_excess = 30.0 * (min(excess, 30.0) / 30.0) ** 1.25
        raw_total = 70 + compressed_excess

    total = max(0, min(100, round(raw_total)))  # Hard cap at 100

    # ── Step 7: Verdict ──
    if total >= SCORE_THRESHOLDS["GEM"]:
        verdict = "GEM"
    elif total >= SCORE_THRESHOLDS["BUY"]:
        verdict = "BUY"
    elif total >= SCORE_THRESHOLDS["HOLD"]:
        verdict = "HOLD"
    else:
        verdict = "PASS"

    # ── Step 8: Build scores dict ──
    scores = {
        "CommercialIntent": commercial,
        "MarketDemand": demand,
        "Clarity": clarity,
        "BuyerPool": buyers,
        "GeoNiche": geo_niche,
        "Liquidity": liquidity,
    }

    # ── Step 9: Reasoning ──
    reasoning = generate_reasoning(
        domain_name, domain_type, scores, niche_info, geo_info,
        extra_data, resell_speed, total, verdict, kps_result
    )
    target_buyer = generate_target_buyer(domain_type, niche_info, geo_info, kps_result)

    # ── Step 10: Arabic ──
    reasoning_ar = generate_reasoning_ar(
        domain_name, domain_type, scores, niche_info, geo_info,
        extra_data, resell_speed, total, verdict, kps_result
    )
    target_buyer_ar = generate_target_buyer_ar(domain_type, niche_info, geo_info, kps_result)

    # ── Final output ──
    best_kps_match = kps_result.get("best_match") or {}
    return {
        "TotalScore": total,
        "Verdict": verdict,
        "DomainType": domain_type,
        "DomainTypeLabel": DOMAIN_TYPES.get(domain_type, domain_type),
        "TargetBuyer": target_buyer,
        "TargetBuyerAR": target_buyer_ar,
        "ResellSpeed": resell_speed,
        "Reasoning": reasoning,
        "ReasoningAR": reasoning_ar,
        # Sub-scores
        "CommercialIntent": commercial,
        "MarketDemand": demand,
        "Clarity": clarity,
        "BuyerPool": buyers,
        "GeoNiche": geo_niche,
        "Liquidity": liquidity,
        # Keyword Power Score
        "KPSEvidenceBonus": kps_evidence_bonus,
        "KPSConfidence": kps_result.get("kps_confidence", 0.0),
        "KeywordPowerScore": kps_result.get("kps_score", 0),
        "KPSTier": kps_result.get("kps_tier", "none"),
        "KPSKeyword": best_kps_match.get("keyword", ""),
        "KPSMatchType": best_kps_match.get("match_type", ""),
        "KPSAvgPrice": best_kps_match.get("avg_price", 0),
        "KPSSaleCount": best_kps_match.get("sale_count", 0),
        "KPSMaxPrice": best_kps_match.get("max_price", 0),
        "KPSReasoning": kps_result.get("kps_reasoning", ""),
        "KPSReasoningAR": kps_result.get("kps_reasoning_ar", ""),
        "KPSAllMatches": kps_result.get("all_matches", []),
        "KPSKeywordsMatched": kps_result.get("kps_keywords_matched", []),
        "_kps_coverage": kps_result.get("coverage_ratio", 0.0),
        # Context
        "NicheName": niche_info.get("niche", "-"),
        "NicheTier": niche_info.get("niche_tier", "none"),
        "GeoName": geo_info.get("geo_name", ""),
        "IsGeo": geo_info["geo_found"],
        # Penalties
        "Penalties": penalties,
        "PenaltyReasons": " | ".join(penalty_reasons) if penalty_reasons else "",
        # Coherence Gate output (V5)
        "CoherenceScore": coherence.get("coherence_score", 100),
        "CoherencePasses": coherence.get("passes", True),
        "RejectionReasons": coherence.get("rejection_codes", []),
        "IsKeywordStuffed": coherence.get("is_keyword_stuffed", False),
        "IsIncoherent": coherence.get("is_incoherent", False),
        # Internal: full coherence dict passed to decision_engine to avoid re-evaluation
        "_CoherenceGate": coherence,
    }
