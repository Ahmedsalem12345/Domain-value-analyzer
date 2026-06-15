"""
Coherence Gate V1 — Universal Semantic & Structural Sanity Gate
================================================================

This is the keystone of the rebalanced scoring engine. It runs on EVERY
domain (not just brandables) BEFORE any keyword bonus is applied, and
returns a structured verdict that downstream scorers MUST honor.

Why it exists
-------------
The previous engine had a fatal flaw: any domain containing a high-CPC
keyword (insurance, lawyer, health, finance, loan, crypto, ...) received
huge automatic boosts (+3 commercial, +8 geo+niche, +12 KPS evidence)
WITHOUT verifying that the keyword was used coherently. As a result:

  xqz-insurance-blah.net  →  BUY  (false positive)
  best-cheap-loan-now.biz →  BUY  (keyword stuffing, no real buyer)
  bestlawyertoday.info    →  BUY  (incoherent, bad TLD)

At the same time, perfectly good non-niche names (e.g. "novak.com",
"tessa.io", "drift.app", "miamicleaners.com") were systematically
underscored because they didn't contain a hardcoded "premium" keyword.

The Coherence Gate solves both problems simultaneously:
  1. Domains with poor structure can never trigger niche boosts.
  2. Domains with good structure are scored fairly regardless of niche.

Output
------
{
    "passes": bool,                 # gate-level pass/fail (hard fail → max HOLD)
    "coherence_score": 0..100,      # gradient signal for downstream scaling
    "rejection_codes": [...],       # machine-readable rejection reasons
    "warnings": [...],              # human-readable soft warnings
    "is_keyword_stuffed": bool,     # 3+ commercial keywords crammed
    "is_incoherent": bool,          # gibberish + keyword combo
    "structural_penalty": int,      # negative number, applied uniformly
}

The gate is INTENTIONALLY niche-agnostic. It does NOT know whether
"insurance" is more valuable than "ceramics". It only judges whether
THE NAME ITSELF is a coherent, sellable string.
"""

import re
import logging

try:
    import wordninja
except ImportError:
    wordninja = None

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

try:
    from analyzer.word_data import ALL_WORDS, TIER1_WORDS, try_split_compound
except ImportError:
    ALL_WORDS = set()
    TIER1_WORDS = set()
    try_split_compound = None

logger = logging.getLogger("analyzer.coherence")

_DEGRADED_MODE = wordninja is None or nlp is None

if wordninja is None:
    logger.warning(
        "wordninja not installed — coherence gate in DEGRADED MODE. "
        "Gibberish detection disabled. Fix: pip install wordninja"
    )
if nlp is None:
    logger.warning(
        "spaCy model 'en_core_web_sm' not loaded — NLP coherence checks DISABLED. "
        "Fix: python -m spacy download en_core_web_sm"
    )


# ── Vocabularies (intentionally narrow — keyword stuffing detection only) ──
# These are NOT a "high-value list". They are simply the words most often
# stuffed by spam-droppers. Any 3+ of them in one domain triggers the
# stuffing flag. We removed specific niches (law, health, etc.) to avoid bias.
_STUFFING_TOKENS = {
    "best", "top", "cheap", "buy", "shop", "find", "get", "deal", "deals",
    "discount", "sale", "free", "fast", "quick", "easy", "online", "now",
    "today", "premium", "pro", "expert", "official", "direct", "near",
}

_VOWELS = set("aeiouy")

_KNOWN_SHORT = {
    "ai", "go", "my", "we", "us", "io", "up", "in", "on", "it",
    "mr", "dr", "uk", "la", "ny", "sf", "dc", "co", "me", "hi",
    "no", "so", "do", "be", "by", "to", "or", "an", "of", "at",
    "is", "as", "ok", "oh", "tv", "pc", "dj", "vr", "ar", "hr",
    "pr", "ad", "id", "ex", "fx", "rx", "biz", "app", "pro",
    "hub", "lab", "net", "web", "dev", "pay", "top", "max", "new",
    "one", "all", "big", "eco", "bio", "geo", "fit", "pet", "car",
    "job", "tax", "law", "med", "vet", "art", "era", "zen", "the",
    "low", "hot", "sky", "sun", "run", "buy", "set", "cup", "box",
    "map", "win", "add", "bay", "bed", "bit", "bus", "cut",
    "day", "dig", "dry", "eat", "end", "eye", "fan", "fly", "fun",
    "gap", "gas", "got", "gun", "had", "has", "hat", "her", "him",
    "his", "hit", "ice", "its", "key", "kid", "lay", "led", "let",
    "lip", "log", "lot", "mad", "man", "may", "men", "mix", "mud",
    "nor", "not", "now", "nut", "odd", "off", "oil", "old",
    "out", "own", "pan", "pen", "per", "pin", "pit", "pop",
    "pot", "put", "ran", "raw", "red", "rid", "row", "rub", "sad",
    "sat", "saw", "say", "sea", "she", "sir", "sit", "six", "son",
    "sub", "sum", "ten", "tip", "ton", "too", "try", "two", "use",
    "van", "war", "was", "way", "wet", "who", "why", "won", "yes",
    "yet", "you", "zip",
}

