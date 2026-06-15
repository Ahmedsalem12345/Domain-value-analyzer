"""
Name Fit Score — Evaluates how well a domain name fits its keyword/market.

A strong keyword inside a weak name structure should NOT get the same
value as a clean, sellable domain.

NameFitScore (0-100) considers:
  - Length appropriateness         (0-20)
  - Readability / pronounceability (0-20)
  - Clean structure                (0-20)
  - KPS coverage ratio             (0-15)
  - TLD quality                    (0-15)
  - Word boundary alignment        (0-10)  ← was missing, now implemented
"""
import re
import logging

logger = logging.getLogger("analyzer.name_fit")


def _word_boundary_score(name: str, kps_result: dict) -> tuple[int, list]:
    """
    Axis 6: Word Boundary Alignment (0-10).

    Checks whether the KPS keyword sits cleanly at the START or END of the
    domain (prefix/suffix), rather than buried in the middle.  A keyword
    at a natural word boundary is easier to read and signals clear intent
    to a buyer — "loansfast" reads better than "fastloansco".

    Also rewards names whose wordninja split aligns perfectly with the KPS
    keyword match — meaning the domain is a natural, dictionary-clean compound.
    """
    pts = 0
    reasons = []

    kps_result = kps_result or {}
    best_match = kps_result.get("best_match") or {}
    match_type = best_match.get("match_type", "")
    keyword = best_match.get("keyword", "")
    coverage = kps_result.get("coverage_ratio", 0.0)

    # ── Match position reward ──
    if match_type == "exact":
        pts += 10            # Whole name IS the keyword — perfect fit
        reasons.append("exact_keyword_match")
    elif match_type in ("prefix", "suffix"):
        pts += 7             # Keyword anchors the start or end — clean read
        reasons.append(f"keyword_{match_type}")
    elif match_type == "middle":
        pts += 2             # Keyword buried in middle — harder to read
        reasons.append("keyword_embedded_middle")

    # ── Coverage bonus: KPS parsed most of the name into known keywords ──
    # High coverage = the whole name is composed of market-relevant words.
    # This is a word-boundary quality signal independent of match_type.
    if coverage >= 0.95 and match_type != "exact":
        pts = min(10, pts + 2)   # Near-perfect coverage on a compound
    elif coverage >= 0.80 and match_type not in ("exact", "prefix", "suffix"):
        pts = min(10, pts + 1)

    # ── Natural boundary heuristic (no KPS match available) ──
    # If we have no KPS data, check structural word boundaries using
    # wordninja.  A clean 2-word split at a midpoint suggests the name
    # is a natural compound rather than random concatenation.
    if not match_type and pts == 0:
        try:
            import wordninja
            words = wordninja.split(name)
            if 1 <= len(words) <= 3:
                # 1-3 words = clean compound or single word
                pts = 5
                reasons.append("clean_word_split")
            elif len(words) == 4:
                pts = 3
                reasons.append("four_word_compound")
            else:
                pts = 1
                reasons.append("many_word_compound")
        except Exception:
            # wordninja unavailable — grant a neutral mid-score
            pts = 3
            reasons.append("boundary_unverified")

    return max(0, min(10, pts)), reasons


def score_name_fit(name: str, tld: str, kps_result: dict = None,
                   domain_type: str = "low_value") -> dict:
    """
    Compute NameFitScore (0-100) for a domain.

    Returns dict with:
        name_fit_score: int 0-100
        name_fit_reasons: list[str]
        name_fit_grade: str (A/B/C/D/F)
    """
    if not name:
        return {"name_fit_score": 0, "name_fit_reasons": ["empty name"], "name_fit_grade": "F"}

    kps_result = kps_result or {}
    score = 0
    reasons = []

    # ── 1. Length Score (0-20) ──
    # (was 0-25; 5 pts redistributed to new word-boundary axis)
    n = len(name)
    if n <= 5:
        length_pts = 20
    elif n <= 7:
        length_pts = 17
    elif n <= 10:
        length_pts = 14
    elif n <= 13:
        length_pts = 9
    elif n <= 16:
        length_pts = 5
    elif n <= 20:
        length_pts = 2
    else:
        length_pts = 0
        reasons.append("very_long_name")
    score += length_pts

    # ── 2. Readability / Pronounceability (0-20) ──
    # (unchanged max, but tightened thresholds)
    vowels = sum(1 for c in name if c in 'aeiouy')
    alpha_count = sum(1 for c in name if c.isalpha())
    ratio = vowels / alpha_count if alpha_count > 0 else 0

    # Consonant cluster analysis — only count actual consonants, not digits/hyphens
    max_cons = max((len(r) for r in re.findall(r'[bcdfghjklmnpqrstvwxz]+', name)), default=0)

    read_pts = 0
    if 0.20 <= ratio <= 0.55 and max_cons <= 3:
        read_pts = 20   # Excellent readability
    elif 0.15 <= ratio <= 0.60 and max_cons <= 4:
        read_pts = 15
    elif 0.10 <= ratio <= 0.65 and max_cons <= 5:
        read_pts = 8
    else:
        read_pts = 2
        reasons.append("poor_readability")
    score += read_pts

    # ── 3. Clean Structure (0-20) ──
    struct_pts = 20

    if '-' in name:
        struct_pts -= 12
        reasons.append("contains_hyphen")

    if any(c.isdigit() for c in name):
        struct_pts -= 10
        reasons.append("contains_number")

    # Double/triple word patterns without natural compound
    if n > 18:
        struct_pts -= 5
        reasons.append("keyword_stuffing_risk")

    struct_pts = max(0, struct_pts)
    score += struct_pts

    # ── 4. KPS Coverage (0-15) ──
    coverage = kps_result.get("coverage_ratio", 0.0)
    kps_tier = kps_result.get("kps_tier", "none")

    if coverage >= 0.95:
        cov_pts = 15
    elif coverage >= 0.80:
        cov_pts = 12
    elif coverage >= 0.60:
        cov_pts = 8
    elif coverage >= 0.40:
        cov_pts = 4
    else:
        cov_pts = 0
        if kps_tier not in ("none", "low"):
            reasons.append("low_keyword_coverage")
    score += cov_pts

    # ── 5. TLD Quality (0-15) ──
    from config import TLD_MULTIPLIERS
    tld_mult = TLD_MULTIPLIERS.get(tld, 0.30)

    if tld_mult >= 0.95:
        tld_pts = 15    # .com
    elif tld_mult >= 0.80:
        tld_pts = 12    # .ai, .org
    elif tld_mult >= 0.65:
        tld_pts = 9     # .net, .co, .io
    elif tld_mult >= 0.45:
        tld_pts = 5     # .me, .shop
    elif tld_mult >= 0.25:
        tld_pts = 2     # .info, .xyz
    else:
        tld_pts = 0
        reasons.append("weak_tld")
    score += tld_pts

    # ── 6. Word Boundary Alignment (0-10) ──
    # Rewards keywords that sit at natural word boundaries (prefix/suffix/exact)
    # and names whose wordninja split is clean and compact.
    wb_pts, wb_reasons = _word_boundary_score(name, kps_result)
    score += wb_pts
    reasons.extend(wb_reasons)

    # ── Grade Assignment ──
    score = max(0, min(100, score))

    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "name_fit_score": score,
        "name_fit_reasons": reasons,
        "name_fit_grade": grade,
    }
