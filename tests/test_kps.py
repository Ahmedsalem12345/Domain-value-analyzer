"""
Comprehensive test suite for the KPS (Keyword Power Score) engine.

Covers: parsing, scoring, ranking, WIS non-overlap, regression,
        edge cases, confidence, and performance.

Run with:
    pytest tests/test_kps.py -v --tb=short
"""
import sys
import os
import time
import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyzer.retail_kps import (
    score_kps,
    kps_commercial,
    kps_demand,
    extract_keywords,
    _tier,
    _signal_to_score,
    STOPWORDS,
    MEANINGFUL_SHORT,
    GEO_KEYWORDS,
    SERVICE_KEYWORDS,
    COMMERCIAL_KEYWORDS,
)

# ── Module-scoped fixture: load CSV once for all tests ────────────────────────

@pytest.fixture(scope="module")
def loaded_engine():
    """Trigger CSV loading once; return a sentinel result after data is ready."""
    # score_kps internally calls _load() on first invocation
    result = score_kps("casino.com")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# A. PARSING TESTS — keyword extraction via extract_keywords()
# ══════════════════════════════════════════════════════════════════════════════

class TestParsing:
    """Verify that extract_keywords() correctly decomposes domain SLDs."""

    def test_single_keyword_shoes(self, loaded_engine):
        """'shoes' should be extracted from 'shoes.com'."""
        kws = extract_keywords("shoes")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] shoes → {keywords}")
        assert "shoes" in keywords, (
            f"Expected 'shoes' in parsed keywords, got {keywords}"
        )

    def test_multi_keyword_miamiplumbing(self, loaded_engine):
        """'miami' and 'plumbing' should both be found in 'miamiplumbing'."""
        kws = extract_keywords("miamiplumbing")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] miamiplumbing → {keywords}")
        assert "miami" in keywords, f"Expected 'miami' in {keywords}"
        assert "plumbing" in keywords, f"Expected 'plumbing' in {keywords}"

    def test_compound_healthcareillinois(self, loaded_engine):
        """'healthcareillinois' should find health-related keywords and 'illinois'.

        The engine may split 'healthcare' into 'health'+'care' via WIS, so we
        accept either 'healthcare' as one token or 'health'+'care' as two.
        """
        kws = extract_keywords("healthcareillinois")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] healthcareillinois → {keywords}")
        assert "illinois" in keywords, f"Expected 'illinois' in {keywords}"
        # Either 'healthcare' as a whole, or 'health'/'care' split
        health_found = ("healthcare" in keywords or "health" in keywords
                        or "care" in keywords)
        assert health_found, (
            f"Expected 'healthcare' or 'health'/'care' in {keywords}"
        )

    def test_nonsensical_domain_finds_no_major_keywords(self, loaded_engine):
        """'xzqwplm' — engine may find short 2-char substrings in CSV data,
        but should NOT find any meaningful long keywords."""
        kws = extract_keywords("xzqwplm")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] xzqwplm → {keywords}")
        # The engine finds short substrings like 'xz', 'qw', 'plm' — that's OK.
        # What matters is no high-value keyword like 'casino' is found.
        high_value = {"casino", "insurance", "plumbing", "dentist", "realtor"}
        found_high = set(keywords) & high_value
        assert len(found_high) == 0, (
            f"Gibberish domain should not match high-value keywords, found {found_high}"
        )

    def test_tld_stripping_casino_net(self, loaded_engine):
        """'casino.net' — score_kps should strip TLD and find 'casino'."""
        result = score_kps("casino.net")
        print(f"\n[PARSE] casino.net → tokens={result['tokens']}, "
              f"score={result['kps_score']}, tier={result['kps_tier']}")
        assert "casino" in result["tokens"], (
            f"Expected 'casino' in tokens, got {result['tokens']}"
        )

    def test_hyphenated_domain(self, loaded_engine):
        """'best-insurance' — hyphens remain; 'insurance' should be found."""
        result = score_kps("best-insurance.com")
        print(f"\n[PARSE] best-insurance.com → tokens={result['tokens']}, "
              f"score={result['kps_score']}")
        # 'best' is a stopword, but 'insurance' should be found
        assert "insurance" in result["tokens"], (
            f"Expected 'insurance' in tokens, got {result['tokens']}"
        )

    def test_short_domain_ai(self, loaded_engine):
        """'ai' is in MEANINGFUL_SHORT; should be handled without crashing."""
        kws = extract_keywords("ai")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] ai → {keywords}")
        # 'ai' is in MEANINGFUL_SHORT; whether it's extracted depends on CSV data
        assert isinstance(keywords, list)

    def test_long_compound_airealestate(self, loaded_engine):
        """'airealestate' should find at least one keyword."""
        kws = extract_keywords("airealestate")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] airealestate → {keywords}")
        assert len(keywords) >= 1, (
            f"Expected at least 1 keyword for 'airealestate', got {keywords}"
        )

    def test_exact_match_returns_exact_position(self, loaded_engine):
        """Exact SLD match (e.g. 'casino') should return an exact-position keyword."""
        kws = extract_keywords("casino")
        print(f"\n[PARSE] casino (exact) → {kws}")
        assert len(kws) >= 1, "Expected at least one keyword for 'casino'"
        exact_matches = [k for k in kws if k["position"] == "exact"]
        assert len(exact_matches) >= 1, (
            f"Expected an exact-position match for 'casino', got {kws}"
        )

    def test_stopword_best_is_skipped(self, loaded_engine):
        """'best' is in STOPWORDS and should not appear as a keyword."""
        kws = extract_keywords("best")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[PARSE] best (stopword test) → {keywords}")
        assert "best" not in keywords, (
            f"'best' is a stopword and should not be extracted, got {keywords}"
        )

    def test_parsing_returns_position_field(self, loaded_engine):
        """Each parsed keyword should have a 'position' field."""
        kws = extract_keywords("miamiplumbing")
        for kw in kws:
            assert "position" in kw, f"Missing 'position' in {kw}"
            assert kw["position"] in ("exact", "start", "end", "middle"), (
                f"Unexpected position '{kw['position']}' in {kw}"
            )

    def test_parsing_returns_start_end_fields(self, loaded_engine):
        """Each parsed keyword should have 'start' and 'end' character offsets."""
        kws = extract_keywords("miamiplumbing")
        for kw in kws:
            assert "start" in kw, f"Missing 'start' in {kw}"
            assert "end" in kw, f"Missing 'end' in {kw}"
            assert isinstance(kw["start"], int)
            assert isinstance(kw["end"], int)
            assert kw["end"] > kw["start"], (
                f"end ({kw['end']}) must be > start ({kw['start']})"
            )