def _smart_split(name):
    """Wrap wordninja.split to merge single-letter tokens if they form a known short word."""
    if not wordninja:
        return []
        
    wn_parts = wordninja.split(name)
    i = 0
    merged_parts = []
    while i < len(wn_parts):
        if i < len(wn_parts) - 1 and len(wn_parts[i]) == 1 and len(wn_parts[i+1]) == 1:
            combo = wn_parts[i] + wn_parts[i+1]
            if combo in _KNOWN_SHORT or combo in ALL_WORDS or combo in TIER1_WORDS:
                merged_parts.append(combo)
                i += 2
                continue
        merged_parts.append(wn_parts[i])
        i += 1
    return merged_parts

def _vowel_ratio(s):
    if not s: return 0.0
    letters = [c for c in s if c.isalpha()]
    if not letters: return 0.0
    return sum(1 for c in letters if c in _VOWELS) / len(letters)


def _max_consonant_run(s):
    run = best = 0
    for c in s:
        if c.isalpha() and c not in _VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _max_vowel_run(s):
    run = best = 0
    for c in s:
        if c in _VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _count_stuffing_tokens(name):
    """
    Count DISTINCT stuffing tokens. Suppresses substring overlap so
    "lawyers" doesn't simultaneously count as {"law", "lawyer", "lawyers"}.

    For each match we keep only the LONGEST token at each position.
    """
    # Find all (start, end, token) matches
    matches = []
    for tok in _STUFFING_TOKENS:
        i = 0
        while True:
            idx = name.find(tok, i)
            if idx < 0:
                break
            matches.append((idx, idx + len(tok), tok))
            i = idx + 1

    # Sort by start, then length descending (longest first at each start)
    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

    # Greedy non-overlapping selection (favor longest)
    chosen = []
    last_end = -1
    for start, end, tok in matches:
        if start >= last_end:
            chosen.append(tok)
            last_end = end
    return set(chosen)


def _has_pronounceable_segment(name, min_len=4):
    """Heuristic: does the name contain a pronounceable run of letters?"""
    # Strip non-letters then check vowel/consonant balance per chunk
    chunks = re.split(r'[^a-z]+', name.lower())
    for ch in chunks:
        if len(ch) >= min_len:
            vr = _vowel_ratio(ch)
            cr = _max_consonant_run(ch)
            if 0.20 <= vr <= 0.75 and cr <= 4:
                return True
    return False

