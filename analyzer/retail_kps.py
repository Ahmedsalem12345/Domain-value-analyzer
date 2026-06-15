"""
Retail Keyword Power Score (KPS) v2 — Rebuilt per KPS_ENGINE_REBUILD_PROMPT.md

Key fixes vs v1:
  - Weighted Interval Scheduling replaces brute substring scan (no more overlapping tokens)
  - Log-scaled signal replaces hardcoded tier tables
  - BEST + controlled combo boost replaces SUM aggregation
  - kps_confidence (0-1) added everywhere
  - 0-100 score scale (kps_score_legacy kept at 0-30 for DB backward compat)
  - Newer CSV loaded first; falls back to data/retailstats.csv
"""
import copy
import csv
import math
import logging
import threading
from functools import lru_cache
from pathlib import Path

try:
    import ahocorasick
    _HAS_AC = True
except ImportError:
    _HAS_AC = False

logger = logging.getLogger("analyzer.retail_kps")

# ── Data file paths ─────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_DATA_FILE_PRIMARY  = _ROOT / "retailstats_20260427.csv"
_DATA_FILE_FALLBACK = _ROOT / "data" / "retailstats.csv"

_KW_DATA: dict = {}         # kw → {exact/start/end/middle: {sale_count,price_*}}
_KEYWORD_SET: set = set()
_KEYWORDS_BY_LEN: list = [] # sorted longest-first for greedy scan (fallback)
_AUTOMATON = None            # Aho-Corasick automaton (primary, 50x faster)
_loaded = False
_load_lock = threading.Lock()   # prevents concurrent load races (prewarm vs first request)

# Derived-form maps (populated during _load)
_NOSPACE_MAP: dict = {}  # "realestate" → "real estate"  (multi-word → joined)
_MORPH_MAP:   dict = {}  # "lawyers"    → "lawyer"        (inflected → base)


# ── Token lists ──────────────────────────────────────────────────────────────

STOPWORDS = frozenset({
    'the', 'a', 'an', 'my', 'i', 'we', 'our', 'your', 'of', 'for', 'to',
    'in', 'on', 'and', 'or', 'but', 'is', 'are', 'be', 'it', 'this', 'that',
    'with', 'from', 'by', 'as', 'at', 'not', 'no', 'so', 'do', 'if', 'up',
    'out', 'go', 'can', 'will', 'just', 'its',
    # Personal pronouns — never commercially meaningful as domain keywords
    'you', 'me', 'us', 'him', 'her', 'them', 'they', 'he', 'she',
    # Common verbs with no domain investment signal
    'want', 'wants', 'need', 'needs', 'love', 'loves', 'like', 'likes',
    'make', 'makes', 'take', 'takes', 'give', 'gives', 'know', 'knows',
    # Audit: generic / TLD-like words (NOT commercially valuable words)
    'online', 'web', 'site', 'www', 'com', 'net',
    'org', 'info', 'page', 'home', 'inc', 'llc', 'co', 'usa',
    'la', 'ny', 'sf', 'dc',
})

MEANINGFUL_SHORT = frozenset({
    'ai', 'vr', 'ar', 'ev', 'hr', 'tv', 'uk', 'us', 'eu',
    # Audit: high-value short keywords
    'io', 'app', 'pro', 'fit', 'tax', 'law', 'med', 'car', 'job', 'pet',
    'day', 'fun', 'hub', 'box', 'pay', 'dna', 'vip', 'gps', 'led', 'seo',
})

COMMON_INFLATED_WORDS = frozenset({
    'online', 'web', 'site', 'page', 'home', 'best', 'top', 'free',
    'now', 'new', 'pro', 'plus', 'hub', 'zone', 'world', 'land',
    'app', 'apps', 'info', 'net', 'one', 'first', 'live',
    'find', 'get',
})

POSITION_WEIGHTS = {
    'exact':  1.00,
    'start':  0.70,
    'end':    0.75,
    'middle': 0.35,
}

GEO_KEYWORDS = frozenset({
    # USA — major metros
    'miami', 'chicago', 'houston', 'phoenix', 'dallas', 'seattle', 'denver',
    'boston', 'atlanta', 'detroit', 'vegas', 'austin', 'portland', 'nashville',
    'newyork', 'losangeles', 'sanfrancisco', 'sandiego', 'philadelphia',
    'charlotte', 'orlando', 'tampa', 'minneapolis', 'brooklyn', 'manhattan',
    # USA — states
    'florida', 'texas', 'california', 'illinois', 'georgia', 'ohio',
    'minnesota', 'arizona', 'colorado', 'washington', 'nevada', 'oregon',
    'michigan', 'virginia', 'carolina', 'indiana', 'tennessee',
    # UK & Europe
    'london', 'manchester', 'birmingham', 'liverpool', 'edinburgh', 'glasgow',
    'paris', 'berlin', 'hamburg', 'munich', 'frankfurt', 'cologne',
    'amsterdam', 'rotterdam', 'brussels', 'antwerp', 'vienna', 'zurich',
    'geneva', 'madrid', 'barcelona', 'seville', 'rome', 'milan', 'naples',
    'florence', 'stockholm', 'oslo', 'copenhagen', 'helsinki', 'lisbon',
    'prague', 'budapest', 'warsaw', 'athens',
    # Middle East (Arab)
    'dubai', 'abudhabi', 'sharjah', 'ajman',   # UAE
    'riyadh', 'jeddah', 'mecca', 'medina', 'dammam', 'khobar',  # Saudi Arabia
    'doha', 'qatar',                            # Qatar
    'kuwait', 'manama', 'bahrain',              # Gulf
    'muscat', 'oman',                           # Oman
    'cairo', 'alexandria', 'giza',              # Egypt
    'amman', 'jordan',                          # Jordan
    'beirut', 'lebanon',                        # Lebanon
    'casablanca', 'rabat', 'marrakech',         # Morocco
    'tunis', 'algiers',                         # North Africa
    'baghdad', 'basra',                         # Iraq
    # Asia Pacific
    'singapore', 'hongkong', 'tokyo', 'osaka', 'kyoto',
    'seoul', 'busan', 'shanghai', 'beijing', 'shenzhen', 'guangzhou',
    'taipei', 'bangkok', 'kualalumpur', 'jakarta', 'manila',
    'mumbai', 'delhi', 'bangalore', 'hyderabad', 'chennai', 'pune',
    'karachi', 'lahore', 'islamabad',
    # Canada & Oceania
    'toronto', 'vancouver', 'montreal', 'calgary', 'ottawa',
    'sydney', 'melbourne', 'brisbane', 'perth', 'auckland',
    # Africa
    'capetown', 'johannesburg', 'lagos', 'nairobi', 'accra', 'dakar',
    # Latin America
    'saopaulo', 'rio', 'buenosaires', 'bogota', 'lima',
    'mexicocity', 'guadalajara', 'monterrey', 'santiago',
})