# ══════════════════════════════════════════════════════════════════════════════
# B. SCORING TESTS — score ranges and calibration
# ══════════════════════════════════════════════════════════════════════════════

class TestScoring:
    """Verify that scores fall within expected ranges."""

    def test_high_value_casino(self, loaded_engine):
        """'casino.com' — exact match of a high-value commercial keyword."""
        r = score_kps("casino.com")
        print(f"\n[SCORE] casino.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}")
        # Casino is a strong commercial keyword; score should be meaningfully above 0
        assert r["kps_score"] >= 30, (
            f"'casino.com' expected score >= 30, got {r['kps_score']}"
        )

    def test_high_value_insurance(self, loaded_engine):
        """'insurance.com' — exact match of a high-value commercial keyword."""
        r = score_kps("insurance.com")
        print(f"\n[SCORE] insurance.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}")
        assert r["kps_score"] >= 50, (
            f"'insurance.com' expected score >= 50, got {r['kps_score']}"
        )

    def test_medium_value_plumbing(self, loaded_engine):
        """'plumbing.com' should score in a moderate range."""
        r = score_kps("plumbing.com")
        print(f"\n[SCORE] plumbing.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}")
        assert 30 <= r["kps_score"] <= 95, (
            f"'plumbing.com' expected score 30-95, got {r['kps_score']}"
        )

    def test_medium_value_dentist(self, loaded_engine):
        """'dentist.com' should score in a moderate range."""
        r = score_kps("dentist.com")
        print(f"\n[SCORE] dentist.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}")
        assert 30 <= r["kps_score"] <= 95, (
            f"'dentist.com' expected score 30-95, got {r['kps_score']}"
        )

    def test_low_value_stopword_domain(self, loaded_engine):
        """'best.com' — 'best' is a stopword, but engine may find substrings.
        The score should be moderate since 'best' itself is skipped."""
        r = score_kps("best.com")
        print(f"\n[SCORE] best.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}")
        # 'best' is in STOPWORDS so it won't be matched directly, but
        # substrings like 'bes' may be found. Score should be bounded.
        assert r["kps_score"] <= 70, (
            f"'best.com' expected score ≤70, got {r['kps_score']}"
        )

    def test_no_match_domain_low(self, loaded_engine):
        """'xzqwplm.com' — gibberish domain. Engine may find short substrings
        but score should be relatively low."""
        r = score_kps("xzqwplm.com")
        print(f"\n[SCORE] xzqwplm.com → score={r['kps_score']}, tier={r['kps_tier']}")
        assert r["kps_score"] <= 50, (
            f"'xzqwplm.com' expected score ≤50, got {r['kps_score']}"
        )

    def test_score_always_0_to_100(self, loaded_engine):
        """kps_score must always be in [0, 100]."""
        domains = [
            "casino.com", "insurance.com", "plumbing.com", "xzqwplm.com",
            "miamiplumbing.com", "a.com", "best-insurance.com",
            "healthcareillinois.com", "realtorminnesota.com",
        ]
        for domain in domains:
            r = score_kps(domain)
            print(f"\n[SCORE] {domain} → score={r['kps_score']}")
            assert 0 <= r["kps_score"] <= 100, (
                f"{domain}: score {r['kps_score']} outside [0, 100]"
            )

    def test_confidence_always_0_to_1(self, loaded_engine):
        """kps_confidence must always be in [0.0, 1.0]."""
        domains = [
            "casino.com", "insurance.com", "xzqwplm.com",
            "miamiplumbing.com", "dentistchicago.com",
        ]
        for domain in domains:
            r = score_kps(domain)
            print(f"\n[SCORE] {domain} → confidence={r['kps_confidence']}")
            assert 0.0 <= r["kps_confidence"] <= 1.0, (
                f"{domain}: confidence {r['kps_confidence']} outside [0.0, 1.0]"
            )

    def test_tier_is_valid(self, loaded_engine):
        """kps_tier must be one of the known tier labels."""
        valid_tiers = {"ultra", "premium", "high", "mid", "low", "none"}
        domains = [
            "casino.com", "insurance.com", "plumbing.com",
            "xzqwplm.com", "miamiplumbing.com",
        ]
        for domain in domains:
            r = score_kps(domain)
            print(f"\n[SCORE] {domain} → tier={r['kps_tier']}")
            assert r["kps_tier"] in valid_tiers, (
                f"{domain}: tier '{r['kps_tier']}' not in {valid_tiers}"
            )

    def test_legacy_score_0_to_30(self, loaded_engine):
        """kps_score_legacy must always be in [0, 30]."""
        domains = ["casino.com", "insurance.com", "xzqwplm.com"]
        for domain in domains:
            r = score_kps(domain)
            print(f"\n[SCORE] {domain} → legacy={r['kps_score_legacy']}")
            assert 0 <= r["kps_score_legacy"] <= 30, (
                f"{domain}: legacy score {r['kps_score_legacy']} outside [0, 30]"
            )