def _run_ai_heuristics(name):
    """
    Uses a Local NLP AI model (Spacy) to evaluate domain grammatical coherence.
    Returns: penalty (int), warnings (list), rejections (list)
    """
    penalty = 0
    warnings = []
    rejections = []
    
    if not wordninja:
        return penalty, warnings, rejections
        
    try:
        words = _smart_split(name)
        if not words: return penalty, warnings, rejections
        
        # 1. Structural Complexity
        if len(words) >= 5:
            rejections.append("RJ_TOO_MANY_WORDS")
            penalty -= 30
            
        # 2. Local AI Syntactic Analysis (NLP)
        if nlp and len(words) > 1:
            # Join words to form a phrase for the NLP model
            phrase = " ".join(words)
            doc = nlp(phrase)
            
            # Extract Part-Of-Speech tags
            pos_tags = [token.pos_ for token in doc]
            
            # --- AI Rules for Grammatical Coherence & Stuffing ---
            
            # Rule A: Adjective Stuffing (e.g., "cheap best fast")
            if pos_tags.count("ADJ") >= 3:
                rejections.append("RJ_AI_ADJECTIVE_STUFFING")
                penalty -= 25
                
            # Rule B: Verb Stuffing (e.g., "buy get find")
            if pos_tags.count("VERB") >= 3 and pos_tags.count("NOUN") == 0:
                rejections.append("RJ_AI_VERB_STUFFING")
                penalty -= 25
                
            # Rule C: Noun Compounding Limit (e.g., "insurance lawyer doctor dentist")
            if pos_tags.count("NOUN") + pos_tags.count("PROPN") >= 4 and len(words) >= 4:
                consecutive_nouns = 0
                for pos in pos_tags:
                    if pos in ("NOUN", "PROPN"):
                        consecutive_nouns += 1
                        if consecutive_nouns >= 4:
                            rejections.append("RJ_AI_NOUN_STUFFING")
                            penalty -= 30
                            break
                    else:
                        consecutive_nouns = 0
                        
            # Rule D: Verb + Verb Conflict (e.g., "buy invest")
            if len(pos_tags) == 2 and pos_tags[0] == "VERB" and pos_tags[1] == "VERB":
                warnings.append("ai_grammar_verb_verb")
                penalty -= 15
                
            # Rule E: Meaningless Trailing Prepositions (e.g., "cars of", "shoes in")
            if len(pos_tags) >= 2 and pos_tags[-1] in ("ADP", "PART", "CCONJ", "DET"):
                warnings.append("ai_grammar_trailing_prep")
                penalty -= 10
                
    except Exception as e:
        logger.error(f"Local NLP AI error: {e}")
        
    return penalty, warnings, rejections


