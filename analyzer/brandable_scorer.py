"""
Brandable Scorer — Standalone Engine V1.

Evaluates EVERY domain independently on startup/brand potential.
Benchmark: devcell.com — 7 chars, dev+cell, tech prefix + clean noun,
           2 syllables, pronounceable, memorable, company-ready.

6 Axes (100 pts total):
  1. Length           (0-10)   — shorter is better
  2. Pronounceability (0-20)   — vowel/consonant balance, syllable flow
  3. Memorability     (0-20)   — recognizable parts, word quality
  4. Pattern/Rhythm   (0-15)   — compound structure, tech prefix, rhythm
  5. Letter Quality   (0-15)   — no hyphens/numbers, clean letters
  6. Market Signals   (0-20)   — REG/RDT/AGE from CSV if available

is_brandable threshold: >= 55
"""

import re
import logging

logger = logging.getLogger("analyzer.brandable")

# ─── Tech/Startup Prefixes ────────────────────────────────────────────────────
# Words commonly used as startup/brand prefixes (recognizable, techy, modern)
TECH_PREFIXES = {
    "dev", "tech", "app", "net", "web", "bit", "sys", "bot", "hub", "pay",
    "ai", "io", "go", "my", "get", "be", "do", "zap", "tap", "snap", "clip",
    "dash", "ping", "sync", "node", "data", "meta", "nano", "auto", "fast",
    "smart", "open", "uni", "co", "pro", "max", "top", "next", "neo", "nova",
    "ultra", "omni", "key", "run", "via", "ion", "evo", "arc", "lab", "api",
    "ops", "git", "bin", "pop", "dot", "box", "kit", "hex", "dig", "digi",
    "byte", "core", "link", "wire", "grid", "flux", "flow", "base", "safe",
    "true", "pure", "lean", "live", "real", "one", "on", "up", "re",
    "in", "ex", "en", "at", "by", "of", "so", "we", "us",
}

# ─── Brand-Friendly Nouns / Suffixes ─────────────────────────────────────────
# Clean, startup-ready words that work well as domain endings
BRAND_NOUNS = {
    "cell", "hub", "core", "base", "zone", "flow", "sync", "link", "node",
    "port", "dash", "vault", "pulse", "spark", "grid", "shift", "wave",
    "forge", "craft", "slate", "grove", "mint", "peak", "edge", "bloom",
    "hive", "nest", "bench", "loft", "lane", "wire", "byte", "kit",
    "lab", "pad", "ship", "bay", "cap", "dot", "box", "den", "gem", "jet",
    "key", "map", "mix", "pod", "run", "set", "sky", "tab", "tap", "tip",
    "top", "way", "win", "zip", "arc", "beam", "bind", "bolt", "bond",
    "boot", "cast", "clip", "code", "coin", "cord", "crop", "data", "deed",
    "deep", "disk", "dive", "dock", "dome", "drop", "drum", "dual", "emit",
    "epic", "feed", "file", "find", "fire", "firm", "flag", "flat", "flex",
    "flip", "flux", "foam", "fold", "font", "fork", "form", "fort", "fuel",
    "fuse", "gain", "gate", "gear", "gist", "glow", "goal", "gold", "grip",
    "grow", "hack", "halo", "hand", "hash", "head", "heat", "helm", "hero",
    "high", "hold", "hook", "horn", "host", "icon", "idea", "info", "iron",
    "jump", "kind", "king", "kite", "knot", "lamp", "land", "last", "lava",
    "leaf", "lean", "leap", "ledge", "lens", "lift", "lime", "line", "list",
    "lite", "live", "load", "loan", "lock", "loop", "luck", "lure", "mesh",
    "mode", "move", "pack", "page", "pair", "pass", "path", "pipe", "plan",
    "play", "plot", "plug", "plus", "poll", "pool", "post", "push", "rack",
    "rail", "rank", "rate", "read", "real", "reef", "ring", "rise", "roll",
    "root", "rope", "rule", "rush", "sail", "sale", "sand", "save", "scan",
    "seal", "seed", "seek", "send", "ship", "shot", "sign", "silk", "site",
    "skip", "slot", "soil", "span", "spec", "spin", "spot", "star", "stat",
    "stay", "stem", "step", "stop", "suit", "surf", "swap", "task", "team",
    "term", "test", "text", "tide", "tilt", "time", "tone", "tool", "tree",
    "trim", "trio", "trip", "tune", "turn", "type", "unit", "vibe", "view",
    "vine", "volt", "vote", "walk", "wall", "ward", "warp", "wash", "well",
    "wide", "wild", "wind", "wing", "wise", "word", "work", "wrap", "yard",
    "yell", "zone", "ray", "bay", "hay", "jay", "lay", "pay", "say",
    "play", "clay", "gray", "pray", "slay", "spray", "stay", "tray",
    "lair", "flair", "heir", "pair", "stair", "chair", "fair", "hair",
    "cube", "tube", "lube", "dune", "tune", "rune", "bone", "cone", "drone",
    "phone", "stone", "tone", "zone", "hone", "lone", "gone", "none",
    "mate", "gate", "fate", "late", "rate", "slate", "plate", "state",
    "bite", "kite", "lite", "mite", "site", "white", "write", "quite",
    "cove", "dove", "grove", "move", "prove", "rove", "stove", "trove",
    "blaze", "craze", "daze", "gaze", "glaze", "graze", "haze", "maze",
    "phase", "phrase", "raze", "raise",
}

