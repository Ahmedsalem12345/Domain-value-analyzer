"""
Decision Engine V1 — Multi-signal investment decision.

Replaces the simple TotalScore threshold system with a proper
investment decision framework that considers:
  - Signal strength (what supports the domain's value)
  - Sellability (can you actually find a buyer)
  - Risk factors (what could go wrong)
  - Data quality (how confident are we in the analysis)

OpportunityScore = SignalScore*0.35 + SellabilityScore*0.30
                 + LiquidityScore*0.20 + PriceConfidence*0.10
                 + StrategicBonus*0.05 - RiskPenalty
"""
import re
import logging
from config import TLD_MULTIPLIERS, tld_for_lookup
from analyzer.coherence_gate import evaluate_coherence
from analyzer.word_data import get_geo_market_quality, TIER1_WORDS

logger = logging.getLogger("analyzer.decision")

# NOTE: HOT_SERVICE_NICHES removed in V5. The previous engine special-cased
# "Insurance/Legal" and "Real Estate" with extra signal floors; this created
# a systemic bias where any name containing those keywords got promoted while
# names from other industries (with equal or better KPS evidence) were ignored.
# The new engine treats all industries identically — value comes from evidence
# (KPS, REG, RDT, CPC, name_fit), NOT from category labels.


def compute_decision(domain: str, total_score: int, scores: dict,
                     kps_result: dict, geo_info: dict, niche_info: dict,
                     extra_data: dict, name_fit: dict,
                     brand_result: dict, price_result: dict,
                     domain_type: str,
                     coherence: dict = None,
                     ml_pred: dict = None) -> dict:
    """
    Multi-signal investment decision engine.
    
    Returns a rich decision dict with:
        OpportunityScore, SignalScore, SellabilityScore, RiskScore,
        DecisionVerdict, DecisionReason, RiskFlags, TopSignals,
        TopRisks, ManualResearchRequired, DataQualityScore,
        SellThroughProbability, MaxAcquisitionPrice, IdealAcquisitionPrice,
        PriceConfidence, PriceWarnings, BuyerPersona, BuyerClarity,
        RankingCategory, BrandSellabilityScore, NameFitScore,
        KeywordMarketValue
    """
    name = domain.split('.')[0].lower()
    tld = tld_for_lookup(domain)
    tld_mult = TLD_MULTIPLIERS.get(tld, 0.30)
    kps_result = kps_result or {}
    extra_data = extra_data or {}
    name_fit = name_fit or {}
    brand_result = brand_result or {}
    price_result = price_result or {}
    ml_pred = ml_pred or {}
    niche = niche_info.get("niche", "-")
    niche_tier = niche_info.get("niche_tier", "none")
    
    # ── Helper parsers ──
    def _pi(k, d=0):
        try: return int(float(str(extra_data.get(k, d)).replace(',','').strip()))
        except (ValueError, TypeError): return d
    
    reg = _pi("reg")
    rdt = _pi("rdt")
    aby = _pi("aby")
    
    kps_score = kps_result.get("kps_score", 0)
    kps_tier = kps_result.get("kps_tier", "none")
    kps_conf = kps_result.get("kps_confidence", 0.0)
    kps_coverage = kps_result.get("coverage_ratio", 0.0)
    best_match = kps_result.get("best_match") or {}
    kps_match_type = best_match.get("match_type", "")
    kps_avg = best_match.get("avg_price", 0)
    kps_cnt = best_match.get("sale_count", 0)
    
    name_fit_score = name_fit.get("name_fit_score", 50)
    brand_score = brand_result.get("BrandableScore", 0)
    
    risk_flags = []
    top_signals = []
    top_risks = []
    price_warnings = []
    
    geo_name = geo_info.get("geo_name", "")
    geo_market_q = get_geo_market_quality(geo_name) if geo_name else 3
    
    # ━━━━━━━━━━━━ 0. COHERENCE GATE (universal — runs before scoring) ━━━━━━━━━━━━
    # Use pre-computed coherence from market_scorer when available to avoid
    # evaluating the same domain twice. {} is treated as "not evaluated yet".
    if not coherence:
        coherence = evaluate_coherence(domain, kps_result=kps_result, geo_info=geo_info)
    coherence_score = coherence["coherence_score"]
    coherence_passes = coherence["passes"]
    rejection_codes = list(coherence["rejection_codes"])

    # ━━━━━━━━━━━━ 1. DATA QUALITY SCORE ━━━━━━━━━━━━
    dq = _compute_data_quality(reg, rdt, aby, kps_score, kps_match_type,
                               kps_cnt, kps_conf, tld_mult, name_fit_score)

    # ━━━━━━━━━━━━ 2. SIGNAL SCORE (0-100) ━━━━━━━━━━━━
    signal = 0
    # KPS signal (strongest)
    if kps_tier == "ultra":
        signal += 35
        top_signals.append(f"Ultra KPS keyword '{best_match.get('keyword','')}'")
    elif kps_tier == "premium":
        signal += 28
        top_signals.append(f"Premium KPS keyword")
    elif kps_tier == "high":
        signal += 20
    elif kps_tier == "mid":
        signal += 12
    
    # ── Niche signal — DATA-DRIVEN, NOT TIER-DRIVEN ──
    # The previous engine hardcoded a tier hierarchy (Insurance/Legal=12,
    # Finance=12, Health=10, ...) which biased the entire pipeline toward a
    # narrow set of "premium" keywords. The rebalanced version only awards
    # niche signal when there is REAL evidence: KPS sales data, CPC, REG,
    # or RDT. A new sector (e.g. "vegan-supplements") with strong KPS
    # evidence now scores identically to "Insurance/Legal" with the same
    # evidence — and "Insurance/Legal" with NO evidence scores zero.
    niche_signal = 0
    niche_signal_source = None

    # Primary path: KPS-proven value (works for ANY industry)
    if kps_tier == "ultra":
        niche_signal = 10
        niche_signal_source = "kps_ultra"
    elif kps_tier == "premium":
        niche_signal = 8
        niche_signal_source = "kps_premium"
    elif kps_tier == "high":
        niche_signal = 6
        niche_signal_source = "kps_high"
    elif kps_tier == "mid":
        niche_signal = 4
        niche_signal_source = "kps_mid"

    # Secondary path: CPC validates advertiser demand even without KPS
    cpc_val = 0.0
    try: cpc_val = float(extra_data.get("cpc", 0) or 0)
    except (ValueError, TypeError): cpc_val = 0.0
    if not niche_signal and cpc_val >= 20.0:
        niche_signal = 10
        niche_signal_source = "cpc_ultra"
    elif not niche_signal and cpc_val >= 15.0:
        niche_signal = 8
        niche_signal_source = "cpc_high"
    elif not niche_signal and cpc_val >= 8.0:
        niche_signal = 5
        niche_signal_source = "cpc_mid"
    elif not niche_signal and cpc_val >= 4.0:
        niche_signal = 2
        niche_signal_source = "cpc_low"

    # Hardcoded niche tier ONLY adds a small ceiling lift, never a floor.
    # This preserves a small cap of recognition for known categories without
    # making them the only path to a high score.
    if niche_tier == "tier1" and niche_signal:
        niche_signal = min(niche_signal + 1, 10)
    elif niche_tier == "tier2" and niche_signal:
        niche_signal = min(niche_signal + 1, 9)

    # ── COHERENCE GATE: keyword bonuses are forfeit on incoherent names ──
    # This is the centerpiece of the rebalancing. A domain like
    # "xqz-insurance-blah.net" gets ZERO niche signal regardless of how
    # much "insurance" data exists, because the name itself is unsellable.
    if not coherence_passes:
        # is_keyword_stuffed always implies not coherence_passes, so zero it here
        if coherence.get("is_keyword_stuffed"):
            niche_signal = 0
        else:
            niche_signal = min(niche_signal, 2)
    elif coherence.get("is_incoherent"):
        niche_signal = min(niche_signal, 3)
    elif coherence_score < 60 and niche_signal > 0:
        # graceful degradation
        niche_signal = max(0, int(niche_signal * coherence_score / 60))

    # Match-type discount — middle/no-match keywords don't deserve full credit
    if kps_match_type == "middle":
        niche_signal = min(niche_signal, 3)
    elif kps_match_type not in ("exact", "prefix", "suffix") and not (niche_signal_source and niche_signal_source.startswith("cpc")):
        niche_signal = min(niche_signal, 2)

    if niche_signal:
        signal += niche_signal
        if niche_signal_source and niche_signal >= 8:
            top_signals.append(f"Strong market evidence ({niche_signal_source})")
        elif niche != "-":
            top_signals.append(f"{niche} niche signal")
        elif niche_signal_source:
            top_signals.append(f"Dynamic sector signal ({niche_signal_source})")
    
    # Market data signals
    if reg >= 10: signal += 10
    elif reg >= 5: signal += 6
    elif reg >= 2: signal += 3

    # RDT tiered scoring — logarithmic scale rewards genuinely popular keywords
    if rdt >= 100:
        signal += 20
        top_signals.append(f"Exceptional RDT ({rdt} root domains)")
    elif rdt >= 50:
        signal += 16
        top_signals.append(f"Very high RDT ({rdt})")
    elif rdt >= 20:
        signal += 12
    elif rdt >= 10:
        signal += 8
    elif rdt >= 5:
        signal += 5
    elif rdt >= 2:
        signal += 3

    # Vintage bonus — pre-2004 domains have proven multi-decade staying power
    if 0 < aby <= 2003:
        signal += 5
        top_signals.append(f"Vintage domain ({aby})")
    elif 0 < aby <= 2007:
        signal += 3
    elif 0 < aby <= 2010:
        signal += 1

    # Search volume — independent demand evidence beyond CPC/KPS
    sv_val = 0
    try: sv_val = int(float(str(extra_data.get("sv", 0) or 0).replace(',', '')))
    except (ValueError, TypeError): sv_val = 0
    if sv_val >= 1_000_000:
        signal += 8
        top_signals.append(f"Massive search volume ({sv_val:,}/mo)")
    elif sv_val >= 100_000:
        signal += 5
        top_signals.append(f"High search volume ({sv_val:,}/mo)")
    elif sv_val >= 10_000:
        signal += 3
    elif sv_val >= 1_000:
        signal += 1

    # Commercial intent
    ci = scores.get("CommercialIntent", 0)
    if ci >= 20: signal += 10
    elif ci >= 15: signal += 6
    elif ci >= 10: signal += 3

    # TLD bonus
    if tld_mult >= 0.95: signal += 10
    elif tld_mult >= 0.75: signal += 5

    # ML sales-data signal (optional — only when a trained model exists)
    ml_score = ml_pred.get("ml_investment_score", scores.get("ml_investment_score", 0))
    ml_grade = ml_pred.get("ml_grade", scores.get("ml_grade", "PASS"))
    ml_price = ml_pred.get("ml_price_estimate", scores.get("ml_price_estimate", 0))

    # Strong ML signal boosts signal meaningfully; weak/conflicting signal
    # does not penalise — it is used as supporting evidence only.
    if ml_score >= 0.7:
        signal += int(18 * ml_score)
        top_signals.append(f"ML model highly confident in comparable sales ({ml_score:.0%})")
    elif ml_score >= 0.4:
        signal += int(12 * ml_score)
        top_signals.append(f"ML model sees strong comparable sales ({ml_score:.0%})")
    elif ml_score >= 0.2:
        signal += int(6 * ml_score)
        top_signals.append(f"ML model supports value ({ml_score:.0%})")

    # Price-level confirmation: high ML price estimate reinforces signal
    if ml_price >= 50_000:
        signal += 5
        top_signals.append("ML estimates premium resale value ($50k+)")
    elif ml_price >= 10_000:
        signal += 3

    signal = min(100, signal)

    # ━━━━━━━━━━━━ 3. SELLABILITY SCORE (0-100) ━━━━━━━━━━━━
    sell = 0
    # Name quality
    sell += int(name_fit_score * 0.4)
    
    # Buyer pool
    bp = scores.get("BuyerPool", 0)
    sell += int(bp * 100 / 15 * 0.3)
    
    # Clarity
    cl = scores.get("Clarity", 0)
    sell += int(cl * 100 / 15 * 0.2)
    
    # Brand value as a SELLABILITY OVERLAY only — capped to prevent the
    # previous "brandable lane to GEM" bias. The boost here adds resale
    # appeal but does NOT independently push a domain into GEM territory.
    if brand_score >= 80 and name_fit_score >= 75 and domain_type != "local_service":
        sell += 10
        top_signals.append("Excellent brandable name")
    elif brand_score >= 60 and name_fit_score >= 65 and domain_type != "local_service":
        sell += 6

    sell = min(100, sell)
    
    # ━━━━━━━━━━━━ 4. RISK ASSESSMENT ━━━━━━━━━━━━
    risk_penalty = 0
    
    # Geo risk
    if domain_type == "local_service":
        if geo_market_q == 4:
            risk_penalty += 25
            risk_flags.append("weak_geo_market")
            top_risks.append(f"Weak geo market ({geo_name})")
        elif geo_market_q == 3:
            risk_penalty += 12
            risk_flags.append("emerging_geo_market")
            top_risks.append(f"Emerging geo market ({geo_name})")
    
    # Name fit risk
    if name_fit_score < 35:
        risk_penalty += 15
        risk_flags.append("poor_name_quality")
        top_risks.append("Poor name structure")
    elif name_fit_score < 50:
        risk_penalty += 8
        risk_flags.append("weak_name_quality")
    
    # TLD risk
    if tld_mult < 0.30:
        risk_penalty += 15
        risk_flags.append("very_weak_tld")
        top_risks.append(f".{tld} has minimal resale market")
    elif tld_mult < 0.50:
        risk_penalty += 8
        risk_flags.append("weak_tld")
    
    # Data quality risk
    if dq["score"] < 30:
        risk_penalty += 10
        risk_flags.append("insufficient_data")
        top_risks.append("Low data quality — analysis unreliable")
    elif dq["score"] < 50:
        risk_penalty += 5
        risk_flags.append("limited_data")
    
    # KPS mismatch risk
    if kps_tier in ("ultra", "premium") and name_fit_score < 50 and kps_match_type != "exact":
        risk_penalty += 12
        risk_flags.append("kps_name_mismatch")
        top_risks.append("Strong keyword in weak name structure")

    # ── Coherence-driven risk (replaces HOT_SERVICE_NICHES special-case) ──
    # Universal: applies to ANY incoherent name. Uses elif to prevent
    # triple-stacking penalties for what is ultimately one structural flaw.
    if coherence["is_keyword_stuffed"]:
        risk_penalty += 20
        risk_flags.append("keyword_stuffing")
        top_risks.append("Multiple commercial keywords stuffed in name")
    elif coherence["is_incoherent"]:
        risk_penalty += 12
        risk_flags.append("incoherent_structure")
        top_risks.append("Name has commercial keyword in unsellable structure")
    elif not coherence_passes:
        risk_penalty += 15
        risk_flags.append("failed_coherence")
        top_risks.append("Name fails basic structural sanity")
    elif coherence_score < 60:
        risk_penalty += 5
        risk_flags.append("weak_structure")

    # Length risk
    if len(name) > 18:
        risk_penalty += 8
        risk_flags.append("very_long_domain")

    risk_score = min(100, risk_penalty)
    
    # ━━━━━━━━━━━━ 5. PRICE CONFIDENCE ━━━━━━━━━━━━
    pc = _compute_price_confidence(kps_match_type, kps_cnt, kps_conf,
                                    name_fit_score, geo_market_q, tld_mult,
                                    domain_type, price_warnings)
    
    # ━━━━━━━━━━━━ 6. SELL-THROUGH PROBABILITY ━━━━━━━━━━━━
    stp = _compute_sell_through(domain_type, tld_mult, len(name),
                                 scores.get("Clarity", 0), bp, 
                                 scores.get("Liquidity", 0),
                                 kps_conf, geo_market_q, brand_score,
                                 name_fit_score, dq["score"])
    
    # ━━━━━━━━━━━━ 7. ACQUISITION SAFETY ━━━━━━━━━━━━
    acq = _compute_acquisition_safety(price_result, stp, risk_penalty)
    
    # ━━━━━━━━━━━━ 8. STRATEGIC BONUS ━━━━━━━━━━━━
    # Capped contributions — must be backed by evidence, not category labels.
    strategic = 0

    # Premium exact-match single-word .com — universally valuable regardless of niche
    if (kps_match_type == "exact" and tld_mult >= 0.95 and len(name) <= 8
            and kps_tier in ("ultra", "premium") and coherence_passes):
        strategic += 5
        top_signals.append("Premium single-word .com asset")

    # Strong local service — only when geo market is real AND there is evidence
    if (domain_type == "local_service" and geo_market_q <= 2
            and (kps_tier in ("ultra", "premium", "high") or rdt >= 5)
            and coherence_passes):
        strategic += 3
        top_signals.append("Strong local service in premium geo")

    # Brandable bonus — gated to require BOTH structural and evidence support.
    # Previously this bonus fired on shape alone, creating the brandable bias.
    if (brand_score >= 75 and name_fit_score >= 75 and tld_mult >= 0.75
            and len(name) <= 12 and (reg >= 3 or rdt >= 3 or kps_tier != "none")
            and coherence_passes):
        strategic += 4
    elif (brand_score >= 58 and name_fit_score >= 70 and tld_mult >= 0.75
            and len(name) <= 12 and (reg >= 2 or rdt >= 2)
            and coherence_passes):
        strategic += 2
    
    # ━━━━━━━━━━━━ 9. OPPORTUNITY SCORE ━━━━━━━━━━━━
    liquidity_score = min(100, scores.get("Liquidity", 0) * 10)  # scale 0-10 -> 0-100
    
    opp = (signal * 0.35
           + sell * 0.30
           + liquidity_score * 0.20
           + pc["confidence_score"] * 0.10
           + strategic * 0.05
           - risk_penalty)
    opp = max(0, min(100, round(opp)))
    
    # ━━━━━━━━━━━━ 9b. SINGLE-BUYER & TRADEMARK SIMILARITY DETECTION ━━━━━━━━━━━━
    _single_buyer_check = _detect_single_buyer_or_trademark(name)
    if _single_buyer_check["is_single_buyer"]:
        risk_flags.append("single_buyer_domain")
        top_risks.append(
            f"Single-buyer play — likely end user: {_single_buyer_check['brand']}"
        )
        # Single-buyer domains have high value IF the named company buys,
        # but near-zero resale market otherwise. Flag for manual review.
        risk_penalty = min(100, risk_penalty + 10)
        risk_score = min(100, risk_penalty)
    elif _single_buyer_check["is_trademark_similar"]:
        risk_flags.append("trademark_similarity")
        top_risks.append(
            f"Resembles '{_single_buyer_check['brand']}' — trademark/cybersquatting risk"
        )
        risk_penalty = min(100, risk_penalty + 15)
        risk_score = min(100, risk_penalty)
        # Recalculate opp to reflect updated risk
        opp = max(0, min(100, round(
            signal * 0.35 + sell * 0.30
            + min(100, scores.get("Liquidity", 0) * 10) * 0.20
            + pc["confidence_score"] * 0.10
            + strategic * 0.05
            - risk_penalty
        )))

    # ━━━━━━━━━━━━ 10. DECISION VERDICT (UNIFIED — no type-based lanes) ━━━━━━━━━━━━
    verdict, reason, opp = _decide_verdict(
        opp, total_score, signal, sell, risk_score, risk_flags,
        kps_tier, kps_match_type, kps_coverage, name_fit_score,
        domain_type, geo_market_q, tld_mult, brand_score,
        dq["score"], reg, rdt, top_signals, name,
        coherence_passes, coherence_score, rejection_codes,
        cpc_val=cpc_val,
        ml_grade=ml_grade, ml_score=ml_score, ml_price=ml_price,
    )
    
    # ━━━━━━━━━━━━ 11. BUYER PERSONA ━━━━━━━━━━━━
    persona = _compute_buyer_persona(domain_type, niche_info, geo_info, 
                                      kps_tier, brand_score, name, kps_result)
    
    # ━━━━━━━━━━━━ 12. RANKING CATEGORY ━━━━━━━━━━━━
    ranking = _compute_ranking_category(verdict, opp, stp, domain_type,
                                         brand_score, risk_flags, signal)
    
    # ━━━━━━━━━━━━ 13. BRAND SELLABILITY ━━━━━━━━━━━━
    brand_sell = _compute_brand_sellability(brand_score, len(name), name_fit_score,
                                            reg, rdt, aby, tld_mult, name)
    
    manual_research = (dq["score"] < 50 or "insufficient_data" in risk_flags
                       or verdict in ("BUY", "GEM"))
    
    # Keyword market value = KPS score adjusted for match type
    kmv = kps_score
    if kps_match_type == "exact":
        kmv = kps_score
    elif kps_match_type in ("prefix", "suffix"):
        kmv = int(kps_score * 0.7)
    elif kps_match_type == "middle":
        kmv = int(kps_score * 0.4)
    
    return {
        "OpportunityScore": opp,
        "SignalScore": signal,
        "SellabilityScore": sell,
        "RiskScore": risk_score,
        "RiskFlags": risk_flags,
        "DecisionVerdict": verdict,
        "DecisionReason": reason,
        "TopSignals": top_signals[:5],
        "TopRisks": top_risks[:5],
        "ManualResearchRequired": manual_research,
        "DataQualityScore": dq["score"],
        "DataQualityFlags": dq["flags"],
        "NameFitScore": name_fit_score,
        "KeywordMarketValue": kmv,
        "BrandSellabilityScore": brand_sell,
        "PriceConfidence": pc["level"],
        "PriceConfidenceScore": pc["confidence_score"],
        "PriceWarnings": price_warnings,
        "SellThroughProbability": stp,
        "MaxAcquisitionPrice": acq["max_buy_price"],
        "IdealAcquisitionPrice": acq["ideal_buy_price"],
        "OverpricedWarning": acq.get("overpriced_warning", ""),
        "BuyerPersona": persona["persona"],
        "BuyerClarity": persona["clarity"],
        "BuyerCountEstimate": persona["count_estimate"],
        "OutboundDifficulty": persona["outbound_difficulty"],
        "RankingCategory": ranking,
        # Coherence Gate output — exposed for UI / CSV / debugging
        "CoherenceScore": coherence_score,
        "CoherencePasses": coherence_passes,
        "RejectionReasons": rejection_codes,
        "CoherenceWarnings": coherence.get("warnings", []),
    }


