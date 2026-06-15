"""
Domain Value Analyzer V4 — Flask Backend
Market Intelligence Scoring with Investor Logic.
"""
from flask import Flask, render_template, request, jsonify, Response, send_file
import json
import io
import re
import threading
import logging
import atexit
from urllib.parse import urlparse
import pandas as pd

from database import Database
from analyzer.pipeline import process_domain
from config import PENALTIES, SCORE_THRESHOLDS, BATCH_SAVE_INTERVAL, LOG_FILE, LOG_LEVEL

# ─── Logging Setup ───
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("analyzer.app")

app = Flask(__name__)
# Reject uploads larger than 100 MB (covers ~1M-row CSVs, blocks DoS)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

db = Database()
atexit.register(db.close)
stop_flag = threading.Event()
_start_lock = threading.Lock()  # prevents concurrent /api/start race condition

MAX_CSV_ROWS = 100_000  # safety cap; prevents 5M-row files from exhausting memory

# ─── Pre-warm KPS retail data at startup ───
# The CSV is 6.6 MB / 96k keywords. Loading it on the first /api/start request
# adds 200-400 ms latency to the first domain analyzed. Pre-loading at import
# time hides that cost and keeps the analysis loop tight.
def _prewarm_kps():
    try:
        from analyzer.retail_kps import _load
        _load()
        logger.info("KPS retail data pre-loaded successfully")
    except Exception as e:
        logger.warning(f"KPS pre-warm failed (will lazy-load): {e}")

threading.Thread(target=_prewarm_kps, daemon=True).start()


# ─── Verify ML model artifacts at startup ───
def _verify_ml_artifacts():
    try:
        from analyzer.ml_valuation import load_artifacts
        load_artifacts()
        logger.info("ML valuation artifacts loaded successfully")
    except FileNotFoundError as e:
        logger.error(f"ML model artifacts not found: {e}. Run scripts/retrain_ml_combined_real.py before starting analysis.")
    except Exception as e:
        logger.error(f"ML valuation startup check failed: {e}", exc_info=True)

_verify_ml_artifacts()


# ━━━━━━━━━━━━ Helpers ━━━━━━━━━━━━
def _parse_json(raw, default=None):
    """Safely parse a JSON string from the DB. Returns default on failure."""
    if default is None:
        default = {}
    try:
        val = json.loads(raw) if raw else default
        return val if isinstance(val, (dict, list)) else default
    except (json.JSONDecodeError, TypeError):
        return default

_DOMAIN_RE = re.compile(r'^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)+$')

def clean_domain(d):
    if not d or not isinstance(d, str):
        return None
    d = d.lower().strip().replace("http://", "").replace("https://", "").replace("www.", "")
    d = d.split('/')[0].strip('"').strip("'").strip()
    if not d or '.' not in d:
        return None
    # Strict allow-list: only lowercase letters, digits, hyphens, dots.
    # Rejects HTML/JS-special chars (defense-in-depth against XSS via stored domain).
    if not _DOMAIN_RE.match(d):
        return None
    parts = d.split('.')
    if len(parts[-1]) < 2:
        return None
    return d


# ━━━━━━━━━━━━ Security Helpers ━━━━━━━━━━━━

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


def _is_local_origin() -> bool:
    """Return True if the request originates from localhost (CSRF guard).

    Uses urlparse to extract the exact hostname so that
    http://localhost.evil.com does NOT pass this check.
    """
    for header in ('Origin', 'Referer'):
        val = request.headers.get(header, '')
        if val:
            try:
                parsed = urlparse(val)
                host = parsed.hostname or ''
                return host in ('localhost', '127.0.0.1')
            except Exception:
                return False
    return False  # no Origin/Referer header → unknown origin → deny mutations


# ━━━━━━━━━━━━ Error Handlers ━━━━━━━━━━━━
@app.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": "File too large (max 100 MB)"}), 413


# ━━━━━━━━━━━━ PAGE ━━━━━━━━━━━━
@app.route('/')
def index():
    return render_template('index.html')


