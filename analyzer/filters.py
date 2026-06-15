"""
Domain Filters V2 — Expanded trademark/hard lists, improved gibberish detection.
"""
import re
import logging

logger = logging.getLogger("analyzer.filters")

KNOWN_TRADEMARKS = {
    # ── AI & Cloud Platforms ──
    "openai", "anthropic", "chatgpt", "gemini", "midjourney", "perplexity",
    "huggingface", "databricks", "palantir", "snowflake", "confluent",

    # ── Tech Giants ──
    "apple", "google", "facebook", "meta", "amazon", "netflix", "microsoft",
    "airbnb", "uber", "twitter", "instagram", "tiktok", "disney",
    "spotify", "snapchat", "linkedin", "pinterest", "paypal", "stripe",
    "shopify", "walmart", "target", "costco", "starbucks", "mcdonalds", "subway",
    "samsung", "huawei", "xiaomi", "oneplus", "sony", "panasonic", "lenovo",
    "oracle", "cisco", "adobe", "nvidia", "intel", "qualcomm", "amd",
    "youtube", "whatsapp", "telegram", "reddit", "twitch", "github", "gitlab",
    "slack", "zoom", "dropbox", "notion", "figma", "miro", "webflow",
    "salesforce", "hubspot", "canva", "mailchimp", "zendesk", "atlassian",
    "twilio", "square", "venmo", "revolut", "robinhood", "coinbase",
    "roblox", "bytedance", "baidu", "alibaba", "tencent", "jdcom",
    "lyft", "doordash", "instacart", "grubhub",
    "cloudflare", "fastly", "akamai", "datadog", "newrelic",
    "hashicorp", "mongodb", "elastic", "splunk", "okta", "crowdstrike",

    # ── Consumer Hardware ──
    "tesla", "rivian", "lucid", "nio", "byd",
    "dyson", "roomba", "irobot", "nespresso", "keurig",

    # ── Fashion & Luxury ──
    "nike", "adidas", "puma", "reebok", "underarmour", "lululemon",
    "gucci", "prada", "chanel", "louisvuitton", "hermes", "dior", "versace",
    "burberry", "balenciaga", "valentino", "givenchy", "fendi",
    "rolex", "cartier", "omega", "tagheuer", "tiffany", "bvlgari", "swarovski",
    "rayban", "oakley", "vans", "converse", "timberland", "northface",
    "mercedes", "ferrari", "lamborghini", "porsche", "bentley", "maserati",
    "bmw", "audi", "volkswagen", "volvo", "jaguar", "landrover",

    # ── Food & Beverages ──
    "cocacola", "pepsi", "redbull", "monster", "gatorade",
    "dunkin", "timhortons", "caribou", "peets",
    "burgerking", "dominos", "chipotle", "wendys", "tacobell", "kfc",
    "nestle", "unilever", "colgate", "gillette", "procter",

    # ── Entertainment & Gaming ──
    "hulu", "paramount", "warner", "universal", "dreamworks",
    "playstation", "nintendo", "blizzard", "activision", "electronic",
    "riotgames", "epicgames", "ubisoft", "bethesda", "rockstar",
    "applemusic", "soundcloud", "pandora", "deezer", "tidal",
    "disneyplus", "hbomax", "peacock", "crunchyroll",

    # ── Finance & Banking ──
    "mastercard", "americanexpress", "discover", "visa",
    "bankofamerica", "wellsfargo", "capitalone", "citibank", "jpmorgan",
    "goldman", "morganstanley", "berkshire", "vanguard", "fidelity",
    "chime", "sofi", "klarna", "affirm", "afterpay",

    # ── Airlines & Travel ──
    "southwest", "jetblue", "delta", "united", "american",
    "emirates", "etihad", "lufthansa", "britishairways", "qatarairways",
    "saudia", "flyadeal", "flynas",
    "marriott", "hilton", "hyatt", "intercontinental", "fourseasons",
    "airasia", "singapore", "cathay",
    "booking", "expedia", "tripadvisor", "airbnb",

    # ── Retail & E-commerce ──
    "bestbuy", "homedepot", "walgreens", "cvs",
    "etsy", "wayfair", "chewy", "zappos",

    # ── Crypto & Fintech ──
    "binance", "kraken", "gemini", "metamask", "ledger", "trezor",
    "bitpay", "bitfinex", "bitstamp", "ftx",

    # ── Health & Pharma ──
    "pfizer", "moderna", "johnsonandjohnson", "abbvie", "merck",
    "roche", "novartis", "astrazeneca", "bayer", "sanofi",
    "unitedhealth", "cigna", "humana", "anthem",

    # ── Middle East brands ──
    "aramco", "sabic", "alrajhi", "alfaisaliah", "emaar",
    "etisalat", "stc", "mobily", "zain", "ooredoo",
    "talabat", "careem", "jahez", "noon", "namshi",
}