# ━━━━━━━━━━━━ INTERNAL FUNCTIONS ━━━━━━━━━━━━

def _compute_data_quality(reg, rdt, aby, kps_score, kps_match_type,
                          kps_cnt, kps_conf, tld_mult, name_fit_score):
    score = 0
    flags = []
    if reg > 0: score += 15
    else: flags.append("no_reg_data")
    if rdt > 0: score += 15
    else: flags.append("no_rdt_data")
    if aby > 0: score += 10
    else: flags.append("no_age_data")
    if kps_score > 0: score += 20
    else: flags.append("no_kps_match")
    if kps_match_type == "exact": score += 10
    elif kps_match_type in ("prefix", "suffix"): score += 5
    if kps_cnt >= 10: score += 10
    elif kps_cnt >= 3: score += 5
    else: flags.append("low_sales_sample")
    if tld_mult >= 0.50: score += 10
    if kps_conf >= 0.7: score += 10
    elif kps_conf >= 0.4: score += 5
    return {"score": min(100, score), "flags": flags}


def _compute_price_confidence(kps_match_type, kps_cnt, kps_conf,
                               name_fit_score, geo_market_q, tld_mult,
                               domain_type, warnings):
    cs = 50  # base
    if kps_match_type == "exact" and kps_cnt >= 10:
        cs = 85
    elif kps_match_type == "exact" and kps_cnt >= 3:
        cs = 70
    elif kps_match_type in ("prefix", "suffix") and kps_cnt >= 10:
        cs = 60
        warnings.append("Price based on keyword position, not exact domain")
    elif kps_match_type in ("prefix", "suffix"):
        cs = 45
        warnings.append("Price based on keyword position, not exact domain")
    elif kps_match_type == "middle":
        cs = 25
        warnings.append("Keyword embedded in middle — weak price anchor")
    else:
        cs = 15
        warnings.append("No keyword price anchor available")
    
    if name_fit_score < 40:
        cs = int(cs * 0.7)
        warnings.append("Low name fit reduces price confidence")
    if geo_market_q >= 4:
        cs = int(cs * 0.6)
        warnings.append("Weak geo market — uncertain buyer pool")
    if tld_mult < 0.50:
        cs = int(cs * 0.7)
        warnings.append("Weak TLD reduces value significantly")
    
    cs = max(0, min(100, cs))
    level = "high" if cs >= 70 else "medium" if cs >= 45 else "low"
    return {"confidence_score": cs, "level": level}


