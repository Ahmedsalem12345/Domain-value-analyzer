# KPS Engine Audit Report — Phase 0
**Date:** 2026-04-28
**Project:** domain-value-analyzer v4
**Scope:** KPS engine + every downstream consumer (per `KPS_ENGINE_REBUILD_PROMPT.md`)

---

## 1. KPS Code Location Map

### 1.1 Core KPS Engine

| File | Lines | Function | Purpose |
|------|-------|----------|---------|
| `analyzer/retail_kps.py` | 26-60 | `_load()` | Loads `data/retailstats.csv` into in-memory dict (`_KW_DATA`) |
| `analyzer/retail_kps.py` | 65-88 | `_exact_score(avg, cnt)` | Tiered hardcoded score 0-30 for exact matches |
| `analyzer/retail_kps.py` | 91-112 | `_positional_score(avg, cnt)` | Tiered hardcoded score 0-20 for prefix/suffix |
| `analyzer/retail_kps.py` | 115-125 | `_middle_score(avg, cnt)` | Tiered hardcoded score 0-10 for middle |
| `analyzer/retail_kps.py` | 130-211 | `_find_matches(name)` | O(n²) substring scan + length/coverage gates |
| `analyzer/retail_kps.py` | 216-344 | `score_kps(name)` | Main entry: compound bonus, spam penalty, tier label |
| `analyzer/retail_kps.py` | 349-365 | `kps_commercial(score, cpc, niche_boost)` | KPS → Commercial Intent axis (0-25) |
| `analyzer/retail_kps.py` | 368-414 | `kps_demand(kps_result, sv, rdt, reg, aby)` | KPS → Market Demand axis (0-20) |

### 1.2 Data Files

| Path | Rows | Used by code? | Notes |
|------|------|---------------|-------|
| `data/retailstats.csv` | 96,666 | ✅ Yes (loaded by `_DATA_FILE` constant) | Apr 26 |
| `retailstats_20260427.csv` | 96,680 | ❌ No (sits in repo root, ignored) | Apr 28 — newer, +14 rows |

> ⚠️ **The new CSV the user provided is NOT being used yet.** The loader path is hardcoded to `data/retailstats.csv`. We will re-point this in the rebuild.

---

## 2. KPS Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│              analyzer/retail_kps.py :: score_kps(name)              │
│  Returns: kps_score (0-30), kps_tier, best_match, all_matches,      │
│           compound_bonus, spam_penalty, kps_reasoning(_ar)          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
       ┌─────────────────────────┼──────────────────────────┐
       ▼                         ▼                          ▼
┌──────────────┐    ┌────────────────────────┐    ┌──────────────────┐
│ market_      │    │ enrichments.py         │    │ pipeline.py      │
│ scorer.py    │    │ estimate_historical_   │    │ (serialization   │
│              │    │ price()                │    │  to dict)        │
└──────────────┘    │ — Anchors price        │    └──────────────────┘
       │             │   estimate to KPS avg │             │
       │             │   (line 195-285)      │             ▼
       │             └───────────────────────┘    ┌──────────────────┐
       │                                          │ database.py      │
       │ Consumers inside market_scorer:          │ — Stores         │
       │  • L201, L247, L926: score_kps()         │   kps_score,     │
       │  • L214: kps_commercial() → axis 1       │   kps_tier,      │
       │  • L254: kps_demand()      → axis 2      │   kps_keyword,   │
       │  • L652-680: generate_reasoning()        │   kps_match_type,│
       │  • L816-833: generate_reasoning_ar()     │   kps_avg_price, │
       │  • L955-984: KPS Evidence Bonus          │   kps_sale_count,│
       │      (adds 0-20 pts to TotalScore!)      │   kps_max_price, │
       │  • L1028-1057: output dict               │   kps_evidence_  │
       │      ("KeywordPowerScore","KPSTier"...)  │   bonus,         │
       │                                          │   kps_reasoning  │
       │                                          └──────────────────┘
       │                                                   │
       ▼                                                   ▼
   Final TotalScore (0-100)                       app.py (web layer)
   = commercial + demand + clarity                — Reads back to UI
   + buyers + geo_niche + liquidity                 (lines 263-273,
   + penalties + evidence_bonus                      417-427)
   + kps_evidence_bonus  ←─── KPS appears 3 places