HARD_FILTER_WORDS = {
    # ── Counterfeit pharmaceuticals ONLY (not legal cannabis/medical) ──
    "viagra", "cialis", "xanax", "valium", "oxycontin", "percocet",

    # ── Genuinely illegal substances ──
    "cocaine", "heroin", "ecstasy",

    # ── Weapons / terrorism ──
    "explosive", "terrorism",

    # ── Dark web / hacking ──
    "darkweb", "darknet", "warez", "keygen", "nulled", "phishing",
    "laundering",

    # ── Bulk spam infrastructure ──
    "bulkmail", "massmail", "clickfarm",

    # ── Financial fraud ──
    "ponzi", "forexscam", "cryptoscam",

    # ── Hate speech ──
    "supremacist", "hategroup",

    # ── Dubious supplement spam ──
    "maleenhancement", "weightlosspill",

    # NOTE: Gambling (casino, poker, gambling, slots) and adult content (porn, xxx)
    # are LEGAL industries with proven premium aftermarket sales — avg $55k–$841k
    # per retail transaction data. They are intentionally NOT blocked here.
}


# Regulated-niche keywords: legal but flagged with a note in scoring
REGULATED_NICHE_KEYWORDS = {
    "casino", "poker", "gambling", "gamble", "gambl", "slots",
    "roulette", "blackjack", "baccarat", "sportsbook", "bookmaker",
    "porn", "adult", "xxx", "escort",
}


# Common English words that happen to be trademarks but should NOT block
# compound domains (e.g. "targetfit.com" should not be blocked by "target",
# "geminihealth.com" should not be blocked by "gemini" AI brand, etc.)
_TM_COMMON_WORDS = {
    "target", "square", "uber", "meta", "slack", "bolt",
    "gemini",   # also a zodiac sign / common compound word
    "oracle",   # also a general word
    "elastic",  # also a general word
    "notion",   # also a general word
    "delta",    # also a Greek letter / common word
    "visa",     # also a travel document word
    "byd",      # too short, allow compounds
    "nio",      # too short
    "amd",      # too short
}


def trademark_filter(domain: str) -> bool:
    name = domain.lower().split('.')[0]
    for tm in KNOWN_TRADEMARKS:
        if len(tm) < 3:
            continue
        # Exact match — always block
        if tm == name:
            return True
        # Trademark as prefix or suffix (e.g. "googlepay", "paygoogle")
        # But skip common words when used as part of a compound
        if tm in _TM_COMMON_WORDS:
            continue
        if name.startswith(tm) or name.endswith(tm):
            return True
    return False


def hard_filter(domain: str) -> bool:
    name = domain.lower().split('.')[0]
    for word in HARD_FILTER_WORDS:
        # Skip very short words
        if len(word) < 3:
            continue
        if word in name:
            logger.debug(f"Hard filter: {domain} contains '{word}'")
            return True
    return False


def _count_vowels(s):
    return sum(1 for c in s if c in "aeiouy")


def _has_repeating_chars(s):
    return bool(re.search(r'(.)\1{2,}', s))


def _longest_consonant_run(s):
    runs = re.findall(r'[^aeiouy]+', s)
    return max((len(r) for r in runs), default=0)


def _has_valid_bigrams(s):
    impossible = {"qx","qz","zx","xz","jq","qj","vx","xv","zj","jz","qk","kq","vq","qv","wx","xw"}
    bad = sum(1 for i in range(len(s)-1) if s[i:i+2] in impossible)
    return bad < 2


def smart_readability_filter(domain_name: str) -> dict:
    sld = domain_name.split('.')[0].lower()
    # Short check on the *original* SLD — otherwise a name like "1a2b3"
    # collapses to "ab" after digit/hyphen stripping and bypasses gibberish
    # checks despite being clearly junk.
    if len(sld) <= 4:
        return {"is_gibberish": False, "reason": "Short domain"}

    name = re.sub(r'[0-9\-]', '', sld)
    if len(name) <= 4:
        # After stripping, too little signal remains to evaluate readability.
        # Treat heavily numeric/hyphenated names as gibberish.
        return {"is_gibberish": True, "reason": "Mostly digits/hyphens"}

    vowel_count = _count_vowels(name)
    vowel_ratio = vowel_count / len(name) if len(name) > 0 else 0
    longest_cons = _longest_consonant_run(name)

    if _has_repeating_chars(name) and vowel_ratio < 0.20:
        return {"is_gibberish": True, "reason": f"Repeating chars + low vowels ({vowel_ratio:.2f})"}

    if longest_cons >= 5 and vowel_ratio < 0.25:
        return {"is_gibberish": True, "reason": f"Consonant cluster ({longest_cons}) + low vowels"}

    if not _has_valid_bigrams(name) and vowel_ratio < 0.25:
        return {"is_gibberish": True, "reason": "Impossible letter combinations"}

    if len(name) > 6 and vowel_count == 0:
        return {"is_gibberish": True, "reason": "No vowels in long name"}

    return {"is_gibberish": False, "reason": "Passes readability"}