def _compute_sell_through(domain_type, tld_mult, name_len, clarity,
                           buyer_pool, liquidity, kps_conf, geo_q,
                           brand_score, name_fit, dq_score):
    """Estimate sell-through probability (percentage)."""
    # Base rates by domain type — calibrated to real aftermarket sell-through.
    # Prior rates (12/10/6/3) were 2-3x too high, inflating acquisition prices.
    base = {"local_service": 6, "seo_keyword": 5, "global_service": 3,
            "brandable": 1.5, "content_media": 2, "low_value": 0.5}.get(domain_type, 1)
    
    # Adjustments
    if tld_mult >= 0.95: base *= 1.5       # .com premium
    elif tld_mult < 0.50: base *= 0.4      # weak TLD
    
    if name_len <= 6: base *= 1.4
    elif name_len >= 15: base *= 0.5
    
    if clarity >= 12: base *= 1.3
    elif clarity < 6: base *= 0.6
    
    if geo_q >= 4: base *= 0.3              # weak geo
    elif geo_q == 1: base *= 1.5            # premium geo
    
    if name_fit < 40: base *= 0.5
    elif name_fit >= 75: base *= 1.3
    
    if brand_score >= 75 and domain_type == "brandable": base *= 1.4
    
    if dq_score < 30: base *= 0.5
    
    if kps_conf >= 0.8: base *= 1.2
    
    return round(max(0.5, min(20, base)), 1)


