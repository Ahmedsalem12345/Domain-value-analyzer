"""
SQLite Database V4 — Market Intelligence Schema.
"""
import sqlite3
import threading
import json
import io
import csv
import logging
import atexit
from config import DB_FILE

logger = logging.getLogger("analyzer.db")


def _safe_meta(raw):
    """Parse a metadata JSON blob, tolerating NULL or malformed values."""
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}

# Column list for CSV export — defined once as a constant so it is never
# assembled via f-string interpolation at query time (avoids fragile pattern).
_EXPORT_COLS = (
    "domain,verdict,total_score,domain_type,target_buyer,resell_speed,reasoning,"
    "commercial_intent,market_demand,clarity,buyer_pool,geo_niche,liquidity,"
    "niche_name,niche_tier,geo_name,is_geo,penalties,penalty_reasons,"
    "price_low,price_high,brandable_score,is_brandable,"
    "kps_score,kps_tier,kps_keyword,kps_match_type,kps_avg_price,"
    "kps_sale_count,kps_max_price,kps_evidence_bonus,kps_confidence,"
    "opportunity_score,signal_score,sellability_score,risk_score,risk_flags,"
    "decision_verdict,decision_reason,data_quality_score,name_fit_score,"
    "sell_through_prob,max_acquisition_price,ideal_acquisition_price,"
    "price_confidence,buyer_persona,ranking_category,brand_sellability,"
    "coherence_score,coherence_passes,"
    "top_signals,top_risks,price_warnings,overpriced_warning,manual_research,kps_anchored,"
    "buyer_clarity,buyer_count_estimate,outbound_difficulty,"
    "ml_price_estimate,ml_grade,ml_investment_score,ml_grade_proba"
)


