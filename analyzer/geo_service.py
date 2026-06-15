"""
Niche & Geo Detection V3 — Improved niche detection with priority + geo awareness.
"""
import re
import logging
from config import NICHE_CATEGORIES, NICHE_TIER_SCORES

logger = logging.getLogger("analyzer.niche")

# ━━━━━━━━━━━━ Niche Keywords (grouped by tier) ━━━━━━━━━━━━
NICHES = [
    {
        "name": "Insurance/Legal",
        "keywords": [
            "insurance", "insure", "insured", "underwrite", "actuary", "indemnity",
            "attorney", "lawyer", "lawfirm", "legal", "litigation", "counsel",
            "advocate", "solicitor", "paralegal", "notary", "barrister",
            "claim", "claims", "lawsuit", "verdict", "settlement", "liability",
            "malpractice", "negligence", "injury", "accident", "compensation",
            "disability", "bail", "defense", "prosecutor", "judge", "court",
        ],
    },
    {
        "name": "Finance",
        "keywords": [
            "finance", "financial", "fintech", "banking", "bank", "credit",
            "loan", "lending", "lender", "mortgage", "refinance", "debt",
            "invest", "investment", "investing", "investor", "capital", "equity",
            "wealth", "asset", "portfolio", "fund", "trading", "forex",
            "payroll", "accounting", "accountant", "tax", "bookkeeping", "audit",
            "revenue", "profit", "dividend", "stock", "bond", "ipo",
        ],
    },
    {
        "name": "Crypto/Blockchain",
        "keywords": [
            "crypto", "bitcoin", "ethereum", "blockchain", "nft", "defi",
            "wallet", "mining", "miner", "token", "ico", "airdrop",
            "swap", "stake", "staking", "yield",
            "web3", "dapp", "ledger", "coin",
        ],
    },
    {
        "name": "Health/Medical",
        "keywords": [
            "health", "healthcare", "medical", "medicine", "clinic", "hospital",
            "doctor", "physician", "surgeon", "surgery", "dental", "dentist",
            "orthodontist", "dermatologist", "pediatric", "psychiatric",
            "therapy", "therapist", "counseling", "rehab", "rehabilitation",
            "pharmacy", "pharma", "wellness", "nutrition",
            "supplement", "vitamin", "mental", "anxiety", "addiction",
            "recovery", "detox", "nursing", "nurse", "hospice",
        ],
    },
    {
        "name": "Real Estate",
        "keywords": [
            "realty", "realtor", "realestate", "property", "properties",
            "homes", "house", "housing", "apartment", "condo", "villa",
            "rent", "rental", "lease", "tenant", "landlord",
            "escrow", "appraisal", "foreclosure",
            "construction", "builder", "contractor", "renovation", "remodel",
            "roofing", "roofer", "plumber", "plumbing", "hvac",
            "electrician", "landscaping", "architect",
        ],
    },
    {
        "name": "AI/Machine Learning",
        "keywords": [
            "artificial", "intelligence", "machine", "learning",
            "neural", "deeplearning", "chatbot",
            "automation", "predict", "prediction",
            "nlp", "vision", "recognition", "speech", "tensor",
            "ai", "ml", "llm", "genai", "aiml",
        ],
    },
    {
        "name": "Tech/SaaS",
        "keywords": [
            "tech", "technology", "software", "saas", "cloud", "hosting",
            "server", "database", "platform", "api", "sdk",
            "cyber", "security", "firewall", "encryption", "backup",
            "data", "analytics", "robot", "drone",
            "digital", "internet", "network", "devops",
            "dashboard", "portal", "crm", "erp", "cms", "ecommerce",
        ],
    },
    {
        "name": "E-commerce/Retail",
        "keywords": [
            "shop", "store", "cart", "checkout",
            "retail", "wholesale", "supplier", "vendor", "merchant",
            "product", "inventory", "warehouse", "shipping", "delivery",
            "marketplace", "dropship",
        ],
    },
    {
        "name": "Cloud/Hosting",
        "keywords": [
            "hosting", "vps", "dedicated", "shared",
            "dns", "ssl", "cdn", "storage",
            "wordpress", "joomla", "drupal",
        ],
    },
    {
        "name": "Business/Marketing",
        "keywords": [
            "business", "marketing", "branding", "brand", "advertising",
            "seo", "sem", "ppc", "content",
            "startup", "entrepreneur", "consulting", "consultant",
            "agency", "sales", "lead", "conversion",
            "email", "funnel", "growth", "affiliate", "partnership",
        ],
    },
    {
        "name": "Education",
        "keywords": [
            "school", "university", "college", "academy", "institute",
            "education", "training", "course", "learn", "learning",
            "tutor", "tutoring", "teacher", "professor", "instructor",
            "degree", "diploma", "certification", "curriculum",
            "scholarship", "student", "campus",
        ],
    },
    {
        "name": "Travel",
        "keywords": [
            "travel", "tour", "tours", "tourism", "hotel", "resort",
            "vacation", "holiday", "cruise", "flight", "airline", "booking",
            "destination", "adventure", "safari", "trip", "journey",
            "backpack", "explore",
        ],
    },
    {
        "name": "Security",
        "keywords": [
            "security", "protect", "protection", "guard", "safe", "safety",
            "alarm", "camera", "surveillance", "monitor", "lock",
            "cybersecurity", "antivirus", "vpn", "password",
            "identity", "authentication", "biometric",
        ],
    },
    {
        "name": "Fitness/Wellness",
        "keywords": [
            "fitness", "gym", "workout", "exercise",
            "yoga", "pilates", "crossfit", "bodybuilding",
            "diet", "weight", "slim", "muscle", "strength",
        ],
    },
    {
        "name": "Jobs/Career",
        "keywords": [
            "job", "jobs", "career", "employment", "hire", "hiring",
            "resume", "recruit", "recruitment", "talent",
            "salary", "work", "remote", "freelance", "gig",
            "internship", "vacancy",
        ],
    },
    {
        "name": "Food/Restaurant",
        "keywords": [
            "food", "restaurant", "cafe", "coffee", "bakery",
            "diner", "pizza", "burger", "sushi", "catering", "chef",
            "recipe", "cooking", "kitchen", "menu",
            "organic", "vegan", "vegetarian", "grill", "bbq",
        ],
    },
    {
        "name": "Entertainment",
        "keywords": [
            "entertainment", "movie", "film", "cinema", "television",
            "concert", "show", "streaming",
            "video", "podcast", "media",
        ],
    },
    {
        "name": "Gaming",
        "keywords": [
            "game", "gaming", "gamer", "play", "player", "esports",
            "mmorpg", "rpg", "fps", "battle", "multiplayer",
            "console", "indie",
            "casino", "poker", "gambling", "gamble", "slots", "betting",
            "roulette", "blackjack", "baccarat", "sportsbook", "bingo",
        ],
    },
    {
        "name": "Automotive",
        "keywords": [
            "auto", "car", "cars", "vehicle", "motor", "motorcycle",
            "truck", "suv", "dealer", "dealership",
            "repair", "parts", "tire", "engine", "mechanic",
            "electric", "hybrid", "charging",
        ],
    },
    {
        "name": "Fashion/Beauty",
        "keywords": [
            "fashion", "style", "clothing", "apparel", "wear", "outfit",
            "beauty", "cosmetic", "makeup", "skincare", "skin", "hair",
            "spa", "salon", "nail", "perfume", "fragrance",
            "jewelry", "accessories", "shoes", "dress",
            "luxury", "designer", "boutique",
        ],
    },
    {
        "name": "Home/Garden",
        "keywords": [
            "home", "garden", "yard", "lawn", "landscape",
            "furniture", "decor", "design", "interior", "exterior",
            "bathroom", "bedroom", "patio",
            "diy", "tools", "hardware", "cleaning",
        ],
    },
    {
        "name": "Sports",
        "keywords": [
            "sport", "sports", "football", "basketball", "soccer", "tennis",
            "golf", "baseball", "hockey", "boxing", "mma", "wrestling",
            "athlete", "coach", "team", "league", "championship",
        ],
    },
    {
        "name": "Dating/Relationships",
        "keywords": [
            "dating", "date", "match", "matchmaking", "love", "romance",
            "relationship", "marriage", "wedding", "bride", "groom",
            "singles", "meet", "flirt", "partner",
        ],
    },
    {
        "name": "Pets",
        "keywords": [
            "pet", "pets", "dog", "cat", "puppy", "kitten", "animal",
            "veterinary", "vet", "petcare", "grooming", "adoption",
            "breed",
        ],
    },
    {
        "name": "Green/Eco",
        "keywords": [
            "green", "eco", "sustainable", "renewable", "solar", "wind",
            "energy", "climate", "carbon", "emission", "recycle",
            "biodegradable", "clean",
            "environment", "conservation",
        ],
    },
    {
        "name": "Music",
        "keywords": [
            "music", "song", "audio", "sound", "beat", "instrument",
            "guitar", "piano", "drum", "band", "artist", "producer",
            "studio", "record", "label",
            "concert", "live", "remix", "track", "album",
        ],
    },
    {
        "name": "Photography",
        "keywords": [
            "photo", "photography", "photographer", "camera", "lens",
            "portrait", "event",
            "edit", "editing", "filter",
            "gallery", "portfolio", "stock", "image", "picture",
        ],
    },
    {
        "name": "Logistics/Supply Chain",
        "keywords": [
            "logistics", "shipping", "freight", "cargo", "supply",
            "warehouse", "fulfillment", "trucking", "courier", "dispatch",
            "fleet", "transport", "transportation", "import", "export",
            "customs", "container", "tracking", "lastmile", "distribution",
        ],
    },
    {
        "name": "Agriculture/AgTech",
        "keywords": [
            "farm", "farming", "agriculture", "agtech", "agri",
            "harvest", "crop", "seed", "soil", "irrigation",
            "livestock", "dairy", "poultry", "organic", "greenhouse",
            "fertilizer", "pesticide", "tractor", "aquaculture",
        ],
    },
    {
        "name": "Space/Aerospace",
        "keywords": [
            "space", "aerospace", "satellite", "rocket", "orbit",
            "astronaut", "launch", "spacecraft", "lunar", "mars",
            "aviation", "aircraft", "airspace", "unmanned",
            "propulsion", "payload", "telemetry",
        ],
    },
    {
        "name": "Cannabis/CBD",
        "keywords": [
            "cannabis", "marijuana", "dispensary", "hemp", "cbd",
            "thc", "edible", "edibles", "indica", "sativa",
            "grower", "cultivate", "extraction", "terpene", "strain",
        ],
    },
    {
        "name": "HR/Staffing",
        "keywords": [
            "staffing", "payroll", "hr", "humanresource", "workforce",
            "onboarding", "benefits", "compensation", "headhunter",
            "outsource", "outsourcing", "contractor", "compliance",
            "retention", "engagement", "screening",
        ],
    },
    {
        "name": "Manufacturing/Industrial",
        "keywords": [
            "manufacturing", "factory", "industrial", "machinery",
            "assembly", "fabrication", "tooling", "cnc", "welding",
            "casting", "molding", "prototype", "production", "lean",
            "automation", "conveyor", "stamping", "forging",
        ],
    },
]