def _compute_acquisition_safety(price_result, sell_through, risk_penalty):
    low = price_result.get("low_estimate", 0) if price_result else 0
    if low <= 0:
        return {"max_buy_price": 0, "ideal_buy_price": 0, "overpriced_warning": ""}

    # Max acquisition = 25% of low estimate, discounted by risk.
    # Ideal = 15% of low estimate, discounted by risk.
    # sell_through calibrates the ratio between ideal and max, but is NOT
    # used as a multiplier against the price (that would double-discount).
    risk_discount = max(0.3, 1.0 - risk_penalty / 100)
    stp_factor = max(0.5, min(1.0, sell_through / 20))  # normalize around 20% STP

    max_buy  = int(low * 0.25 * risk_discount)
    ideal_buy = int(low * 0.15 * risk_discount * stp_factor)

    # ── Realistic Wholesale Drop-catch Floor ──
    # If the domain's low wholesale value is at least $200, the max_buy should 
    # not fall below standard drop-catch auction minimums ($69) assuming risk is low.
    if low >= 200 and risk_penalty < 50 and max_buy < 69:
        max_buy = 69
    if low >= 200 and risk_penalty < 50 and ideal_buy < 59:
        ideal_buy = 59

    warning = ""
    if max_buy < 10:
        warning = "Domain may not justify any acquisition cost"
    elif max_buy < 59:
        warning = "Only worth acquiring at hand-reg price"
    elif 59 <= max_buy <= 100:
        warning = "Worth placing a standard drop-catch backorder (e.g., $69)"

    return {"max_buy_price": max_buy, "ideal_buy_price": ideal_buy,
            "overpriced_warning": warning}