# ─── Patterns indicating startup/tech compound ───────────────────────────────
STARTUP_PATTERNS = [
    r'^(dev|tech|app|net|web|hub|bit|sys|bot|pay|ai|io|go|my|get|be|do|zap)',
    r'(hub|core|base|zone|flow|sync|link|node|port|dash|vault|pulse|spark|grid|shift|wave|forge|craft|mint|peak|edge|bloom|hive|nest|loft|lane|wire|bolt|byte|kit|lab|pad|ship|bay|cap|gem|jet|key|mix|pod|sky|way|win|arc|beam|code|fire|glow|grip|icon|leap|lime|list|lite|live|load|lock|mesh|mode|rack|rail|rank|rate|ring|rise|roll|root|rope|rule|rush|sail|save|scan|seal|seed|seek|send|shot|sign|silk|site|skip|slot|span|spec|spin|spot|star|stay|stem|step|tone|tool|trim|trio|tune|turn|type|vibe|view|vine|volt|walk|wall|ward|wash|wind|wing|wise|word|work|wrap|zone)$',
]

_VOWELS = set("aeiouy")
_HARSH_ENDINGS = {"q", "j", "v", "x"}
_LIQUID_ENDINGS = {"l", "r", "n", "m", "s"}


# ─── Utility ──────────────────────────────────────────────────────────────────

def _parse_int(val, default=0):
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def _count_syllables(name: str) -> int:
    """Heuristic syllable count from name string."""
    name = name.lower()
    vowel_groups = re.findall(r'[aeiouy]+', name)
    count = len(vowel_groups)
    if name.endswith('e') and not name.endswith('le') and count > 1:
        count -= 1
    return max(1, count)


def _vowel_ratio(name: str) -> float:
    if not name:
        return 0.0
    return sum(1 for c in name if c in _VOWELS) / len(name)


def _max_consonant_cluster(name: str) -> int:
    clusters = re.findall(r'[^aeiouy]+', name)
    return max((len(c) for c in clusters), default=0)


def _find_brand_split(name: str):
    """
    Try to split name into (prefix, suffix) where prefix is a tech prefix
    or known word, and suffix is a brand noun or known word.
    Returns (left, right) or None.
    """
    for i in range(2, len(name) - 1):
        left = name[:i]
        right = name[i:]
        if left in TECH_PREFIXES and (right in BRAND_NOUNS or len(right) >= 3):
            return (left, right)
        if right in BRAND_NOUNS and len(left) >= 2:
            return (left, right)
    return None


def _has_startup_pattern(name: str) -> bool:
    for p in STARTUP_PATTERNS:
        if re.search(p, name):
            return True
    return False


def _is_pronounceable(name: str) -> bool:
    """Quick check: does name have reasonable vowel/consonant balance."""
    ratio = _vowel_ratio(name)
    cluster = _max_consonant_cluster(name)
    return 0.15 <= ratio <= 0.65 and cluster <= 4


# ─── Axis 1: Length Score (0–10) ─────────────────────────────────────────────

def _score_length(name: str) -> int:
    n = len(name)
    if n <= 4:  return 10
    if n == 5:  return 9
    if n == 6:  return 8
    if n == 7:  return 7   # devcell
    if n == 8:  return 6
    if n == 9:  return 4
    if n == 10: return 2
    if n == 11: return 1
    return 0