def _get_niche_tier(niche_name: str) -> str:
    """Get the tier for a niche name."""
    for tier, niche_list in NICHE_CATEGORIES.items():
        if niche_name in niche_list:
            return tier
    return "generic"


def _build_keyword_index():
    """Build a keyword-to-niche lookup for fast access."""
    index = {}
    for niche in NICHES:
        for kw in niche["keywords"]:
            if kw not in index:
                index[kw] = niche["name"]
    return index

_KW_INDEX = _build_keyword_index()


def _at_word_boundary(kw: str, name: str) -> bool:
    """
    Return True if `kw` appears at a proper word boundary within `name`.
    Boundary = start-of-name, end-of-name, or adjacent to another word
    from the dictionary (not just any character).
    This prevents 'car' matching 'oscar', 'tax' matching 'syntax',
    'art' matching 'start', 'log' matching 'catalog', etc.
    """
    pos = name.find(kw)
    if pos == -1:
        return False
    end = pos + len(kw)

    # Check all occurrences (kw could appear multiple times)
    while pos != -1:
        start_ok = (pos == 0)                       # at domain start
        end_ok   = (end == len(name))               # at domain end

        # Check that the character before kw (if any) isn't a plain letter
        # that would indicate kw is buried mid-word (e.g. 'car' in 'oscar')
        if not start_ok and name[pos - 1].isalpha():
            pos = name.find(kw, pos + 1)
            end = pos + len(kw) if pos != -1 else -1
            continue

        # Similarly, character after kw (if any) should not be a letter unless
        # it starts a new recognizable segment (we can't detect that cheaply,
        # so we require end_ok for short keywords ≤ 4 chars)
        if not end_ok and len(kw) <= 4 and end < len(name) and name[end].isalpha():
            pos = name.find(kw, pos + 1)
            end = pos + len(kw) if pos != -1 else -1
            continue

        return True  # found a valid boundary occurrence
    return False



