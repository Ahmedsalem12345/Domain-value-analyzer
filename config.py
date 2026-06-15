"""
Domain Value Analyzer V4 — Market Intelligence Configuration
Scoring: Commercial (25) + Demand (20) + Clarity (15) + Buyers (15) + Geo+Niche (15) + Liquidity (10) = 100
Philosophy: "Can this domain realistically be sold for profit?"
"""
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "DomainValueAnalyzerV4"
DB_FILE = APP_SUPPORT_DIR / "analyzer_v4.db"
LOG_FILE = APP_SUPPORT_DIR / "analyzer.log"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)

# ━━━━━━━━━━━━ Verdict Thresholds ━━━━━━━━━━━━
SCORE_THRESHOLDS = {"GEM": 72, "BUY": 65, "HOLD": 40}
# Below 40 → PASS

VERDICT_LABELS = {
    "GEM":  "💎 GEM — Buy immediately",
    "BUY":  "✅ BUY — Strong opportunity",
    "HOLD": "⏳ HOLD — Needs more research",
    "PASS": "❌ PASS — Skip",
}

# ━━━━━━━━━━━━ Axis Maximums ━━━━━━━━━━━━
AXIS_MAX = {
    "COMMERCIAL_INTENT": 25,
    "MARKET_DEMAND": 20,
    "CLARITY": 15,
    "BUYER_POOL": 15,
    "GEO_NICHE": 15,
    "LIQUIDITY": 10,
}

# ━━━━━━━━━━━━ CPC Tiers (real market data) ━━━━━━━━━━━━
CPC_TIERS = [
    (15.0, 25),   # Ultra-premium: insurance, legal, finance
    (8.0,  20),   # Premium: medical, real estate
    (4.0,  15),   # Strong: tech, SaaS
    (2.0,  10),   # Good: business services
    (0.5,  5),    # Moderate: general commerce
    (0.01, 2),    # Minimal signal
]

# ━━━━━━━━━━━━ Niche Categories (V4.1 — expanded with dynamic industries) ━━━━━━━━━━━━
NICHE_CATEGORIES = {
    "tier1": ["Insurance/Legal", "Finance"],
    "tier2": ["Health/Medical", "Real Estate", "AI/Machine Learning", "Crypto/Blockchain", "Gaming"],
    "tier3": ["Tech/SaaS", "E-commerce/Retail", "Cloud/Hosting", "Business/Marketing",
              "Logistics/Supply Chain", "Cannabis/CBD"],
    "tier4": ["Education", "Travel", "Security", "Fitness/Wellness", "Jobs/Career",
              "Space/Aerospace", "HR/Staffing", "Manufacturing/Industrial", "Agriculture/AgTech"],
    "tier5": ["Entertainment", "Automotive", "Fashion/Beauty", "Home/Garden",
              "Sports", "Food/Restaurant", "Dating/Relationships", "Pets",
              "Green/Eco", "Music", "Photography"],
}

NICHE_TIER_SCORES = {
    # V5 — softened hierarchy. The previous tier1=8 created a systemic bias
    # where any "Insurance/Legal" or "Finance" domain got a guaranteed +8
    # purely from category. The rebalanced engine awards real points based
    # on KPS/CPC evidence, with these tier values acting as a small ceiling
    # lift only. Any industry can score high if the evidence supports it.
    "tier1": 5, "tier2": 4, "tier3": 3,
    "tier4": 2, "tier5": 2, "generic": 1, "none": 0,
}