def _decide_verdict(opp, total_score, signal, sell, risk_score, risk_flags,
                    kps_tier, kps_match_type, kps_coverage, name_fit,
                    domain_type, geo_q, tld_mult, brand_score, dq_score,
                    reg, rdt, top_signals, name,
                    coherence_passes=True, coherence_score=100, rejection_codes=None,
                    cpc_val=0.0,
                    ml_grade="PASS", ml_score=0.0, ml_price=0):
    """
    Unified decision verdict — V5 Balanced Engine.

    The previous engine had four parallel "lanes" (low-value, geo, premium-
    single-word, brandable) where each could short-circuit to GEM/BUY without
    going through the same evidence requirements. This created systemic bias:
    - Brandable lane (Gate D) granted GEM purely on shape (brand>=70 AND
      name_fit>=90), without ANY market evidence.
    - HOT_SERVICE_NICHES lane gave insurance/lawyer/realtor names automatic
      promotion regardless of coherence.

    V5 uses a SINGLE verdict path. Every domain — brandable, geo, SEO,
    single-word, content — must clear the same evidence bar to be GEM:
        opp >= 72 AND coherence_passes AND risk_score < 25 AND dq_score >= 50

    The only soft adjustments are:
    - Coherence gate caps verdict at HOLD on hard-fail.
    - Weak geo (geo_q=4) caps verdict at HOLD.
    - Exact-match KPS rescues PASS to HOLD (proven evidence floor).
    """
    rejection_codes = rejection_codes or []
    reasons = []

    # ── 0. ULTRA-SHORT PREMIUM BYPASS ──
    is_ultra_short = len(name) <= 4 and (name.isalpha() or name.isdigit())
    if is_ultra_short and tld_mult >= 0.5:
        verdict = "GEM" if tld_mult >= 0.95 else "BUY"
        reasons.append("Ultra-Premium Short Domain — inherent global value")
        return verdict, " | ".join(reasons), opp

    # ── 0b. SHORT PREMIUM DICTIONARY WORD FLOOR ──
    # 5-6 letter Tier1 words on quality TLDs (.com/.ai/.io) are inherently
    # sellable even when external data (REG/RDT/KPS) is absent.
    # This prevents strong single-word .com domains from falling to PASS.
    if (5 <= len(name) <= 6 and name in TIER1_WORDS
            and tld_mult >= 0.85 and coherence_passes):
        if opp < 60:
            verdict = "BUY"
            reasons.append("Premium short dictionary word on quality TLD — floor BUY")
            return verdict, " | ".join(reasons), opp

    # ── 1. COHERENCE HARD GATE ──
    if not coherence_passes:
        if "RJ_KEYWORD_STUFFING" in rejection_codes:
            return "PASS", "Keyword stuffing — name is unsellable to a real buyer", opp
        if "RJ_NO_LETTERS" in rejection_codes or "RJ_DIGIT_DOMINATED" in rejection_codes:
            return "PASS", "Name dominated by digits — not a brandable structure", opp
        if "RJ_MULTIPLE_HYPHENS" in rejection_codes:
            return "PASS", "Multiple hyphens — flip-unfriendly structure", opp
        if "RJ_NO_VOWELS" in rejection_codes or "RJ_CONSONANT_CLUSTER" in rejection_codes:
            return "PASS", "Unpronounceable structure", opp
        if "RJ_TOO_LONG" in rejection_codes:
            return "PASS", "Excessively long name", opp
        # Generic coherence fail — allow rescue to HOLD only on exact-match evidence
        if kps_match_type == "exact" and kps_tier in ("ultra", "premium"):
            return "HOLD", "Exact-match keyword present but name structure is weak", opp
        return "PASS", "Failed structural coherence", opp

    # ── 2. WEAK GEO HARD CAP (only for local_service — others not affected) ──
    if domain_type == "local_service" and geo_q == 4:
        if reg < 5 and rdt < 5 and kps_tier in ("none", "low"):
            return "PASS", "Weak geo market with no validation signals", opp
        return "HOLD", "Weak geo market — limited buyer pool", opp

    if domain_type == "local_service" and geo_q == 3:
        if opp >= 72 and kps_tier in ("ultra", "premium") and name_fit >= 70:
            pass  # Allow GEM/BUY — strong evidence overrides geo concern
        elif cpc_val >= 15.0:
            pass  # Ultra-high CPC validates advertiser demand; geo penalty waived
        elif cpc_val >= 8.0:
            if opp >= 72:
                opp = min(opp, 71)  # Allow BUY but block GEM in moderate geo
                reasons.append("Soft-capped at BUY — high CPC partially offsets emerging geo")
        elif opp >= 65:
            opp = min(opp, 64)  # Cap below BUY threshold
            reasons.append("Capped to HOLD — emerging geo market limits confident buyer pool")


    # ── 2b. ML VERDICT OVERRIDE / RESCUE ──
    # When the trained sales model is highly confident, it acts as an
    # independent evidence signal. Strong ML consensus can upgrade a
    # borderline BUY to GEM or rescue a PASS to HOLD, but it never
    # overrides hard coherence/trademark failures.
    ml_override_applied = False
    if ml_score >= 0.8 and ml_grade == "GEM" and coherence_passes and risk_score < 35:
        if opp < 72:
            opp = min(100, opp + 12)
            reasons.append("ML sales model signals GEM with high confidence")
            ml_override_applied = True
    elif ml_score >= 0.6 and ml_grade == "BUY" and coherence_passes and risk_score < 45:
        if opp < 65:
            opp = min(100, opp + 8)
            reasons.append("ML sales model supports BUY")
            ml_override_applied = True

    # ── 3. UNIFIED EVIDENCE-BASED VERDICT (the only path to GEM) ──
    # GEM requires: opportunity AND low risk AND data quality AND coherence.
    # No type-based shortcuts. No category-based promotions.

    if opp >= 72 and risk_score < 25 and dq_score >= 50 and coherence_score >= 70:
        verdict = "GEM"
        reasons.append("Strong opportunity with verified evidence")
        if top_signals:
            reasons.append(top_signals[0])
    elif opp >= 65 and risk_score < 35 and coherence_score >= 60:
        verdict = "BUY"
        reasons.append("Solid investment fundamentals")
        if signal >= 40:
            reasons.append("market signals confirmed")
        if sell >= 55:
            reasons.append("good sellability")
    elif opp >= 40 or (total_score >= 45 and risk_score < 50 and coherence_passes):
        verdict = "HOLD"
        reasons.append("Mixed signals — needs more research")
        if risk_flags:
            reasons.append(f"risks: {', '.join(risk_flags[:2])}")
    else:
        # Evidence floor: ultra/premium exact-match keywords don't fall to PASS
        if kps_tier in ("ultra", "premium") and kps_match_type == "exact":
            verdict = "HOLD"
            reasons.append("Rescued from PASS — exact-match high-value keyword")
        elif ml_score >= 0.5 and ml_grade in ("BUY", "GEM") and coherence_passes:
            verdict = "HOLD"
            reasons.append("Rescued from PASS — ML sales model sees value")
        else:
            verdict = "PASS"
            reasons.append("Insufficient investment signals")

    # ── 4. POST-DECISION GUARDS (apply uniformly to ALL types) ──

    # Guard A: GEM requires 2+ INDEPENDENT market evidence signals.
    # A confident ML GEM/BUY counts as one signal so strong ML-driven names
    # are not automatically downgraded purely for missing CSV metadata.
    # Reduced from 3→2 because many strong domains lack CSV metadata (no REG/RDT)
    # but still have clear multi-signal evidence. Requiring 3 systematically
    # suppressed good domains that were missing one data point.
    if verdict == "GEM":
        evidence_count = 0
        if kps_tier in ("ultra", "premium", "high"):
            evidence_count += 1
        if reg >= 3:
            evidence_count += 1
        if rdt >= 3:
            evidence_count += 1
        if name_fit >= 65:
            evidence_count += 1
        if coherence_score >= 80:
            evidence_count += 1
        if tld_mult >= 0.95:
            evidence_count += 1
        if signal >= 60:
            evidence_count += 1
        if brand_score >= 70:  # strong brandability is independent market validation
            evidence_count += 1
        if ml_score >= 0.6 and ml_grade in ("BUY", "GEM"):
            evidence_count += 1

        if evidence_count < 2:
            verdict = "BUY"
            found_signals = []
            if kps_tier in ("ultra", "premium", "high"): found_signals.append("KPS")
            if reg >= 3: found_signals.append("REG")
            if rdt >= 3: found_signals.append("RDT")
            if name_fit >= 65: found_signals.append("FIT")
            if coherence_score >= 80: found_signals.append("COH")
            if tld_mult >= 0.95: found_signals.append("TLD")
            if signal >= 60: found_signals.append("SIG")
            if brand_score >= 70: found_signals.append("BRAND")

            sig_str = ", ".join(found_signals) if found_signals else "None"
            reasons.insert(0, f"Downgraded from GEM — only {evidence_count}/2 signals found ({sig_str})")

    # Guard A2: GEM requires name_fit to meet a minimum quality bar.
    # Consumer-campaign / slogan domains (coloradowantsyou, texasproudofyou)
    # can reach GEM via geo KPS signal alone but have no real resale market.
    if verdict == "GEM" and name_fit < 55:
        verdict = "BUY"
        reasons.insert(0, "Downgraded from GEM — name structure too campaign-like for investment-grade")

    # Guard B: GEM cannot survive significant risk.
    if verdict == "GEM" and risk_score >= 25:
        verdict = "BUY"
        reasons.insert(0, "Downgraded from GEM due to risk factors")

    # Guard C: BUY for brandables still requires SOME evidence beyond shape.
    # Threshold lowered 70→60 to avoid suppressing genuine startup-style names.
    # name_fit_score >= 70 is an additional rescue path — a well-fitting name
    # is itself evidence of sellability even without external data.
    if verdict == "BUY" and domain_type == "brandable":
        if (reg < 3 and rdt < 3 and kps_tier in ("none", "low")
                and brand_score < 60 and name_fit < 70):
            verdict = "HOLD"
            reasons = ["Brandable shape but no market validation"]

    # Guard D: Coherence-degraded names cap at HOLD even if opp is high.
    if verdict in ("GEM", "BUY") and coherence_score < 55:
        verdict = "HOLD"
        reasons.insert(0, "Capped — coherence score too low for confident verdict")

    return verdict, " | ".join(reasons), opp