# ─── Axis 2: Pronounceability (0–20) ─────────────────────────────────────────

def _score_pronounceability(name: str) -> int:
    score = 0

    # Vowel ratio (0–8)
    ratio = _vowel_ratio(name)
    if 0.20 <= ratio <= 0.50:
        score += 8
    elif 0.15 <= ratio <= 0.60:
        score += 5
    elif 0.10 <= ratio <= 0.65:
        score += 2
    # else 0

    # Max consonant cluster (0–7)
    cluster = _max_consonant_cluster(name)
    if cluster <= 1:
        score += 7
    elif cluster == 2:
        score += 6
    elif cluster == 3:
        score += 4
    elif cluster == 4:
        score += 1
    # else 0

    # Syllable count (0–5)
    syl = _count_syllables(name)
    if syl == 2:
        score += 5
    elif syl == 3:
        score += 4
    elif syl == 1:
        score += 3
    elif syl == 4:
        score += 2
    # else 0

    return min(20, score)


# ─── Axis 3: Memorability (0–20) ─────────────────────────────────────────────

def _score_memorability(name: str) -> int:
    """
    Based on word recognition and compound quality.
    Devcell: dev (tech prefix) + cell (real word) → 17
    """
    try:
        from analyzer.word_data import TIER1_WORDS, ALL_WORDS, try_split_compound
    except ImportError:
        TIER1_WORDS, ALL_WORDS, try_split_compound = set(), set(), lambda x: None

    score = 0

    # Full word match (single-word domain)
    if name in TIER1_WORDS:
        return 18  # "bolt", "cloud", "spark" — premium single word
    if name in ALL_WORDS:
        return 14  # Known word, good memorability

    # Check tech-prefix + brand-noun compound (the ideal pattern)
    split = _find_brand_split(name)
    if split:
        left, right = split
        if left in TECH_PREFIXES and right in BRAND_NOUNS:
            score = 17  # dev+cell, tech+node, app+core — best compound
        elif left in TECH_PREFIXES and right in ALL_WORDS:
            score = 15
        elif left in TECH_PREFIXES:
            score = 13  # tech prefix + unknown but clean suffix
        elif right in BRAND_NOUNS:
            score = 14  # unknown prefix + strong brand noun
        elif right in ALL_WORDS:
            score = 12
        else:
            score = 9  # 2-part structure but less recognizable
    else:
        # Try standard compound split
        compound = try_split_compound(name)
        if compound:
            w1, w2 = compound
            if w1 in TIER1_WORDS and w2 in TIER1_WORDS:
                score = 16
            elif w1 in ALL_WORDS and w2 in ALL_WORDS:
                score = 13
            elif w1 in ALL_WORDS or w2 in ALL_WORDS:
                score = 10
            else:
                score = 7
        else:
            # Partial recognition
            has_prefix = any(name.startswith(p) for p in TECH_PREFIXES if len(p) >= 3)
            has_suffix = any(name.endswith(s) for s in BRAND_NOUNS if len(s) >= 3)
            if has_prefix and has_suffix:
                score = 11
            elif has_prefix:
                score = 8
            elif has_suffix:
                score = 7
            else:
                # No recognizable parts — score based on length heuristic
                score = 4 if len(name) <= 7 else 2

    return min(20, score)


# ─── Axis 4: Pattern / Rhythm (0–15) ─────────────────────────────────────────

def _score_pattern(name: str) -> int:
    """
    Rewards startup compound structure, tech prefix, and phonetic rhythm.
    Devcell: tech prefix(6) + 2-part(5) + 2-syllable(4) = 15
    """
    score = 0

    # Tech prefix detected
    has_prefix = any(name.startswith(p) for p in TECH_PREFIXES if len(p) >= 3)
    if has_prefix:
        score += 6

    # Clean 2-part compound structure
    split = _find_brand_split(name)
    if split:
        score += 5
    else:
        try:
            from analyzer.word_data import try_split_compound
            if try_split_compound(name):
                score += 4
        except ImportError:
            pass

    # Syllable rhythm bonus
    syl = _count_syllables(name)
    if syl == 2:
        score += 4
    elif syl == 3:
        score += 3
    elif syl == 1 and len(name) <= 5:
        score += 3  # Very short monosyllabic can be punchy

    # CVCV-ish pattern bonus (alternating vowel/consonant)
    transitions = sum(
        1 for i in range(len(name) - 1)
        if (name[i] in _VOWELS) != (name[i + 1] in _VOWELS)
    )
    if len(name) > 0:
        flow_ratio = transitions / len(name)
        if flow_ratio >= 0.6:
            score = min(15, score + 2)
        elif flow_ratio >= 0.4:
            score = min(15, score + 1)

    return min(15, score)