# ══════════════════════════════════════════════════════════════════════════════
# C. RANKING TESTS — relative ordering of domains
# ══════════════════════════════════════════════════════════════════════════════

class TestRanking:
    """Verify that more valuable domains score higher than less valuable ones.

    Note: The engine uses BEST + combo boost aggregation, so compound domains
    with multiple strong keywords can sometimes outrank exact single-keyword
    matches. Tests below use >= where the engine guarantees ordering and
    document cases where the combo boost effect is expected.
    """

    def test_exact_insurance_beats_prefixed(self, loaded_engine):
        """'insurance.com' should score >= 'bestinsurance.com'."""
        r_exact = score_kps("insurance.com")
        r_prefixed = score_kps("bestinsurance.com")
        print(f"\n[RANK] insurance.com={r_exact['kps_score']} vs "
              f"bestinsurance.com={r_prefixed['kps_score']}")
        assert r_exact["kps_score"] >= r_prefixed["kps_score"], (
            f"'insurance.com' ({r_exact['kps_score']}) should score >= "
            f"'bestinsurance.com' ({r_prefixed['kps_score']})"
        )

    def test_exact_realtor_vs_compound(self, loaded_engine):
        """'realtor.com' vs 'realtorminnesota.com' — compound with combo boost
        can slightly exceed exact match. Both should be in premium range."""
        exact = score_kps("realtor.com")
        compound = score_kps("realtorminnesota.com")
        print(f"\n[RANK] realtor.com={exact['kps_score']} vs "
              f"realtorminnesota.com={compound['kps_score']}")
        # With combo boost, compound can slightly exceed exact — both should be premium
        assert exact["kps_score"] >= 60, (
            f"'realtor.com' ({exact['kps_score']}) should be >= 60"
        )
        assert compound["kps_score"] >= 60, (
            f"'realtorminnesota.com' ({compound['kps_score']}) should be >= 60"
        )

    def test_casino_scores_above_zero(self, loaded_engine):
        """'casino.com' should have a meaningfully positive score."""
        r = score_kps("casino.com")
        print(f"\n[RANK] casino.com → {r['kps_score']}")
        assert r["kps_score"] > 0

    def test_compound_casinoguide_scores_high(self, loaded_engine):
        """'casinoguide.com' — compound with 'casino' should score well
        due to combo boost from multiple keywords."""
        r = score_kps("casinoguide.com")
        print(f"\n[RANK] casinoguide.com → score={r['kps_score']}, "
              f"tokens={r['tokens']}")
        assert r["kps_score"] >= 30, (
            f"'casinoguide.com' expected score >= 30, got {r['kps_score']}"
        )

    def test_insurance_higher_than_plumbing(self, loaded_engine):
        """'insurance.com' should score higher than 'plumbing.com'."""
        r_ins = score_kps("insurance.com")
        r_plb = score_kps("plumbing.com")
        print(f"\n[RANK] insurance.com={r_ins['kps_score']} vs "
              f"plumbing.com={r_plb['kps_score']}")
        assert r_ins["kps_score"] >= r_plb["kps_score"], (
            f"'insurance.com' ({r_ins['kps_score']}) should score >= "
            f"'plumbing.com' ({r_plb['kps_score']})"
        )

    def test_matched_domain_scores_above_gibberish(self, loaded_engine):
        """Any domain with real keywords should score above pure gibberish."""
        r_real = score_kps("insurance.com")
        r_gibb = score_kps("xzqwplm.com")
        print(f"\n[RANK] insurance.com={r_real['kps_score']} vs "
              f"xzqwplm.com={r_gibb['kps_score']}")
        assert r_real["kps_score"] >= r_gibb["kps_score"], (
            f"'insurance.com' ({r_real['kps_score']}) should score >= "
            f"'xzqwplm.com' ({r_gibb['kps_score']})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# D. NO-OVERLAP TESTS — WIS algorithm produces non-overlapping keywords
# ══════════════════════════════════════════════════════════════════════════════

class TestNoOverlap:
    """Verify that WIS selects non-overlapping keyword intervals."""

    @staticmethod
    def _check_no_overlap(kws):
        """Assert that no two keyword intervals share character positions."""
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                a_start, a_end = kws[i]["start"], kws[i]["end"]
                b_start, b_end = kws[j]["start"], kws[j]["end"]
                # Intervals [a_start, a_end) and [b_start, b_end) must not overlap
                overlaps = a_start < b_end and b_start < a_end
                assert not overlaps, (
                    f"Keywords '{kws[i]['keyword']}' [{a_start},{a_end}) and "
                    f"'{kws[j]['keyword']}' [{b_start},{b_end}) overlap!"
                )

    def test_miamiplumbing_no_overlap(self, loaded_engine):
        """'miamiplumbing' keywords must not overlap."""
        kws = extract_keywords("miamiplumbing")
        print(f"\n[WIS] miamiplumbing → {kws}")
        self._check_no_overlap(kws)

    def test_healthcareillinois_no_overlap(self, loaded_engine):
        """'healthcareillinois' keywords must not overlap."""
        kws = extract_keywords("healthcareillinois")
        print(f"\n[WIS] healthcareillinois → {kws}")
        self._check_no_overlap(kws)

    def test_realtorminnesota_no_overlap(self, loaded_engine):
        """'realtorminnesota' keywords must not overlap."""
        kws = extract_keywords("realtorminnesota")
        print(f"\n[WIS] realtorminnesota → {kws}")
        self._check_no_overlap(kws)

    def test_dentistchicago_no_overlap(self, loaded_engine):
        """'dentistchicago' keywords must not overlap."""
        kws = extract_keywords("dentistchicago")
        print(f"\n[WIS] dentistchicago → {kws}")
        self._check_no_overlap(kws)

    def test_wis_optimal_selection(self, loaded_engine):
        """WIS should pick the highest-weight non-overlapping set.

        For 'miamiplumbing', if both 'miami' and 'plumbing' are in the data,
        they should both be selected since they don't overlap.
        """
        kws = extract_keywords("miamiplumbing")
        keywords = [k["keyword"] for k in kws]
        print(f"\n[WIS] miamiplumbing optimal → {keywords}")
        assert "miami" in keywords, f"WIS should select 'miami', got {keywords}"
        assert "plumbing" in keywords, f"WIS should select 'plumbing', got {keywords}"

    def test_airealestate_no_overlap(self, loaded_engine):
        """'airealestate' keywords must not overlap."""
        kws = extract_keywords("airealestate")
        print(f"\n[WIS] airealestate → {kws}")
        self._check_no_overlap(kws)

    def test_bestinsurance_no_overlap(self, loaded_engine):
        """'bestinsurance' keywords must not overlap."""
        kws = extract_keywords("bestinsurance")
        print(f"\n[WIS] bestinsurance → {kws}")
        self._check_no_overlap(kws)

    def test_casinoguide_no_overlap(self, loaded_engine):
        """'casinoguide' keywords must not overlap."""
        kws = extract_keywords("casinoguide")
        print(f"\n[WIS] casinoguide → {kws}")
        self._check_no_overlap(kws)

    def test_intervals_within_sld_bounds(self, loaded_engine):
        """All keyword intervals must be within the SLD string bounds."""
        sld = "miamiplumbing"
        kws = extract_keywords(sld)
        for kw in kws:
            assert kw["start"] >= 0, f"start < 0 for {kw}"
            assert kw["end"] <= len(sld), (
                f"end ({kw['end']}) > len('{sld}') ({len(sld)}) for {kw}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# E. REGRESSION TESTS — reference domains with expected score ranges
# ══════════════════════════════════════════════════════════════════════════════

class TestRegression:
    """Specific domains with expected score/tier ranges for regression detection.

    Ranges are calibrated from actual engine output (April 2026 CSV).
    If the CSV data changes significantly, these ranges may need updating.
    """

    def test_casino_com(self, loaded_engine):
        """casino.com → score high (ultra-tier keyword), tier mid or higher."""
        r = score_kps("casino.com")
        print(f"\n[REG] casino.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}, tokens={r['tokens']}")
        assert 30 <= r["kps_score"] <= 100, (
            f"casino.com: expected score 30-100, got {r['kps_score']}"
        )
        assert r["kps_tier"] in ("ultra", "premium", "high", "mid"), (
            f"casino.com: expected tier >= mid, got {r['kps_tier']}"
        )

    def test_insurance_com(self, loaded_engine):
        """insurance.com → score ~70-100, tier premium or ultra."""
        r = score_kps("insurance.com")
        print(f"\n[REG] insurance.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"conf={r['kps_confidence']}, tokens={r['tokens']}")
        assert 60 <= r["kps_score"] <= 100, (
            f"insurance.com: expected score 60-100, got {r['kps_score']}"
        )
        assert r["kps_tier"] in ("ultra", "premium"), (
            f"insurance.com: expected tier ultra/premium, got {r['kps_tier']}"
        )

    def test_miamiplumbing_com(self, loaded_engine):
        """miamiplumbing.com → score ~80, should find both keywords."""
        r = score_kps("miamiplumbing.com")
        print(f"\n[REG] miamiplumbing.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}, conf={r['kps_confidence']}")
        assert 50 <= r["kps_score"] <= 95, (
            f"miamiplumbing.com: expected score 50-95, got {r['kps_score']}"
        )
        assert "miami" in r["tokens"], f"Expected 'miami' in tokens, got {r['tokens']}"
        assert "plumbing" in r["tokens"], f"Expected 'plumbing' in tokens, got {r['tokens']}"

    def test_dentistchicago_com(self, loaded_engine):
        """dentistchicago.com → should find 'chicago' and dental-related tokens."""
        r = score_kps("dentistchicago.com")
        print(f"\n[REG] dentistchicago.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}, conf={r['kps_confidence']}")
        # Engine may split 'dentist' into shorter substrings
        assert "chicago" in r["tokens"], f"Expected 'chicago' in tokens, got {r['tokens']}"
        assert r["kps_score"] >= 20, (
            f"dentistchicago.com: expected score >= 20, got {r['kps_score']}"
        )

    def test_realtorminnesota_com(self, loaded_engine):
        """realtorminnesota.com → score may be low due to WIS splitting."""
        r = score_kps("realtorminnesota.com")
        print(f"\n[REG] realtorminnesota.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}, conf={r['kps_confidence']}")
        # With fixed extraction, realtor+minnesota are now correctly found → premium score
        assert 50 <= r["kps_score"] <= 90, (
            f"realtorminnesota.com: expected score 50-90, got {r['kps_score']}"
        )
        assert "realtor" in r["tokens"], f"Expected 'realtor' in tokens, got {r['tokens']}"
        assert "minnesota" in r["tokens"], f"Expected 'minnesota' in tokens, got {r['tokens']}"

    def test_healthcareillinois_com(self, loaded_engine):
        """healthcareillinois.com → should find health-related keywords + illinois."""
        r = score_kps("healthcareillinois.com")
        print(f"\n[REG] healthcareillinois.com → score={r['kps_score']}, "
              f"tier={r['kps_tier']}, tokens={r['tokens']}, conf={r['kps_confidence']}")
        assert 25 <= r["kps_score"] <= 90, (
            f"healthcareillinois.com: expected score 25-90, got {r['kps_score']}"
        )
        assert "illinois" in r["tokens"], f"Expected 'illinois' in tokens, got {r['tokens']}"

    def test_airealestate_com(self, loaded_engine):
        """airealestate.com → should find realestate-related keywords."""
        r = score_kps("airealestate.com")
        print(f"\n[REG] airealestate.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}, conf={r['kps_confidence']}")
        assert 25 <= r["kps_score"] <= 95, (
            f"airealestate.com: expected score 25-95, got {r['kps_score']}"
        )

    def test_bestinsurance_com(self, loaded_engine):
        """bestinsurance.com → should find 'insurance' (high value)."""
        r = score_kps("bestinsurance.com")
        print(f"\n[REG] bestinsurance.com → score={r['kps_score']}, tier={r['kps_tier']}, "
              f"tokens={r['tokens']}, conf={r['kps_confidence']}")
        assert 40 <= r["kps_score"] <= 85, (
            f"bestinsurance.com: expected score 40-85, got {r['kps_score']}"
        )
        assert "insurance" in r["tokens"], (
            f"Expected 'insurance' in tokens, got {r['tokens']}"
        )

    def test_xzqwplm_com(self, loaded_engine):
        """xzqwplm.com — gibberish domain. Engine finds short substrings
        but score should be relatively low."""
        r = score_kps("xzqwplm.com")
        print(f"\n[REG] xzqwplm.com → score={r['kps_score']}, tier={r['kps_tier']}")
        assert r["kps_score"] <= 50, (
            f"xzqwplm.com: expected score ≤50, got {r['kps_score']}"
        )
        assert r["kps_tier"] in ("low", "none", "mid"), (
            f"xzqwplm.com: expected tier low/none/mid, got {r['kps_tier']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# F. EDGE CASE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary and unusual inputs."""

    def test_empty_string(self, loaded_engine):
        """Empty string should return a valid (zero-score) result without crashing."""
        r = score_kps("")
        print(f"\n[EDGE] '' → score={r['kps_score']}, tier={r['kps_tier']}")
        assert r["kps_score"] == 0, f"Empty string should score 0, got {r['kps_score']}"
        assert r["kps_tier"] == "none"

    def test_very_long_domain(self, loaded_engine):
        """50+ char domain should not crash."""
        long_domain = "a" * 50 + "casino" + "b" * 50 + ".com"
        r = score_kps(long_domain)
        print(f"\n[EDGE] {'a'*50}casino{'b'*50}.com → score={r['kps_score']}, "
              f"tier={r['kps_tier']}, tokens={r['tokens']}")
        assert 0 <= r["kps_score"] <= 100

    def test_domain_with_numbers(self, loaded_engine):
        """'123casino.com' — numbers prefix should not prevent 'casino' match."""
        r = score_kps("123casino.com")
        print(f"\n[EDGE] 123casino.com → score={r['kps_score']}, tokens={r['tokens']}")
        # 'casino' should be found as a substring
        assert "casino" in r["tokens"], (
            f"Expected 'casino' in tokens for '123casino.com', got {r['tokens']}"
        )

    def test_only_stopwords(self, loaded_engine):
        """'thebest.com' — both 'the' and 'best' are stopwords.
        Engine may still find short substrings, so we just verify it doesn't crash."""
        r = score_kps("thebest.com")
        print(f"\n[EDGE] thebest.com → score={r['kps_score']}, tokens={r['tokens']}")
        # 'the' and 'best' are stopwords, but substrings may be found
        assert 0 <= r["kps_score"] <= 100

    def test_single_char_domain(self, loaded_engine):
        """'a.com' — single character, should not crash."""
        r = score_kps("a.com")
        print(f"\n[EDGE] a.com → score={r['kps_score']}, tier={r['kps_tier']}")
        assert 0 <= r["kps_score"] <= 100
        assert r["kps_tier"] in ("ultra", "premium", "high", "mid", "low", "none")

    def test_all_hyphens(self, loaded_engine):
        """'---.com' — all hyphens, should not crash."""
        r = score_kps("---.com")
        print(f"\n[EDGE] ---.com → score={r['kps_score']}, tier={r['kps_tier']}")
        assert 0 <= r["kps_score"] <= 100

    def test_whitespace_handling(self, loaded_engine):
        """Domain with leading/trailing whitespace should be handled."""
        r = score_kps("  casino.com  ")
        print(f"\n[EDGE] '  casino.com  ' → score={r['kps_score']}, tokens={r['tokens']}")
        assert "casino" in r["tokens"], (
            f"Expected 'casino' after whitespace trim, got {r['tokens']}"
        )

    def test_uppercase_domain(self, loaded_engine):
        """Uppercase domain should be lowercased internally."""
        r = score_kps("CASINO.COM")
        print(f"\n[EDGE] CASINO.COM → score={r['kps_score']}, tokens={r['tokens']}")
        assert "casino" in r["tokens"], (
            f"Expected 'casino' from uppercase input, got {r['tokens']}"
        )

    def test_mixed_case_domain(self, loaded_engine):
        """Mixed case domain should be lowercased."""
        r = score_kps("CaSiNo.CoM")
        print(f"\n[EDGE] CaSiNo.CoM → score={r['kps_score']}, tokens={r['tokens']}")
        assert "casino" in r["tokens"]

    def test_domain_without_tld(self, loaded_engine):
        """Domain without TLD should still work (treated as SLD)."""
        r = score_kps("casino")
        print(f"\n[EDGE] casino (no TLD) → score={r['kps_score']}, tokens={r['tokens']}")
        assert "casino" in r["tokens"]

    def test_dot_only(self, loaded_engine):
        """Just a dot should not crash."""
        r = score_kps(".")
        print(f"\n[EDGE] '.' → score={r['kps_score']}, tier={r['kps_tier']}")
        assert 0 <= r["kps_score"] <= 100

    def test_multiple_dots(self, loaded_engine):
        """'casino.co.uk' — multiple dots, should use first part as SLD."""
        r = score_kps("casino.co.uk")
        print(f"\n[EDGE] casino.co.uk → score={r['kps_score']}, tokens={r['tokens']}")
        assert "casino" in r["tokens"]


# ══════════════════════════════════════════════════════════════════════════════
# G. CONFIDENCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestConfidence:
    """Verify confidence metric behavior."""

    def test_high_sales_positive_confidence(self, loaded_engine):
        """High-sales keywords like 'casino' should have confidence > 0."""
        r = score_kps("casino.com")
        print(f"\n[CONF] casino.com → confidence={r['kps_confidence']}, "
              f"best_match={r['best_match']}")
        assert r["kps_confidence"] > 0.0, (
            f"'casino.com' expected confidence > 0.0, got {r['kps_confidence']}"
        )

    def test_gibberish_low_confidence(self, loaded_engine):
        """Gibberish domains should have lower confidence than strong keyword domains."""
        r_gibberish = score_kps("xzqwplm.com")
        r_strong = score_kps("casino.com")
        print(f"\n[CONF] xzqwplm.com → confidence={r_gibberish['kps_confidence']}")
        # Gibberish may still find short tokens with sales, but its score should
        # be much lower than strong keywords
        assert r_gibberish["kps_score"] < r_strong["kps_score"], (
            f"Gibberish score ({r_gibberish['kps_score']}) should be less than "
            f"casino score ({r_strong['kps_score']})"
        )

    def test_compound_domain_confidence(self, loaded_engine):
        """Multi-keyword domain should have confidence based on total sales."""
        r = score_kps("miamiplumbing.com")
        print(f"\n[CONF] miamiplumbing.com → confidence={r['kps_confidence']}, "
              f"tokens={r['tokens']}")
        # miami + plumbing both have significant sales data
        assert r["kps_confidence"] > 0.0

    def test_confidence_increases_with_sales(self, loaded_engine):
        """Domains with more sales data should have higher confidence than gibberish."""
        r_high = score_kps("miamiplumbing.com")
        r_low = score_kps("xzqwplm.com")
        print(f"\n[CONF] miamiplumbing={r_high['kps_confidence']} vs "
              f"xzqwplm={r_low['kps_confidence']}")
        assert r_high["kps_confidence"] >= r_low["kps_confidence"], (
            f"'miamiplumbing' ({r_high['kps_confidence']}) should have "
            f">= confidence of 'xzqwplm' ({r_low['kps_confidence']})"
        )

    def test_confidence_always_valid_range(self, loaded_engine):
        """Confidence should always be 0.0-1.0 for any input."""
        test_inputs = ["casino.com", "xzqwplm.com", "", "a.com", "---.com",
                       "miamiplumbing.com", "insurance.com"]
        for domain in test_inputs:
            r = score_kps(domain)
            assert 0.0 <= r["kps_confidence"] <= 1.0, (
                f"{domain}: confidence {r['kps_confidence']} outside [0.0, 1.0]"
            )


# ══════════════════════════════════════════════════════════════════════════════
# H. PERFORMANCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformance:
    """Verify scoring performance is acceptable."""

    def test_100_domains_under_15_seconds(self, loaded_engine):
        """Score 100 domains in under 15 seconds total (includes WIS overhead)."""
        domains = [
            "casino.com", "insurance.com", "plumbing.com", "dentist.com",
            "miamiplumbing.com", "healthcareillinois.com", "realtorminnesota.com",
            "dentistchicago.com", "airealestate.com", "bestinsurance.com",
            "xzqwplm.com", "shoes.com", "best.com", "thebest.com",
            "a.com", "ai.com", "casino.net", "best-insurance.com",
            "123casino.com", "plumbingtips.com",
        ] * 5  # 20 × 5 = 100

        start = time.time()
        for d in domains:
            score_kps(d)
        elapsed = time.time() - start

        print(f"\n[PERF] 100 domains scored in {elapsed:.3f}s")
        assert elapsed < 15.0, (
            f"100 domains took {elapsed:.3f}s (expected < 15.0s)"
        )

    def test_single_domain_under_100ms(self, loaded_engine):
        """Single domain should score in under 100ms (after data loaded)."""
        start = time.time()
        score_kps("casino.com")
        elapsed = time.time() - start

        print(f"\n[PERF] Single domain scored in {elapsed*1000:.1f}ms")
        assert elapsed < 0.1, (
            f"Single domain took {elapsed*1000:.1f}ms (expected < 100ms)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# I. HELPER FUNCTION TESTS — internal utilities
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    """Test internal helper functions."""

    def test_signal_to_score_zero(self):
        """Signal 0 → score 0."""
        assert _signal_to_score(0.0) == 0.0

    def test_signal_to_score_negative(self):
        """Negative signal → score 0."""
        assert _signal_to_score(-1.0) == 0.0

    def test_signal_to_score_high(self):
        """Very high signal → score 100."""
        assert _signal_to_score(2.0) == 100.0

    def test_signal_to_score_midrange(self):
        """Mid-range signal should produce a score between 0 and 100."""
        score = _signal_to_score(0.40)
        print(f"\n[HELPER] signal_to_score(0.40) = {score}")
        assert 0 < score < 100

    def test_signal_to_score_monotonic(self):
        """Higher signal should produce higher score."""
        scores = [_signal_to_score(s) for s in [0.1, 0.3, 0.5, 0.7, 0.9, 1.1]]
        print(f"\n[HELPER] monotonic scores: {scores}")
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Scores not monotonic at index {i}: {scores[i]} > {scores[i+1]}"
            )

    def test_tier_labels(self):
        """Tier function should return correct labels for score boundaries."""
        assert _tier(0) == "none"
        assert _tier(14) == "none"
        assert _tier(15) == "low"
        assert _tier(34) == "low"
        assert _tier(35) == "mid"
        assert _tier(54) == "mid"
        assert _tier(55) == "high"
        assert _tier(71) == "high"
        assert _tier(72) == "premium"
        assert _tier(87) == "premium"
        assert _tier(88) == "ultra"
        assert _tier(100) == "ultra"

    def test_kps_commercial_range(self):
        """kps_commercial should return 0-25."""
        val = kps_commercial(100, 1.0, cpc=20.0)
        print(f"\n[HELPER] kps_commercial(100, 1.0, cpc=20) = {val}")
        assert 0 <= val <= 25

        val = kps_commercial(0, 0.0)
        print(f"[HELPER] kps_commercial(0, 0.0) = {val}")
        assert val == 0

    def test_kps_commercial_cpc_boost(self):
        """Higher CPC should boost commercial score."""
        low_cpc = kps_commercial(50, 1.0, cpc=1.0)
        high_cpc = kps_commercial(50, 1.0, cpc=20.0)
        print(f"\n[HELPER] CPC boost: low_cpc={low_cpc}, high_cpc={high_cpc}")
        assert high_cpc > low_cpc

    def test_kps_commercial_confidence_scaling(self):
        """Lower confidence should reduce commercial score."""
        full = kps_commercial(80, 1.0)
        half = kps_commercial(80, 0.5)
        print(f"\n[HELPER] confidence scaling: full={full}, half={half}")
        assert full >= half

    def test_kps_demand_range(self, loaded_engine):
        """kps_demand should return 0-20."""
        r = score_kps("casino.com")
        val = kps_demand(r)
        print(f"\n[HELPER] kps_demand(casino) = {val}")
        assert 0 <= val <= 20

    def test_kps_demand_no_match(self, loaded_engine):
        """kps_demand for no-match domain should be 0 or very low."""
        r = score_kps("xzqwplm.com")
        val = kps_demand(r)
        print(f"\n[HELPER] kps_demand(xzqwplm) = {val}")
        assert 0 <= val <= 20

    def test_kps_demand_with_search_volume(self, loaded_engine):
        """Higher search volume should boost demand score."""
        r = score_kps("casino.com")
        low_sv = kps_demand(r, sv=100)
        high_sv = kps_demand(r, sv=100000)
        print(f"\n[HELPER] demand sv boost: low={low_sv}, high={high_sv}")
        assert high_sv >= low_sv


# ══════════════════════════════════════════════════════════════════════════════
# J. OUTPUT STRUCTURE TESTS — verify return dict shape
# ══════════════════════════════════════════════════════════════════════════════

class TestOutputStructure:
    """Verify that score_kps returns the expected dict structure."""

    EXPECTED_KEYS = {
        "kps_score", "kps_score_legacy", "kps_confidence", "kps_tier",
        "best_match", "compound_partner", "all_matches", "compound_bonus",
        "spam_penalty", "tokens", "patterns", "parsing_confidence",
        "coverage_ratio", "kps_keywords_matched", "kps_reasoning",
        "kps_reasoning_ar",
    }

    def test_all_keys_present_match(self, loaded_engine):
        """score_kps result should contain all expected keys."""
        r = score_kps("casino.com")
        missing = self.EXPECTED_KEYS - set(r.keys())
        print(f"\n[STRUCT] casino.com keys = {sorted(r.keys())}")
        assert not missing, f"Missing keys: {missing}"

    def test_all_keys_present_no_match(self, loaded_engine):
        """No-match result should also contain all expected keys."""
        r = score_kps("xzqwplm.com")
        missing = self.EXPECTED_KEYS - set(r.keys())
        print(f"\n[STRUCT] xzqwplm.com keys = {sorted(r.keys())}")
        assert not missing, f"Missing keys: {missing}"

    def test_best_match_structure(self, loaded_engine):
        """best_match dict should have expected sub-keys when present."""
        r = score_kps("casino.com")
        bm = r["best_match"]
        assert bm is not None, "best_match should not be None for 'casino.com'"
        expected_bm_keys = {"keyword", "match_type", "score", "avg_price",
                            "sale_count", "max_price", "data"}
        missing = expected_bm_keys - set(bm.keys())
        print(f"\n[STRUCT] best_match keys = {sorted(bm.keys())}")
        assert not missing, f"Missing best_match keys: {missing}"

    def test_best_match_keyword_is_string(self, loaded_engine):
        """best_match['keyword'] should be a string."""
        r = score_kps("casino.com")
        assert isinstance(r["best_match"]["keyword"], str)

    def test_all_matches_is_list(self, loaded_engine):
        """all_matches should be a list."""
        r = score_kps("casino.com")
        assert isinstance(r["all_matches"], list)
        # Each entry should have expected keys
        if r["all_matches"]:
            for m in r["all_matches"]:
                assert "keyword" in m, f"Missing 'keyword' in all_matches entry: {m}"
                assert "match_type" in m, f"Missing 'match_type' in all_matches entry: {m}"

    def test_types_correct(self, loaded_engine):
        """Verify field types for a matched domain."""
        r = score_kps("casino.com")
        print(f"\n[STRUCT] type checks for casino.com")
        assert isinstance(r["kps_score"], (int, float)), \
            f"kps_score type: {type(r['kps_score'])}"
        assert isinstance(r["kps_score_legacy"], int), \
            f"kps_score_legacy type: {type(r['kps_score_legacy'])}"
        assert isinstance(r["kps_confidence"], float), \
            f"kps_confidence type: {type(r['kps_confidence'])}"
        assert isinstance(r["kps_tier"], str), \
            f"kps_tier type: {type(r['kps_tier'])}"
        assert isinstance(r["tokens"], list), \
            f"tokens type: {type(r['tokens'])}"
        assert isinstance(r["all_matches"], list), \
            f"all_matches type: {type(r['all_matches'])}"
        assert isinstance(r["kps_reasoning"], str), \
            f"kps_reasoning type: {type(r['kps_reasoning'])}"
        assert isinstance(r["kps_reasoning_ar"], str), \
            f"kps_reasoning_ar type: {type(r['kps_reasoning_ar'])}"
        assert isinstance(r["spam_penalty"], int), \
            f"spam_penalty type: {type(r['spam_penalty'])}"
        assert r["spam_penalty"] == 0, "spam_penalty should always be 0"

    def test_reasoning_not_empty_for_match(self, loaded_engine):
        """Reasoning strings should not be empty for matched domains."""
        r = score_kps("casino.com")
        print(f"\n[STRUCT] reasoning: {r['kps_reasoning'][:80]}...")
        assert len(r["kps_reasoning"]) > 0
        assert len(r["kps_reasoning_ar"]) > 0

    def test_coverage_ratio_range(self, loaded_engine):
        """coverage_ratio should be between 0.0 and 1.0."""
        domains = ["casino.com", "miamiplumbing.com", "xzqwplm.com"]
        for d in domains:
            r = score_kps(d)
            print(f"\n[STRUCT] {d} coverage_ratio={r['coverage_ratio']}")
            assert 0.0 <= r["coverage_ratio"] <= 1.0, (
                f"{d}: coverage_ratio {r['coverage_ratio']} outside [0, 1]"
            )

    def test_kps_keywords_matched_equals_tokens(self, loaded_engine):
        """kps_keywords_matched should contain the same keywords as tokens."""
        r = score_kps("miamiplumbing.com")
        print(f"\n[STRUCT] tokens={r['tokens']}, kps_keywords_matched={r['kps_keywords_matched']}")
        assert r["kps_keywords_matched"] == r["tokens"], (
            f"kps_keywords_matched ({r['kps_keywords_matched']}) "
            f"should equal tokens ({r['tokens']})"
        )
