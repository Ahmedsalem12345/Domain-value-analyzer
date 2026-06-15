# ⚡ KPS (Keyword Power Score) Engine — Surgical Rebuild Specification
## Scope: KPS ONLY + Its Downstream Dependencies

> **📋 USE CASE CONTEXT**
>
> This is a domain investment evaluation system. The user buys, registers, and resells domain names for profit.
> The system analyzes domains, scores them across multiple engines, and surfaces the best investment opportunities.
> The retailstats dataset (96,665 keywords with real historical sales data) is the PRIMARY data source because
> the user does not have paid API subscriptions (no CPC/SV APIs). This makes retailstats the cornerstone —
> KPS must extract maximum value from it.
>
> **The goal is NOT academic accuracy — it's finding profitable domains to buy and sell.**

---

> **⛔ SCOPE LOCK — READ THIS FIRST**
>
> This prompt targets **ONE component**: the KPS (Keyword Power Score) engine.
> You are NOT rebuilding the entire domain evaluation system.
> You are NOT touching any engine, module, or scoring logic that does NOT depend on KPS output.
>
> **What you ARE doing:**
> 1. Completely rebuilding the KPS engine (domain parsing, keyword extraction, keyword scoring)
> 2. Updating any formula, weight, multiplier, threshold, or bonus that READS from KPS output
> 3. Rebalancing KPS influence on the final domain score so it's fair — not too heavy, not too light
> 4. Adding regression tests for the KPS engine specifically
>
> **What you are NOT doing:**
> - Changing brandable scoring logic (unless it reads KPS)
> - Changing TLD scoring logic (unless it reads KPS)
> - Changing liquidity scoring logic (unless it reads KPS)
> - Changing CPC/SV logic (unless it reads KPS)
> - Redesigning the UI, output schema, or pipeline architecture
> - Rewriting classification, normalization, or any other independent engine
>
> If a component does NOT consume KPS output, **leave it alone**.

---

## 0. PHASE 0 — AUDIT KPS BEFORE TOUCHING IT (🔴 MANDATORY)

Before writing or modifying ANY code, you MUST:

### Step 1 — Locate KPS in the Codebase

1. Search the entire codebase for: `KPS`, `kps`, `keyword_power`, `keyword_score`, `keywordpower`, `keyword power`
2. For each file found, document:
   - File path
   - Function/class name
   - What it computes (formula verbatim)
   - What inputs it takes
   - What outputs it produces
   - Who consumes those outputs (trace downstream)

### Step 2 — Map KPS Dependencies

Build a dependency graph:
```
[KPS Engine]
    ├── reads from: ???
    ├── outputs: ??? (score? points? multiplier?)
    ├── consumed by: ??? (final score? ranking? pricing? verdict?)
    └── also affects: ??? (any bonus/penalty that references KPS?)
```

Document every downstream consumer. These are the ONLY things you're allowed to modify outside the KPS engine itself.

### Step 3 — Document Current KPS Bugs

Test the current KPS with these domains and record what it produces:

| Domain | Expected Tokens | Expected Strong Keywords |
|--------|----------------|------------------------|
| `realtorminnesota.com` | realtor + minnesota | realtor (commercial), minnesota (geo) |
| `healthcareillinois.com` | healthcare + illinois | healthcare (commercial), illinois (geo) |
| `dentistchicago.com` | dentist + chicago | dentist (commercial), chicago (geo) |
| `casino.com` | casino | casino (exact match, S-tier) |
| `miamiplumbing.com` | miami + plumbing | miami (geo), plumbing (service) |
| `xzqwplm.com` | xzqwplm | none (junk) |
| `bestinsurance.com` | best + insurance | insurance (commercial) |
| `myshop4less.com` | my + shop + 4 + less | shop (commercial, weak context) |
| `airealestate.com` | ai + real + estate OR ai + realestate | ai (trend), realestate (commercial) |
| `newyorkdentist.com` | new + york + dentist OR newyork + dentist | newyork (geo), dentist (commercial) |

Record what the current system actually outputs for each. This is your "before" baseline.

### Step 4 — Present Findings