# ─── Axis 5: Letter Quality (0–15) ───────────────────────────────────────────

def _score_letter_quality(name: str) -> int:
    """
    Penalizes hyphens, numbers, awkward letter combos.
    Devcell: no hyphen, no numbers, ends in 'l' (liquid) = 14
    """
    # Hard penalties — these nearly disqualify
    if '-' in name:
        return 0   # Hyphens destroy brandability
    if any(c.isdigit() for c in name):
        return 2   # Numbers badly hurt brand perception

    score = 10  # Base

    # Clean ending bonus
    if name[-1] in _LIQUID_ENDINGS:
        score += 2  # Ends in l/r/n/m/s — smooth, memorable
    elif name[-1] in _VOWELS:
        score += 3  # Ends in vowel — very clean (vibe, nova, neo)
    elif name[-1] in _HARSH_ENDINGS:
        score -= 2  # Ends in q/j/v/x — awkward

    # Clean start bonus
    if name[0] not in _HARSH_ENDINGS and name[0] not in _VOWELS:
        score += 1  # Consonant start — punchy
    elif name[0] in _VOWELS:
        score += 1  # Vowel start — also fine

    # Penalty for awkward consonant combos at start
    harsh_combos = ["bx", "xk", "qv", "jx", "vx", "xj", "kv"]
    for combo in harsh_combos:
        if combo in name:
            score -= 2
            break

    # Penalty for excessive double consonants (feels clunky)
    doubles = re.findall(r'([^aeiouy])\1', name)
    if len(doubles) > 1:
        score -= 1  # One double is fine (cell), two+ is clunky

    return max(0, min(15, score))


# ─── Axis 6: Market Signals (0–20) ───────────────────────────────────────────

def _score_market_signals(extra_data: dict) -> int:
    """
    Uses CSV data (REG, RDT, ABY) to validate real-world market interest.
    Domains with strong market history are more valuable as brands.
    """
    score = 0

    reg = _parse_int(extra_data.get("reg", 0))
    rdt = _parse_int(extra_data.get("rdt", 0))
    aby = _parse_int(extra_data.get("aby", 0))

    # REG: registered in multiple TLDs = proven name interest
    if reg >= 50:   score += 10
    elif reg >= 20: score += 8
    elif reg >= 10: score += 6
    elif reg >= 5:  score += 3
    elif reg >= 2:  score += 1

    # RDT: used in related domains = proven word popularity
    if rdt >= 50:   score += 10
    elif rdt >= 20: score += 8
    elif rdt >= 10: score += 6
    elif rdt >= 5:  score += 3
    elif rdt >= 2:  score += 1

    # ABY: old domain = proven history (vintage brand asset)
    if 1990 <= aby <= 2000:  score += 2
    elif 2000 < aby <= 2005: score += 1

    return min(20, score)


# ─── Hard Penalties ───────────────────────────────────────────────────────────

def _calculate_hard_penalties(name: str) -> tuple[int, list]:
    """
    Penalties that can reduce total score significantly.
    Returns (penalty_points, reasons_list).
    """
    total = 0
    reasons = []

    # Hyphen — kills brandability. Reduced from -20 to -10 to avoid
    # double-counting with _score_letter_quality which already zeroes its axis.
    if '-' in name:
        total -= 10
        reasons.append("Contains hyphen")

    # Numbers — modern brands avoid them. Reduced from -12 to -5 to avoid
    # double-counting with _score_letter_quality which already drops to 2/15.
    if any(c.isdigit() for c in name):
        total -= 5
        reasons.append("Contains number")

    # Pure gibberish: extremely low vowel ratio
    ratio = _vowel_ratio(name)
    if ratio < 0.12:
        total -= 15
        reasons.append("No pronounceable vowels")

    # Unpronounceable consonant clusters
    if _max_consonant_cluster(name) >= 5:
        total -= 8
        reasons.append("Unpronounceable consonant cluster")

    # Too long (13+ chars) — _score_length already returns 0 for 12+ chars;
    # this adds a small extra penalty for truly excessive length only.
    if len(name) >= 16:
        total -= 5
        reasons.append(f"Too long ({len(name)} chars)")

    # Starts with number — reduced from -15, as the digit penalty above already covers it
    if name and name[0].isdigit():
        total -= 5
        reasons.append("Starts with number")

    return total, reasons