def _compute_buyer_persona(domain_type, niche_info, geo_info, 
                            kps_tier, brand_score, name, kps_result=None):
    niche = niche_info.get("niche", "-")
    geo = geo_info.get("geo_name", "")
    kps_kw = (kps_result or {}).get("best_match", {}).get("keyword", "") if kps_result else ""
    
    personas = {
        "local_service": {"persona": "SMBs, agencies, lead-gen companies",
                          "clarity": "high", "count_estimate": "hundreds",
                          "outbound_difficulty": "low"},
        "seo_keyword": {"persona": "Affiliates, SEO builders, niche businesses",
                        "clarity": "medium", "count_estimate": "dozens to hundreds",
                        "outbound_difficulty": "medium"},
        "brandable": {"persona": "Startups, SaaS founders, rebranding companies",
                      "clarity": "low", "count_estimate": "unknown",
                      "outbound_difficulty": "high"},
        "global_service": {"persona": "Service companies, SaaS platforms",
                           "clarity": "medium", "count_estimate": "dozens",
                           "outbound_difficulty": "medium"},
        "content_media": {"persona": "Publishers, bloggers, media companies",
                          "clarity": "medium", "count_estimate": "dozens",
                          "outbound_difficulty": "medium"},
    }
    
    base = personas.get(domain_type, {
        "persona": "Unclear", "clarity": "low",
        "count_estimate": "unknown", "outbound_difficulty": "high"
    })
    
    if niche != "-" and geo:
        base["persona"] = f"{niche} businesses in {geo.title()}"
        base["clarity"] = "high"
    elif niche != "-":
        base["persona"] = f"{niche} companies, {base['persona']}"
    elif kps_kw and geo:
        base["persona"] = f"'{kps_kw}'-related businesses in {geo.title()}"
        base["clarity"] = "high"
    elif kps_kw:
        base["persona"] = f"'{kps_kw}' industry businesses, {base['persona']}"
        base["clarity"] = "medium"
    
    # Premium single-word gets different buyer persona
    if kps_tier in ("ultra", "premium") and len(name) <= 8:
        base["persona"] = "Category leaders, domain investors, marketplaces"
        base["clarity"] = "high"
        base["count_estimate"] = "small but high-value"
        base["outbound_difficulty"] = "low"
    
    return base