SERVICE_KEYWORDS = frozenset({
    'plumbing', 'dentist', 'dental', 'lawyer', 'attorney', 'insurance',
    'accounting', 'realtor', 'realty', 'mortgage', 'healthcare', 'medical',
    'roofing', 'flooring', 'painting', 'cleaning', 'moving', 'storage',
    'pest', 'hvac', 'solar', 'electric', 'electrician', 'locksmith',
    'landscaping', 'catering', 'pharmacy', 'clinic', 'hospital',
})

COMMERCIAL_KEYWORDS = frozenset({
    'insurance', 'mortgage', 'loan', 'credit', 'finance', 'invest',
    'casino', 'poker', 'crypto', 'bitcoin', 'realestate', 'realtor',
    'healthcare', 'medical', 'pharmacy', 'legal', 'attorney', 'lawyer',
    'hotel', 'travel', 'flights', 'cars', 'auto', 'dealer',
    'shop', 'store', 'market', 'trade', 'buy', 'sell',
})

TREND_KEYWORDS = frozenset({
    'ai', 'ml', 'crypto', 'bitcoin', 'blockchain', 'nft', 'defi', 'web3',
    'ev', 'solar', 'vr', 'ar', 'metaverse', 'saas', 'cloud',
})

# Piecewise mapping: raw signal → KPS score 0-100
# Calibrated against real retailstats percentile distribution (Apr 2026)
_BREAKPOINTS = [
    (0.00,   0),
    (0.25,  15),
    (0.35,  35),
    (0.45,  55),
    (0.55,  72),
    (0.70,  88),
    (0.85,  95),
    (1.10, 100),
]


# ── Morphological variant generator (used by _load) ─────────────────────────

def _add_morph_variants(kw: str, data: dict) -> None:
    """
    For a base keyword already in _KW_DATA, index its most common inflected forms
    so that domain names containing those forms still receive full scoring credit.

    Conservative set — only patterns that are unambiguous in domain naming:
      lawyer   → lawyers          (plural +s)
      attorney → attorneys        (plural +s)
      mortgage → mortgages        (plural +s  on -e words)
      clean    → cleaning/cleaner/cleaners  (service gerunds)
      paint    → painting/painter/painters
      manage   → managing         (drop-e gerund)
      insure   → insuring/insurer/insures/insured
    """
    global _MORPH_MAP

    def _add(variant: str) -> None:
        if len(variant) >= 3 and variant not in _KW_DATA:
            _KW_DATA[variant] = data
            _MORPH_MAP[variant] = kw

    last = kw[-1]

    # ── Plural ──────────────────────────────────────────────────────
    if last not in ('s', 'x', 'z') and not kw.endswith('ing'):
        if last == 'y' and len(kw) >= 5 and kw[-2] not in 'aeiou':
            _add(kw[:-1] + 'ies')   # city→cities, boundary→boundaries
        elif last == 'e':
            _add(kw + 's')           # manage → manages, insure → insures
        elif kw.endswith('ch') or kw.endswith('sh') or kw.endswith('ss'):
            _add(kw + 'es')          # search → searches, brush → brushes
        else:
            _add(kw + 's')           # lawyer → lawyers, loan → loans

    # ── Gerund / progressive ────────────────────────────────────────
    if not kw.endswith('ing') and not kw.endswith('er') and len(kw) >= 4:
        if last == 'e' and len(kw) >= 5:
            _add(kw[:-1] + 'ing')    # manage→managing, insure→insuring
            _add(kw[:-1] + 'ed')     # manage→managed,  insure→insured
        elif last not in 'aeiou':
            _add(kw + 'ing')         # clean→cleaning, paint→painting, roof→roofing
            _add(kw + 'ed')          # clean→cleaned,  paint→painted

    # ── Agent noun ──────────────────────────────────────────────────
    if not kw.endswith('er') and not kw.endswith('ing') and len(kw) >= 4:
        if last == 'e':
            _add(kw[:-1] + 'er')     # insure→insurer,  manage→manager
            _add(kw[:-1] + 'ers')    # insure→insurers, manage→managers
        elif last not in 'aeiou':
            _add(kw + 'er')          # clean→cleaner,   paint→painter
            _add(kw + 'ers')         # clean→cleaners,  paint→painters


# ── Loader ───────────────────────────────────────────────────────────────────