# Strong short keywords that are clear niche signals even at 2-3 chars.
# Exempt from the default low-weight treatment for short tokens.
_STRONG_SHORT_KWS = {"ai", "ml"}

# Keywords that are AMBIGUOUS in compound words — they appear naturally in
# non-niche domains ("courtyard", "taxicab", "bankroll") and should not
# automatically trigger a high-value niche without additional evidence.
# These receive a 0.5× weight penalty.
_AMBIGUOUS_KWS = {
    "court",   # courtyard, basketball court, food court, courtship
    "tax",     # taxicab, taxidermy, taxi
    "law",     # lawn, Lawrence — "lawyer" is NOT in this list (unambiguous)
    "bank",    # riverbank, bankroll — "banking" is NOT in this list
    "fund",    # fundamental, fundament
    "bond",    # bonding, bondage (non-financial)
    "stock",   # livestock, overstock, stockade
    "mine",    # mine (possessive), undermine
    "lead",    # leadership, lead (metal/position)
    "note",    # notebook, notepad, notable
    "guard",   # lifeguard, bodyguard, safeguard
}


def _kw_weight(kw: str, is_exact: bool = False) -> float:
    """
    Keyword evidence weight based on specificity (length) + ambiguity.
    Longer keyword = more specific = stronger evidence.
    Ambiguous words (see _AMBIGUOUS_KWS) get a 0.5× penalty so a single
    occurrence is never enough to claim a high-value niche on its own.
    Strong short keywords (see _STRONG_SHORT_KWS) bypass the low-weight
    treatment for 2-char tokens — "ai" at end of a domain is unambiguous.
    """
    if is_exact:
        return 3.0
    # Strong 2-char abbreviations are clear niche signals (e.g. "ai", "ml")
    if kw in _STRONG_SHORT_KWS:
        return 1.0
    n = len(kw)
    if n >= 9:  base = 3.0   # "insurance", "attorney", "healthcare"
    elif n >= 7: base = 2.0  # "fitness", "medical", "banking", "housing"
    elif n >= 5: base = 1.5  # "health", "legal", "store", "hotel"
    elif n >= 4: base = 1.0  # "loan", "fund", "tech", "care", "shop"
    else:        base = 0.7  # "vet", "gym", "spa"
    # Ambiguous words get halved — they need a partner keyword to qualify
    if kw in _AMBIGUOUS_KWS:
        base *= 0.5
    return base