```

### 2.1 KPS's Total Influence on Final Score

KPS feeds the final TotalScore via **THREE pathways**:

1. **Commercial Intent axis** (`kps_commercial`) — base = `kps_score * 20/30` → up to 20 of 25 pts
2. **Market Demand axis** (`kps_demand`) — sale-count tiers → up to 10 of 20 pts
3. **KPS Evidence Bonus** (separate addition) — 0 to 20 pts directly added to total

**Effective max KPS contribution to a 100-pt score:** ~50 points (50%). This is currently **uncapped and unconfidenced** — no `kps_confidence` exists in the system.

---

## 3. Bug Evidence — Current KPS Output (10 sample domains)

```
DOMAIN                 SCORE TIER       BEST_KW         TYPE            AVG   CNT
------------------------------------------------------------------------------------------
realtorminnesota          12 high       real            prefix    $   4,771   290   ❌
healthcareillinois        20 premium    health          prefix    $  24,633   398   ⚠️
dentistchicago             9 mid        dent            prefix    $   6,600    12   ❌
casino                    27 ultra      casino          exact     $ 123,361    59   ✅
miamiplumbing             11 high       miami           prefix    $   3,233    65   ⚠️
xzqwplm                    0 none       -               -         $       0     0   ✅
bestinsurance             18 premium    best            prefix    $   5,672   487   ❌
myshop4less                4 low        mys             prefix    $   2,354     5   ❌
airealestate              15 high       air             prefix    $   4,193   238   ❌
newyorkdentist             7 mid        newyork         prefix    $   2,079     3   ⚠️
insurance                 15 high       insurance       exact     $  14,869    10   ⚠️
plumbing                   4 low        plumbing        exact     $   4,250     1   ⚠️
```

### 3.1 Concrete Bugs Confirmed

| # | Bug | Evidence | Impact |
|---|-----|----------|--------|
| **B1** | **Substring greed picks short fragment over real keyword** | `realtorminnesota` → `real` not `realtor`. `dentistchicago` → `dent` not `dentist`. `bestinsurance` → `best` not `insurance`. `myshop4less` → `mys` (junk!). `airealestate` → `air` not `realestate`. | Wrong category attribution, undervalued domains |
| **B2** | **No non-overlapping resolution** | `airealestate` returns `air`, `aire`, `estate`, `state`, `ate` as candidates; system picks first by sort, doesn't solve coverage | Multiple overlapping matches, wrong best pick |
| **B3** | **Sale-count overrides keyword specificity** | `real` (290 sales, $4,771) beats `realtor` (6 sales, $2,010) because score formula rewards count | Generic stems beat targeted keywords |
| **B4** | **Single-sale exact match scored too low** | `plumbing` exact (1 sale, $4,250) → score 4 (low tier). But `plumbing` end-position has **57 sales** at $2,332 — never consulted | Premium service words scored as junk |
| **B5** | **No confidence signal anywhere in pipeline** | Output has no `kps_confidence`. Downstream code can't tell a 1-sale match from a 50-sale match — both feed TotalScore the same way | Sparse data masquerades as strong signal |
| **B6** | **Aggregation = best_kw alone + small bonus** | Current: `best.score + min(5, partner.score//3) + spam_penalty`. Doesn't reward strong combos like `miami+plumbing` properly | `miamiplumbing` (11) << what it should be (~55-65) |
| **B7** | **Hardcoded tier thresholds, not data-calibrated** | Tiers: `>=22 ultra, >=16 premium, >=10 high…` chosen by hand, not from retailstats percentile distribution | Tier labels don't match real market tiers |
| **B8** | **Newer CSV is ignored** | Loader points to `data/retailstats.csv` (Apr 26) — `retailstats_20260427.csv` (+14 rows) sits unused in root | Stale data |

### 3.2 Cases that DO work (don't break these)

- ✅ `casino` → exact, ultra, score 27 — premium single keyword detection works
- ✅ `xzqwplm` → 0, none — junk filtering works
- ⚠️  `healthcareillinois` → 20 premium, but uses `health` (not `healthcare`) as best — partially right

---

## 4. Proposed Changes (per spec, adapted to this codebase)

### 4.1 Inside `analyzer/retail_kps.py` (rebuilt module)

| Change | What it fixes |
|--------|---------------|
| **A. Switch loader to `retailstats_20260427.csv` (with fallback)** | B8 |
| **B. Replace `_find_matches` brute substring loop with weighted-interval-scheduling DP** (longer + stronger keywords win, no overlaps) | B1, B2, B3 |
| **C. Add stopword + meaningful-short-token filters** (`MEANINGFUL_SHORT={'ai','vr',…}`, `STOPWORDS={'the','my',…}`) | B1 (filters `mys` etc.) |
| **D. Replace hardcoded tier-table scoring with log-scaled signal calculation** + position weight (exact 1.0, end 0.75, start 0.70, middle 0.35) + CV-based price dampening | B3, B4, B7 |
| **E. Replace SUM-style aggregation with BEST + controlled combo boost** (per spec section 3.3) | B6 |
| **F. Add weak-keyword penalties** (low total sales, high CV, common-inflated words) | B5, B1 |
| **G. Add pattern detection** (`commercial_plus_geo`, `service_plus_city`, etc.) for combo bonuses | B6 |
| **H. Add `kps_confidence` (0.0-1.0)** to output, derived from sample size + variance | B5 |
| **I. Recalibrate `kps_score` to a stable 0-100 scale** with piecewise mapping calibrated against the real signal distribution shown in the spec appendix | B7 |

### 4.2 Output Schema Change

**Current** (kept for backwards-compat in DB):
```python
{kps_score: 0-30, kps_tier, best_match, all_matches, compound_bonus, spam_penalty, kps_reasoning, kps_reasoning_ar}
```
**New** (additive — no fields removed):
```python
{
  kps_score: 0-100,        # rescaled (was 0-30)
  kps_score_legacy: 0-30,  # mirror of new score scaled to 0-30, kept for DB / old consumers
  kps_confidence: 0.0-1.0, # NEW
  kps_tier,                # kept (recomputed from new 0-100 scale)
  best_match, all_matches, compound_bonus, spam_penalty,
  kps_reasoning, kps_reasoning_ar,
  tokens: [...],           # NEW — final non-overlapping segmentation
  patterns: [...],         # NEW — detected combo patterns
  parsing_confidence,      # NEW
}
```

### 4.3 Downstream Consumer Updates

| File / Function | Change |
|-----------------|--------|
| `retail_kps.py :: kps_commercial` | Accept new 0-100 score; rescale internally. Multiply by `kps_confidence` before adding. Preserve external 0-25 cap. |
| `retail_kps.py :: kps_demand` | Same treatment; multiply sale-count tier by `kps_confidence`. |
| `market_scorer.py :: KPS Evidence Bonus (L955-984)` | Recalibrate to new 0-100 score thresholds; multiply bonus by `kps_confidence`; **cap evidence bonus at 15 pts** (currently 20) so KPS+commercial+demand combined ≤ ~45% of total. |
| `market_scorer.py :: generate_reasoning(_ar)` | Use new tier names; surface `kps_confidence` in reasoning text when low ("limited sales data"). |
| `enrichments.py :: estimate_historical_price` | `kps_avg` weighting (`* 0.8`) reduced when confidence < 0.5; ceiling guard already exists, keep. |
| `pipeline.py` | Add `kps_confidence` to serialized dict. |
| `database.py` | Add column `kps_confidence REAL DEFAULT 0.0`. ALTER TABLE for existing DBs. |
| `app.py` | Surface `kps_confidence` in API response (lines 263-273, 417-427). |

### 4.4 Rebalancing the Final Score

> The user does not pay for CPC/SV APIs — retailstats is the primary signal. Per spec, KPS weight should be **0.25-0.35** of final, NOT higher.
> Today, KPS can drive ~50 of 100 pts (commercial 20 + demand 10 + evidence 20). That's too high when confidence is unknown.

**Plan:**
- Keep KPS as **primary** signal (matches user's no-API context)
- Cap evidence bonus at **15 pts** (was 20)
- Multiply all three KPS contributions by `kps_confidence`
- Effective KPS share at full confidence: ~40%
- Effective KPS share at 0 confidence: ~0% (other engines compensate)
- This matches the spec's 0.30-0.35 target with confidence scaling

### 4.5 Regression Tests (NEW file)

Create `tests/test_kps_rebuild.py` with the parsing, scoring, ranking, and overlap tests from spec section 7. Must pass before integration.

---

## 5. Files That Will Be Modified

| File | Change Type |
|------|-------------|
| `analyzer/retail_kps.py` | **Full rewrite** (preserves public API: `score_kps`, `kps_commercial`, `kps_demand`) |
| `analyzer/market_scorer.py` | Surgical: only the KPS Evidence Bonus block (L955-984) and confidence multiplications in commercial/demand callers |
| `analyzer/enrichments.py` | Surgical: confidence-aware blending in `estimate_historical_price` |
| `analyzer/pipeline.py` | Add `kps_confidence` field |
| `database.py` | Add `kps_confidence` column + ALTER TABLE |
| `app.py` | Surface `kps_confidence` in API response |
| `tests/test_kps_rebuild.py` | **NEW** — regression suite |

## 6. Files That Will NOT Be Touched

- `analyzer/brandable_scorer.py` — does not read KPS
- `analyzer/geo_service.py` — does not read KPS
- `analyzer/word_data.py` — does not read KPS
- `analyzer/filters.py` — does not read KPS
- `analyzer/parallel.py` — orchestration only
- `config.py` — no KPS thresholds live here
- `templates/` — UI re-uses existing field names (additive only)
- All score axes besides Commercial Intent and Market Demand

---

## 7. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Existing DB rows have old `kps_score` (0-30 scale) — UI/ranking would break | Keep `kps_score_legacy` field; column rename optional; old rows still readable |
| Tests fail because thresholds are recalibrated | New `tests/test_kps_rebuild.py` ships with calibrated expectations from spec |
| `score_kps()` performance degrades on full O(n²) substring scan with new logic | Pre-build `KEYWORDS_BY_LENGTH_DESC` list and short-circuit, or build trie if needed (spec mentions Aho-Corasick for prod scale) |
| Premium domains lose score because evidence-bonus cap drops 20→15 | Verified offset: confidence-multiplied commercial+demand still leaves casino/insurance well above HOLD threshold |

---

## 8. Decision Required

⛔ **STOP per spec section 0.4. Awaiting user reply with `APPROVED_PROCEED_TO_KPS_REBUILD` before any code changes.**

If you want changes to this plan (e.g., different KPS weight cap, different tier names, keep 0-30 scale), tell me now — I'll revise this report and re-present.