# ━━━━━━━━━━━━ Niche Profitability (real market data) ━━━━━━━━━━━━
# avg_domain_price: average sale price for domains in this niche
# buyer_density: how many businesses per city actively seek domains (1-10)
# resell_ease: how easy to find a buyer (1-10)
NICHE_PROFITABILITY = {
    "Insurance/Legal":      {"profit_tier": 1, "avg_price": 5000, "buyer_density": 9, "resell_ease": 8},
    "Finance":              {"profit_tier": 1, "avg_price": 4500, "buyer_density": 8, "resell_ease": 7},
    "Health/Medical":       {"profit_tier": 2, "avg_price": 3000, "buyer_density": 9, "resell_ease": 7},
    "Real Estate":          {"profit_tier": 2, "avg_price": 2500, "buyer_density": 8, "resell_ease": 7},
    "AI/Machine Learning":  {"profit_tier": 2, "avg_price": 3500, "buyer_density": 5, "resell_ease": 5},
    "Crypto/Blockchain":    {"profit_tier": 2, "avg_price": 2000, "buyer_density": 4, "resell_ease": 4},
    "Tech/SaaS":            {"profit_tier": 3, "avg_price": 2000, "buyer_density": 7, "resell_ease": 6},
    "E-commerce/Retail":    {"profit_tier": 3, "avg_price": 1500, "buyer_density": 7, "resell_ease": 6},
    "Cloud/Hosting":        {"profit_tier": 3, "avg_price": 1800, "buyer_density": 5, "resell_ease": 5},
    "Business/Marketing":   {"profit_tier": 3, "avg_price": 1200, "buyer_density": 7, "resell_ease": 6},
    "Education":            {"profit_tier": 4, "avg_price": 1000, "buyer_density": 5, "resell_ease": 5},
    "Travel":               {"profit_tier": 4, "avg_price": 1200, "buyer_density": 5, "resell_ease": 5},
    "Security":             {"profit_tier": 4, "avg_price": 1500, "buyer_density": 4, "resell_ease": 4},
    "Fitness/Wellness":     {"profit_tier": 4, "avg_price": 800,  "buyer_density": 6, "resell_ease": 5},
    "Jobs/Career":          {"profit_tier": 4, "avg_price": 1000, "buyer_density": 5, "resell_ease": 5},
    "Entertainment":        {"profit_tier": 5, "avg_price": 600,  "buyer_density": 4, "resell_ease": 3},
    "Gaming":               {"profit_tier": 2, "avg_price": 3500, "buyer_density": 7, "resell_ease": 7},
    "Automotive":           {"profit_tier": 5, "avg_price": 800,  "buyer_density": 5, "resell_ease": 4},
    "Fashion/Beauty":       {"profit_tier": 5, "avg_price": 600,  "buyer_density": 5, "resell_ease": 4},
    "Home/Garden":          {"profit_tier": 5, "avg_price": 500,  "buyer_density": 5, "resell_ease": 4},
    "Sports":               {"profit_tier": 5, "avg_price": 500,  "buyer_density": 3, "resell_ease": 3},
    "Food/Restaurant":      {"profit_tier": 5, "avg_price": 600,  "buyer_density": 7, "resell_ease": 4},
    "Dating/Relationships": {"profit_tier": 5, "avg_price": 500,  "buyer_density": 2, "resell_ease": 2},
    "Pets":                 {"profit_tier": 5, "avg_price": 400,  "buyer_density": 4, "resell_ease": 3},
    "Green/Eco":            {"profit_tier": 5, "avg_price": 500,  "buyer_density": 3, "resell_ease": 3},
    "Music":                {"profit_tier": 5, "avg_price": 500,  "buyer_density": 3, "resell_ease": 3},
    "Photography":          {"profit_tier": 5, "avg_price": 400,  "buyer_density": 4, "resell_ease": 3},
    # ── New Niches (added in V4.1 dynamic expansion) ──
    "Logistics/Supply Chain": {"profit_tier": 3, "avg_price": 2000, "buyer_density": 6, "resell_ease": 5},
    "Cannabis/CBD":           {"profit_tier": 3, "avg_price": 2500, "buyer_density": 5, "resell_ease": 5},
    "Space/Aerospace":        {"profit_tier": 4, "avg_price": 1500, "buyer_density": 3, "resell_ease": 3},
    "HR/Staffing":            {"profit_tier": 4, "avg_price": 1000, "buyer_density": 5, "resell_ease": 5},
    "Manufacturing/Industrial":{"profit_tier": 4, "avg_price": 1200, "buyer_density": 5, "resell_ease": 4},
    "Agriculture/AgTech":     {"profit_tier": 4, "avg_price": 800,  "buyer_density": 4, "resell_ease": 4},
}

# ━━━━━━━━━━━━ SV Tiers ━━━━━━━━━━━━
SV_TIERS = [
    (50000, 20), (10000, 16), (5000, 12),
    (1000, 8), (100, 4),
]

# ━━━━━━━━━━━━ Penalties (V5 — universal, applied across all domain types) ━━━━━━━━━━━━
PENALTIES = {
    "PERSONAL_NAME":         -10,
    "LONG_UNCLEAR":          -8,    # Long + no clarity
    "LONG_UNCLEAR_THRESHOLD": 18,
    "SPAM_HISTORY":          -15,
    # V5 additions — were previously only enforced inside brandable_scorer,
    # which meant SEO/niche/keyword domains got no penalty for hyphens or
    # digits. Now applied universally in market_scorer.calculate_penalties.
    "HYPHEN":                -5,    # one hyphen, non-geo
    "MULTI_HYPHEN":          -10,   # 2+ hyphens
    "DIGITS_IN_LONG":        -5,    # digits inside long names
    "MANY_DIGITS":           -10,   # 3+ digits
}

# ━━━━━━━━━━━━ Domain Type Labels ━━━━━━━━━━━━
DOMAIN_TYPES = {
    "seo_keyword":    "🔍 SEO Keyword",
    "local_service":  "📍 Local Service",
    "global_service": "🌐 Global Service",
    "brandable":      "🏷️ Brandable",
    "content_media":  "📰 Content/Media",
    "low_value":      "⚪ Low Value",
}

DOMAIN_TYPES_AR = {
    "seo_keyword":    "كلمات دلالية (SEO)",
    "local_service":  "خدمة محلية",
    "global_service": "خدمة عالمية",
    "brandable":      "براند قابل للتسويق",
    "content_media":  "محتوى وإعلام",
    "low_value":      "قيمة منخفضة",
}