def _compute_ranking_category(verdict, opp, stp, domain_type, 
                               brand_score, risk_flags, signal):
    if verdict == "GEM" and opp >= 72:
        return "Best Overall Opportunities"
    if verdict in ("GEM", "BUY") and stp >= 15:
        return "Fast Flip Candidates"
    if verdict in ("GEM", "BUY") and signal >= 60 and stp < 10:
        return "Premium Long-Term Holds"
    if domain_type == "brandable" and brand_score >= 62:
        return "Brandable Candidates"
    if domain_type == "local_service" and verdict in ("BUY", "HOLD"):
        return "Geo-Service Plays"
    if signal >= 40 and len(risk_flags) >= 2:
        return "High Risk / High Reward"
    if verdict == "PASS" or (verdict == "HOLD" and opp < 30):
        return "Avoid / False Positive Risk"
    return "Standard Opportunities"


def _compute_brand_sellability(brand_score, name_len, name_fit,
                                reg, rdt, aby, tld_mult, name):
    """BrandSellabilityScore — can this brand name actually be sold?"""
    score = 0
    score += int(brand_score * 0.4)
    
    if name_len <= 6: score += 15
    elif name_len <= 8: score += 10
    elif name_len <= 10: score += 5
    
    if name_fit >= 70: score += 10
    elif name_fit >= 50: score += 5
    
    if reg >= 5: score += 10
    elif reg >= 2: score += 5
    
    if rdt >= 5: score += 5
    
    if tld_mult >= 0.95: score += 10
    elif tld_mult >= 0.75: score += 5
    
    if '-' in name: score -= 15
    if any(c.isdigit() for c in name): score -= 10
    
    # Vintage bonus is conditional on overall name quality (was unconditional).
    # A spammy 1998 domain doesn't deserve +5 just for being old.
    if 1990 <= aby <= 2005 and brand_score >= 50 and name_fit >= 50:
        score += 5

    return max(0, min(100, score))