# ━━━━━━━━━━━━ API — Domain Input ━━━━━━━━━━━━
@app.route('/api/domains', methods=['POST'])
def add_domains():
    data = request.get_json(silent=True) or {}
    raw = data.get('domains', []) or []
    metadata = data.get('metadata', {}) or {}
    if not isinstance(raw, list):
        return jsonify({"error": "domains must be a list"}), 400
    clean = [c for d in raw if (c := clean_domain(d))]
    if not clean:
        return jsonify({"error": "No valid domains"}), 400
    # Auto-detect flat metadata format {"cpc": 5} vs per-domain {"foo.com": {"cpc": 5}}.
    # If none of the values are dicts, treat metadata as applying to all domains.
    if metadata and not any(isinstance(v, dict) for v in metadata.values()):
        metadata = {d: metadata for d in clean}
    added = db.add_domains(clean, metadata)
    total = db.get_domain_count()
    return jsonify({"added": added, "duplicates_skipped": len(clean) - added, "total": total})


@app.route('/api/upload/csv', methods=['POST'])
def upload_csv():
    file = request.files.get('file')
    domain_col = request.form.get('domain_column', '')
    if not file:
        return jsonify({"error": "No file"}), 400
    try:
        raw = file.read()
        for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        else:
            text = raw.decode('utf-8', errors='ignore')

        # Use sep=None and engine='python' to auto-detect commas, semicolons, and tabs.
        # on_bad_lines='skip' prevents the parser from crashing on malformed lines.
        df = pd.read_csv(io.StringIO(text), sep=None, engine='python', on_bad_lines='skip', nrows=MAX_CSV_ROWS)
        df.columns = [str(c).strip().strip('"').strip("'") for c in df.columns]

        if not domain_col or domain_col not in df.columns:
            domain_col_clean = domain_col.strip().strip('"').strip("'")
            matched = False
            for col in df.columns:
                if col.lower().strip() in ('domain', 'name', 'domains', 'url', 'website'):
                    domain_col = col
                    matched = True
                    break
            if not matched:
                for col in df.columns:
                    if col == domain_col_clean:
                        domain_col = col
                        matched = True
                        break
                if not matched:
                    domain_col = df.columns[0]

        col_map = {}
        for c in df.columns:
            cl = c.strip().lower()
            if cl == 'cpc': col_map['cpc'] = c
            elif cl == 'dp': col_map['dp'] = c
            elif cl == 'bl': col_map['bl'] = c
            elif cl in ('aby', 'birth'): col_map['aby'] = c
            elif cl == 'wby': col_map['wby'] = c
            elif cl == 'acr': col_map['acr'] = c
            elif cl in ('rdt', 'redirect'): col_map['rdt'] = c
            elif cl == 'reg': col_map['reg'] = c
            elif cl == 'le': col_map['le'] = c
            elif cl in ('sv', 'sg', 'search volume', 'exact search', 'lms', 'gms'): col_map['sv'] = c

        domains, metadata = [], {}
        for row in df.to_dict('records'):
            d = clean_domain(str(row[domain_col]))
            if not d:
                continue
            domains.append(d)
            m = {}
            for key, csv_col in col_map.items():
                try:
                    val_str = str(row[csv_col]).strip().strip('"').strip("'").lower()
                    val_str = val_str.replace('$', '').replace(',', '').strip()
                    if val_str and val_str != '-' and val_str != 'nan':
                        multiplier = 1
                        if val_str.endswith('k'):
                            multiplier = 1000
                            val_str = val_str[:-1]
                        elif val_str.endswith('m'):
                            multiplier = 1000000
                            val_str = val_str[:-1]
                        
                        num = float(val_str) * multiplier
                        m[key] = float(num) if key == 'cpc' else int(num)
                except (ValueError, TypeError):
                    pass
            if m:
                metadata[d] = m

        added = db.add_domains(domains, metadata)
        total = db.get_domain_count()
        logger.info(f"CSV upload: {added} added, {len(metadata)} enriched, columns: {list(col_map.keys())}")
        return jsonify({
            "added": added, "duplicates_skipped": len(domains) - added,
            "enriched": len(metadata), "detected": list(col_map.keys()), "total": total
        })
    except Exception as e:
        logger.error(f"CSV upload error: {e}", exc_info=True)
        return jsonify({"error": "CSV upload failed"}), 400