# Minimum score to claim a high-value niche tier.
# One clear keyword (e.g. "lawyer" = 1.5, "health" = 1.5) is enough.
# One ambiguous word alone ("court" = 0.75, "tax" = 0.35) is NOT enough.
_TIER_MIN_SCORE = {
    "tier1": 1.0,   # Insurance/Legal, Finance
    "tier2": 0.8,   # Health/Medical, Real Estate
    # tier3+ — any positive score accepted (no gate needed)
}

_NO_NICHE = {
    "niche": "-", "niche_tier": "none",
    "niche_class": "n-none", "confidence": "none", "matches": 0,
}


def detect_niche(domain: str) -> dict:
    """
    Niche detection — weighted substring matching with tier-bias removal.

    Key improvements over V2:
    - Keywords weighted by length (longer = more specific = higher score)
    - Tiebreaker: score → longest keyword → tier (tier NO LONGER primary)
    - Minimum score gates for tier1/tier2 (single short keyword not enough)
    - Downgrade to best lower-tier alternative when tier1/tier2 gate fails
    """
    name = domain.lower().split('.')[0]

    # 1. Exact match first — highest confidence, no boundary needed
    if name in _KW_INDEX:
        niche_name = _KW_INDEX[name]
        tier = _get_niche_tier(niche_name)
        return {
            "niche": niche_name, "niche_tier": tier,
            "niche_class": "n-found", "confidence": "exact", "matches": 1,
        }

    from analyzer.word_data import ALL_WORDS
    is_known_word = name in ALL_WORDS

    # If the domain name is a common dictionary word (e.g. "start", "oscar",
    # "syntax"), skip all substring matching — false positives like
    # 'art' in 'start' or 'car' in 'scar' are inevitable otherwise.
    if is_known_word:
        return dict(_NO_NICHE)

    # ── 2. Weighted substring matching ──
    niche_scores  = {}  # niche → accumulated weight
    _best_kw_len  = {}  # niche → length of its longest matched keyword

    for kw, niche_name in _KW_INDEX.items():
        if kw not in name:
            continue

        kw_len = len(kw)

        # Very short keywords (< 4 chars) — only at domain start or end
        if kw_len < 4:
            if kw != name and not name.startswith(kw) and not name.endswith(kw):
                continue
            # Strong short abbreviations (ai, ml) only qualify in compound names
            # of sufficient length to avoid false positives on foreign/short words
            # (e.g. "lanai", "banzai" ending with "ai" are not AI domains).
            if kw in _STRONG_SHORT_KWS and len(name) < 7:
                continue

        # Medium keywords (4-5 chars) — must be at a proper word boundary
        elif kw_len <= 5:
            if not _at_word_boundary(kw, name):
                continue

        # Longer keywords (6+ chars) — specific enough; substring is fine

        delta = _kw_weight(kw, is_exact=(name == kw))
        niche_scores[niche_name]  = niche_scores.get(niche_name, 0) + delta
        _best_kw_len[niche_name]  = max(_best_kw_len.get(niche_name, 0), kw_len)

    if not niche_scores:
        return dict(_NO_NICHE)

    # ── 3. Pick best niche ──
    # Order: accumulated score → longest matched keyword → tier (last resort only)
    # Tier is demoted to last resort to remove the "always picks highest-value niche" bias.
    def _rank(n):
        return (
            round(niche_scores[n], 2),
            _best_kw_len.get(n, 0),
            NICHE_TIER_SCORES.get(_get_niche_tier(n), 0),
        )

    best_niche = max(niche_scores, key=_rank)
    tier        = _get_niche_tier(best_niche)
    best_score  = niche_scores[best_niche]

    # ── 4. Minimum score gate for high-value tiers ──
    # Prevent a single weak keyword ("tax", "court", "bank") from classifying
    # a domain as Insurance/Legal or Finance with high confidence.
    min_score = _TIER_MIN_SCORE.get(tier, 0)
    if best_score < min_score:
        # Try the best lower-tier alternative that passes its own threshold
        lower = {
            n: s for n, s in niche_scores.items()
            if _get_niche_tier(n) not in ("tier1", "tier2")
            and s >= _TIER_MIN_SCORE.get(_get_niche_tier(n), 0)
        }
        if lower:
            best_niche  = max(lower, key=lambda n: _rank(n))
            tier        = _get_niche_tier(best_niche)
            best_score  = niche_scores[best_niche]
        else:
            # No sufficient alternative — not enough evidence for any niche
            return dict(_NO_NICHE)

    # ── 5. Confidence ──
    if best_score >= 3.0:    confidence = "high"
    elif best_score >= 2.0:  confidence = "medium"
    else:                    confidence = "low"

    return {
        "niche": best_niche, "niche_tier": tier,
        "niche_class": "n-found", "confidence": confidence,
        "matches": round(best_score, 1),
    }