Produce: `kps_audit_report.md` with:
1. Current KPS formula (verbatim)
2. Dependency graph
3. Bug evidence (test results from Step 3)
4. Proposed changes (list of what you'll fix and why)

**⛔ STOP. Present the report. Wait for `APPROVED_PROCEED_TO_KPS_REBUILD` before any code changes.**

---

## 1. KPS ENGINE REBUILD SPECIFICATION

### 1.1 What KPS Must Do

KPS answers one question: **"How much real market value do the keywords in this domain carry?"**

It does this by:
1. Parsing the domain into its component keywords
2. Looking up each keyword in the retailstats dataset
3. Scoring each keyword based on its position, sales history, and price strength
4. Combining keyword scores into a single KPS value that represents total keyword power

### 1.2 Input

- `sld` — second-level domain label (e.g., `miamiplumbing` from `miamiplumbing.com`)
- `retailstats` — the full retailstats dataset loaded as an in-memory lookup

### 1.3 Output

```python
{
    "kps_score": 0-100,        # final KPS score
    "kps_confidence": 0.0-1.0, # how much data backs this score
    "tokens": ["miami", "plumbing"],
    "token_details": [
        {
            "token": "miami",
            "position": "start",        # exact | start | end | middle
            "sale_count": 14,
            "price_avg": 4200,
            "price_max": 28000,
            "price_stddev": 5100,
            "raw_signal": 0.65,
            "confidence": 1.0
        },
        ...
    ],
    "parsing_confidence": 0.95,
    "alternative_parses": [["miami", "plumbing"]],
    "notes": ["geo+service pattern detected", "both tokens have strong sales data"]
}
```

---

## 2. DOMAIN PARSING & KEYWORD EXTRACTION (Critical Fix #1)

The current parser is broken. It misses compound keywords. This must be completely rebuilt.

### 2.1 Parsing Strategy: RetailStats-First Greedy Match

**Core idea:** The retailstats dataset IS the dictionary. A "valid keyword" is any string that exists as a keyword in retailstats. We don't need an external English dictionary — we use the sales data itself as ground truth.

**Algorithm:**

```
function extract_keywords(sld, retailstats_keywords):
    # Phase 1: Try exact match (whole SLD is one keyword)
    if sld in retailstats_keywords:
        return [sld]  # exact match — strongest signal
    
    # Phase 2: RetailStats-aware segmentation
    # Find ALL possible keyword matches in the SLD
    candidates = []
    for each keyword in retailstats_keywords:
        if keyword appears as substring in sld:
            record: (keyword, start_position, end_position, keyword_strength)
    
    # Phase 3: Optimal non-overlapping coverage
    # Select the combination of keywords that:
    #   a) Covers the most characters of the SLD
    #   b) Prefers LONGER keywords over shorter ones
    #   c) Prefers STRONGER keywords (higher sale_count × price_avg) over weaker ones
    #   d) Has NO overlapping character ranges
    #   e) Filters out stopwords and single-char noise
    
    best_combination = solve_weighted_interval_scheduling(candidates)
    
    # Phase 4: Fallback — if retailstats coverage < 50% of SLD length
    # Use wordninja/wordsegment as secondary splitter for uncovered portions
    
    return best_combination
```

### 2.2 Keyword Overlap Resolution

This is CRITICAL. The current system fails here.

**Problem:** `realestate` contains `real`, `estate`, `realestate`, `ale`, `stat`, `state`, `eat`, `ate`.

**Solution: Weighted Interval Scheduling**

```python
def solve_best_keywords(sld, retailstats):
    """
    Find optimal non-overlapping keyword combination.
    Uses dynamic programming (weighted interval scheduling).
    """
    # Step 1: Find all keyword matches with positions
    matches = []
    sld_lower = sld.lower()
    
    for keyword in retailstats:
        if len(keyword) < 2:  # skip single chars (handled separately)
            continue
        if keyword in STOPWORDS:
            continue
        
        idx = 0
        while True:
            pos = sld_lower.find(keyword, idx)
            if pos == -1:
                break
            
            # Calculate keyword strength (used as weight)
            stats = retailstats[keyword]
            strength = compute_keyword_strength(stats)
            
            matches.append({
                'keyword': keyword,
                'start': pos,
                'end': pos + len(keyword),
                'length': len(keyword),
                'strength': strength
            })
            idx = pos + 1
    
    # Step 2: Sort by end position
    matches.sort(key=lambda x: x['end'])
    
    # Step 3: DP — maximize total weight (length × strength)
    # Weight function: prefer longer + stronger keywords
    for m in matches:
        m['weight'] = m['length'] * (1 + math.log1p(m['strength']))
    
    # Standard weighted interval scheduling DP
    best = weighted_interval_schedule(matches)
    
    return best
```

### 2.3 Position Detection

After extracting keywords, determine each keyword's position in the SLD:

```python
def detect_position(keyword, sld, all_tokens):
    """
    Determine the positional role of a keyword within the SLD.
    """
    if keyword == sld:
        return 'exact'      # keyword IS the entire SLD
    elif sld.startswith(keyword):
        return 'start'      # keyword begins the SLD
    elif sld.endswith(keyword):
        return 'end'        # keyword ends the SLD
    else:
        return 'middle'     # keyword is embedded inside
```

### 2.4 Parsing Edge Cases

| Case | Example | Handling |
|------|---------|----------|
| Whole SLD is a keyword | `casino.com` | Exact match, skip segmentation |
| Clean 2-word compound | `miamiplumbing.com` | `miami` (start) + `plumbing` (end) |
| Overlapping options | `realtorminnesota.com` | Prefer `realtor` (7 chars, strong) over `real`+`tor` (weaker) |
| Stopword prefix | `theshop.com` | Extract `shop`, ignore `the` |
| Numbers | `shop4less.com` | Split on digit boundaries: `shop` + `4` + `less` |
| Hyphens | `miami-plumbing.com` | Split on hyphen, treat as multi-keyword |
| Junk / no matches | `xzqwplm.com` | Return empty tokens, KPS = 0, confidence = 0 |
| Long compound 3+ | `newyorkdentist.com` | `newyork` (if in retailstats) + `dentist`, or `new`+`york`+`dentist` |
| Ambiguous splits | `airealestate.com` | Try both: `ai`+`realestate` vs `air`+`estate`. Pick higher total weight |

### 2.5 Stopwords & Noise Filters

```python
STOPWORDS = {
    'the', 'a', 'an', 'my', 'i', 'we', 'our', 'your', 'of', 'for', 'to',
    'in', 'on', 'and', 'or', 'but', 'is', 'are', 'be', 'it', 'this', 'that',
    'with', 'from', 'by', 'as', 'at', 'not', 'no', 'so', 'do', 'if', 'up',
    'out', 'get', 'go', 'can', 'will', 'just', 'its'
}

# Single chars that CAN be meaningful as brands
BRAND_LETTERS = {'x', 'z', 'q', 'k', 'v'}

# Meaningful short tokens (don't filter these)
MEANINGFUL_SHORT = {'ai', 'vr', 'ar', 'ev', 'hr', 'it', 'tv', 'uk', 'us', 'eu'}

def should_skip_token(token, retailstats):
    if token in STOPWORDS:
        return True
    if len(token) == 1 and token not in BRAND_LETTERS:
        return True
    if len(token) == 2 and token not in MEANINGFUL_SHORT:
        # Check if it has real sales data — if yes, keep it
        if token in retailstats and best_sale_count(retailstats[token]) >= 3:
            return False
        return True
    return False
```

---

## 3. KEYWORD SCORING (Critical Fix #2)

### 3.1 Position Weights

```python
POSITION_WEIGHTS = {
    'exact':  1.00,   # keyword IS the domain — strongest signal
    'start':  0.70,   # keyword leads the domain (branding position)
    'end':    0.75,   # keyword ends the domain (suffix/category position)
    'middle': 0.35    # keyword buried — weakest signal
}
```

**Note:** `end` is slightly higher than `start` because suffix-position keywords often define the domain's category (e.g., `miami` + `**plumbing**`).

### 3.2 Per-Keyword Signal Calculation

For each keyword found in the domain:

```python
def score_keyword(token, position, retailstats):
    """
    Score a single keyword based on retailstats data at its detected position.
    Returns raw signal (0-1 range) and confidence (0-1).
    """
    if token not in retailstats:
        return {'signal': 0, 'confidence': 0}
    
    stats = retailstats[token][position]
    n = stats['sale_count']
    
    if n == 0:
        # No sales at this position — check other positions as fallback
        fallback = best_available_position(retailstats[token])
        if fallback:
            stats = retailstats[token][fallback['position']]
            n = stats['sale_count']
            position_weight = POSITION_WEIGHTS[fallback['position']] * 0.5  # penalize mismatch
        else:
            return {'signal': 0, 'confidence': 0}
    else:
        position_weight = POSITION_WEIGHTS[position]
    
    # --- Sale Count Factor (log-scaled, saturates at ~60 sales) ---
    count_factor = math.log1p(n) / math.log1p(60)
    count_factor = min(count_factor, 1.0)
    
    # --- Price Factor (log-scaled, robust to outliers) ---
    avg = stats['price_avg']
    stddev = stats['price_stddev']
    max_price = stats['price_max']
    
    # Coefficient of variation — detect unreliable averages
    cv = stddev / avg if avg > 0 else 0
    
    if cv > 2.0:
        # Extremely skewed — heavily dampen (e.g., one $10M sale inflating avg)
        price_est = avg * 0.35
    elif cv > 1.0:
        # Moderately skewed — dampen
        price_est = avg * 0.60
    else:
        # Stable distribution — trust the average
        price_est = avg
    
    price_factor = math.log1p(price_est) / math.log1p(100_000)
    price_factor = min(price_factor, 1.0)
    
    # --- Upside Signal (max price as premium indicator) ---
    upside_factor = math.log1p(max_price) / math.log1p(1_000_000)
    upside_factor = min(upside_factor, 1.0)
    
    # --- Combined Signal ---
    signal = (
        count_factor * 0.30 +      # market validation (30%)
        price_factor * 0.40 +       # main value signal (40%)
        upside_factor * 0.10        # premium potential (10%)
    ) * position_weight              # position multiplier (20% effective via multiplication)
    
    # --- Market Demand Boost (price_sum as total market size) ---
    demand = stats['price_sum']
    if demand > 0:
        demand_boost = math.log1p(demand) / math.log1p(10_000_000)
        signal += demand_boost * 0.05  # small boost for total market size
    
    # --- Confidence based on sample size ---
    if n >= 10:
        confidence = 1.0
    elif n >= 5:
        confidence = 0.80
    elif n >= 3:
        confidence = 0.60
    elif n >= 2:
        confidence = 0.40
    elif n == 1:
        confidence = 0.20
    else:
        confidence = 0.0
    
    # Penalize high-variance samples
    if cv > 1.5:
        confidence *= 0.7
    
    return {
        'signal': min(signal, 1.0),
        'confidence': confidence,
        'sale_count': n,
        'price_est': price_est,
        'cv': cv,
        'position_weight': position_weight
    }
```

### 3.3 Multi-Keyword Aggregation

> **⚠️ CRITICAL BUG FIX (calibrated against real retailstats data)**
>
> The old approach SUMMED keyword signals. This caused `miamiplumbing` (0.92) to score HIGHER
> than `casino` (0.77), which is catastrophically wrong — `casino` is an S-tier keyword worth $123K avg.
>
> **Fix: Use BEST keyword signal as anchor, add controlled combo boost for multi-keyword domains.**
> This ensures single premium keywords always outrank weaker multi-word combos.
>
> Verified ranking with this approach:
> - casino (0.77) > insurance (0.59) > miamiplumbing (0.55) > dentistchicago (0.45) > realtorminnesota (0.41) ✓

```python
def aggregate_kps(token_scores, sld):
    """
    Combine multiple keyword scores into final KPS.
    
    APPROACH: Best-keyword anchor + combo boost.
    NOT sum. NOT mean. The strongest keyword defines the base,
    additional strong keywords add a controlled boost.
    
    This prevents multi-word domains from outranking premium single-keyword domains.
    """
    if not token_scores:
        return {'kps_score': 0, 'kps_confidence': 0}
    
    # --- Step 1: Find the BEST keyword signal ---
    best_token = max(token_scores, key=lambda ts: ts['signal'])
    base_signal = best_token['signal']
    base_confidence = best_token['confidence']
    
    # --- Step 2: Combo boost from additional strong keywords ---
    # Only keywords with signal > 0.25 contribute a boost
    strong_extras = [ts for ts in token_scores if ts != best_token and ts['signal'] > 0.25]
    
    combo_multiplier = 1.0
    
    if strong_extras:
        # Each strong extra keyword adds a diminishing boost
        for i, extra in enumerate(sorted(strong_extras, key=lambda x: -x['signal'])):
            # First extra: up to +15%, second: up to +8%, third: up to +4%
            boost_rate = 0.15 / (2 ** i)
            # Scale by the extra keyword's signal strength
            boost = boost_rate * (extra['signal'] / base_signal)
            combo_multiplier += min(boost, boost_rate)
    
    # --- Step 3: Pattern-based combo bonuses ---
    patterns = detect_keyword_patterns(token_scores)
    
    if 'commercial_plus_geo' in patterns:
        # e.g., dentist + chicago, plumbing + miami — high commercial intent
        combo_multiplier += 0.15
    
    if 'service_plus_city' in patterns:
        # more specific: recognized service + recognized city
        combo_multiplier += 0.08
    
    if 'premium_cluster' in patterns:
        # multiple high-value keywords together (rare, very valuable)
        combo_multiplier += 0.12
    
    if 'trend_plus_commercial' in patterns:
        # e.g., ai + insurance — trending + commercial
        combo_multiplier += 0.10
    
    # Cap combo multiplier — combos can boost up to 45%, never more
    combo_multiplier = min(combo_multiplier, 1.45)
    
    agg_signal = base_signal * combo_multiplier
    
    # --- Step 4: Confidence aggregation ---
    # Weight confidence by signal strength — stronger keywords matter more
    conf_weights = [ts['signal'] for ts in token_scores]
    total_conf_weight = sum(conf_weights)
    if total_conf_weight > 0:
        agg_confidence = sum(ts['confidence'] * w for ts, w in zip(token_scores, conf_weights)) / total_conf_weight
    else:
        agg_confidence = 0
    
    # --- Step 5: Penalties ---
    
    # Penalty: too many tokens (domain is too long / noisy)
    num_tokens = len(token_scores)
    if num_tokens > 3:
        length_penalty = 0.85 ** (num_tokens - 3)
        agg_signal *= length_penalty
    
    # Penalty: low coverage (keywords cover < 60% of SLD characters)
    covered_chars = sum(len(ts['token']) for ts in token_scores)
    coverage_ratio = covered_chars / len(sld) if len(sld) > 0 else 0
    if coverage_ratio < 0.6:
        agg_signal *= 0.7 + 0.3 * coverage_ratio
    
    # --- Step 6: Map signal to 0-100 score ---
    kps_score = signal_to_score(agg_signal)
    
    return {
        'kps_score': round(kps_score, 1),
        'kps_confidence': round(min(agg_confidence, 1.0), 2),
        'combo_multiplier': round(combo_multiplier, 3),
        'coverage_ratio': round(coverage_ratio, 2),
        'patterns': patterns,
        'best_keyword': best_token['token'],
        'best_signal': round(base_signal, 4)
    }


def signal_to_score(signal):
    """
    Map raw aggregate signal to KPS score (0-100).
    
    CALIBRATED against real retailstats data (96,665 keywords, April 2026).
    
    Real signal distribution for exact-match keywords:
        P5  = 0.264    P10 = 0.293    P25 = 0.345
        P50 = 0.379    P75 = 0.412    P90 = 0.459
        P95 = 0.493    P99 = 0.558    Max = 0.770
    
    After combo boosts, multi-keyword domains can reach ~1.1.
    
    Mapping targets:
        signal >= 0.70  → 90-100  (S-tier: casino, ai, crypto)
        signal 0.55-0.70 → 75-89  (premium: insurance, credit, mortgage)
        signal 0.45-0.55 → 60-74  (strong combos: miamiplumbing, dentistchicago)
        signal 0.35-0.45 → 40-59  (moderate: single medium keywords, weak combos)
        signal 0.25-0.35 → 20-39  (weak: low-sale keywords)
        signal < 0.25    → 0-19   (noise: no real data, junk)
    """
    if signal <= 0:
        return 0.0
    if signal >= 1.0:
        return 100.0
    
    # Piecewise linear mapping (calibrated breakpoints)
    breakpoints = [
        (0.00, 0),
        (0.25, 15),
        (0.35, 35),
        (0.45, 55),
        (0.55, 72),
        (0.70, 88),
        (0.85, 95),
        (1.10, 100),
    ]
    
    for i in range(len(breakpoints) - 1):
        s1, score1 = breakpoints[i]
        s2, score2 = breakpoints[i + 1]
        if s1 <= signal <= s2:
            # Linear interpolation within this segment
            ratio = (signal - s1) / (s2 - s1)
            return score1 + ratio * (score2 - score1)
    
    return 100.0  # above max breakpoint
```

### 3.4 Keyword Pattern Detection

```python
def detect_keyword_patterns(token_scores):
    """
    Identify valuable keyword combinations.
    Uses the tokens and their retailstats categories.
    """
    patterns = set()
    tokens = [ts['token'] for ts in token_scores]
    
    has_geo = any(is_geo_keyword(t) for t in tokens)
    has_commercial = any(is_commercial_keyword(t) for t in tokens)
    has_service = any(is_service_keyword(t) for t in tokens)
    has_trend = any(is_trend_keyword(t) for t in tokens)
    has_premium = sum(1 for ts in token_scores if ts['signal'] > 0.5)
    
    if has_commercial and has_geo:
        patterns.add('commercial_plus_geo')
    if has_service and has_geo:
        patterns.add('service_plus_city')
    if has_trend and has_commercial:
        patterns.add('trend_plus_commercial')
    if has_premium >= 2:
        patterns.add('premium_cluster')
    
    return patterns
```

---

## 4. WEAK KEYWORD PENALTIES (Critical Fix #3)

Penalize keywords that add noise instead of value:

```python
def apply_weak_keyword_penalties(token_scores, retailstats):
    """
    Down-weight or remove keywords that are noise.
    Applied BEFORE aggregation.
    """
    filtered = []
    
    for ts in token_scores:
        token = ts['token']
        stats = retailstats.get(token, {})
        
        # --- Penalty 1: Low sale count across ALL positions ---
        total_sales = sum(
            stats.get(pos, {}).get('sale_count', 0)
            for pos in ['exact', 'start', 'end', 'middle']
        )
        if total_sales <= 1:
            ts['signal'] *= 0.30  # heavy penalty — nearly no market evidence
            ts['notes'] = ts.get('notes', []) + ['low_sales_penalty']
        elif total_sales <= 3:
            ts['signal'] *= 0.60
            ts['notes'] = ts.get('notes', []) + ['moderate_sales_penalty']
        
        # --- Penalty 2: High volatility (CV > 2) ---
        if ts.get('cv', 0) > 2.0:
            ts['signal'] *= 0.50
            ts['notes'] = ts.get('notes', []) + ['high_volatility_penalty']
        
        # --- Penalty 3: Very short keyword with weak data ---
        if len(token) <= 3 and total_sales < 5:
            ts['signal'] *= 0.40
            ts['notes'] = ts.get('notes', []) + ['short_weak_penalty']
        
        # --- Penalty 4: Keyword is a common English word with inflated stats ---
        if token in COMMON_INFLATED_WORDS:
            ts['signal'] *= 0.50
            ts['notes'] = ts.get('notes', []) + ['inflated_common_word']
        
        filtered.append(ts)
    
    return filtered

COMMON_INFLATED_WORDS = {
    'online', 'web', 'site', 'page', 'home', 'best', 'top', 'free',
    'now', 'new', 'pro', 'plus', 'hub', 'zone', 'world', 'land',
    'app', 'apps', 'info', 'net', 'one', 'first', 'live'
}
```

---

## 5. DOWNSTREAM DEPENDENCY UPDATES (Critical Fix #4)

### 5.1 Identify What Reads KPS

During the Phase 0 audit, you mapped every downstream consumer of KPS. For each one, apply the following rules:

### 5.2 Final Score Integration

The final domain score formula likely combines multiple engines. KPS should be integrated as follows:

```python
# KPS weight in final score depends on confidence
def kps_contribution(kps_result, base_weight=0.25):
    """
    How much KPS contributes to the final domain score.
    
    base_weight: 0.25 means KPS is 25% of the final score at full confidence.
    When confidence is low, KPS influence shrinks proportionally.
    """
    score = kps_result['kps_score']
    confidence = kps_result['kps_confidence']
    
    # Confidence-adjusted weight
    effective_weight = base_weight * confidence
    
    # Contribution to final score
    contribution = score * effective_weight
    
    return {
        'contribution': contribution,
        'effective_weight': effective_weight,
        'base_weight': base_weight
    }
```

**Rebalancing rules:**

> **IMPORTANT CONTEXT:** The user does NOT have CPC/SV/Reg API subscriptions.
> RetailStats is the PRIMARY (and often ONLY) market data source.
> This means KPS carries MORE weight than it would if external APIs were available.
> Adjust `base_weight` accordingly — lean toward 0.30 rather than 0.20.

- KPS `base_weight` should be **0.25-0.35** of the final score (higher than usual because retailstats is the primary data source)
- When `kps_confidence < 0.3`, KPS effective weight drops to near-zero — other engines compensate
- When `kps_confidence > 0.8` AND `kps_score > 75`, boost weight to 0.35 (strong keyword signal with strong data = high conviction)
- When `kps_score < 20`, cap KPS contribution at 5 points maximum (don't let weak KPS drag down an otherwise good domain)

### 5.3 Bonus/Penalty Systems That Reference KPS

Any existing bonus or penalty that reads KPS output needs updating:

| Old Pattern | New Pattern |
|-------------|-------------|
| `if kps > X: add Y points` | `if kps_score > X AND kps_confidence > 0.5: add Y * kps_confidence points` |
| `kps_penalty = -Z` | `kps_penalty = -(Z * (1 - kps_confidence))` (penalize less when data is thin) |
| `kps * fixed_multiplier` | `kps_score * kps_confidence * calibrated_multiplier` |
| Any hardcoded KPS threshold | Recalibrate against the retailstats percentile distribution |

### 5.4 Verdict/Tier Adjustments

If KPS feeds into verdict tiers (GEM/STRONG BUY/BUY/etc.), ensure:
- A domain with `kps_score = 90+` AND `kps_confidence > 0.8` gets at minimum a `STRONG BUY` signal from KPS
- A domain with `kps_score = 0` AND `kps_confidence = 0` does NOT drag the verdict below what other engines support
- KPS alone should never be enough to push a junk domain to BUY

---

## 6. RETAILSTATS INTEGRATION

### 6.1 Data Loading

```python
def load_retailstats(filepath):
    """
    Load retailstats CSV into an efficient lookup structure.
    Call ONCE at startup.
    """
    import pandas as pd
    
    df = pd.read_csv(filepath)
    
    lookup = {}
    for _, row in df.iterrows():
        keyword = str(row['keyword']).lower().strip()
        lookup[keyword] = {
            'exact': {
                'sale_count': int(row.get('exact_sale_count', 0)),
                'price_sum': float(row.get('exact_price_sum', 0)),
                'price_avg': float(row.get('exact_price_avg', 0)),
                'price_max': float(row.get('exact_price_max', 0)),
                'price_stddev': float(row.get('exact_price_stddev', 0)),
            },
            'start': {
                'sale_count': int(row.get('start_sale_count', 0)),
                'price_sum': float(row.get('start_price_sum', 0)),
                'price_avg': float(row.get('start_price_avg', 0)),
                'price_max': float(row.get('start_price_max', 0)),
                'price_stddev': float(row.get('start_price_stddev', 0)),
            },
            'end': {
                'sale_count': int(row.get('end_sale_count', 0)),
                'price_sum': float(row.get('end_price_sum', 0)),
                'price_avg': float(row.get('end_price_avg', 0)),
                'price_max': float(row.get('end_price_max', 0)),
                'price_stddev': float(row.get('end_price_stddev', 0)),
            },
            'middle': {
                'sale_count': int(row.get('middle_sale_count', 0)),
                'price_sum': float(row.get('middle_price_sum', 0)),
                'price_avg': float(row.get('middle_price_avg', 0)),
                'price_max': float(row.get('middle_price_max', 0)),
                'price_stddev': float(row.get('middle_price_stddev', 0)),
            }
        }
    
    return lookup
```

### 6.2 Performance

- ~97K keywords in retailstats = ~6MB in memory as dict
- Dict lookup = O(1) per keyword
- Substring matching for parsing: pre-build a set of all keywords sorted by length (descending) for greedy matching
- For production scale: pre-build a trie or Aho-Corasick automaton for O(n) multi-pattern matching against the SLD

### 6.3 Known Data Limitations (handle in code)

```python
# Document these as code comments wherever retailstats is used:
#
# LIMITATION 1: No timestamps — can't detect trend direction
# LIMITATION 2: No TLD breakdown — .com and .xyz sales are mixed
# LIMITATION 3: Heavy-tailed price distributions — use CV check before trusting avg
# LIMITATION 4: 65% of keywords have only 1 sale — weak statistical basis
# LIMITATION 5: Stopwords (the, my, i) have inflated counts — filter them
# LIMITATION 6: Single-char keywords need special handling
```

---

## 7. REGRESSION TESTS

### 7.1 Parsing Tests

```python
PARSING_TESTS = [
    # (input_sld, expected_tokens, must_include_keyword)
    ("casino", ["casino"], "casino"),
    ("miamiplumbing", ["miami", "plumbing"], "plumbing"),
    ("realtorminnesota", ["realtor", "minnesota"], "realtor"),
    ("healthcareillinois", ["healthcare", "illinois"], "healthcare"),
    ("dentistchicago", ["dentist", "chicago"], "dentist"),
    ("bestinsurance", ["best", "insurance"], "insurance"),  # or just ["insurance"] if best is filtered
    ("newyorkdentist", ["newyork", "dentist"], "dentist"),  # or ["new", "york", "dentist"]
    ("airealestate", ["ai", "realestate"], "realestate"),   # prefer realestate over real+estate
    ("xzqwplm", [], None),  # junk — no valid keywords
    ("theshop", ["shop"], "shop"),  # stopword filtered
    ("shop4less", ["shop", "less"], "shop"),  # digit boundary
    ("miami-plumbing", ["miami", "plumbing"], "plumbing"),  # hyphen split
]

def test_parsing():
    for sld, expected, must_include in PARSING_TESTS:
        result = extract_keywords(sld, retailstats)
        tokens = [t['keyword'] for t in result]
        
        if must_include:
            assert must_include in tokens, f"FAIL: {sld} — missing {must_include}, got {tokens}"
        
        # Verify no overlapping character ranges
        for i, t1 in enumerate(result):
            for t2 in result[i+1:]:
                assert t1['end'] <= t2['start'] or t2['end'] <= t1['start'], \
                    f"FAIL: {sld} — overlapping tokens {t1['keyword']} and {t2['keyword']}"
```

### 7.2 Scoring Tests (calibrated against real retailstats April 2026)

```python
SCORING_TESTS = [
    # (sld, expected_score_range, expected_confidence_range)
    # Calibrated using piecewise mapping:
    #   casino signal=0.77 → score ~89    insurance signal=0.59 → score ~76
    #   miamiplumbing best=0.48 + combo → ~63   dentistchicago → ~55
    ("casino", (85, 100), (0.8, 1.0)),         # S-tier exact match ($123K avg, 59 sales)
    ("insurance", (70, 85), (0.7, 1.0)),        # premium exact ($14.8K avg, 10 sales)
    ("miamiplumbing", (55, 72), (0.5, 1.0)),    # strong geo+service combo
    ("dentistchicago", (45, 65), (0.4, 0.9)),   # good geo+service combo
    ("realtorminnesota", (40, 58), (0.3, 0.8)), # moderate combo (lower sales)
    ("xzqwplm", (0, 5), (0.0, 0.1)),           # junk — no keywords found
    ("bestinsurance", (65, 82), (0.7, 1.0)),    # insurance@end (520 sales!)
]

def test_scoring():
    for sld, score_range, conf_range in SCORING_TESTS:
        result = compute_kps(sld, retailstats)
        
        assert score_range[0] <= result['kps_score'] <= score_range[1], \
            f"FAIL: {sld} — score {result['kps_score']} not in {score_range}"
        assert conf_range[0] <= result['kps_confidence'] <= conf_range[1], \
            f"FAIL: {sld} — confidence {result['kps_confidence']} not in {conf_range}"
```

### 7.3 Ranking Tests (CRITICAL — these must never break)

```python
def test_ranking_order():
    """
    Premium single keywords MUST outrank multi-keyword combos.
    This is the core invariant that the old SUM approach broke.
    """
    domains = ["casino", "insurance", "miamiplumbing", "dentistchicago", 
               "realtorminnesota", "myshop4less", "xzqwplm"]
    scores = {d: compute_kps(d, retailstats)['kps_score'] for d in domains}
    
    # Strict ranking order (verified with real retailstats data):
    assert scores["casino"] > scores["insurance"], \
        f"casino ({scores['casino']}) must beat insurance ({scores['insurance']})"
    assert scores["insurance"] > scores["miamiplumbing"], \
        f"insurance ({scores['insurance']}) must beat miamiplumbing ({scores['miamiplumbing']})"
    assert scores["miamiplumbing"] > scores["dentistchicago"], \
        f"miamiplumbing ({scores['miamiplumbing']}) must beat dentistchicago ({scores['dentistchicago']})"
    assert scores["dentistchicago"] > scores["realtorminnesota"], \
        f"dentistchicago ({scores['dentistchicago']}) must beat realtorminnesota ({scores['realtorminnesota']})"
    assert scores["realtorminnesota"] > scores["xzqwplm"], \
        f"realtorminnesota ({scores['realtorminnesota']}) must beat xzqwplm ({scores['xzqwplm']})"
    assert scores["xzqwplm"] < 5, f"junk should score near zero, got {scores['xzqwplm']}"
```

### 7.4 Overlap Tests

```python
def test_no_overlaps():
    """No two extracted keywords should cover overlapping characters."""
    tricky_domains = [
        "realestate", "realtorminnesota", "healthcareillinois",
        "newyorkdentist", "airealestate", "bestinsurance",
        "onlinecasino", "shopforless", "carbuyernow"
    ]
    
    for sld in tricky_domains:
        result = extract_keywords(sld, retailstats)
        positions = [(t['start'], t['end'], t['keyword']) for t in result]
        
        for i, (s1, e1, k1) in enumerate(positions):
            for s2, e2, k2 in positions[i+1:]:
                overlap = not (e1 <= s2 or e2 <= s1)
                assert not overlap, f"OVERLAP in {sld}: {k1}[{s1}:{e1}] vs {k2}[{s2}:{e2}]"
```

---

## 8. PERFORMANCE TARGETS

| Operation | Target |
|-----------|--------|
| Single KPS computation | < 5 ms |
| KPS for batch of 10,000 domains | < 30 seconds |
| RetailStats loading (startup) | < 2 seconds |
| Keyword lookup | < 0.1 ms |

---

## 9. IMPLEMENTATION CHECKLIST

```
Phase 0 (Audit):
  [ ] Locate all KPS-related code
  [ ] Map dependency graph
  [ ] Test current KPS with 10 sample domains
  [ ] Present audit report
  [ ] Wait for APPROVED_PROCEED_TO_KPS_REBUILD

Phase 1 (Core KPS):
  [ ] Implement retailstats loader
  [ ] Implement keyword extraction (greedy match + weighted interval scheduling)
  [ ] Implement position detection
  [ ] Implement per-keyword scoring
  [ ] Implement multi-keyword aggregation
  [ ] Implement weak keyword penalties
  [ ] Implement pattern detection + combo bonuses
  [ ] Run parsing regression tests → all pass
  [ ] Run scoring regression tests → all pass
  [ ] Run overlap tests → all pass

Phase 2 (Integration):
  [ ] Update every downstream consumer of KPS (mapped in Phase 0)
  [ ] Recalibrate final score formula with new KPS weights
  [ ] Recalibrate bonus/penalty systems that reference KPS
  [ ] Recalibrate verdict thresholds if KPS contribution changed
  [ ] Run full system tests → verify no regressions outside KPS scope

Phase 3 (Validation):
  [ ] Compare old KPS vs new KPS on 100+ domains
  [ ] Verify premium keyword domains (casino, insurance, etc.) get proper boosts
  [ ] Verify junk domains (xzqwplm, etc.) get near-zero KPS
  [ ] Verify geo+service combinations get combo bonuses
  [ ] Verify final domain rankings improved (not just KPS in isolation)

Phase 4 (Deploy):
  [ ] Shadow mode: run new KPS alongside old, log differences
  [ ] Review differences, fix any surprises
  [ ] Switch to new KPS
  [ ] Monitor for 1 week
  [ ] Archive old KPS code (don't delete for 30 days)
```

---

## 10. ANTI-PATTERNS (DO NOT DO)

| ❌ Don't | ✅ Do |
|---------|------|
| Touch engines that don't read KPS | Leave them alone |
| Rebuild the entire scoring pipeline | Fix KPS and its consumers only |
| Use retailstats avg when stddev/avg > 2 | Use dampened estimator |
| Trust sale_count = 1 as strong signal | Confidence = 0.20 for single-sale keywords |
| Prefer `real` over `realtor` | Prefer longer, stronger keywords |
| Let overlapping keywords both score | Non-overlapping weighted interval scheduling |
| Add KPS weight > 0.35 to final score | Cap at 0.30, use confidence scaling |
| Skip the audit | MANDATORY. No audit = no code changes |
| Ignore stopwords in retailstats | Filter or heavily penalize stopwords |
| Use linear price scaling | Use log scaling (prices are log-distributed) |
| **SUM keyword signals for multi-word domains** | **Use BEST keyword + controlled combo boost** |
| Let miamiplumbing score higher than casino | Single S-tier keywords always outrank combos |
| Aggregate without confidence weighting | Every output needs `kps_confidence` paired with `kps_score` |

---

## APPENDIX A: RETAILSTATS CALIBRATION REFERENCE (April 2026)

> This data was computed from the actual `retailstats_20260425.csv` file.
> Use these numbers to validate your implementation.

### Dataset Stats
- Total keywords: 96,665
- Keywords with exact sales: 76,060
- Keywords with ANY sales signal: ~96,000+

### Exact Price Percentiles
| Percentile | Value |
|-----------|-------|
| P10 | $321 |
| P25 | $1,068 |
| P50 | $2,288 |
| P75 | $4,442 |
| P90 | $10,000 |
| P95 | $20,000 |
| P99 | $87,097 |

### Sale Count Distribution (exact match)
| Count | Keywords | Note |
|-------|----------|------|
| 0 sales | ~20,600 | No exact signal — check other positions |
| 1 sale | ~63,000 (65%) | Weak — confidence = 0.20 |
| 2-5 sales | ~12,000 (13%) | Moderate |
| 6-10 sales | ~800 (0.8%) | Strong |
| 11+ sales | ~185 (0.2%) | S-tier |

### S-Tier Keywords (for reference)
| Keyword | Exact Sales | Avg Price | Position as Domain |
|---------|------------|-----------|-------------------|
| voice | 7 | $4,298,706 | `voice.com` |
| ai | 25 | $2,824,604 | `ai.com` |
| crypto | 24 | $523,520 | `crypto.com` |
| casino | 59 | $123,361 | `casino.com` |
| shop | 25 | $160,278 | `shop.com` |
| sex | 36 | $841,656 | `sex.com` |
| mortgage | 8 | $235,387 | `mortgage.com` |
| credit | 12 | $82,442 | `credit.com` |

### Expected KPS Scores (use for validation)
| Domain | Best Keyword | Signal | Expected KPS |
|--------|-------------|--------|-------------|
| `casino.com` | casino (exact) | 0.77 | ~89 |
| `insurance.com` | insurance (exact) | 0.59 | ~76 |
| `miamiplumbing.com` | plumbing (end) + combo | 0.55 | ~63 |
| `dentistchicago.com` | chicago (end) + combo | 0.45 | ~55 |
| `realtorminnesota.com` | minnesota (end) + combo | 0.41 | ~48 |
| `xzqwplm.com` | none | 0.00 | ~0 |

### End vs Start Position Data (confirms end > start for services)
| Keyword | Start Sales | Start Avg | End Sales | End Avg |
|---------|------------|-----------|-----------|---------|
| insurance | 130 | $3,323 | 520 | $21,736 |
| lawyer | 28 | $3,153 | 165 | $3,462 |
| plumbing | 13 | $3,428 | 57 | $2,332 |
| dentist | 19 | $2,263 | 50 | $2,485 |
| solar | 268 | $3,122 | 108 | $3,655 |

---

## END OF KPS REBUILD SPECIFICATION

**Summary:** This prompt rebuilds the KPS engine from the ground up — domain parsing, keyword extraction, keyword scoring — while leaving the rest of the evaluation system untouched. Every downstream dependency on KPS gets updated to work with the new output format and calibrated weights. The result is a market-driven keyword valuation that accurately detects, scores, and weighs domain keywords using real retailstats data.

**Critical fix included:** Aggregation changed from SUM to BEST+combo, calibrated against real retailstats percentiles. This ensures premium single keywords (casino, insurance) always outrank weaker multi-word combos (miamiplumbing, dentistchicago).

**Scope reminder:** KPS + its dependencies. Nothing else.