def _load():
    global _KW_DATA, _KEYWORD_SET, _KEYWORDS_BY_LEN, _AUTOMATON, _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:  # double-check after acquiring lock
            return

        data_file = _DATA_FILE_PRIMARY if _DATA_FILE_PRIMARY.exists() else _DATA_FILE_FALLBACK

        try:
            with open(data_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    kw = row["keyword"].strip().lower()
                    if not kw or kw in STOPWORDS:
                        continue
                    _KW_DATA[kw] = {
                        "exact": {
                            "sale_count":   int(float(row.get("exact_sale_count",  0) or 0)),
                            "price_sum":  float(row.get("exact_price_sum",    0) or 0),
                            "price_avg":  float(row.get("exact_price_avg",    0) or 0),
                            "price_max":  float(row.get("exact_price_max",    0) or 0),
                            "price_stddev": float(row.get("exact_price_stddev", 0) or 0),
                        },
                        "start": {
                            "sale_count":   int(float(row.get("start_sale_count",  0) or 0)),
                            "price_sum":  float(row.get("start_price_sum",    0) or 0),
                            "price_avg":  float(row.get("start_price_avg",    0) or 0),
                            "price_max":  float(row.get("start_price_max",    0) or 0),
                            "price_stddev": float(row.get("start_price_stddev", 0) or 0),
                        },
                        "end": {
                            "sale_count":   int(float(row.get("end_sale_count",  0) or 0)),
                            "price_sum":  float(row.get("end_price_sum",    0) or 0),
                            "price_avg":  float(row.get("end_price_avg",    0) or 0),
                            "price_max":  float(row.get("end_price_max",    0) or 0),
                            "price_stddev": float(row.get("end_price_stddev", 0) or 0),
                        },
                        "middle": {
                            "sale_count":   int(float(row.get("middle_sale_count",  0) or 0)),
                            "price_sum":  float(row.get("middle_price_sum",    0) or 0),
                            "price_avg":  float(row.get("middle_price_avg",    0) or 0),
                            "price_max":  float(row.get("middle_price_max",    0) or 0),
                            "price_stddev": float(row.get("middle_price_stddev", 0) or 0),
                        },
                    }
            base_count = len(_KW_DATA)

            # ── Nospace variants: "real estate" → index "realestate" ──
            # Allows compound domains (no spaces/hyphens) to match multi-word CSV entries.
            for kw in list(_KW_DATA.keys()):
                if ' ' in kw:
                    nospace = kw.replace(' ', '')
                    if len(nospace) >= 3 and nospace not in _KW_DATA:
                        _KW_DATA[nospace] = _KW_DATA[kw]
                        _NOSPACE_MAP[nospace] = kw

            # ── Morphological variants: "lawyer" → index "lawyers", "cleaning" etc ──
            # Covers the most common domain-name patterns: plurals and gerunds.
            for kw in list(_KW_DATA.keys()):
                if kw in STOPWORDS or len(kw) < 4 or ' ' in kw:
                    continue
                _add_morph_variants(kw, _KW_DATA[kw])

            added = len(_KW_DATA) - base_count
            _KEYWORD_SET = set(_KW_DATA)
            _KEYWORDS_BY_LEN = sorted(_KEYWORD_SET, key=len, reverse=True)
            # Build Aho-Corasick automaton for O(n) keyword matching
            _AUTOMATON = _build_automaton(_KEYWORD_SET)
            _loaded = True
            logger.info(
                "Retail KPS v2: loaded %d base + %d derived (%d nospace, %d morph) "
                "keywords from %s (AC=%s)",
                base_count, added, len(_NOSPACE_MAP), len(_MORPH_MAP),
                data_file.name, 'yes' if _AUTOMATON else 'fallback',
            )
        except FileNotFoundError:
            logger.warning(
                "┌─────────────────────────────────────────────────────────┐\n"
                "│  RETAIL KPS DATA FILE NOT FOUND — KPS SCORING DISABLED  │\n"
                "│  Expected: %s\n"
                "│  Fallback: %s\n"
                "│  All domains will score 0 for KPS-based price anchoring. │\n"
                "└─────────────────────────────────────────────────────────┘",
                _DATA_FILE_PRIMARY, _DATA_FILE_FALLBACK,
            )
            _loaded = True
        except Exception as exc:
            # Mark as loaded even on error to prevent infinite retry on every domain call.
            # Partial data is cleared to avoid serving a half-populated dict.
            logger.error(
                "Retail KPS load error: %s — KPS disabled for this session to prevent "
                "retry loop. Restart the app to retry loading.",
                exc, exc_info=True,
            )
            _KW_DATA.clear()
            _KEYWORD_SET = set()
            _KEYWORDS_BY_LEN = []
            _loaded = True


# ── Token helpers ────────────────────────────────────────────────────────────

def _is_inside_stopword(name: str, start: int, end: int) -> bool:
    """Check if the token at name[start:end] is a fragment of a STOPWORD in the domain."""
    token_len = end - start
    for sw in STOPWORDS:
        if token_len >= len(sw): continue
        idx = 0
        while True:
            pos = name.find(sw, idx)
            if pos == -1: break
            if pos <= start and pos + len(sw) >= end:
                return True
            idx = pos + 1
    return False

try:
    from analyzer.word_data import ALL_WORDS as _SKIP_ALL_WORDS
except ImportError:
    _SKIP_ALL_WORDS = set()


def _get_segment_boundaries(name: str) -> frozenset:
    """
    Return the set of character positions that are natural word boundaries.
    Position 0 = domain start, len(name) = domain end.
    Positions immediately before/after a hyphen are also boundaries.

    Example: "car-insurance" → {0, 3, 4, 13}
    """
    b = {0, len(name)}
    for i, c in enumerate(name):
        if c == '-':
            b.add(i)       # right before hyphen
            b.add(i + 1)   # right after hyphen
    return frozenset(b)


def _normalize_to_known(token: str) -> str:
    """
    Map an inflected token to its best matching base form in _KW_DATA.
    Only activates when the original token has NO entry — avoids overriding real hits.

    Handles: plural -s/-es, agentive -er/-ers, gerund -ing, past -ed.
    Returns the original token unchanged when no normalised form is found.
    """
    if token in _KW_DATA:
        return token
    t = token

    # plural -s  (lawyers → lawyer, mortgages → mortgage)
    if t.endswith('s') and len(t) > 4:
        base = t[:-1]
        if base in _KW_DATA:
            return base

    # plural -es  (searches → search)
    if t.endswith('es') and len(t) > 5:
        base = t[:-2]
        if base in _KW_DATA:
            return base

    # agentive -ers  (cleaners → cleaner → clean)
    if t.endswith('ers') and len(t) > 6:
        if t[:-1] in _KW_DATA:   return t[:-1]   # cleaners → cleaner
        if t[:-3] in _KW_DATA:   return t[:-3]   # cleaners → clean

    # agentive -er  (cleaner → clean, manager → manage)
    if t.endswith('er') and len(t) > 5:
        if t[:-2] in _KW_DATA:   return t[:-2]   # cleaner → clean
        if t[:-2] + 'e' in _KW_DATA: return t[:-2] + 'e'  # manager → manage

    # gerund -ing  (cleaning → clean, managing → manage)
    if t.endswith('ing') and len(t) > 6:
        base = t[:-3]
        if base in _KW_DATA:         return base
        if base + 'e' in _KW_DATA:   return base + 'e'

    # past -ed  (insured → insure, managed → manage)
    if t.endswith('ed') and len(t) > 5:
        if t[:-2] in _KW_DATA:       return t[:-2]
        if t[:-2] + 'e' in _KW_DATA: return t[:-2] + 'e'
        if t[:-1] in _KW_DATA:       return t[:-1]   # moved → move

    return token


def _should_skip_token(token: str, name: str = "", start: int = -1, end: int = -1,
                       boundaries: frozenset = None) -> bool:
    if token in STOPWORDS:
        return True
    if len(token) == 1:
        return True

    # Determine whether this match sits on natural word boundaries
    at_both = (boundaries and start >= 0 and end >= 0
               and start in boundaries and end in boundaries)

    # ── 2-char tokens ──────────────────────────────────────────────
    if len(token) == 2 and token not in MEANINGFUL_SHORT:
        d = _KW_DATA.get(token, {})
        total = sum(d.get(p, {}).get("sale_count", 0) for p in ("exact", "start", "end", "middle"))
        if total < 10:
            return True
        # Mid-fragment 2-char tokens need very high sales to be credible
        if not at_both and total < 50:
            return True

    # ── 3-char tokens ──────────────────────────────────────────────
    if len(token) == 3 and token not in MEANINGFUL_SHORT and token not in _SKIP_ALL_WORDS:
        d = _KW_DATA.get(token, {})
        total = sum(d.get(p, {}).get("sale_count", 0) for p in ("exact", "start", "end", "middle"))
        if total < 30:
            return True
        # Embedded 3-char fragments (e.g. "car" inside "careful") need 100+ sales
        if not at_both and total < 100:
            return True

    # ── 4-char tokens not at any boundary ──────────────────────────
    # Prevents tokens like "real" (inside "realtor") from competing with "realtor"
    if len(token) == 4 and boundaries and start >= 0 and end >= 0:
        if start not in boundaries and end not in boundaries:
            d = _KW_DATA.get(token, {})
            total = sum(d.get(p, {}).get("sale_count", 0) for p in ("exact", "start", "end", "middle"))
            if total < 20:
                return True

    return False


def _keyword_strength(kw: str) -> float:
    """
    Raw strength used as WIS weight (log-scale total volume × best price).
    Falls back to the normalised base form when the inflected form has no data.
    """
    lookup = _normalize_to_known(kw)
    d = _KW_DATA.get(lookup)
    if not d:
        return 0.0
    total_cnt = sum(d[p]["sale_count"] for p in ("exact", "start", "end", "middle"))
    max_avg   = max(d[p]["price_avg"]   for p in ("exact", "start", "end", "middle"))
    if total_cnt == 0 or max_avg == 0:
        return 0.0
    return math.log1p(total_cnt) * math.log1p(max_avg)


# ── Weighted Interval Scheduling DP ─────────────────────────────────────────

def _wis(matches: list) -> list:
    """
    Non-overlapping keyword selection that maximises total weight.
    Standard weighted interval scheduling via DP + binary search.
    """
    if not matches:
        return []
    s = sorted(matches, key=lambda x: x["end"])
    n = len(s)
    ends = [x["end"] for x in s]

    def last_non_overlap(i):
        lo, hi = 0, i - 1
        while lo <= hi:
            mid_idx = (lo + hi) // 2
            if ends[mid_idx] <= s[i]["start"]:
                if mid_idx == i - 1 or ends[mid_idx + 1] > s[i]["start"]:
                    return mid_idx
                lo = mid_idx + 1
            else:
                hi = mid_idx - 1
        return -1

    dp = [0.0] * (n + 1)
    for i in range(1, n + 1):
        p = last_non_overlap(i - 1)
        include = s[i - 1]["weight"] + (dp[p + 1] if p >= 0 else 0)
        dp[i] = max(dp[i - 1], include)

    # Backtrack
    selected, i = [], n
    while i > 0:
        p = last_non_overlap(i - 1)
        include = s[i - 1]["weight"] + (dp[p + 1] if p >= 0 else 0)
        if include >= dp[i - 1]:
            selected.append(s[i - 1])
            i = p + 1
        else:
            i -= 1

    selected.sort(key=lambda x: x["start"])
    return selected


# ── Aho-Corasick Automaton Builder ───────────────────────────────────────────

def _build_automaton(keyword_set):
    """Build Aho-Corasick automaton from keyword set. Returns None if library unavailable."""
    global _AUTOMATON
    if not _HAS_AC:
        logger.info("pyahocorasick not installed — using fallback keyword scan")
        return None
    try:
        A = ahocorasick.Automaton()
        for kw in keyword_set:
            if len(kw) >= 2:
                A.add_word(kw, kw)
        A.make_automaton()
        return A
    except Exception as e:
        logger.warning("Failed to build Aho-Corasick automaton: %s", e)
        return None


# ── Keyword Extraction ───────────────────────────────────────────────────────

def extract_keywords(sld: str) -> list:
    """
    Parse SLD into non-overlapping keywords using RetailStats-aware WIS.
    Uses Aho-Corasick automaton for O(n) matching instead of O(96K) full scan.
    Returns list of {keyword, start, end, position}.
    """
    _load()
    if not _KW_DATA:
        return []

    name = sld.lower().strip().split('.')[0]
    n    = len(name)

    # Pre-compute natural segment boundaries (start/end of domain + hyphen edges)
    seg_bounds = _get_segment_boundaries(name)

    # ── Exact match fast-path ────────────────────────────────────────────────
    # If the whole SLD (or its normalized form) is a known keyword with enough
    # sales, return immediately — no need for compound splitting.
    # "lawyers" → normalises to "lawyer" if "lawyers" not in _KW_DATA directly.
    _has_exact_fallback = False
    exact_result        = None

    _exact_kw = name if name in _KW_DATA else _normalize_to_known(name)
    if _exact_kw in _KW_DATA and not _should_skip_token(_exact_kw, name, 0, n, seg_bounds):
        exact_data  = _KW_DATA[_exact_kw]
        exact_sales = exact_data.get("exact", {}).get("sale_count", 0)
        total_sales = sum(exact_data[p]["sale_count"]
                          for p in ("exact", "start", "end", "middle"))
        # Only skip compound-split when:
        #   1. Strong explicit domain-exact sales data (keyword IS its own category)
        #   2. AND the keyword has meaningful market strength (not just a CSV stub)
        # This prevents weak compound entries like "realestate" (low data) from
        # blocking the superior split "real"+"estate" (both high-value keywords).
        exact_strength = _keyword_strength(_exact_kw)
        if exact_sales > 10 and total_sales > 50 and exact_strength > 30.0:
            return [{"keyword": _exact_kw, "start": 0, "end": n, "position": "exact"}]
        # Weak or moderate direct match: save as fallback, also try compound splitting.
        exact_result        = [{"keyword": _exact_kw, "start": 0, "end": n, "position": "exact"}]
        _has_exact_fallback = True

    # ── Candidate generation ─────────────────────────────────────────────────
    # For each match we compute a boundary-aware weight so that:
    #   • keywords aligned to natural segment edges get a 2.5× bonus
    #   • keywords at one edge get a 1.4× bonus
    #   • mid-fragment keywords (e.g. "car" inside "careful") get no bonus
    # This makes WIS strongly prefer meaningful full-segment keywords.
    candidates = []

    def _make_candidate(kw: str, start_pos: int, end_pos: int) -> None:
        """Validate a keyword match and append to candidates with boundary weight."""
        kw_len = len(kw)
        norm   = _normalize_to_known(kw)        # base form for strength/data
        if _should_skip_token(kw, name, start_pos, end_pos, seg_bounds):
            return
        if _is_inside_stopword(name, start_pos, end_pos):
            return
        strength = _keyword_strength(norm)
        if strength <= 0:
            return
        at_start = start_pos in seg_bounds
        at_end   = end_pos   in seg_bounds
        boundary_mult = 2.5 if (at_start and at_end) else 1.4 if (at_start or at_end) else 1.0
        weight = (kw_len ** 1.5) * (1 + math.log1p(strength)) * boundary_mult
        # Store the normalised form so _score_token has correct data, but keep
        # original display name via a separate field.
        candidates.append({
            "keyword": norm,         # base form used for scoring
            "display": kw,           # original form found in domain
            "start":   start_pos,
            "end":     end_pos,
            "weight":  weight,
        })

    if _AUTOMATON is not None:
        for end_pos, kw in _AUTOMATON.iter(name):
            kw_len    = len(kw)
            start_pos = end_pos - kw_len + 1
            _make_candidate(kw, start_pos, end_pos + 1)
    else:
        for kw in _KEYWORDS_BY_LEN:
            if len(kw) > n or len(kw) < 2:
                continue
            idx = 0
            while True:
                pos = name.find(kw, idx)
                if pos == -1:
                    break
                _make_candidate(kw, pos, pos + len(kw))
                idx = pos + 1

    best_combo = _wis(candidates)

    def _assign_positions(combo):
        out = []
        for m in combo:
            s, e = m["start"], m["end"]
            if s == 0 and e == n:     pos = "exact"
            elif s == 0:              pos = "start"
            elif e == n:              pos = "end"
            else:                     pos = "middle"
            out.append({
                "keyword":  m["keyword"],
                "display":  m.get("display", m["keyword"]),
                "start":    s,
                "end":      e,
                "position": pos,
            })
        return out

    result = _assign_positions(best_combo)

    # ── Compound vs. exact comparison ───────────────────────────────────────
    if _has_exact_fallback and exact_result:
        exact_strength = _keyword_strength(_exact_kw)

        # When WIS selected the full-domain match (len==1), we must also try a
        # forced compound split by excluding any candidate that spans the entire
        # domain.  This prevents a weak "realestate" entry from blocking the
        # superior "real"+"estate" combination.
        sub_candidates = [c for c in candidates
                          if not (c["start"] == 0 and c["end"] == n)]
        sub_combo = _wis(sub_candidates) if sub_candidates else []
        sub_result = _assign_positions(sub_combo) if sub_combo else []

        # Prefer compound result when it is meaningfully stronger
        best_compound = sub_result if (len(sub_result) > 1
                                       or (sub_result and len(sub_result) >= 1))  \
                        else result

        if best_compound and len(best_compound) >= 1:
            compound_strength = sum(_keyword_strength(m["keyword"]) for m in best_compound)
            # Genuine multi-word split (e.g. "real"+"estate") uses 1.2× threshold.
            # Single sub-word substitute (e.g. "mortgage" replacing "mortgages") needs
            # 2.0× — otherwise a stronger base form incorrectly displaces the whole-domain
            # exact match and drops the position from "exact" to "start".
            compound_threshold = 1.2 if len(best_compound) > 1 else 2.0
            if compound_strength > exact_strength * compound_threshold:
                return best_compound   # compound split is clearly stronger

        return exact_result

    return result


# ── Per-keyword Signal ───────────────────────────────────────────────────────

def _score_token(token: str, position: str) -> dict:
    """
    Compute signal (0-1) and confidence (0-1) from retailstats data.
    Applies log-scaling + CV-based price dampening (spec section 3.2).

    ``token`` is already the normalised base form from extract_keywords.
    We still attempt _normalize_to_known as a last-resort safety net for
    any token that slipped through without normalisation.
    """
    lookup = token if token in _KW_DATA else _normalize_to_known(token)
    if lookup not in _KW_DATA:
        return {"signal": 0.0, "confidence": 0.0, "token": token,
                "sale_count": 0, "total_sales": 0, "total_volume": 0,
                "price_avg": 0, "price_max": 0,
                "price_stddev": 0, "price_sum": 0, "position": position,
                "position_weight": 0.0, "cv": 0.0, "price_est": 0.0}

    d = _KW_DATA[lookup]

    # Total sales evidence across ALL positions (full market validation)
    total_sales  = sum(d[p]["sale_count"] for p in ("exact", "start", "end", "middle"))
    total_volume = sum(d[p]["price_sum"]  for p in ("exact", "start", "end", "middle"))

    pos_key = position  # "exact"/"start"/"end"/"middle"
    stats   = d[pos_key]
    n       = stats["sale_count"]
    pw      = POSITION_WEIGHTS.get(position, 0.35)

    # Fallback to best available position if no sales here
    if n == 0:
        best_pos = max(("exact", "start", "end", "middle"),
                       key=lambda p: d[p]["sale_count"] * d[p]["price_avg"])
        fb = d[best_pos]
        if fb["sale_count"] == 0:
            return {"signal": 0.0, "confidence": 0.0, "token": token,
                    "sale_count": 0, "total_sales": 0, "total_volume": 0,
                    "price_avg": 0, "price_max": 0,
                    "price_stddev": 0, "price_sum": 0, "position": position,
                    "position_weight": 0.0, "cv": 0.0, "price_est": 0.0}
        stats, n = fb, fb["sale_count"]
        pw = POSITION_WEIGHTS.get(best_pos, 0.35) * 0.5

    avg    = stats["price_avg"]
    stddev = stats["price_stddev"]
    maxp   = stats["price_max"]
    psum   = stats["price_sum"]
    cv     = (stddev / avg) if avg > 0 else 0

    # ── Robust Mean Calculation (Outlier Mitigation) ──
    # Domain prices follow a Power Law. One massive $1M sale can inflate a $100 keyword.
    avg_robust = avg
    if n >= 3 and maxp > 0:
        sum_without_max = psum - maxp
        if sum_without_max > 0:
            avg_without_max = sum_without_max / (n - 1)
            # If the max price is more than 5x the average of the rest, it's an extreme outlier
            if maxp > (avg_without_max * 5):
                # Logarithmic dampening of the max price to prevent distortion
                # Instead of blending with the flawed 'avg' (which contains the extreme maxp),
                # we add a logarithmic bonus based on the max price to the robust mean.
                bonus = avg_without_max * (math.log10(maxp / avg_without_max) if maxp > avg_without_max else 0)
                avg_robust = avg_without_max + (bonus * 0.5)

    # CV dampening — but relax for well-sampled keywords (high n = reliable avg)
    # NOTE: In domain markets, high CV is natural (same keyword sells $100–$100k
    # depending on TLD, length, etc.), so we relax thresholds vs. traditional stats.
    cv_dampen = 1.0
    if cv > 2.0:
        cv_dampen = 0.45   # was 0.35 — less aggressive for domain markets
    elif cv > 1.0:
        cv_dampen = 0.70   # was 0.60
    # With enough sales, the average is reliable even with high CV
    if total_sales >= 15:
        cv_dampen = max(cv_dampen, 0.80)   # was 30 → 0.75
    elif total_sales >= 8:
        cv_dampen = max(cv_dampen, 0.65)   # was 15 → 0.60
    price_est = avg_robust * cv_dampen

    # Use TOTAL sales across all positions for count_factor (full market evidence)
    count_factor  = min(math.log1p(total_sales) / math.log1p(60), 1.0)
    price_factor  = min(math.log1p(price_est) / math.log1p(100_000), 1.0)
    upside_factor = min(math.log1p(maxp) / math.log1p(1_000_000), 1.0)

    signal = (count_factor * 0.30 + price_factor * 0.40 + upside_factor * 0.10) * pw

    # Market depth bonus based on total volume across ALL positions
    if total_volume > 0:
        signal += min(math.log1p(total_volume) / math.log1p(10_000_000), 1.0) * 0.05

    # Confidence based on total sales (full market evidence)
    if total_sales >= 10:
        confidence = 1.0
    elif total_sales >= 5:
        confidence = 0.80
    elif total_sales >= 3:
        confidence = 0.60
    elif total_sales >= 2:
        confidence = 0.40
    elif total_sales >= 1:
        confidence = 0.20
    else:
        confidence = 0.0

    # CV-based confidence reduction — but only for low-sample keywords
    if cv > 1.5 and total_sales < 20:
        confidence *= 0.7

    return {
        "token":           token,
        "signal":          min(signal, 1.0),
        "confidence":      confidence,
        "sale_count":      n,
        "total_sales":     total_sales,
        "total_volume":    total_volume,
        "price_avg":       avg,
        "price_max":       maxp,
        "price_stddev":    stddev,
        "price_sum":       psum,
        "price_est":       price_est,
        "cv":              cv,
        "position":        position,
        "position_weight": pw,
    }


# ── Weak Keyword Penalties ───────────────────────────────────────────────────

def _apply_weak_penalties(token_scores: list) -> list:
    for ts in token_scores:
        d = _KW_DATA.get(ts["token"], {})
        total = sum(d.get(p, {}).get("sale_count", 0)
                    for p in ("exact", "start", "end", "middle"))
        if total <= 1:
            ts["signal"] *= 0.30
        elif total <= 3:
            ts["signal"] *= 0.60
        # CV penalty only for low-sample keywords (high sample = reliable despite CV)
        if ts.get("cv", 0) > 2.0 and total < 15:
            ts["signal"] *= 0.50
        if len(ts["token"]) <= 3 and total < 5:
            ts["signal"] *= 0.40
        if ts["token"] in COMMON_INFLATED_WORDS:
            ts["signal"] *= 0.50
    return token_scores


# ── Pattern Detection ────────────────────────────────────────────────────────

def _detect_patterns(token_scores: list) -> set:
    tokens        = {ts["token"] for ts in token_scores}
    has_geo        = bool(tokens & GEO_KEYWORDS)
    has_commercial = bool(tokens & COMMERCIAL_KEYWORDS)
    has_service    = bool(tokens & SERVICE_KEYWORDS)
    has_trend      = bool(tokens & TREND_KEYWORDS)
    
    # ── Dynamic Commercial Discovery ──
    # If a keyword isn't in our hardcoded sets but has strong historical sales,
    # it is implicitly commercial or service-oriented.
    for ts in token_scores:
        if ts["price_avg"] >= 1000 and ts.get("total_sales", ts["sale_count"]) >= 3:
            has_commercial = True
        if ts["price_avg"] >= 500 and ts.get("total_sales", ts["sale_count"]) >= 5:
            has_service = True

    premium_count  = sum(1 for ts in token_scores if ts["signal"] > 0.5)

    patterns = set()
    if has_commercial and has_geo:       patterns.add("commercial_plus_geo")
    if has_service    and has_geo:       patterns.add("service_plus_city")
    if has_trend      and has_commercial: patterns.add("trend_plus_commercial")
    if premium_count  >= 2:              patterns.add("premium_cluster")
    return patterns


# ── Signal → Score mapping ───────────────────────────────────────────────────

def _signal_to_score(signal: float) -> float:
    if signal <= 0:
        return 0.0
    for i in range(len(_BREAKPOINTS) - 1):
        s1, v1 = _BREAKPOINTS[i]
        s2, v2 = _BREAKPOINTS[i + 1]
        if s1 <= signal <= s2:
            return v1 + (signal - s1) / (s2 - s1) * (v2 - v1)
    return 100.0


def _score_to_legacy(score: float) -> int:
    """Map 0-100 → 0-30 for DB backward compatibility."""
    return max(0, min(30, round(score * 30 / 100)))


def _tier(score: float) -> str:
    if score >= 88: return "ultra"
    if score >= 72: return "premium"
    if score >= 55: return "high"
    if score >= 35: return "mid"
    if score >= 15: return "low"
    return "none"


# ── Aggregation ──────────────────────────────────────────────────────────────

def _aggregate(token_scores: list, sld: str) -> dict:
    """
    BEST keyword as anchor + controlled combo boost.
    Prevents multi-word domains outranking S-tier single keywords (spec 3.3).
    """
    if not token_scores:
        return {"agg_signal": 0.0, "kps_confidence": 0.0,
                "combo_multiplier": 1.0, "coverage_ratio": 0.0,
                "patterns": set(), "best_token": None}

    best       = max(token_scores, key=lambda ts: ts["signal"])
    base_sig   = best["signal"]

    combo_mult = 1.0
    extras     = sorted([ts for ts in token_scores if ts["token"] != best["token"] and ts["signal"] > 0.25],
                        key=lambda x: -x["signal"])
    for i, extra in enumerate(extras):
        rate  = 0.15 / (2 ** i)
        boost = rate * (extra["signal"] / base_sig) if base_sig > 0 else 0
        combo_mult += min(boost, rate)

    patterns = _detect_patterns(token_scores)
    if "commercial_plus_geo"   in patterns: combo_mult += 0.15
    if "service_plus_city"     in patterns: combo_mult += 0.08
    if "premium_cluster"       in patterns: combo_mult += 0.12
    if "trend_plus_commercial" in patterns: combo_mult += 0.10
    combo_mult = min(combo_mult, 1.45)

    agg_sig = base_sig * combo_mult

    # Confidence: use best token's per-token confidence (already calibrated by sale count)
    # plus a small volume bonus from total sales across all matched tokens
    best_conf = best.get("confidence", 0.0) if best else 0.0
    total_sales = sum(ts.get("total_sales", ts.get("sale_count", 0)) for ts in token_scores)
    volume_bonus = min(0.15, total_sales / 100) if total_sales > 0 else 0.0
    conf = min(1.0, best_conf + volume_bonus)

    # Length penalty
    if len(token_scores) > 3:
        agg_sig *= 0.85 ** (len(token_scores) - 3)

    # Coverage penalty — use actual character span positions when available,
    # falling back to token length (normalized form may differ from sld span).
    covered = sum(
        (ts["end"] - ts["start"]) if ("start" in ts and "end" in ts) else len(ts["token"])
        for ts in token_scores
    )
    coverage = covered / len(sld) if sld else 0
    if coverage < 0.6:
        agg_sig *= 0.7 + 0.3 * coverage

    return {
        "agg_signal":      agg_sig,
        "kps_confidence":  min(conf, 1.0),
        "combo_multiplier": combo_mult,
        "coverage_ratio":  round(coverage, 2),
        "patterns":        patterns,
        "best_token":      best,
    }


# ── Main Entry Point ─────────────────────────────────────────────────────────

# LRU cache for score_kps — most domains in a batch won't repeat, but some
# pipeline stages call score_kps multiple times for the same name.
# The cached version is private; the public wrapper returns a shallow copy
# so callers can't corrupt the cache by mutating the returned dict.
@lru_cache(maxsize=4096)
def _score_kps_cached(name: str) -> dict:
    """
    Compute Keyword Power Score for a domain name.

    Public fields (backward-compatible + new):
        kps_score         int 0-100   new calibrated scale
        kps_score_legacy  int 0-30    kept for DB / old consumers
        kps_confidence    float 0-1   sample-size confidence
        kps_tier          str         ultra/premium/high/mid/low/none
        best_match        dict|None
        compound_partner  dict|None
        all_matches       list
        compound_bonus    int         (legacy compat)
        spam_penalty      int         always 0 now; kept for compat
        tokens            list[str]   final parse tokens
        patterns          list[str]   detected combo patterns
        parsing_confidence float
        coverage_ratio    float
        kps_reasoning     str
        kps_reasoning_ar  str
    """
    _load()
    name = name.lower().strip()
    sld  = name.split('.')[0] if '.' in name else name

    _EMPTY = {
        "kps_score": 0, "kps_score_legacy": 0, "kps_confidence": 0.0,
        "kps_tier": "none", "best_match": None, "compound_partner": None,
        "all_matches": [], "compound_bonus": 0, "spam_penalty": 0,
        "tokens": [], "patterns": [], "parsing_confidence": 0.0,
        "coverage_ratio": 0.0, "kps_keywords_matched": [],
        "total_keyword_sales": 0, "total_keyword_volume": 0,
        "kps_reasoning":    "No keyword match found in retail domain sales data.",
        "kps_reasoning_ar": "لا توجد كلمة مطابقة في بيانات مبيعات النطاقات.",
    }

    if not _KW_DATA:
        return _EMPTY

    parsed = extract_keywords(sld)
    if not parsed:
        return _EMPTY

    token_scores = []
    for pt in parsed:
        ts          = _score_token(pt["keyword"], pt["position"])
        ts["start"] = pt["start"]
        ts["end"]   = pt["end"]
        token_scores.append(ts)

    token_scores = _apply_weak_penalties(token_scores)

    agg          = _aggregate(token_scores, sld)
    kps_score_f  = _signal_to_score(agg["agg_signal"])
    kps_score    = round(kps_score_f, 1)
    kps_legacy   = _score_to_legacy(kps_score_f)
    kps_conf     = round(agg["kps_confidence"], 2)
    tier_label   = _tier(kps_score_f)
    patterns     = list(agg["patterns"])
    coverage     = agg["coverage_ratio"]
    parsing_conf = round(min(coverage * 1.5, 1.0), 2)

    _pos_to_match = {"exact": "exact", "start": "prefix",
                     "end": "suffix", "middle": "middle"}

    best_t     = agg["best_token"]
    best_match = {
        "keyword":    best_t["token"],
        "match_type": _pos_to_match.get(best_t["position"], "prefix"),
        "score":      kps_legacy,
        "avg_price":  best_t["price_avg"],
        "sale_count": best_t["sale_count"],
        "total_sales": best_t.get("total_sales", best_t["sale_count"]),
        "max_price":  best_t["price_max"],
        "data":       _KW_DATA.get(best_t["token"], {}),
    }

    all_sorted  = sorted(token_scores, key=lambda x: -x["signal"])
    all_matches = [
        {
            "keyword":    ts["token"],
            "match_type": _pos_to_match.get(ts["position"], "prefix"),
            "score":      round(ts["signal"] * 30, 1),
            "avg_price":  ts["price_avg"],
            "sale_count": ts["sale_count"],
            "max_price":  ts["price_max"],
        }
        for ts in all_sorted[:5]
    ]

    # Legacy compound_bonus / compound_partner
    compound_bonus, compound_partner = 0, None
    others = sorted([ts for ts in token_scores if ts["token"] != best_t["token"]],
                    key=lambda x: -x["signal"])
    if others and others[0]["signal"] > 0.2:
        compound_bonus   = min(5, round(others[0]["signal"] * 10))
        compound_partner = {
            "keyword":    others[0]["token"],
            "match_type": _pos_to_match.get(others[0]["position"], "prefix"),
            "avg_price":  others[0]["price_avg"],
            "sale_count": others[0]["sale_count"],
        }

    if tier_label == "none":
        # Preserve any actual matches' info even when tier rounds to "none";
        # otherwise the UI shows the empty-state placeholder despite real matches.
        none_reasoning = (
            f"KPS: '{best_match['keyword']}' matched but signal too weak "
            f"({all_matches[0]['score']}/30) — no tier"
            if all_matches else _EMPTY["kps_reasoning"]
        )
        return {**_EMPTY,
                "kps_score": kps_score, "kps_score_legacy": kps_legacy,
                "kps_confidence": kps_conf, "all_matches": all_matches,
                "kps_reasoning": none_reasoning,
                "best_match": best_match if all_matches else _EMPTY.get("best_match"),
                "tokens": [p["keyword"] for p in parsed], "patterns": patterns,
                "parsing_confidence": parsing_conf, "coverage_ratio": coverage,
                "kps_keywords_matched": [p["keyword"] for p in parsed]}

    # ── Reasoning (EN + AR) ──
    b        = best_match
    pos_en   = {"exact": "exact domain", "prefix": "prefix keyword",
                "suffix": "suffix keyword", "middle": "embedded keyword"}.get(b["match_type"], b["match_type"])
    cnote_en = (" (limited data)" if kps_conf < 0.4
                else " (moderate data)" if kps_conf < 0.7 else "")

    parts_en = [
        f"KPS: '{b['keyword']}' ({pos_en}) — "
        f"avg ${b['avg_price']:,.0f} / {b.get('total_sales', b['sale_count'])} total sales, "
        f"ceiling ${b['max_price']:,.0f}{cnote_en}"
    ]
    if compound_bonus > 0 and compound_partner:
        parts_en.append(
            f"| Compound +'{compound_partner['keyword']}' "
            f"({compound_partner['match_type']}, avg ${compound_partner['avg_price']:,.0f})"
        )
    if patterns:
        parts_en.append(f"| Patterns: {', '.join(patterns)}")

    pos_ar   = {"exact": "نطاق مطابق تماماً", "prefix": "يبدأ بهذه الكلمة",
                "suffix": "ينتهي بهذه الكلمة", "middle": "يحتوي على الكلمة"}.get(b["match_type"], "")
    cnote_ar = (" (بيانات محدودة)" if kps_conf < 0.4
                else " (بيانات معتدلة)" if kps_conf < 0.7 else "")
    reasoning_ar = (
        f"KPS: '{b['keyword']}' ({pos_ar}) — "
        f"متوسط ${b['avg_price']:,.0f} في {b.get('total_sales', b['sale_count'])} صفقة، "
        f"أعلى سعر ${b['max_price']:,.0f}{cnote_ar}"
    )

    # Aggregate total keyword sales across ALL positions for ALL matched keywords
    total_keyword_sales  = sum(ts.get("total_sales", 0)  for ts in token_scores)
    total_keyword_volume = sum(ts.get("total_volume", 0) for ts in token_scores)

    return {
        "kps_score":          kps_score,
        "kps_score_legacy":   kps_legacy,
        "kps_confidence":     kps_conf,
        "kps_tier":           tier_label,
        "best_match":         best_match,
        "compound_partner":   compound_partner,
        "all_matches":        all_matches,
        "compound_bonus":     compound_bonus,
        "spam_penalty":       0,
        "tokens":             [p["keyword"] for p in parsed],
        "patterns":           patterns,
        "parsing_confidence": parsing_conf,
        "coverage_ratio":     coverage,
        "kps_keywords_matched": [p["keyword"] for p in parsed],
        "total_keyword_sales":  total_keyword_sales,
        "total_keyword_volume": total_keyword_volume,
        "kps_reasoning":      " . ".join(parts_en),
        "kps_reasoning_ar":   reasoning_ar,
    }


def score_kps(name: str) -> dict:
    """Public entry point — returns a deep copy so callers can't corrupt the LRU cache."""
    return copy.deepcopy(_score_kps_cached(name))


# ── Score converters (updated for 0-100 scale + confidence) ─────────────────

def kps_commercial(kps_score: float, kps_confidence: float = 1.0,
                   cpc: float = 0.0, niche_boost: int = 0) -> int:
    """Convert KPS → Commercial Intent axis (0-25), confidence-scaled."""
    base = (kps_score / 100.0) * 20.0 * kps_confidence

    if cpc >= 20.0:   cpc_boost = 2
    elif cpc >= 10.0: cpc_boost = 1
    else:             cpc_boost = 0

    return min(25, int(base + cpc_boost + niche_boost))


def kps_demand(kps_result: dict, sv: int = 0, rdt: int = 0,
               reg: int = 0, aby: int = 0) -> int:
    """Convert KPS → Market Demand axis (0-20), confidence-scaled."""
    # Use total keyword sales across ALL positions and ALL matched keywords
    sale_count = kps_result.get("total_keyword_sales", 0)
    if sale_count == 0:
        # Fallback for backward compatibility
        best = kps_result.get("best_match")
        sale_count = best["sale_count"] if best else 0
    confidence = kps_result.get("kps_confidence", 1.0)

    if sale_count >= 500:   sc_pts = 10
    elif sale_count >= 200: sc_pts = 9
    elif sale_count >= 100: sc_pts = 8
    elif sale_count >= 50:  sc_pts = 7
    elif sale_count >= 20:  sc_pts = 6
    elif sale_count >= 10:  sc_pts = 5
    elif sale_count >= 5:   sc_pts = 4
    elif sale_count >= 3:   sc_pts = 3
    elif sale_count >= 1:   sc_pts = 2
    else:                   sc_pts = 0

    score = sc_pts * confidence

    if sv >= 50_000:   score += 6
    elif sv >= 10_000: score += 5
    elif sv >= 5_000:  score += 4
    elif sv >= 1_000:  score += 3
    elif sv >= 100:    score += 1

    if 1990 <= aby < 2000:   score += 3
    elif 1990 <= aby < 2004: score += 2
    elif 1990 <= aby < 2008: score += 1

    if reg >= 10:   score += 2
    elif reg >= 5:  score += 1

    if rdt >= 20:   score += 4
    elif rdt >= 10: score += 3
    elif rdt >= 5:  score += 2
    elif rdt >= 2:  score += 1

    return min(20, int(score))