RESELL_SPEED_AR = {
    "Fast": "سريع",
    "Medium": "متوسط",
    "Slow": "بطيء",
}

# ━━━━━━━━━━━━ Transactional Keywords ━━━━━━━━━━━━
# Words that signal buying intent in the domain itself
TRANSACTIONAL_KEYWORDS = {
    "buy", "shop", "store", "deal", "deals", "cheap", "best", "top",
    "review", "reviews", "compare", "quote", "quotes", "hire", "find",
    "get", "order", "book", "booking", "rent", "rental", "lease",
    "service", "services", "repair", "install", "consulting",
    "lawyer", "attorney", "dentist", "doctor", "plumber", "electrician",
    "agency", "clinic", "firm", "company", "pro", "expert", "premium",
}

# ━━━━━━━━━━━━ Content/Media Keywords ━━━━━━━━━━━━
CONTENT_KEYWORDS = {
    "news", "blog", "magazine", "journal", "daily", "weekly", "monthly",
    "guide", "tips", "how", "learn", "tutorial", "academy", "hub",
    "world", "zone", "central", "insider", "digest", "report",
    "forum", "community", "network", "podcast", "media", "today",
    "watch", "tracker", "monitor", "update", "wire", "post",
}

# ━━━━━━━━━━━━ Processing ━━━━━━━━━━━━
BATCH_SAVE_INTERVAL = 50
LOG_LEVEL = "INFO"

# ━━━━━━━━━━━━ TLD Multipliers ━━━━━━━━━━━━
# Single source of truth — used in BOTH scoring AND price estimation.
# .com = 1.0 (baseline). All others are relative to .com.
# This table replaces the old separate table in enrichments.py.
TLD_MULTIPLIERS = {
    # Generic TLDs
    "com":  1.00,  # Gold standard
    "net":  0.75,
    "org":  0.80,
    "io":   0.85,
    "ai":   0.90,
    "co":   0.65,
    "app":  0.75,
    "dev":  0.65,
    "me":   0.45,
    "tv":   0.55,
    "info": 0.25,
    "biz":  0.20,
    "xyz":  0.25,
    "us":   0.35,
    "online": 0.20,
    "site": 0.20,
    "web":  0.20,
    "shop": 0.45,
    "store": 0.40,
    "tech": 0.50,
    "club": 0.20,
    # Country-code TLDs (ccTLD) — premium markets
    "uk":   0.70,   # Great Britain
    "de":   0.75,   # Germany (large e-commerce market)
    "ca":   0.65,   # Canada
    "au":   0.65,   # Australia
    "fr":   0.65,   # France
    "nl":   0.60,   # Netherlands
    "es":   0.55,   # Spain
    "it":   0.55,   # Italy
    "jp":   0.70,   # Japan (premium tech market)
    "cn":   0.50,   # China
    "in":   0.45,   # India
    "br":   0.45,   # Brazil
    "mx":   0.40,   # Mexico
    "ae":   0.65,   # UAE (Dubai market)
    "sa":   0.55,   # Saudi Arabia
    "eg":   0.35,   # Egypt
    "sg":   0.65,   # Singapore
    "hk":   0.60,   # Hong Kong
    "nz":   0.55,   # New Zealand
    "za":   0.40,   # South Africa
    "se":   0.60,   # Sweden
    "no":   0.60,   # Norway
    "dk":   0.60,   # Denmark
    "fi":   0.55,   # Finland
    "ch":   0.65,   # Switzerland
    "at":   0.55,   # Austria
    "be":   0.55,   # Belgium
    "pl":   0.45,   # Poland
    "ru":   0.35,   # Russia
    "tr":   0.35,   # Turkey
}

# ━━━━━━━━━━━━ ccTLD Collapsing ━━━━━━━━━━━━
# Two-part TLDs that collapse to a single base country for multiplier lookup.
CCTLD_MAP = {
    "co.uk": "uk", "com.au": "au", "co.nz": "nz",
    "com.br": "br", "co.in": "in", "co.za": "za",
    "com.mx": "mx", "co.jp": "jp",  "com.sg": "sg",
    "com.hk": "hk", "com.tr": "tr", "com.eg": "eg",
    "com.sa": "sa", "com.ae": "ae",
}


def tld_for_lookup(domain: str) -> str:
    """
    Return the TLD key for TLD_MULTIPLIERS lookup, honoring two-part ccTLDs
    like example.co.uk → "uk". Falls back to the last label.

    Single source of truth — used by market_scorer, enrichments, etc. so
    `.com.au` doesn't get parsed as `.au` in one place and `.com` in another.
    """
    if not domain or '.' not in domain:
        return "com"
    parts = domain.lower().split('.')
    if len(parts) >= 3:
        combined = f"{parts[-2]}.{parts[-1]}"
        if combined in CCTLD_MAP:
            return CCTLD_MAP[combined]
    return parts[-1]