# ━━━━━━━━━━━━ SINGLE-BUYER & TRADEMARK SIMILARITY DETECTION ━━━━━━━━━━━━

# Well-known brand fragments — exact substring match triggers trademark check.
# Keys are lowercase substrings to detect; values are the brand name to cite.
_BRAND_FRAGMENTS = {
    "homedepot": "Home Depot", "lowes": "Lowe's",
    "walmart": "Walmart", "amazon": "Amazon",
    "google": "Google", "apple": "Apple",
    "microsoft": "Microsoft", "facebook": "Facebook",
    "instagram": "Instagram", "netflix": "Netflix",
    "uber": "Uber", "airbnb": "Airbnb",
    "tesla": "Tesla", "buick": "Buick/GM",
    "chevrolet": "Chevrolet", "mercedes": "Mercedes-Benz",
    "bmw": "BMW", "toyota": "Toyota",
    "honda": "Honda", "ford": "Ford",
    "starbucks": "Starbucks", "mcdonalds": "McDonald's",
    "nike": "Nike", "adidas": "Adidas",
    "costco": "Costco", "nordstrom": "Nordstrom",
    "marriott": "Marriott", "hilton": "Hilton",
    "hyatt": "Hyatt", "sheraton": "Sheraton",
    "verizon": "Verizon", "comcast": "Comcast",
    "att": "AT&T", "tmobile": "T-Mobile",
    "pfizer": "Pfizer", "moderna": "Moderna",
    "fedex": "FedEx", "ups": "UPS", "dhl": "DHL",
    "hertz": "Hertz", "avis": "Avis",
    "expedia": "Expedia", "tripadvisor": "TripAdvisor",
    "redfin": "Redfin", "zillow": "Zillow",
    "mckinsey": "McKinsey", "deloitte": "Deloitte",
    "accenture": "Accenture",
}

# When a domain contains a brand AND one of these modifiers, it's a
# single-buyer domain — only one company would want it.
_SINGLE_BUYER_MODIFIERS = {
    "certified", "official", "motors", "dealership", "dealer",
    "store", "shop", "online", "direct", "auto", "car",
    "service", "parts", "club", "rewards", "plus", "pro",
    "inc", "corp", "llc", "group", "global", "international",
    "world", "nation", "usa", "uk", "canada", "australia",
    "real", "genuine", "authorized", "approved",
}

# Brands associated with trademark squatting risk even as a fragment
# (e.g. "depot" in "horndepot" — too close to Home Depot)
_PARTIAL_BRAND_MAP = {
    "depot": "Home Depot",
    "appstore": "Apple App Store",
    "playstore": "Google Play Store",
}


def _brand_at_boundary(name_lower: str, fragment: str) -> bool:
    """
    Return True only when a brand fragment appears at a genuine word boundary,
    preventing false positives like 'ford' in 'afford' or 'att' in 'battery'.

    Rules:
    - Fragment is a standalone hyphen/underscore-separated token → always match.
    - Fragment is a prefix (starts the stripped name) → match.
    - Fragment is 6+ chars → allow substring match (long brands are specific enough).
    - Otherwise → skip (fragment is embedded inside a word).
    """
    # Standalone token check (respects hyphens/underscores as word separators)
    tokens = re.split(r'[-_]', name_lower)
    if fragment in tokens:
        return True
    # Prefix check in the stripped (no-hyphen) form
    stripped = name_lower.replace('-', '').replace('_', '')
    if stripped.startswith(fragment):
        return True
    # Long fragments are specific enough that a substring match is acceptable
    if len(fragment) >= 6 and fragment in stripped:
        return True
    return False


def _detect_single_buyer_or_trademark(name: str) -> dict:
    """
    Returns:
        is_single_buyer  — name contains a famous brand + purchase-intent modifier
        is_trademark_similar — name contains a known brand fragment (risky)
        brand            — the brand name identified
    """
    n_lower = name.lower()
    n = n_lower.replace('-', '').replace('_', '')

    # Check full brand fragments with proper word-boundary guard
    for fragment, brand in _BRAND_FRAGMENTS.items():
        if not _brand_at_boundary(n_lower, fragment):
            continue
        # Fragment is at a real boundary — check for single-buyer modifier
        remaining = n.replace(fragment, '', 1)
        for mod in _SINGLE_BUYER_MODIFIERS:
            if mod in remaining:
                return {"is_single_buyer": True, "is_trademark_similar": False,
                        "brand": brand}
        # Brand fragment present without modifier → trademark similarity risk
        return {"is_single_buyer": False, "is_trademark_similar": True,
                "brand": brand}

    # Check partial brand map (fragments that imply a specific brand)
    for fragment, brand in _PARTIAL_BRAND_MAP.items():
        if _brand_at_boundary(n_lower, fragment):
            return {"is_single_buyer": False, "is_trademark_similar": True,
                    "brand": brand}

    return {"is_single_buyer": False, "is_trademark_similar": False, "brand": ""}