# ━━━━━━━━━━━━ API — Analysis (SSE) ━━━━━━━━━━━━
@app.route('/api/start')
def start_analysis():
    # CSRF guard: SSE/EventSource only supports GET, but starting analysis
    # mutates state. Reject cross-origin requests at the request line so a
    # malicious page can't trigger a run by embedding the URL.
    if not _is_local_origin():
        return jsonify({"error": "Forbidden"}), 403
    # Atomic check+set: prevents two simultaneous /api/start requests from
    # both passing the is_running check and spawning duplicate generators.
    with _start_lock:
        if db.is_running():
            return jsonify({"error": "Analysis already running"}), 409
        stop_flag.clear()
        db.set_running(True)  # claim the slot before leaving the lock

    def generate():
        idx = db.get_current_index()
        total = db.get_domain_count()
        batch_buffer = []
        _WINDOW = 500          # rows fetched per DB round-trip
        _window_cache = []     # in-memory slice of domains
        _window_start = None   # None until first fetch; avoids -1 sentinel arithmetic

        def _get_domain(i):
            """Return (domain, extra) for position i using a sliding window."""
            nonlocal _window_cache, _window_start
            if _window_start is None or i < _window_start or i >= _window_start + len(_window_cache):
                _window_cache = db.get_domains_window(i, _WINDOW)
                _window_start = i
            local = i - _window_start
            if local < len(_window_cache):
                return _window_cache[local]
            return None, None

        try:
            while not stop_flag.is_set():
                # Re-fetch total each iteration so newly uploaded domains
                # added during a long run get picked up.
                total = db.get_domain_count()
                if idx >= total:
                    break
                domain, extra = _get_domain(idx)
                if domain is None:
                    idx += 1
                    continue

                evt = {'type': 'progress', 'domain': domain, 'index': idx + 1, 'total': total}

                try:
                    result = process_domain(domain, extra_data=extra)

                    if "ExcludeReason" in result:
                        reason = result["ExcludeReason"]
                        db.add_excluded(domain, reason)
                        evt['result_type'] = 'scored'
                        evt['exclude_reason'] = reason
                        evt['is_excluded'] = True
                    else:
                        batch_buffer.append(result)
                        evt['result_type'] = 'scored'
                        evt['result'] = {
                            'domain': result.get('Domain', ''),
                            'verdict': result.get('Verdict', 'PASS'),
                            'total_score': int(result.get('TotalScore', 0)),
                            'domain_type': result.get('DomainType', 'low_value'),
                            'domain_type_label': result.get('DomainTypeLabel', ''),
                            'target_buyer': result.get('TargetBuyer', ''),
                            'resell_speed': result.get('ResellSpeed', 'Slow'),
                            'reasoning': result.get('Reasoning', ''),
                            'reasoning_ar': result.get('ReasoningAR', ''),
                            'target_buyer_ar': result.get('TargetBuyerAR', ''),
                            'csv_metadata': extra,
                            # 6 Axes
                            'commercial_intent': int(result.get('CommercialIntent', 0)),
                            'market_demand': int(result.get('MarketDemand', 0)),
                            'clarity': int(result.get('Clarity', 0)),
                            'buyer_pool': int(result.get('BuyerPool', 0)),
                            'geo_niche': int(result.get('GeoNiche', 0)),
                            'liquidity': int(result.get('Liquidity', 0)),
                            # Context
                            'niche': result.get('NicheName', '-'),
                            'niche_tier': result.get('NicheTier', 'none'),
                            'geo_name': result.get('GeoName', ''),
                            'is_geo': result.get('IsGeo', False),
                            # Penalties & Pricing
                            'penalties': int(result.get('Penalties', 0)),
                            'penalty_reasons': result.get('PenaltyReasons', ''),
                            'price_low': int(result.get('PriceLow', 0)),
                            'price_high': int(result.get('PriceHigh', 0)),
                            # Brandable Engine
                            'brandable_score': int(result.get('BrandableScore', 0)),
                            'is_brandable': bool(result.get('IsBrandable', False)),
                            'brand_axes': result.get('BrandAxes', {}),
                            'brand_reasoning': result.get('BrandReasoning', ''),
                            # Keyword Power Score (KPS)
                            'kps_score': int(result.get('KeywordPowerScore', 0)),
                            'kps_tier': result.get('KPSTier', 'none'),
                            'kps_keyword': result.get('KPSKeyword', ''),
                            'kps_match_type': result.get('KPSMatchType', ''),
                            'kps_avg_price': float(result.get('KPSAvgPrice', 0)),
                            'kps_sale_count': int(result.get('KPSSaleCount', 0)),
                            'kps_max_price': float(result.get('KPSMaxPrice', 0)),
                            'kps_reasoning': result.get('KPSReasoning', ''),
                            'kps_evidence_bonus': int(result.get('KPSEvidenceBonus', 0)),
                            'kps_confidence': float(result.get('KPSConfidence', 0.0)),
                            'kps_anchored': bool(result.get('KPSAnchored', False)),
                            'kps_all_matches': result.get('KPSAllMatches', []),
                            'kps_keywords_matched': result.get('KPSKeywordsMatched', []),
                            # Decision Engine V1
                            'opportunity_score': int(result.get('OpportunityScore', 0)),
                            'signal_score': int(result.get('SignalScore', 0)),
                            'sellability_score': int(result.get('SellabilityScore', 0)),
                            'risk_score': int(result.get('RiskScore', 0)),
                            'risk_flags': result.get('RiskFlags', []),
                            'decision_verdict': result.get('DecisionVerdict', ''),
                            'decision_reason': result.get('DecisionReason', ''),
                            'data_quality_score': int(result.get('DataQualityScore', 0)),
                            'name_fit_score': int(result.get('NameFitScore', 0)),
                            'sell_through_prob': float(result.get('SellThroughProbability', 0.0)),
                            'max_acquisition_price': int(result.get('MaxAcquisitionPrice', 0)),
                            'ideal_acquisition_price': int(result.get('IdealAcquisitionPrice', 0)),
                            'price_confidence': result.get('PriceConfidence', 'low'),
                            'price_warnings': result.get('PriceWarnings', []),
                            'buyer_persona': result.get('BuyerPersona', ''),
                            'buyer_clarity': result.get('BuyerClarity', 'low'),
                            'buyer_count_estimate': result.get('BuyerCountEstimate', 'unknown'),
                            'outbound_difficulty': result.get('OutboundDifficulty', 'high'),
                            'ranking_category': result.get('RankingCategory', ''),
                            'brand_sellability': int(result.get('BrandSellabilityScore', 0)),
                            'top_signals': result.get('TopSignals', []),
                            'top_risks': result.get('TopRisks', []),
                            'overpriced_warning': result.get('OverpricedWarning', ''),
                            'manual_research': bool(result.get('ManualResearchRequired', False)),
                            # ML valuation
                            'ml_price_estimate': float(result.get('MLPriceEstimate', 0)),
                            'ml_grade': result.get('MLGrade', 'PASS'),
                            'ml_investment_score': float(result.get('MLInvestmentScore', 0.0)),
                            'ml_grade_proba': result.get('MLGradeProba', {}),
                        }

                        if len(batch_buffer) >= BATCH_SAVE_INTERVAL:
                            db.add_results_batch(batch_buffer)
                            batch_buffer = []
                            db.set_current_index(idx + 1)

                except Exception as e:
                    logger.error(f"Error processing {domain}: {e}", exc_info=True)
                    db.add_excluded(domain, "error")
                    evt['result_type'] = 'error'

                idx += 1
                try:
                    yield f"data: {json.dumps(evt)}\n\n"
                except GeneratorExit:
                    # Client disconnected — stop this generator but don't set
                    # the global stop_flag so a fresh reconnect can resume.
                    logger.info("SSE client disconnected — generator stopping")
                    break

            # All domains processed — emit completion event before finally cleanup
            if not stop_flag.is_set():
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        finally:
            if batch_buffer:
                db.add_results_batch(batch_buffer)
            db.set_current_index(idx)  # persist final position
            db.set_running(False)
            logger.info("SSE generator exited, is_running set to False")

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/stop', methods=['POST'])
def stop_analysis():
    if not _is_local_origin():
        return jsonify({"error": "Forbidden"}), 403
    stop_flag.set()
    # Don't call db.set_running(False) here — the generator's finally block
    # handles it after it finishes processing. Setting it here races with
    # a new /api/start arriving before the generator completes.
    logger.info("Analysis stopped by user")
    return jsonify({"status": "stopped"})