# ─── Main Scoring Function ────────────────────────────────────────────────────

def score_brandable(domain: str, extra_data: dict = None) -> dict:
    """
    Score a domain on brandability. Returns a dict with:
      brandable_score  (0–100)
      is_brandable     (bool)
      brand_axes       (dict of 6 axis scores)
      brand_reasoning  (str)
    """
    if extra_data is None:
        extra_data = {}

    name = domain.split('.')[0].lower().strip()

    if not name:
        return _empty_result()

    # ── Compute all 6 axes ──
    s_length     = _score_length(name)
    s_pronounce  = _score_pronounceability(name)
    s_memory     = _score_memorability(name)
    s_pattern    = _score_pattern(name)
    s_letters    = _score_letter_quality(name)
    s_market     = _score_market_signals(extra_data)

    # ── Hard penalties ──
    penalty, penalty_reasons = _calculate_hard_penalties(name)

    raw = s_length + s_pronounce + s_memory + s_pattern + s_letters + s_market + penalty
    total = max(0, min(100, raw))

    # Lowered to 53 (was 58): reduces false negatives on genuine startup-style
    # compound names (cloudnova, zentrova, flowpath) that score 53-57 but are
    # clearly sellable. The old threshold was too conservative.
    is_brandable = total >= 53

    # ── Build reasoning ──
    reasoning = _build_reasoning(
        name, total, is_brandable, s_length, s_pronounce, s_memory,
        s_pattern, s_letters, s_market, penalty_reasons
    )

    return {
        "BrandableScore": total,
        "IsBrandable": is_brandable,
        "BrandAxes": {
            "length":        s_length,
            "pronounce":     s_pronounce,
            "memory":        s_memory,
            "pattern":       s_pattern,
            "letters":       s_letters,
            "market":        s_market,
        },
        "BrandReasoning": reasoning,
    }


def _build_reasoning(name, total, is_brandable, s_len, s_pro, s_mem,
                     s_pat, s_let, s_mkt, penalty_reasons):
    parts = []

    if total >= 82:
        parts.append(f"'{name}' is a premium brandable name")
    elif total >= 70:
        parts.append(f"'{name}' has strong brand potential")
    elif total >= 53:
        parts.append(f"'{name}' has solid brand potential")
    else:
        parts.append(f"'{name}' has limited brand appeal")

    if s_len >= 9:
        parts.append("short and punchy")
    elif s_len >= 6:
        parts.append("good length")

    if s_pro >= 18:
        parts.append("excellent pronunciation flow")
    elif s_pro >= 14:
        parts.append("easy to pronounce")

    if s_mem >= 16:
        parts.append("highly memorable compound")
    elif s_mem >= 12:
        parts.append("recognizable structure")

    split = _find_brand_split(name)
    if split:
        parts.append(f"clean '{split[0]}' + '{split[1]}' compound")

    try:
        from analyzer.word_data import TIER1_WORDS
        if name in TIER1_WORDS:
            parts.append("premium English word — any industry can use it")
    except ImportError:
        pass

    if s_pat >= 13:
        parts.append("ideal startup pattern")
    elif s_pat >= 9:
        parts.append("good rhythm")

    if s_mkt > 0:
        parts.append(f"market-validated ({s_mkt}/20 signals)")

    if penalty_reasons:
        parts.append(f"penalized: {', '.join(penalty_reasons)}")

    verdict = "→ Strong brand candidate" if is_brandable else "→ Below brand threshold"
    parts.append(verdict)

    return ". ".join(parts)


def _empty_result():
    return {
        "BrandableScore": 0,
        "IsBrandable": False,
        "BrandAxes": {
            "length": 0, "pronounce": 0, "memory": 0,
            "pattern": 0, "letters": 0, "market": 0,
        },
        "BrandReasoning": "Invalid domain name",
    }