# ━━━━━━━━━━━━ Personal Name Detection ━━━━━━━━━━━━

COMMON_FIRST_NAMES = {
    # English male
    "aaron","adam","alan","albert","alex","alexander","andrew","anthony","arthur",
    "benjamin","bill","bob","brad","brandon","brian","bruce","carl","charles",
    "chris","christopher","craig","dan","daniel","dave","david","dean","dennis",
    "donald","doug","douglas","dustin","edward","eric","eugene","evan","frank",
    "fred","gary","george","gerald","greg","gregory","harold","harry","henry",
    "howard","jack","jacob","jake","james","jason","jeff","jeffrey","jerry",
    "jesse","jim","jimmy","joe","john","johnny","jonathan","jordan","joseph",
    "josh","joshua","justin","keith","ken","kenneth","kevin","kyle","larry",
    "leon","leonard","lewis","luke","mark","martin","matt","matthew","max",
    "michael","mike","nathan","neil","nick","nicholas","noah","norman","owen",
    "patrick","paul","peter","philip","ralph","randy","ray","raymond","richard",
    "rick","rob","robert","roger","ronald","ross","roy","russell","ryan","sam",
    "samuel","scott","sean","seth","shane","simon","stanley","stephen","steve",
    "steven","stuart","ted","terry","thomas","tim","timothy","todd","tom","tommy",
    "tony","tracy","travis","tyler","victor","vincent","walter","wayne","william",
    "zachary",
    # English female
    "sarah","jessica","jennifer","amanda","ashley","emily","rachel",
    "megan","nicole","michelle","elizabeth","stephanie","rebecca","laura","lisa",
    "karen","nancy","betty","margaret","sandra","donna","carol","ruth","sharon",
    "susan","barbara","dorothy","mary","linda","patricia","christine","maria",
    "anna","diana","emma","olivia","sophia","isabella","charlotte","victoria",
    "hannah","abigail","grace","madison","natalie","samantha","katherine",
    # Arabic male
    "ahmed","mohammed","muhammad","mohammad","omar","ali","hassan","hussein",
    "khaled","khalid","youssef","yousef","ibrahim","ismail","abdallah","abdullah",
    "abdulrahman","abdelrahman","fahad","faisal","sultan","majed","saleh",
    "tariq","walid","wassim","bilal","bassam","amr","ammar","karim","nasser",
    "samer","samir","rami","raed","raid","ziad","ziyad","firas","diaa","diyaa",
    "mostafa","mustafa","hesham","hisham","adel","ashraf","essam","osama",
    "wael","tamer","tarek","ayman","sherif","samy","ehab","emad","wissam",
    # Arabic female
    "fatima","fatimah","maryam","mariam","aisha","khadija","zainab","layla",
    "leila","nour","noura","reem","rima","hana","hanan","dina","nadia","nagwa",
    "samira","sawsan","ghada","rana","rania","yasmin","yasmeen","ruba","huda",
    "manal","maha","sahar","suha","eman","iman","amal","amira","lubna","lina",
    "reham","riham","abeer","abir","afnan","afaf","wafa","widad","maysa",
    # European male
    "luca","marco","matteo","giovanni","antonio","roberto","andrea","davide",
    "pierre","jean","nicolas","sebastien","francois","thomas","lucas","hugo",
    "jakob","hans","stefan","markus","tobias","lars","bjorn","erik","henrik",
    "carlos","miguel","diego","alejandro","javier","pablo","manuel","sergio",
    "joao","pedro","rui","tiago","nuno","filipe",
    # European female
    "sofia","giulia","francesca","valentina","chiara","elena","martina",
    "amelie","chloe","lea","camille","manon","clara","elise",
    "katrin","lena","jana","anna","marie","laura","anna",
    "lucia","carmen","ana","isabel","paula","marta","sara",
    # South/East Asian
    "raj","rahul","arjun","vikram","priya","anita","deepa","neha","pooja",
    "ravi","sanjay","suresh","ramesh","anil","sunil","vijay","ajay","nitin",
    "wei","yang","ming","jing","xiao","jun","ling","fang","hong","yi",
    "sung","jin","kyung","hyun","ji","soo","young","eun","min","jae",
    "kenji","yuki","haruki","takeshi","hiroshi","naoto","akira",
}


def detect_personal_name(domain: str) -> bool:
    """Check if domain looks like a personal name."""
    name = domain.lower().split('.')[0]
    
    from analyzer.word_data import ALL_WORDS, try_split_compound
    if name in ALL_WORDS:
        return False
        
    compound = try_split_compound(name)
    if compound:
        return False

    for first in COMMON_FIRST_NAMES:
        if name.startswith(first) and len(name) > len(first) + 2:
            rest = name[len(first):]
            if rest.isalpha() and len(rest) >= 4:
                if rest in ALL_WORDS:
                    continue
                if any(rest.endswith(suffix) for suffix in ["ing", "tion", "ment", "ness", "able", "ible", "less", "ful", "ology", "ance", "ence", "er", "or", "ist", "ity", "ous", "ive", "al", "ism", "ary", "ate"]):
                    continue
                # If the "first name" prefix is also a dictionary word
                # (mark, frank, jack, grace, ...) AND the rest contains a
                # recognizable word fragment, it's almost certainly a
                # compound, not a personal name.
                if first in ALL_WORDS:
                    if try_split_compound(name):
                        continue
                    # Check if any common word appears inside `rest`
                    if any(w in rest for w in ALL_WORDS if len(w) >= 3):
                        continue
                return True
    return False