@app.route('/api/reset', methods=['POST'])
def reset_all():
    if not _is_local_origin():
        return jsonify({"error": "Forbidden"}), 403
    stop_flag.set()
    db.reset()
    logger.info("Full reset")
    return jsonify({"status": "reset"})


# ━━━━━━━━━━━━ API — State & Results ━━━━━━━━━━━━
@app.route('/api/state')
def get_state():
    stats = db.get_stats()
    excl = db.get_excluded_counts()
    from analyzer.coherence_gate import _DEGRADED_MODE as _coh_degraded
    return jsonify({
        'coherence_degraded': _coh_degraded,
        'current_index': db.get_current_index(),
        'total_domains': db.get_domain_count(),
        'is_running': db.is_running(),
        'total_scored': stats['total_scored'],
        'highest': stats['highest'],
        'gem_count': stats['gem_count'],
        'buy_count': stats['buy_count'],
        'hold_count': stats['hold_count'],
        'geo_count': stats['geo_count'],
        'fast_count': stats['fast_count'],
        'brandable_count': stats['brandable_count'],
        'excluded_tm': excl['trademark'],
        'excluded_hd': excl['hard'],
        'excluded_gb': excl['gibberish'],
    })


@app.route('/api/results')
def get_results():
    # Optional pagination: ?limit=N&offset=M — keeps backward compat (default = all rows)
    try:
        limit  = int(request.args.get('limit', 0))
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        limit, offset = 0, 0
    limit  = max(0, min(limit, 100_000))
    offset = max(0, offset)

    # Brandable ranks require the full brandable dataset regardless of pagination.
    # We fetch only the brandable count + rank data separately (lightweight query).
    brandable_rank_map = {}
    if limit > 0:
        # Build rank map from DB without loading full result payload
        all_brandable = db.get_brandable_ranked()
        brandable_rank_map = {r['domain']: idx + 1 for idx, r in enumerate(all_brandable)}

    # Fetch page of results directly from DB — no Python-level slice
    rows = db.get_results(limit=limit, offset=offset)
    if not rows:
        return jsonify([])

    # When no pagination: build rank map from fetched rows
    if limit == 0:
        brandable_sorted = sorted(
            [r for r in rows if r.get('is_brandable')],
            key=lambda x: x.get('brandable_score', 0),
            reverse=True
        )
        brandable_rank_map = {r['domain']: idx + 1 for idx, r in enumerate(brandable_sorted)}

    records = []
    for i, r in enumerate(rows):
        domain = r.get('domain', '')
        brand_axes_raw = r.get('brand_axes', '{}')
        try:
            brand_axes = json.loads(brand_axes_raw) if brand_axes_raw else {}
        except (json.JSONDecodeError, TypeError):
            brand_axes = {}

        try:
            csv_meta_raw = r.get('csv_metadata') or '{}'
            csv_metadata = json.loads(csv_meta_raw)
            if not isinstance(csv_metadata, dict):
                csv_metadata = {}
        except (json.JSONDecodeError, TypeError):
            csv_metadata = {}

        # Global rank = offset + position in this page
        global_rank = (offset + i + 1) if limit > 0 else (i + 1)

        records.append({
            'rank': global_rank,
            'domain': domain,
            'verdict': r.get('verdict', 'PASS'),
            'total_score': r.get('total_score', 0),
            'domain_type': r.get('domain_type', 'low_value'),
            'domain_type_label': r.get('domain_type_label', ''),
            'target_buyer': r.get('target_buyer', ''),
            'resell_speed': r.get('resell_speed', 'Slow'),
            'reasoning': r.get('reasoning', ''),
            'reasoning_ar': r.get('reasoning_ar', ''),
            'target_buyer_ar': r.get('target_buyer_ar', ''),
            'csv_metadata': csv_metadata,
            # 6 Axes
            'commercial_intent': r.get('commercial_intent', 0),
            'market_demand': r.get('market_demand', 0),
            'clarity': r.get('clarity', 0),
            'buyer_pool': r.get('buyer_pool', 0),
            'geo_niche': r.get('geo_niche', 0),
            'liquidity': r.get('liquidity', 0),
            # Context
            'niche': r.get('niche_name', '-'),
            'niche_tier': r.get('niche_tier', 'none'),
            'geo_name': r.get('geo_name', ''),
            'is_geo': r.get('is_geo', 0),
            # Penalties & Pricing
            'penalties': r.get('penalties', 0),
            'penalty_reasons': r.get('penalty_reasons', ''),
            'price_low': r.get('price_low', 0),
            'price_high': r.get('price_high', 0),
            # Brandable Engine
            'brandable_score': r.get('brandable_score', 0),
            'is_brandable': bool(r.get('is_brandable', 0)),
            'brandable_rank': brandable_rank_map.get(domain, None),
            'brand_axes': brand_axes,
            'brand_reasoning': r.get('brand_reasoning', ''),
            # Keyword Power Score (KPS)
            'kps_score': r.get('kps_score', 0),
            'kps_tier': r.get('kps_tier', 'none'),
            'kps_keyword': r.get('kps_keyword', ''),
            'kps_match_type': r.get('kps_match_type', ''),
            'kps_avg_price': r.get('kps_avg_price', 0),
            'kps_sale_count': r.get('kps_sale_count', 0),
            'kps_max_price': r.get('kps_max_price', 0),
            'kps_reasoning': r.get('kps_reasoning', ''),
            'kps_evidence_bonus': r.get('kps_evidence_bonus', 0),
            'kps_confidence': round(float(r.get('kps_confidence', 0.0)), 2),
            'kps_anchored': bool(r.get('kps_anchored', 0)),
            'kps_all_matches': _parse_json(r.get('kps_all_matches', '[]'), []),
            'kps_keywords_matched': [
                m['keyword'] for m in _parse_json(r.get('kps_all_matches', '[]'), [])
                if isinstance(m, dict) and 'keyword' in m
            ],
            # Coherence Gate (V5) — exposed for UI debugging / rejection display
            'coherence_score': r.get('coherence_score', 100),
            'coherence_passes': bool(r.get('coherence_passes', 1)),
            'rejection_reasons': _parse_json(r.get('rejection_reasons', '[]'), []),
            # Decision Engine fields
            'opportunity_score': r.get('opportunity_score', 0),
            'signal_score': r.get('signal_score', 0),
            'sellability_score': r.get('sellability_score', 0),
            'risk_score': r.get('risk_score', 0),
            'risk_flags': _parse_json(r.get('risk_flags', '[]'), []),
            'decision_verdict': r.get('decision_verdict', ''),
            'decision_reason': r.get('decision_reason', ''),
            'data_quality_score': r.get('data_quality_score', 0),
            'name_fit_score': r.get('name_fit_score', 0),
            'sell_through_prob': float(r.get('sell_through_prob', 0.0) or 0.0),
            'max_acquisition_price': r.get('max_acquisition_price', 0),
            'ideal_acquisition_price': r.get('ideal_acquisition_price', 0),
            'price_confidence': r.get('price_confidence', 'low'),
            'price_warnings': _parse_json(r.get('price_warnings', '[]'), []),
            'overpriced_warning': r.get('overpriced_warning', ''),
            'buyer_persona': r.get('buyer_persona', ''),
            'buyer_clarity': r.get('buyer_clarity', 'low'),
            'buyer_count_estimate': r.get('buyer_count_estimate', 'unknown'),
            'outbound_difficulty': r.get('outbound_difficulty', 'high'),
            'ranking_category': r.get('ranking_category', ''),
            'brand_sellability': r.get('brand_sellability', 0),
            'top_signals': _parse_json(r.get('top_signals', '[]'), []),
            'top_risks': _parse_json(r.get('top_risks', '[]'), []),
            'manual_research': bool(r.get('manual_research', 0)),
            # ML valuation
            'ml_price_estimate': float(r.get('ml_price_estimate', 0) or 0),
            'ml_grade': r.get('ml_grade', 'PASS'),
            'ml_investment_score': float(r.get('ml_investment_score', 0.0) or 0.0),
            'ml_grade_proba': _parse_json(r.get('ml_grade_proba', '{}'), {}),
        })
    return jsonify(records)