def evaluate_coherence(domain, kps_result=None, geo_info=None):
    """
    Universal coherence evaluation. Type-agnostic, niche-agnostic.

    Args:
        domain: full domain string (e.g. "miami-lawyers.com")
        kps_result: optional KPS dict (used only to detect exact-match
                    rescue — single-word matches bypass some structural rules)
        geo_info: optional geo dict — geo+niche compounds get a small allowance
                  for hyphens (e.g. "los-angeles-dentist" is a known pattern)

    Returns: dict (see module docstring)
    """
    if not domain or '.' not in domain:
        return _fail("invalid_domain")

    name = domain.lower().split('.')[0]
    if not name:
        return _fail("empty_name")

    rejection = []
    warnings = []
    score = 100  # start clean, deduct as issues emerge
    structural_penalty = 0

    kps_result = kps_result or {}
    best_match = (kps_result.get("best_match") or {})
    kps_match_type = best_match.get("match_type", "")
    kps_keyword = best_match.get("keyword", "")
    is_exact_kps = (kps_match_type == "exact" and kps_keyword == name)

    geo_info = geo_info or {}
    is_geo_compound = bool(geo_info.get("geo_found"))

    nlen = len(name)
    n_letters = sum(1 for c in name if c.isalpha())
    n_digits = sum(1 for c in name if c.isdigit())
    n_hyphens = name.count('-')

    # ── 1. STUFFING CHECK (universal — applies to ALL niches) ──
    stuffing = _count_stuffing_tokens(name)
    is_stuffed = len(stuffing) >= 3
    if is_stuffed:
        rejection.append("RJ_KEYWORD_STUFFING")
        score -= 60
        structural_penalty -= 12
    elif len(stuffing) == 2 and nlen > 18:
        warnings.append("multiple_commercial_keywords")
        score -= 15
        structural_penalty -= 4

    # ── 2. HYPHEN ABUSE ──
    if n_hyphens >= 2:
        rejection.append("RJ_MULTIPLE_HYPHENS")
        score -= 35
        structural_penalty -= 8
    elif n_hyphens == 1:
        # one hyphen is acceptable ONLY for legitimate geo+service compounds
        # (e.g. "new-york-dentist" — the hyphen disambiguates the city name)
        if is_geo_compound:
            warnings.append("hyphenated_geo_compound")
            score -= 5
            structural_penalty -= 2
        else:
            warnings.append("hyphen_present")
            score -= 15
            structural_penalty -= 5

    # ── 3. DIGIT ABUSE ──
    is_meaningful_num = _is_meaningful_number(name)
    if n_digits >= 3 and not is_meaningful_num:
        rejection.append("RJ_MANY_DIGITS")
        score -= 30
        structural_penalty -= 8
    elif n_digits >= 1 and nlen > 6 and not is_meaningful_num:
        warnings.append("digits_in_long_name")
        score -= 15
        structural_penalty -= 6
    elif n_digits >= 1 and nlen <= 6 and not is_meaningful_num:
        warnings.append("digits_in_short_name")
        score -= 5
        structural_penalty -= 2

    # ── 4. LENGTH SANITY ──
    if nlen > 24:
        rejection.append("RJ_TOO_LONG")
        score -= 30
        structural_penalty -= 8
    elif nlen > 20:
        warnings.append("very_long")
        score -= 15
        structural_penalty -= 5
    elif nlen > 16 and not is_geo_compound:
        warnings.append("long_name")
        score -= 8
        structural_penalty -= 3

    # ── 5. PRONOUNCEABILITY (skipped if exact KPS match — single real word) ──
    if not is_exact_kps:
        vr = _vowel_ratio(name)
        cr = _max_consonant_run(name)
        # If the cluster spans a compound word boundary, it's fine.
        # "healthpro" has "lthpr" (5 consonants) but is perfectly readable.
        # Split into known words and take the max cluster within each part.
        if cr >= 5:
            if try_split_compound:
                _comp = try_split_compound(name)
                if _comp:
                    _left, _right = _comp
                    cr = max(_max_consonant_run(_left), _max_consonant_run(_right))
        vrun = _max_vowel_run(name)
        if vr < 0.15 and nlen >= 4:
            rejection.append("RJ_NO_VOWELS")
            score -= 50
            structural_penalty -= 12
        elif vr < 0.20 and nlen >= 5:
            warnings.append("low_vowel_ratio")
            score -= 12
            structural_penalty -= 4
        if cr >= 5:
            rejection.append("RJ_CONSONANT_CLUSTER")
            score -= 35
            structural_penalty -= 8
        elif cr == 4:
            warnings.append("hard_consonant_cluster")
            score -= 8
            structural_penalty -= 3
        if vrun >= 4:
            warnings.append("vowel_cluster")
            score -= 6
            structural_penalty -= 2
        if not _has_pronounceable_segment(name):
            warnings.append("hard_to_pronounce")
            score -= 10

    # ── 5b. GIBBERISH SEGMENT DETECTION (wordninja-powered) ──
    # Catches names like "healthinsurancexqz" or "xqzinsuranceblah" where
    # real keywords are mixed with nonsense fragments. Wordninja splits
    # the name; any leftover fragment ≤3 chars that isn't a known short
    # word is likely gibberish padding.
    gibberish_segments = []
    _all_wn_parts_valid = False  # True when every wordninja segment is a real word
    if wordninja and nlen >= 6 and not is_exact_kps:
        wn_parts = _smart_split(name)
        if len(wn_parts) >= 2:
            # If every part is a legitimate word/abbreviation, the name is a clean
            # compound (e.g. "cloudnova", "zentrova") — skip gibberish detection.
            _all_valid = all(
                len(p) >= 4
                or p in _KNOWN_SHORT
                or p in ALL_WORDS
                or p in TIER1_WORDS
                for p in wn_parts
            )
            if _all_valid:
                _all_wn_parts_valid = True
            else:
                for part in wn_parts:
                    if len(part) <= 1:
                        # Single character fragments are almost always gibberish
                        gibberish_segments.append(part)
                    elif len(part) <= 3 and part not in _KNOWN_SHORT and part not in ALL_WORDS and part not in TIER1_WORDS:
                        gibberish_segments.append(part)

    # Only flag as gibberish if we found 2+ segments (one short fragment
    # could be a legitimate abbreviation) OR one fragment that is a
    # single non-vowel character.
    has_gibberish_filler = (
        not _all_wn_parts_valid
        and (
            len(gibberish_segments) >= 2
            or (len(gibberish_segments) == 1 and len(gibberish_segments[0]) == 1)
        )
    )
    if has_gibberish_filler:
        # Scale penalty: more gibberish segments = worse
        gib_count = len(gibberish_segments)
        gib_penalty = min(30, 12 * gib_count)
        score -= gib_penalty
        structural_penalty -= min(8, 3 * gib_count)
        warnings.append(f"gibberish_segments: {', '.join(gibberish_segments)}")

    # ── 6. KEYWORD-IN-WEAK-NAME (the user's #1 complaint) ──
    # If the name contains a high-CPC keyword AND simultaneously has bad
    # structure, the gate flags it as "incoherent". Downstream scoring
    # will then refuse to apply niche boosts.
    has_commercial_keyword = bool(stuffing) or bool(kps_keyword)
    has_bad_structure = (
        n_hyphens >= 1 and not is_geo_compound
    ) or (
        n_digits >= 2
    ) or (
        nlen > 22
    ) or (
        "RJ_NO_VOWELS" in rejection
    ) or (
        "RJ_CONSONANT_CLUSTER" in rejection
    ) or (
        has_gibberish_filler
    )

    is_incoherent = has_commercial_keyword and has_bad_structure and not is_exact_kps
    if is_incoherent:
        rejection.append("RJ_INCOHERENT_KEYWORD")
        score -= 25
        structural_penalty -= 6

    # ── 7. ALL-DIGIT OR DIGIT-DOMINATED ──
    if n_letters == 0:
        rejection.append("RJ_NO_LETTERS")
        score = 0
    elif n_digits > n_letters:
        rejection.append("RJ_DIGIT_DOMINATED")
        score -= 40
        structural_penalty -= 10

    # ── 8. AI SEMANTIC HEURISTICS (NLP) ──
    ai_penalty, ai_warnings, ai_rejections = _run_ai_heuristics(name)
    score += ai_penalty
    structural_penalty += ai_penalty
    warnings.extend(ai_warnings)
    rejection.extend(ai_rejections)

    # ── Normalize ──
    score = max(0, min(100, score))
    # Hard-fail rejection codes — any of these causes coherence to fail.
    # Includes both rule-based codes AND AI-detected structural problems.
    # Previously the AI codes (RJ_TOO_MANY_WORDS, RJ_AI_*_STUFFING) were
    # added to the rejection list but not checked here, so a domain with
    # NLP-detected noun/adjective/verb stuffing still "passed" the gate.
    passes = (score >= 40) and not any(
        c in rejection for c in (
            "RJ_KEYWORD_STUFFING", "RJ_MULTIPLE_HYPHENS", "RJ_MANY_DIGITS",
            "RJ_NO_LETTERS", "RJ_DIGIT_DOMINATED", "RJ_TOO_LONG",
            "RJ_NO_VOWELS", "RJ_CONSONANT_CLUSTER",
            # AI-detected structural problems (added in _run_ai_heuristics)
            "RJ_TOO_MANY_WORDS",
            "RJ_AI_ADJECTIVE_STUFFING",
            "RJ_AI_VERB_STUFFING",
            "RJ_AI_NOUN_STUFFING",
        )
    )

    return {
        "passes": passes,
        "coherence_score": score,
        "rejection_codes": rejection,
        "warnings": warnings,
        "is_keyword_stuffed": is_stuffed,
        "is_incoherent": is_incoherent,
        "stuffing_tokens": sorted(stuffing),
        "structural_penalty": structural_penalty,
        "hard_fail": not passes,
        "_degraded": _DEGRADED_MODE,
    }


def _is_meaningful_number(name):
    """Detect intentional numeric branding patterns like '7eleven', '247support'.
    These are legitimate brand patterns and should not be penalized.
    """
    # Common meaningful-number patterns (24/7, 365 days, 411, etc.)
    _MEANINGFUL = ("247", "365", "411", "911", "404", "100")
    for num in _MEANINGFUL:
        if name == num or name.startswith(num) or name.endswith(num):
            # Only treat as meaningful if surrounded by letters (not pure digits)
            stripped = name.replace(num, '', 1)
            if stripped and stripped.isalpha():
                return True
            if name == num:
                return True
    if re.match(r'^[1-9]\d?[a-z]+$', name):       # 7eleven, 24hours
        return True
    if re.match(r'^[a-z]+[1-9]\d?$', name):       # cloud9, club7
        return True
    return False


def _fail(reason):
    return {
        "passes": False,
        "coherence_score": 0,
        "rejection_codes": [reason],
        "warnings": [],
        "is_keyword_stuffed": False,
        "is_incoherent": False,  # Invalid/empty input ≠ incoherent keyword combo
        "stuffing_tokens": [],
        "structural_penalty": -20,
        "hard_fail": True,
        "_degraded": _DEGRADED_MODE,
    }