class Database:
    def __init__(self):
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # check_same_thread=True is correct here: each thread gets its own
            # connection via threading.local(), so SQLite's same-thread check
            # is satisfied. WAL mode allows concurrent reads from other threads.
            self._local.conn = sqlite3.connect(str(DB_FILE), check_same_thread=True)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS domains (
                domain TEXT PRIMARY KEY, position INTEGER, metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS results (
                domain TEXT PRIMARY KEY,
                verdict TEXT,
                total_score INTEGER,
                domain_type TEXT DEFAULT 'low_value',
                domain_type_label TEXT DEFAULT '',
                target_buyer TEXT DEFAULT '',
                resell_speed TEXT DEFAULT 'Slow',
                reasoning TEXT DEFAULT '',
                -- 6 Axes
                commercial_intent INTEGER DEFAULT 0,
                market_demand INTEGER DEFAULT 0,
                clarity INTEGER DEFAULT 0,
                buyer_pool INTEGER DEFAULT 0,
                geo_niche INTEGER DEFAULT 0,
                liquidity INTEGER DEFAULT 0,
                -- Context
                niche_name TEXT DEFAULT '-',
                niche_tier TEXT DEFAULT 'none',
                geo_name TEXT DEFAULT '',
                is_geo INTEGER DEFAULT 0,
                -- Penalties & Pricing
                penalties INTEGER DEFAULT 0,
                penalty_reasons TEXT DEFAULT '',
                reasoning_ar TEXT DEFAULT '',
                target_buyer_ar TEXT DEFAULT '',
                price_low INTEGER DEFAULT 0,
                price_high INTEGER DEFAULT 0,
                -- Brandable Engine
                brandable_score INTEGER DEFAULT 0,
                is_brandable INTEGER DEFAULT 0,
                brand_axes TEXT DEFAULT '{}',
                brand_reasoning TEXT DEFAULT '',
                -- Keyword Power Score (KPS)
                kps_score INTEGER DEFAULT 0,
                kps_tier TEXT DEFAULT 'none',
                kps_keyword TEXT DEFAULT '',
                kps_match_type TEXT DEFAULT '',
                kps_avg_price REAL DEFAULT 0,
                kps_sale_count INTEGER DEFAULT 0,
                kps_max_price REAL DEFAULT 0,
                kps_reasoning TEXT DEFAULT '',
                kps_evidence_bonus INTEGER DEFAULT 0,
                kps_confidence REAL DEFAULT 0.0,
                kps_all_matches TEXT DEFAULT '[]',
                -- ML valuation (trained from historical sales)
                ml_price_estimate REAL DEFAULT 0,
                ml_grade TEXT DEFAULT 'PASS',
                ml_investment_score REAL DEFAULT 0.0,
                ml_grade_proba TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS excluded (
                domain TEXT PRIMARY KEY, reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        for k, v in [("current_index", "0"), ("is_running", "0")]:
            conn.execute("INSERT OR IGNORE INTO state (key, value) VALUES (?, ?)", (k, v))
        
        # Column migrations — run in a single pass over PRAGMA table_info
        cursor = conn.execute("PRAGMA table_info(results)")
        cols = {c["name"] for c in cursor.fetchall()}
        _migrations = [
            ("reasoning_ar",    "TEXT",    "''"),
            ("target_buyer_ar", "TEXT",    "''"),
            ("brandable_score", "INTEGER", "0"),
            ("is_brandable",    "INTEGER", "0"),
            ("brand_axes",      "TEXT",    "'{}'"),
            ("brand_reasoning", "TEXT",    "''"),
            ("kps_score",       "INTEGER", "0"),
            ("kps_tier",        "TEXT",    "'none'"),
            ("kps_keyword",     "TEXT",    "''"),
            ("kps_match_type",  "TEXT",    "''"),
            ("kps_avg_price",   "REAL",    "0"),
            ("kps_sale_count",  "INTEGER", "0"),
            ("kps_max_price",   "REAL",    "0"),
            ("kps_reasoning",   "TEXT",    "''"),
            ("kps_evidence_bonus", "INTEGER", "0"),
            ("kps_confidence",  "REAL",    "0.0"),
            ("kps_all_matches", "TEXT",    "'[]'"),
            # Decision Engine V1 fields
            ("opportunity_score",    "INTEGER", "0"),
            ("signal_score",         "INTEGER", "0"),
            ("sellability_score",    "INTEGER", "0"),
            ("risk_score",           "INTEGER", "0"),
            ("risk_flags",           "TEXT",    "'[]'"),
            ("decision_verdict",     "TEXT",    "''"),
            ("decision_reason",      "TEXT",    "''"),
            ("data_quality_score",   "INTEGER", "0"),
            ("name_fit_score",       "INTEGER", "0"),
            ("sell_through_prob",    "REAL",    "0.0"),
            ("max_acquisition_price","INTEGER", "0"),
            ("ideal_acquisition_price","INTEGER","0"),
            ("price_confidence",     "TEXT",    "'low'"),
            ("buyer_persona",        "TEXT",    "''"),
            ("ranking_category",     "TEXT",    "''"),
            ("brand_sellability",    "INTEGER", "0"),
            # Coherence Gate V5 fields
            ("coherence_score",      "INTEGER", "100"),
            ("coherence_passes",     "INTEGER", "1"),
            ("rejection_reasons",    "TEXT",    "'[]'"),
            # Fix #4: persist Decision Engine transient fields
            ("top_signals",          "TEXT",    "'[]'"),
            ("top_risks",            "TEXT",    "'[]'"),
            ("price_warnings",       "TEXT",    "'[]'"),
            ("overpriced_warning",   "TEXT",    "''"),
            ("manual_research",      "INTEGER", "0"),
            ("kps_anchored",         "INTEGER", "0"),
            # Buyer details — previously only in SSE events, now persisted
            ("buyer_clarity",        "TEXT",    "'low'"),
            ("buyer_count_estimate", "TEXT",    "'unknown'"),
            ("outbound_difficulty",  "TEXT",    "'high'"),
            # ML valuation fields
            ("ml_price_estimate",    "REAL",    "0"),
            ("ml_grade",             "TEXT",    "'PASS'"),
            ("ml_investment_score",  "REAL",    "0.0"),
            ("ml_grade_proba",       "TEXT",    "'{}'"),
        ]
        _allowed_cols = {m[0] for m in _migrations}
        for col, typ, default in _migrations:
            if col not in cols:
                if col not in _allowed_cols:
                    raise ValueError(f"Unexpected migration column: {col}")
                # typ and default come from the hardcoded tuple above, never from user input
                conn.execute(f"ALTER TABLE results ADD COLUMN {col} {typ} DEFAULT {default}")

        # ── Indexes for fast filter/sort on large datasets (10x-50x speedup) ──
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_results_total_score ON results(total_score DESC);
            CREATE INDEX IF NOT EXISTS idx_results_verdict     ON results(verdict);
            CREATE INDEX IF NOT EXISTS idx_results_kps_score   ON results(kps_score DESC);
            CREATE INDEX IF NOT EXISTS idx_results_brandable   ON results(is_brandable, brandable_score DESC);
            CREATE INDEX IF NOT EXISTS idx_results_resell      ON results(resell_speed);
            CREATE INDEX IF NOT EXISTS idx_results_geo         ON results(is_geo);
            CREATE INDEX IF NOT EXISTS idx_domains_position    ON domains(position);
            CREATE INDEX IF NOT EXISTS idx_excluded_reason     ON excluded(reason);
        """)

        conn.commit()

    def get_state_val(self, key, default="0"):
        row = self._get_conn().execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state_val(self, key, value):
        with self._write_lock:
            conn = self._get_conn()
            conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()

    def get_current_index(self):
        return int(self.get_state_val("current_index", "0"))

    def set_current_index(self, idx):
        self.set_state_val("current_index", str(idx))

    def is_running(self):
        return self.get_state_val("is_running", "0") == "1"

    def set_running(self, val):
        self.set_state_val("is_running", "1" if val else "0")

    def add_domains(self, domain_list, metadata_map=None):
        with self._write_lock:
            conn = self._get_conn()
            metadata_map = metadata_map or {}
            cur = conn.execute("SELECT COALESCE(MAX(position),0) FROM domains").fetchone()
            pos = (cur[0] or 0) + 1
            added = 0
            for d in domain_list:
                try:
                    meta = json.dumps(metadata_map.get(d, {}))
                    conn.execute("INSERT INTO domains (domain, position, metadata) VALUES (?, ?, ?)", (d, pos, meta))
                    pos += 1
                    added += 1
                except sqlite3.IntegrityError:
                    if d in metadata_map:
                        conn.execute("UPDATE domains SET metadata=? WHERE domain=?", (json.dumps(metadata_map[d]), d))
            conn.commit()
            logger.info(f"Added {added} domains (skipped {len(domain_list)-added} duplicates)")
            return added

    def get_domain_count(self):
        return self._get_conn().execute("SELECT COUNT(*) FROM domains").fetchone()[0]

    def get_domains_window(self, offset: int, size: int = 500):
        """Return up to `size` domains starting at `offset`.
        Replaces repeated get_domain_at calls to avoid O(N²) OFFSET scans.
        """
        rows = self._get_conn().execute(
            "SELECT domain, metadata FROM domains ORDER BY position LIMIT ? OFFSET ?",
            (size, offset)
        ).fetchall()
        return [(r["domain"], _safe_meta(r["metadata"])) for r in rows]

    def _result_to_tuple(self, r):
        """Convert a result dict to INSERT values tuple."""
        return (
            r.get("Domain", ""),
            r.get("Verdict", "PASS"),
            int(r.get("TotalScore", 0)),
            r.get("DomainType", "low_value"),
            r.get("DomainTypeLabel", ""),
            r.get("TargetBuyer", ""),
            r.get("ResellSpeed", "Slow"),
            r.get("Reasoning", ""),
            # 6 Axes
            int(r.get("CommercialIntent", 0)),
            int(r.get("MarketDemand", 0)),
            int(r.get("Clarity", 0)),
            int(r.get("BuyerPool", 0)),
            int(r.get("GeoNiche", 0)),
            int(r.get("Liquidity", 0)),
            # Context
            r.get("NicheName", "-"),
            r.get("NicheTier", "none"),
            r.get("GeoName", ""),
            1 if r.get("IsGeo") else 0,
            # Penalties & Pricing
            int(r.get("Penalties", 0)),
            r.get("PenaltyReasons", ""),
            r.get("ReasoningAR", ""),
            r.get("TargetBuyerAR", ""),
            int(r.get("PriceLow", 0)),
            int(r.get("PriceHigh", 0)),
            # Brandable Engine
            int(r.get("BrandableScore", 0)),
            1 if r.get("IsBrandable") else 0,
            json.dumps(r.get("BrandAxes", {})),
            r.get("BrandReasoning", ""),
            # Keyword Power Score (KPS)
            int(r.get("KeywordPowerScore", 0)),
            r.get("KPSTier", "none"),
            r.get("KPSKeyword", ""),
            r.get("KPSMatchType", ""),
            float(r.get("KPSAvgPrice", 0)),
            int(r.get("KPSSaleCount", 0)),
            float(r.get("KPSMaxPrice", 0)),
            r.get("KPSReasoning", ""),
            int(r.get("KPSEvidenceBonus", 0)),
            float(r.get("KPSConfidence", 0.0)),
            json.dumps(r.get("KPSAllMatches", [])),
            # Decision Engine V1
            int(r.get("OpportunityScore", 0)),
            int(r.get("SignalScore", 0)),
            int(r.get("SellabilityScore", 0)),
            int(r.get("RiskScore", 0)),
            json.dumps(r.get("RiskFlags", [])),
            r.get("DecisionVerdict", ""),
            r.get("DecisionReason", ""),
            int(r.get("DataQualityScore", 0)),
            int(r.get("NameFitScore", 0)),
            float(r.get("SellThroughProbability", 0.0)),
            int(r.get("MaxAcquisitionPrice", 0)),
            int(r.get("IdealAcquisitionPrice", 0)),
            r.get("PriceConfidence", "low"),
            r.get("BuyerPersona", ""),
            r.get("RankingCategory", ""),
            int(r.get("BrandSellabilityScore", 0)),
            int(r.get("CoherenceScore", 100)),
            int(bool(r.get("CoherencePasses", True))),
            json.dumps(r.get("RejectionReasons", [])),
            # Fix #4: persist previously transient Decision Engine fields
            json.dumps(r.get("TopSignals", [])),
            json.dumps(r.get("TopRisks", [])),
            json.dumps(r.get("PriceWarnings", [])),
            r.get("OverpricedWarning", "") or "",
            int(bool(r.get("ManualResearchRequired", False))),
            int(bool(r.get("KPSAnchored", False))),
            # Buyer details
            r.get("BuyerClarity", "low") or "low",
            r.get("BuyerCountEstimate", "unknown") or "unknown",
            r.get("OutboundDifficulty", "high") or "high",
            # ML valuation
            float(r.get("MLPriceEstimate", 0)),
            r.get("MLGrade", "PASS"),
            float(r.get("MLInvestmentScore", 0.0)),
            json.dumps(r.get("MLGradeProba", {})),
        )

    _INSERT_SQL = """
        INSERT OR REPLACE INTO results
        (domain, verdict, total_score, domain_type, domain_type_label,
         target_buyer, resell_speed, reasoning,
         commercial_intent, market_demand, clarity, buyer_pool, geo_niche, liquidity,
         niche_name, niche_tier, geo_name, is_geo,
         penalties, penalty_reasons, reasoning_ar, target_buyer_ar,
         price_low, price_high,
         brandable_score, is_brandable, brand_axes, brand_reasoning,
         kps_score, kps_tier, kps_keyword, kps_match_type,
         kps_avg_price, kps_sale_count, kps_max_price, kps_reasoning, kps_evidence_bonus,
         kps_confidence, kps_all_matches,
         opportunity_score, signal_score, sellability_score, risk_score, risk_flags,
         decision_verdict, decision_reason, data_quality_score, name_fit_score,
         sell_through_prob, max_acquisition_price, ideal_acquisition_price,
         price_confidence, buyer_persona, ranking_category, brand_sellability,
         coherence_score, coherence_passes, rejection_reasons,
         top_signals, top_risks, price_warnings, overpriced_warning,
         manual_research, kps_anchored,
         buyer_clarity, buyer_count_estimate, outbound_difficulty,
         ml_price_estimate, ml_grade, ml_investment_score, ml_grade_proba)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    def add_result(self, r):
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(self._INSERT_SQL, self._result_to_tuple(r))
            conn.commit()

    def add_results_batch(self, results):
        with self._write_lock:
            conn = self._get_conn()
            for r in results:
                conn.execute(self._INSERT_SQL, self._result_to_tuple(r))
            conn.commit()

    def get_results(self, limit=0, offset=0):
        sql = """
            SELECT r.*, d.metadata as csv_metadata
            FROM results r
            LEFT JOIN domains d ON r.domain = d.domain
            ORDER BY r.total_score DESC
        """
        params = []
        # Always push LIMIT/OFFSET into SQLite — never fetch all then slice in Python
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params = [limit, offset]
        elif offset > 0:
            # No limit but has offset — fetch everything from offset onward
            sql += " LIMIT -1 OFFSET ?"
            params = [offset]
        rows = self._get_conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_brandable_ranked(self):
        """Return brandable domains sorted by score — used to build rank map efficiently."""
        rows = self._get_conn().execute(
            "SELECT domain, brandable_score FROM results WHERE is_brandable=1 ORDER BY brandable_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self):
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(MAX(total_score), 0) AS highest,
                COALESCE(SUM(CASE WHEN verdict='GEM'         THEN 1 ELSE 0 END), 0) AS gem,
                COALESCE(SUM(CASE WHEN verdict='BUY'         THEN 1 ELSE 0 END), 0) AS buy,
                COALESCE(SUM(CASE WHEN verdict='HOLD'        THEN 1 ELSE 0 END), 0) AS hold,
                COALESCE(SUM(CASE WHEN is_geo=1              THEN 1 ELSE 0 END), 0) AS geo,
                COALESCE(SUM(CASE WHEN resell_speed='Fast'   THEN 1 ELSE 0 END), 0) AS fast,
                COALESCE(SUM(CASE WHEN is_brandable=1        THEN 1 ELSE 0 END), 0) AS brandable
            FROM results
        """).fetchone()
        return {
            "total_scored":    row["total"],
            "highest":         row["highest"],
            "gem_count":       row["gem"],
            "buy_count":       row["buy"],
            "hold_count":      row["hold"],
            "geo_count":       row["geo"],
            "fast_count":      row["fast"],
            "brandable_count": row["brandable"],
        }

    def add_excluded(self, domain, reason):
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR IGNORE INTO excluded (domain, reason) VALUES (?, ?)", (domain, reason)
            )
            conn.commit()

    def get_excluded_counts(self) -> dict:
        """Return counts per exclusion reason — lightweight, no full list load."""
        rows = self._get_conn().execute(
            "SELECT reason, COUNT(*) as cnt FROM excluded GROUP BY reason"
        ).fetchall()
        result = {"trademark": 0, "hard": 0, "gibberish": 0, "error": 0}
        for r in rows:
            reason = r["reason"] if r["reason"] else "error"
            key = reason if reason in result else "error"
            result[key] += r["cnt"]
        return result

    def close(self):
        """Close the thread-local SQLite connection and force a WAL checkpoint."""
        conn = getattr(self._local, 'conn', None)
        if conn:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    def reset(self):
        with self._write_lock:
            conn = self._get_conn()
            conn.executescript("DELETE FROM domains; DELETE FROM results; DELETE FROM excluded; DELETE FROM state;")
            for k, v in [("current_index", "0"), ("is_running", "0")]:
                conn.execute("INSERT INTO state (key, value) VALUES (?, ?)", (k, v))
            conn.commit()
            logger.info("Database reset complete")

    def export_csv(self, verdict_filter=None, brandable_only=False):
        conn = self._get_conn()
        if brandable_only:
            rows = conn.execute(
                "SELECT " + _EXPORT_COLS + " FROM results WHERE is_brandable=1 ORDER BY brandable_score DESC"
            ).fetchall()
        elif verdict_filter:
            if isinstance(verdict_filter, str):
                verdict_filter = [verdict_filter]
            placeholders = ",".join("?" * len(verdict_filter))
            rows = conn.execute(
                "SELECT " + _EXPORT_COLS + " FROM results WHERE verdict IN (" + placeholders + ") ORDER BY total_score DESC",
                verdict_filter
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT " + _EXPORT_COLS + " FROM results ORDER BY total_score DESC"
            ).fetchall()
        if not rows:
            return None
        buf = io.StringIO()
        writer = csv.writer(buf)
        header = _EXPORT_COLS.split(",")
        header = [h.replace("_", " ").title() for h in header]
        writer.writerow(header)
        for r in rows:
            writer.writerow(list(r))
        return buf.getvalue()