@app.route('/api/results/count')
def get_results_count():
    """Lightweight count endpoint — returns just totals, no payload bloat."""
    stats = db.get_stats()
    return jsonify({"total": stats['total_scored']})


@app.route('/api/export/all')
def export_all():
    csv_data = db.export_csv()
    if not csv_data:
        return jsonify({"error": "No results"}), 404
    buf = io.BytesIO(csv_data.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', as_attachment=True, download_name='all_results.csv')


@app.route('/api/export/buy')
def export_buy():
    csv_data = db.export_csv(verdict_filter=['GEM', 'BUY'])
    if not csv_data:
        return jsonify({"error": "No GEM/BUY results"}), 404
    buf = io.BytesIO(csv_data.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', as_attachment=True, download_name='gem_buy.csv')


@app.route('/api/export/brandable')
def export_brandable():
    csv_data = db.export_csv(brandable_only=True)
    if not csv_data:
        return jsonify({"error": "No brandable results"}), 404
    buf = io.BytesIO(csv_data.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', as_attachment=True, download_name='brandable_domains.csv')


# ━━━━━━━━━━━━ LAUNCH ━━━━━━━━━━━━
if __name__ == '__main__':
    import webbrowser
    print("\n  ◆ Domain Value Analyzer — V4 Market Intelligence")
    print("  → http://localhost:5050\n")
    webbrowser.open('http://localhost:5050')
    app.run(host='127.0.0.1', port=5050, debug=False, threaded=True)
