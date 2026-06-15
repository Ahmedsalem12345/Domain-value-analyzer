"""
Domain Processing Pipeline V4 — Market Intelligence + Decision Engine.

Flow:
  domain → clean → filters → market_scorer (6 axes) → name_fit
  → decision_engine → pricing → brandable → final output
"""
import logging
from config import PENALTIES, tld_for_lookup
from analyzer.filters import trademark_filter, hard_filter, smart_readability_filter
from analyzer.market_scorer import score_domain
from analyzer.enrichments import detect_spam_domain, estimate_historical_price
from analyzer.brandable_scorer import score_brandable
from analyzer.name_fit import score_name_fit
from analyzer.decision_engine import compute_decision

try:
    from analyzer import ml_valuation
    _ML_AVAILABLE = True
except Exception:  # pragma: no cover - optional ML dependency
    _ML_AVAILABLE = False
    ml_valuation = None

logger = logging.getLogger("analyzer.pipeline")


def process_domain(domain: str, extra_data: dict = None) -> dict:
    """Process a single domain through the full pipeline."""
    if not domain or not isinstance(domain, str):
        return {"Domain": domain or "", "Verdict": "EXCLUDED", "ExcludeReason": "invalid"}
    domain = domain.strip().lower()
    if not domain or '.' not in domain:
        return {"Domain": domain, "Verdict": "EXCLUDED", "ExcludeReason": "invalid"}
    if extra_data is None:
        extra_data = {}

    # ── Stage 1: Hard Filters (immediate exclusion flags) ──
    tm_hit = trademark_filter(domain)
    hard_hit = hard_filter(domain)
    readability = smart_readability_filter(domain)
    is_gibberish = readability["is_gibberish"]

    # ── Stage 2: Market Scoring (6 axes + KPS) ──
    scores = score_domain(domain, extra_data=extra_data)
    total = scores["TotalScore"]

    # ── Stage 2b: ML Valuation (optional, trained from historical sales) ──
    ml_pred = None
    if _ML_AVAILABLE:
        try:
            ml_pred = ml_valuation.predict(domain)
            scores.update(ml_pred)
            scores["Reasoning"] += (
                f". ML est. price: ${ml_pred['ml_price_estimate']:,.0f}"
                f" (grade {ml_pred['ml_grade']})"
            )
        except Exception as e:
            logger.error("ML valuation failed for %s: %s", domain, e, exc_info=True)

    # ── Stage 3: Spam Detection ──
    spam_check = detect_spam_domain(domain)
    spam_penalty = 0
    if spam_check["is_spammy"]:
        spam_penalty = PENALTIES.get("SPAM_HISTORY", -15)
        total = max(0, total + spam_penalty)
        scores["TotalScore"] = total
        old_reasons = scores.get("PenaltyReasons", "")
        spam_reason = f"Spam history ({spam_check['spam_score']})"
        scores["PenaltyReasons"] = f"{old_reasons} | {spam_reason}".strip(" |")
        scores["Penalties"] = scores.get("Penalties", 0) + spam_penalty

    # ── Stage 4: Price Estimation (KPS-anchored) ──
    _kps_mini = None
    if not spam_check["is_spammy"] and scores.get("KPSKeyword"):
        _kps_mini = {
            "kps_tier": scores.get("KPSTier", "none"),
            "kps_confidence": scores.get("KPSConfidence", 0.0),
            "best_match": {
                "keyword":    scores.get("KPSKeyword", ""),
                "match_type": scores.get("KPSMatchType", ""),
                "avg_price":  scores.get("KPSAvgPrice", 0),
                "sale_count": scores.get("KPSSaleCount", 0),
                "max_price":  scores.get("KPSMaxPrice", 0),
            },
        }
    price_est = estimate_historical_price(
        domain, total,
        domain_type=scores.get("DomainType", "low_value"),
        niche_name=scores.get("NicheName", "-"),
        kps_result=_kps_mini,
    )
    scores["PriceLow"]  = price_est["low_estimate"]
    scores["PriceHigh"] = price_est["high_estimate"]
    scores["KPSAnchored"] = price_est.get("kps_anchored", False)

    # Append price + KPS anchor note to reasoning
    if price_est["low_estimate"] > 0:
        anchor_note = " (KPS-anchored)" if price_est.get("kps_anchored") else ""
        scores["Reasoning"] += (
            f". Est. value{anchor_note}: "
            f"${price_est['low_estimate']:,}–${price_est['high_estimate']:,}"
        )
        anchor_note_ar = " (مرسّخة بالبيانات)" if price_est.get("kps_anchored") else ""
        scores["ReasoningAR"] = scores.get("ReasoningAR", "") + (
            f" . القيمة التقديرية{anchor_note_ar}: "
            f"${price_est['low_estimate']:,}–${price_est['high_estimate']:,}"
        )

    # ── Stage 5: Brandable Engine ──
    # Always score brandability. Keyword-rich domains can still be brand assets,
    # and hiding that signal makes the all/GEM views miss good names.
    name = domain.split('.')[0].lower()
    domain_type = scores.get("DomainType", "low_value")
    brand = score_brandable(domain, extra_data=extra_data)
    
    scores["BrandableScore"] = brand["BrandableScore"]
    scores["IsBrandable"]    = brand["IsBrandable"]
    scores["BrandAxes"]      = brand["BrandAxes"]
    scores["BrandReasoning"] = brand["BrandReasoning"]

    # ── Stage 6: Name Fit Score ──
    tld = tld_for_lookup(domain)
    # Build kps_result from scores for name_fit
    kps_for_nf = {
        "kps_score": scores.get("KeywordPowerScore", 0),
        "kps_tier": scores.get("KPSTier", "none"),
        "coverage_ratio": scores.get("_kps_coverage", 0.0),
        "kps_confidence": scores.get("KPSConfidence", 0.0),
    }
    name_fit = score_name_fit(name, tld, kps_for_nf, domain_type)
    scores["NameFitScore"] = name_fit["name_fit_score"]

    # ── Stage 7: Decision Engine ──
    # Build full kps_result from scores
    kps_full = {
        "kps_score": scores.get("KeywordPowerScore", 0),
        "kps_tier": scores.get("KPSTier", "none"),
        "kps_confidence": scores.get("KPSConfidence", 0.0),
        "coverage_ratio": scores.get("_kps_coverage", 0.0),
        "best_match": {
            "keyword": scores.get("KPSKeyword", ""),
            "match_type": scores.get("KPSMatchType", ""),
            "avg_price": scores.get("KPSAvgPrice", 0),
            "sale_count": scores.get("KPSSaleCount", 0),
            "max_price": scores.get("KPSMaxPrice", 0),
        },
    }
    geo_info = {
        "geo_found": scores.get("IsGeo", False),
        "geo_name": scores.get("GeoName", ""),
    }
    niche_info = {
        "niche": scores.get("NicheName", "-"),
        "niche_tier": scores.get("NicheTier", "none"),
    }
    
    decision = compute_decision(
        domain, total, scores, kps_full, geo_info, niche_info,
        extra_data, name_fit, brand, price_est, domain_type,
        coherence=scores.get("_CoherenceGate") or {},
        ml_pred=ml_pred,
    )
    
    # Apply decision verdict as the final verdict
    scores["Verdict"] = decision["DecisionVerdict"]

    # Fix #1: Sync TotalScore with OpportunityScore so the two numbers
    # never contradict each other on the UI (e.g. TotalScore=82 / Verdict=HOLD).
    scores["TotalScore"] = decision["OpportunityScore"]

    # Add all decision fields to scores
    for key in ("OpportunityScore", "SignalScore", "SellabilityScore",
                "RiskScore", "RiskFlags", "DecisionVerdict", "DecisionReason",
                "TopSignals", "TopRisks", "ManualResearchRequired",
                "DataQualityScore", "KeywordMarketValue", "BrandSellabilityScore",
                "PriceConfidence", "PriceWarnings", "SellThroughProbability",
                "MaxAcquisitionPrice", "IdealAcquisitionPrice", "OverpricedWarning",
                "BuyerPersona", "BuyerClarity", "BuyerCountEstimate",
                "OutboundDifficulty", "RankingCategory",
                "CoherenceScore", "CoherencePasses", "RejectionReasons"):
        scores[key] = decision.get(key)

    # Persist ML prediction fields for DB / UI (if available)
    if ml_pred:
        scores.setdefault("MLPriceEstimate", ml_pred.get("ml_price_estimate", 0))
        scores.setdefault("MLGrade", ml_pred.get("ml_grade", "PASS"))
        scores.setdefault("MLInvestmentScore", ml_pred.get("ml_investment_score", 0.0))
        scores.setdefault("MLGradeProba", ml_pred.get("ml_grade_proba", {}))

    # ── Override for Hard Exclusions ──
    # They are scored normally so the user can see what they would have scored,
    # but we zero the total and force a PASS verdict.
    if tm_hit or hard_hit or is_gibberish:
        scores["Verdict"] = "PASS"
        scores["TotalScore"] = 0
        scores["OpportunityScore"] = 0
        scores["SignalScore"] = 0
        scores["SellabilityScore"] = 0
        scores["RiskScore"] = 100
        # Zero all 6 scoring axes so the UI doesn't mislead the user
        for axis in ("CommercialIntent", "MarketDemand", "Clarity",
                     "BuyerPool", "GeoNiche", "Liquidity"):
            scores[axis] = 0
        if tm_hit:
            scores["ExcludeReason"] = "trademark"
            scores["RiskFlags"].append("trademark_hazard")
            if "TopRisks" in decision: decision["TopRisks"].insert(0, "Trademark infringement risk")
        elif hard_hit:
            scores["ExcludeReason"] = "hard"
            scores["RiskFlags"].append("hard_filter_block")
            if "TopRisks" in decision: decision["TopRisks"].insert(0, "Blocked by hard filter")
        elif is_gibberish:
            scores["ExcludeReason"] = "gibberish"
            scores["RiskFlags"].append("gibberish")
            if "TopRisks" in decision: decision["TopRisks"].insert(0, "Unreadable/Gibberish name")

    # ── Final Reasoning Sync ──
    # Ensure that crucial decision notes (like GEM downgrades) are visible in the main reasoning text.
    # Save originals BEFORE prepending dec_reason so phrase replacement below
    # searches the correct part of the string (the market_scorer verdict phrase).
    original_reasoning = scores.get("Reasoning", "")
    original_reasoning_ar = scores.get("ReasoningAR", "")

    dec_reason = decision.get("DecisionReason")
    if dec_reason:
        scores["Reasoning"] = f"{dec_reason}. {original_reasoning}"
        ar_dec = dec_reason.replace("Downgraded from GEM", "تم تخفيض التصنيف من جوهرة")
        scores["ReasoningAR"] = f"{ar_dec}. {original_reasoning_ar}"

    # Replace the verdict phrase baked into reasoning by market_scorer
    # (which ran before decision_engine) with the phrase matching the FINAL verdict.
    _EN_PHRASES = {
        "GEM":  "→ STRONG BUY — multiple value signals align, high confidence",
        "BUY":  "→ Worth acquiring — solid fundamentals for resale",
        "HOLD": "→ Borderline — research further before committing money",
        "PASS": "→ Skip — insufficient market signals for profitable resale",
    }
    _AR_PHRASES = {
        "GEM":  "← شراء مؤكد - مؤشرات القيمة متوافقة وبثقة عالية",
        "BUY":  "← يستحق الاقتناء - أساسيات صلبة لإعادة البيع",
        "HOLD": "← منطقة حيادية - يفضل البحث أكثر قبل الاستثمار",
        "PASS": "← تجاهل - لا توجد مؤشرات كافية للربح",
    }
    final_v = scores["Verdict"]
    # Search in original_reasoning (before dec_reason was prepended) to avoid
    # matching a phrase that might accidentally appear inside dec_reason text.
    for phrase in _EN_PHRASES.values():
        if phrase in original_reasoning:
            scores["Reasoning"] = scores["Reasoning"].replace(phrase, _EN_PHRASES[final_v], 1)
            break
    for phrase in _AR_PHRASES.values():
        if phrase in original_reasoning_ar:
            scores["ReasoningAR"] = scores["ReasoningAR"].replace(phrase, _AR_PHRASES[final_v], 1)
            break

    scores["Domain"] = domain
    scores.pop("_CoherenceGate", None)  # internal field, not part of public result

    logger.debug(
        f"{domain} → {scores['Verdict']} (total={total}, opp={decision['OpportunityScore']}) "
        f"[{domain_type}] risks={decision['RiskFlags']}"
    )
    return scores
