"""
Word Frequency Data + Geo Data — Embedded lists for domain scoring.
No external downloads needed. Optimized for batch processing.
"""
import re
import logging

logger = logging.getLogger("analyzer.word_data")

# ━━━━━━━━━━━━ Tier 1: Top Common English Words (~2000 high-value words) ━━━━━━━━━━━━
TIER1_WORDS = {
    "access", "account", "active", "advance", "agent", "alert", "align", "alpha",
    "anchor", "apex", "apply", "arena", "asset", "atlas", "audit", "auto",
    "badge", "balance", "bank", "base", "beam", "bench", "beta", "blade",
    "blast", "blaze", "blend", "block", "bloom", "blue", "board", "bold",
    "bolt", "bond", "bonus", "boost", "border", "boss", "bound", "box",
    "brain", "branch", "brand", "brave", "break", "breed", "bridge", "brief",
    "bright", "broad", "bronze", "brush", "build", "bulk", "burn", "burst",
    "cabin", "cable", "cache", "call", "calm", "camp", "canvas", "cape",
    "capital", "capture", "carbon", "card", "care", "cargo", "case", "cash",
    "cast", "castle", "catch", "cedar", "center", "chain", "chamber", "chance",
    "change", "channel", "charge", "charm", "chart", "chase", "check", "chief",
    "choice", "circle", "civic", "claim", "clan", "clash", "class", "clean",
    "clear", "click", "cliff", "climb", "clip", "clock", "clone", "close",
    "cloud", "club", "clue", "coach", "coast", "code", "coin", "cold",
    "color", "column", "combine", "comfort", "command", "common", "compass",
    "complete", "concept", "connect", "consul", "content", "control",
    "convert", "cool", "copper", "copy", "coral", "core", "corner", "cosmic",
    "count", "couple", "courage", "court", "cover", "craft", "crash", "create",
    "credit", "crew", "crisp", "cross", "crown", "crush", "crystal", "cube",
    "cure", "current", "curve", "custom", "cycle",
    "daily", "dash", "data", "dawn", "deal", "deck", "deep", "delta",
    "dense", "depot", "design", "desk", "detect", "device", "dial",
    "diamond", "direct", "disc", "dock", "domain", "door", "dose", "dot",
    "double", "draft", "dragon", "drain", "draw", "dream", "dress", "drift",
    "drill", "drink", "drive", "drop", "drum", "dual", "duke", "dune",
    "eagle", "earn", "earth", "east", "echo", "edge", "edit", "effect",
    "eight", "elite", "ember", "emerge", "emit", "empire", "enable",
    "energy", "engine", "enjoy", "enter", "epic", "equal", "equip", "era",
    "escape", "estate", "ethic", "event", "ever", "exact", "exam", "excel",
    "exchange", "excite", "expand", "expert", "explore", "export", "express",
    "extra", "eye",
    "face", "fact", "fair", "falcon", "fame", "family", "fan", "farm",
    "fast", "fate", "favor", "feast", "feed", "field", "fight", "file",
    "fill", "film", "filter", "final", "find", "fine", "fire", "firm",
    "first", "fish", "fit", "five", "fix", "flag", "flame", "flash",
    "flat", "fleet", "flex", "flight", "flip", "float", "flock", "floor",
    "flow", "fluid", "flux", "fly", "foam", "focus", "fold", "font",
    "food", "foot", "force", "forge", "fork", "form", "fort", "forum",
    "found", "four", "fox", "frame", "free", "fresh", "front", "frost",
    "fruit", "fuel", "full", "fund", "fusion", "future",
    "gain", "galaxy", "game", "garden", "gate", "gauge", "gear", "gem",
    "gene", "genius", "gift", "giga", "gist", "give", "glad", "glass",
    "gleam", "glide", "globe", "glow", "goal", "gold", "good", "govern",
    "grace", "grade", "grain", "grand", "grant", "graph", "grasp", "grass",
    "grave", "great", "green", "grey", "grid", "grip", "group", "grove",
    "grow", "growth", "guard", "guide", "guild", "gulf",
    "hack", "halo", "hand", "handle", "harbor", "hard", "harm", "harvest",
    "hash", "haste", "haven", "hawk", "head", "health", "heart", "heat",
    "hedge", "height", "helm", "help", "hero", "hide", "high", "hill",
    "hinge", "hire", "hold", "hollow", "home", "honest", "honor", "hook",
    "hope", "horizon", "horn", "horse", "host", "hot", "hour", "house",
    "hub", "human", "humble", "hunt", "hustle",
    "icon", "idea", "ideal", "ignite", "image", "impact", "import", "impress",
    "inch", "index", "inform", "inject", "inner", "input", "insight",
    "inspire", "install", "instant", "intel", "intent", "inter",
    "invest", "invite", "ion", "iron", "island", "issue", "item", "ivory",
    "jack", "jade", "jam", "jar", "jazz", "jet", "jewel", "job", "join",
    "joint", "journal", "journey", "joy", "judge", "juice", "jump",
    "jungle", "just", "justice",
    "keen", "keep", "kernel", "key", "kick", "kind", "king", "kite",
    "knight", "knit", "knot", "know",
    "lab", "label", "lake", "lamp", "land", "lane", "lap", "large",
    "laser", "last", "late", "launch", "lava", "law", "layer", "lead",
    "leaf", "lean", "leap", "learn", "ledge", "left", "legal", "lemon",
    "lens", "level", "lever", "liberty", "life", "lift", "light", "lime",
    "limit", "line", "link", "lion", "list", "lite", "live", "load",
    "loan", "local", "lock", "lodge", "logic", "lone", "long", "look",
    "loop", "lord", "loud", "love", "loyal", "luck", "lunar", "lure",
    "lush", "luxury",
    "macro", "magic", "magnet", "mail", "main", "major", "make", "malt",
    "manage", "manor", "map", "maple", "marble", "march", "margin", "mark",
    "market", "marsh", "mart", "marvel", "mask", "mason", "mass", "master",
    "match", "mate", "matter", "max", "maze", "meadow", "mean", "measure",
    "media", "medic", "meet", "melt", "member", "memo", "mental", "mentor",
    "merge", "merit", "mesh", "metal", "meter", "method", "metro", "micro",
    "might", "mile", "mill", "mind", "mine", "mini", "mint", "mirror",
    "mission", "mix", "mobile", "mode", "model", "modern", "mold", "moment",
    "money", "monk", "moon", "moral", "motion", "motor", "mount", "mouse",
    "move", "much", "multi", "muscle", "music", "myth",
    "nail", "name", "narrow", "natural", "nature", "navy", "near", "neat",
    "neck", "need", "nerve", "nest", "net", "neutral", "never", "next",
    "nice", "night", "nimble", "nine", "noble", "node", "noise", "noon",
    "norm", "north", "nose", "note", "notion", "nova", "novel", "now",
    "nucleus", "number", "nurse", "nut",
    "oak", "oasis", "object", "ocean", "offer", "office", "olive", "omega",
    "once", "onyx", "open", "opera", "option", "orbit", "order", "origin",
    "outer", "output", "oval", "over", "owl", "own", "oxide",
    "pace", "pack", "pad", "page", "paid", "paint", "pair", "palace",
    "palm", "pan", "panel", "paper", "park", "part", "pass", "past",
    "paste", "patch", "path", "pattern", "pause", "pave", "pay", "peace",
    "peak", "pearl", "pen", "penny", "people", "permit", "person", "phase",
    "phone", "photo", "phrase", "pick", "piece", "pilot", "pin", "pine",
    "pink", "pioneer", "pipe", "pitch", "pixel", "place", "plain", "plan",
    "plane", "plant", "plate", "play", "plaza", "pledge", "plot", "plug",
    "plum", "plus", "pocket", "pod", "point", "polar", "pole", "polish",
    "pond", "pool", "pop", "port", "pose", "post", "pot", "pound",
    "pour", "power", "press", "price", "pride", "prime", "prince", "print",
    "prior", "prism", "prize", "probe", "produce", "profit", "program",
    "project", "promise", "proof", "proper", "prose", "protect", "proud",
    "prove", "proxy", "public", "pull", "pulse", "pump", "punch", "pure",
    "purple", "push", "puzzle",
    "quad", "quality", "quantum", "quarter", "queen", "quest", "queue",
    "quick", "quiet", "quiz", "quota", "quote",
    "race", "rack", "radar", "radio", "rail", "rain", "raise", "rally",
    "ramp", "ranch", "range", "rank", "rapid", "rare", "rate", "ratio",
    "raw", "ray", "reach", "react", "read", "ready", "real", "realm",
    "reason", "rebel", "recall", "record", "red", "reef", "reel", "reform",
    "region", "reign", "relay", "relief", "remote", "render", "renew",
    "rent", "repair", "report", "rescue", "reserve", "reset", "resolve",
    "resort", "result", "retain", "reveal", "review", "revolt", "rhythm",
    "rich", "ride", "ridge", "rifle", "right", "rigid", "rim", "ring",
    "rise", "risk", "rival", "river", "road", "roam", "robin", "robust",
    "rock", "rod", "role", "roll", "roof", "room", "root", "rope",
    "rose", "roster", "round", "route", "rover", "royal", "ruby", "rule",
    "run", "rush", "rust",
    "sacred", "safe", "sage", "sail", "saint", "sake", "sale", "salt",
    "sample", "sand", "satin", "save", "scale", "scan", "scene", "school",
    "scope", "score", "scout", "seal", "search", "season", "seat", "second",
    "secret", "sector", "secure", "seed", "select", "self", "sell", "sense",
    "series", "serve", "set", "settle", "seven", "shade", "shadow", "shape",
    "share", "sharp", "shed", "shelf", "shell", "shield", "shift", "shine",
    "ship", "shock", "shoot", "shop", "shore", "short", "show", "side",
    "sight", "sigma", "sign", "signal", "silk", "silver", "simple", "since",
    "single", "site", "six", "size", "skill", "skin", "skull", "sky",
    "slate", "sleep", "slice", "slide", "slim", "slot", "slow", "small",
    "smart", "smile", "smoke", "smooth", "snap", "snow", "social", "socket",
    "soft", "soil", "solar", "sole", "solid", "solve", "sonic", "soul",
    "sound", "source", "south", "space", "span", "spark", "speak", "spear",
    "special", "speed", "sphere", "spice", "spin", "spirit", "splash",
    "split", "spoke", "sport", "spot", "spread", "spring", "sprint", "square",
    "stable", "stack", "staff", "stage", "stake", "stamp", "stand", "star",
    "start", "state", "status", "stay", "steady", "steam", "steel", "steep",
    "stem", "step", "stick", "still", "stock", "stone", "stop", "store",
    "storm", "story", "straight", "strand", "stream", "street", "stress",
    "stretch", "strict", "stride", "strike", "string", "strip", "stroke",
    "strong", "studio", "study", "style", "submit", "sugar", "suit", "summit",
    "sun", "super", "supply", "support", "sure", "surge", "survey", "sustain",
    "swap", "sweep", "sweet", "swift", "swim", "swing", "switch", "symbol",
    "sync", "system",
    "table", "tackle", "tail", "talent", "talk", "tank", "tap", "tape",
    "target", "task", "taste", "tax", "teach", "team", "tech", "temple",
    "tempo", "ten", "tend", "term", "test", "text", "theme", "theory",
    "thick", "think", "third", "thought", "thread", "three", "throne",
    "tide", "tiger", "tight", "tile", "timber", "time", "tiny", "tip",
    "titan", "title", "toast", "token", "tone", "tool", "top", "torch",
    "total", "touch", "tough", "tour", "tower", "town", "trace", "track",
    "trade", "trail", "train", "trait", "transfer", "trap", "travel",
    "treat", "tree", "trend", "trial", "tribe", "trick", "trim", "triple",
    "triumph", "trojan", "trophy", "true", "trump", "trust", "truth", "tube",
    "tune", "tunnel", "turn", "tutor", "twin", "twist", "type",
    "ultra", "umbrella", "under", "union", "unique", "unit", "unite",
    "unity", "universe", "upper", "urban", "usage", "use", "user", "usual",
    "utility",
    "valid", "valley", "value", "valve", "vapor", "vault", "vector",
    "vendor", "venture", "venue", "verse", "vessel", "vest", "vibe", "vice",
    "video", "view", "vigor", "vine", "vintage", "violet", "virtue",
    "vision", "visit", "vista", "vital", "vivid", "vocal", "voice", "void",
    "volt", "volume", "vote", "voyage",
    "wage", "wagon", "wake", "walk", "wall", "wander", "ward", "warm",
    "warn", "warrior", "wash", "watch", "water", "wave", "way", "wealth",
    "weapon", "web", "wedge", "week", "weight", "welcome", "well", "west",
    "wheel", "white", "whole", "wide", "wild", "will", "win", "wind",
    "window", "wine", "wing", "winter", "wire", "wise", "wish", "witch",
    "wolf", "wonder", "wood", "word", "work", "world", "worth", "wrap",
    "yard", "year", "yield", "young",
    "zeal", "zen", "zero", "zinc", "zone", "zoom",
}

# ━━━━━━━━━━━━ Tier 2: Known English Words (broader set) ━━━━━━━━━━━━
TIER2_WORDS = {
    "abbey", "abode", "absorb", "abstract", "academy", "accent", "acclaim",
    "acorn", "adept", "admiral", "advent", "aerial", "affinity", "agenda",
    "agile", "alchemy", "alcove", "alloy", "almanac", "alpine", "amber",
    "amble", "amulet", "anthem", "antler", "anvil", "aperture", "aqua",
    "arbor", "arcade", "archer", "archive", "arctic", "armada", "armor",
    "arrow", "artisan", "aspen", "astral", "atrium", "aurora", "autumn",
    "avalanche", "avenue", "avid", "axiom", "azure",
    "bamboo", "banner", "baron", "barrel", "basalt", "basin", "basket",
    "bastion", "beacon", "belfry", "birch", "bishop", "bison", "bliss",
    "blossom", "boulder", "bounty", "bower", "bramble", "brass", "breeze",
    "bristle", "bronze", "brook", "buckle", "buffer", "bugle", "bunker",
    "burrow", "button",
    "cadet", "cairn", "calico", "candle", "cannon", "canopy", "canyon",
    "cascade", "catalyst", "cavern", "cedar", "cellar", "chalice", "chapel",
    "chariot", "cherry", "chimney", "chisel", "cipher", "citadel", "cloak",
    "cobalt", "cocoa", "comet", "condor", "consul", "coral", "cottage",
    "cougar", "cradle", "crane", "crater", "crescent", "crest", "crimson",
    "cruiser", "crystal", "current", "cypress",
    "dagger", "dahlia", "daisy", "damask", "dapple", "darling", "dazzle",
    "decoy", "deer", "den", "desert", "dewdrop", "diode", "dolphin",
    "donkey", "dove", "dragonfly", "driftwood", "dusk", "dynamo",
    "element", "elk", "ellipse", "emblem", "emerald", "ember", "emporium",
    "enamel", "enigma", "epoch", "equinox", "everest", "evolve",
    "fabric", "fable", "falcon", "fallow", "fathom", "feather", "feline",
    "fern", "ferret", "fiddle", "finch", "fir", "fjord", "flare",
    "flint", "flora", "flutter", "foliage", "foothill", "fossil",
    "fountain", "fractal", "fridge", "fringe", "frontier", "furnace",
    "gadget", "gallop", "garnet", "garrison", "gazelle", "geyser",
    "glacier", "glimmer", "gnome", "gondola", "gorge", "gossamer",
    "granite", "grapevine", "grassland", "gravel", "grotto", "grove",
    "gust", "gypsum",
    "halcyon", "hamlet", "hammock", "hangar", "harbor", "hare", "harpoon",
    "harrier", "hazel", "hearth", "heather", "hedgehog", "hemisphere",
    "herald", "hermit", "heron", "hickory", "highland", "hilltop",
    "hollow", "honeycomb", "hound", "hurricane",
    "iceberg", "igloo", "impala", "indica", "indigo", "inlet",
    "ivory",
    "jagged", "jasmine", "jasper", "javelin", "juniper",
    "kayak", "kelpie", "kennel", "kettle", "keystone", "kindle",
    "kingfisher", "kiosk",
    "labyrinth", "lagoon", "lantern", "lapis", "larch", "lark",
    "lattice", "laurel", "lavender", "leopard", "linden", "locket",
    "locust", "loft", "lotus", "lynx",
    "magpie", "mahogany", "mammoth", "mandala", "mango", "mantle",
    "mare", "marigold", "marlin", "marmot", "marquee", "marsh",
    "mast", "meadow", "mesa", "meteor", "mirage", "mistral",
    "mockingbird", "monarch", "monsoon", "moose", "mortar", "mosaic",
    "moss", "moth", "mulberry", "mustang",
    "narwhal", "nautical", "nebula", "nectar", "nettle", "nimbus",
    "nomad", "nook", "nymph",
    "obsidian", "octet", "onyx", "opal", "orchid", "oriole",
    "osprey", "otter", "outpost", "oyster",
    "paddle", "pagoda", "palette", "panther", "parable", "paragon",
    "parchment", "parrot", "pasture", "patrol", "pavilion", "pebble",
    "pelican", "pendant", "penguin", "pepper", "peridot", "petal",
    "pewter", "phoenix", "pier", "pigeon", "pillar", "pinnacle",
    "plaid", "plateau", "plover", "plume", "poplar",
    "porcupine", "portico", "prairie", "presto", "proton", "pueblo",
    "puffin", "pygmy", "pyramid",
    "quarry", "quartz", "quasar", "quill",
    "rabbit", "rampart", "raven", "ravine", "redwood", "regent",
    "relic", "remnant", "rhino", "ripple", "robin", "rosewood",
    "sable", "saffron", "sandstone", "sapphire", "savanna",
    "scarlet", "sequoia", "serpent", "shuttle", "sierra",
    "silhouette", "silo", "simmer", "skylark", "sloop", "snapper",
    "solstice", "sparrow", "specter", "sphinx", "spindle", "sprout",
    "stallion", "starling", "steeple", "steppe", "stirrup", "stork",
    "stratus", "summit", "sundial", "sunflower", "swallow",
    "talon", "tamarack", "tango", "tapestry", "tarmac", "teal",
    "tempest", "terrace", "thistle", "thorn", "thrush", "thunder",
    "topaz", "torrent", "toucan", "trellis", "trident", "tropic",
    "tulip", "tundra", "turquoise", "turtle", "tusk",
    "umbrella", "urchin",
    "vanguard", "velvet", "veranda", "vermilion", "vertex", "viaduct",
    "viper", "volcano", "vortex", "vulture",
    "walnut", "warden", "warbler", "waterfall", "weasel", "whippet",
    "whisper", "willow", "wolverine", "woodpecker", "wren",
    "yarrow", "yew",
    "zephyr", "zodiac",
    # Common short commercial/tech words needed for compound splitting
    "app", "pro", "dev", "biz", "best", "one", "get", "go",
    "air", "ant", "ape", "art", "ash", "bad", "bag", "bar", "bat", "bed", "bee", "bid", "big", "box", "boy", "bug", "bus", "buy", "cap", "car", "cat", "cow", "cup", "dad", "day", "die", "dog", "dry", "ear", "eat", "egg", "elk", "eye", "fan", "far", "fat", "fee", "fly", "fog", "fox", "fun", "gas", "god", "hat", "hit", "hot", "hut", "ice", "jar", "job", "joy", "key", "kid", "law", "leg", "lip", "log", "mad", "man", "map", "mat", "mom", "mud", "new", "now", "nut", "oil", "old", "pan", "pat", "pay", "pen", "pet", "pie", "pig", "pin", "pot", "rat", "red", "run", "sad", "sat", "sea", "sky", "son", "sun", "tag", "tap", "tar", "tax", "tea", "toe", "toy", "vat", "vet", "war", "wet", "zoo",
}

# ━━━━━━━━━━━━ Geo Data ━━━━━━━━━━━━
GEO_TIER1 = {
    # USA — major metros
    "miami", "newyork", "losangeles", "chicago", "houston", "dallas",
    "sanfrancisco", "seattle", "boston", "denver", "austin", "phoenix",
    "lasvegas", "sandiego", "portland", "nashville", "atlanta",
    "charlotte", "orlando", "tampa", "detroit", "minneapolis",
    "philadelphia", "manhattan", "brooklyn", "hollywood",
    # Europe tier-1
    "london", "paris", "berlin", "amsterdam", "madrid", "barcelona",
    "rome", "milan", "munich", "zurich", "geneva", "vienna",
    "stockholm", "oslo", "copenhagen", "dublin", "lisbon", "prague",
    # Asia Pacific tier-1
    "tokyo", "shanghai", "beijing", "hongkong", "singapore", "seoul",
    "mumbai", "delhi", "bangalore", "bangkok", "taipei", "jakarta",
    "sydney", "melbourne", "toronto", "vancouver",
    # Middle East tier-1
    "dubai", "abudhabi", "riyadh", "doha", "cairo", "istanbul",
    # Latin America & other
    "montreal", "calgary", "ottawa", "brisbane", "perth", "auckland",
    "wellington", "buenosaires", "santiago", "bogota", "lima",
    "mexicocity", "capetown", "lagos", "nairobi", "moscow",
}

GEO_TIER2 = {
    # USA states & secondary cities
    "texas", "california", "florida", "illinois", "ohio",
    "georgia", "michigan", "arizona", "colorado", "virginia", "carolina",
    "indiana", "tennessee", "maryland", "missouri", "wisconsin",
    "minnesota", "alabama", "louisiana", "kentucky", "oregon",
    "oklahoma", "connecticut", "iowa", "mississippi", "arkansas",
    "nevada", "kansas", "utah", "nebraska", "maine", "idaho",
    "hawaii", "montana", "delaware", "alaska", "vermont", "wyoming",
    "jersey", "hampshire", "dakota", "penn", "mass",
    "sacramento", "memphis", "louisville", "richmond", "pittsburgh",
    "cincinnati", "milwaukee", "raleigh", "jacksonville", "tucson",
    "albuquerque", "tulsa", "cleveland", "omaha", "honolulu",
    "sarasota", "scottsdale", "savannah", "charleston", "boise",
    "bethesda", "pasadena", "irvine", "naperville", "mesa",
    "fresno", "bakersfield", "aurora", "annapolis", "plano",
    # Canada secondary
    "winnipeg", "edmonton", "halifax", "victoria", "quebec",
    # UK secondary
    "manchester", "birmingham", "liverpool", "edinburgh", "glasgow",
    "bristol", "leeds", "sheffield", "oxford", "cambridge",
    # Europe secondary
    "hamburg", "frankfurt", "cologne", "dusseldorf", "stuttgart",
    "lyon", "marseille", "toulouse", "naples", "florence", "venice",
    "seville", "valencia", "bilbao", "brussels", "antwerp", "rotterdam",
    "gothenburg", "malmo", "warsaw", "krakow", "budapest", "athens",
    "bucharest", "belgrade", "zagreb", "sofia",
    # Middle East — extended Arab coverage
    "jeddah", "mecca", "medina", "dammam", "khobar", "tabuk", "abha",  # Saudi
    "sharjah", "ajman", "fujairah", "rasalkhaimah",                     # UAE
    "muscat", "salalah",                                                  # Oman
    "manama", "bahrain",                                                  # Bahrain
    "kuwait",                                                             # Kuwait
    "amman", "aqaba", "zarqa",                                           # Jordan
    "beirut", "tripoli",                                                  # Lebanon
    "alexandria", "giza", "luxor", "aswan",                              # Egypt
    "casablanca", "rabat", "marrakech", "fez",                           # Morocco
    "tunis", "sfax",                                                      # Tunisia
    "algiers", "oran",                                                    # Algeria
    "baghdad", "basra", "erbil",                                          # Iraq
    "damascus", "aleppo",                                                 # Syria
    "khartoum", "omdurman",                                               # Sudan
    # Asia secondary
    "osaka", "kyoto", "nagoya", "sapporo",
    "busan", "incheon", "daegu",
    "shenzhen", "guangzhou", "chengdu", "hangzhou", "nanjing", "wuhan",
    "hanoi", "hochiminh", "manila", "cebu", "kualalumpur", "penang",
    "karachi", "lahore", "islamabad", "peshawar",
    "kolkata", "chennai", "hyderabad", "pune", "ahmedabad", "surat",
    "colombo", "dhaka", "kathmandu",
    # Oceania secondary
    "adelaide", "darwin", "hobart", "canberra", "christchurch",
    # Africa secondary
    "johannesburg", "durban", "pretoria", "accra", "abuja",
    "addisababa", "dakar", "tananarive",
    # Latin America secondary
    "saopaulo", "rio", "brasilia", "medellin", "cali", "barranquilla",
    "guadalajara", "monterrey", "puebla",
    "lima", "arequipa", "montevideo", "asuncion", "quito", "lapaz",
    # Cities/regions in GEO_MARKET_QUALITY that were missing from tier sets
    "helsinki", "porto", "ankara",
}

GEO_TIER3 = {
    "usa", "america", "canada", "mexico", "brazil", "argentina", "chile",
    "colombia", "peru", "uk", "britain", "england", "scotland", "ireland",
    "france", "germany", "spain", "italy", "portugal", "netherlands",
    "belgium", "switzerland", "austria", "sweden", "norway", "denmark",
    "finland", "poland", "czech", "hungary", "romania", "greece", "turkey",
    "russia", "ukraine", "japan", "china", "korea", "india", "pakistan",
    "indonesia", "thailand", "vietnam", "malaysia", "philippines",
    "australia", "zealand", "singapore", "taiwan",
    "egypt", "morocco", "nigeria", "kenya", "ethiopia", "ghana",
    "southafrica", "tanzania",
    "saudi", "emirates", "qatar", "oman", "bahrain", "jordan", "iraq",
    "iran", "israel", "lebanon", "kuwait",
    "europe", "asia", "africa", "pacific", "atlantic", "caribbean",
    "mediterranean", "arctic", "nordic", "baltic", "alpine", "midwest",
    "southeast", "southwest", "northeast", "northwest", "central",
    "latin", "arabian", "oceania", "sahara", "siberia",
    # Countries/regions in GEO_MARKET_QUALITY that were missing from tier sets
    "bangladesh", "tunisia", "algeria", "arabia", "gulf",
    "sudan", "syria",
    "bayarea", "tristate", "sunbelt", "newengland", "appalachian",
    "rockies", "greatplains", "gulfcoast",
}

ALL_GEO = GEO_TIER1 | GEO_TIER2 | GEO_TIER3

# ━━━━━━━━━━━━ Pre-sorted geo list (ONCE at import, not per call) ━━━━━━━━━━━━
_GEO_SORTED = []
for _gset, _tier in [(GEO_TIER1, 1), (GEO_TIER2, 2), (GEO_TIER3, 3)]:
    for _g in sorted(_gset, key=len, reverse=True):
        if len(_g) >= 3:
            _GEO_SORTED.append((_g, _tier))

try:
    from config import TRANSACTIONAL_KEYWORDS, CONTENT_KEYWORDS
    ALL_WORDS = TIER1_WORDS | TIER2_WORDS | TRANSACTIONAL_KEYWORDS | CONTENT_KEYWORDS
except ImportError:
    ALL_WORDS = TIER1_WORDS | TIER2_WORDS

# Pre-computed lookup for compound splitting — built ONCE at import, not per call
_COMPOUND_LOOKUP = ALL_WORDS | ALL_GEO


def detect_geo(name: str) -> dict:
    """Detect geographic terms in a domain name — OPTIMIZED."""
    name = name.lower().split('.')[0]

    # 1. Exact match
    if name in GEO_TIER1:
        return {"geo_found": True, "geo_name": name, "geo_tier": 1, "geo_type": "pure", "geo_remaining": ""}
    if name in GEO_TIER2:
        return {"geo_found": True, "geo_name": name, "geo_tier": 2, "geo_type": "pure", "geo_remaining": ""}
    if name in GEO_TIER3:
        return {"geo_found": True, "geo_name": name, "geo_tier": 3, "geo_type": "pure", "geo_remaining": ""}

    # 2. Prefix/suffix match using pre-sorted list.
    # Short geos (3 chars like "usa", "uae") are extremely prone to false
    # positives ("usable" → usa+ble, "uaeful" → uae+ful), so we require the
    # remainder to be a known dictionary word/geo. Longer geos (4+) are
    # specific enough to accept any 2+ char remainder.
    for geo, tier in _GEO_SORTED:
        glen = len(geo)
        if name.startswith(geo) and len(name) > glen + 1:
            remainder = name[glen:]
            if glen >= 4 or remainder in _COMPOUND_LOOKUP:
                return {"geo_found": True, "geo_name": geo, "geo_tier": tier,
                        "geo_type": "prefix", "geo_remaining": remainder}
        if name.endswith(geo) and len(name) > glen + 1:
            remainder = name[:-glen]
            if glen >= 4 or remainder in _COMPOUND_LOOKUP:
                return {"geo_found": True, "geo_name": geo, "geo_tier": tier,
                        "geo_type": "suffix", "geo_remaining": remainder}

    return {"geo_found": False, "geo_name": "", "geo_tier": 0, "geo_type": "none", "geo_remaining": ""}


def try_split_compound(name: str) -> tuple:
    """Split domain into two known words — OPTIMIZED with early exit."""
    if len(name) < 5 or len(name) > 25:
        return None

    best = None
    best_score = 0

    for i in range(2, len(name) - 1):
        left = name[:i]
        if left not in _COMPOUND_LOOKUP:
            continue
        right = name[i:]
        if right not in _COMPOUND_LOOKUP:
            continue
        # Both parts are words — score by quality
        score = len(left) + len(right)
        if left in TIER1_WORDS: score += 2
        if right in TIER1_WORDS: score += 2
        if score > best_score:
            best = (left, right)
            best_score = score

    return best


# ━━━━━━━━━━━━ Plural / Singular Awareness ━━━━━━━━━━━━

def get_singular(name: str) -> str:
    """
    Return the singular form of a domain name if it ends in common plural suffixes.
    Returns the original name if no rule applies.

    Examples:
        "lawyers"   → "lawyer"
        "services"  → "service"
        "cars"      → "car"
        "cities"    → "city"
        "businesses" → "business"
    """
    if len(name) < 4:
        return name
    # -ies → -y  (cities, utilities, agencies)
    # Exception list: words ending in -ies that are NOT consonant+y plurals.
    # "series"→"sery" ✗, "movies"→"movy" ✗ (singular is "movie", via -es rule)
    _IES_NO_Y = frozenset({
        "series", "species", "rabies", "caries", "scabies", "aries",
        "movies", "calories", "brownies", "cookies", "zombies", "birdies",
        "goodies", "smoothies", "genies", "pixies", "selfies", "magpies",
        "collies", "hippies", "yuppies", "groupies", "boogies", "coolies",
        "rookies", "hoagies", "veggies", "birdie", "dearies", "eyries",
    })
    if name.endswith("ies") and len(name) > 5 and name not in _IES_NO_Y:
        return name[:-3] + "y"
    # -ves → -f or -fe  (leaves → leaf, knives → knife)
    if name.endswith("ves") and len(name) > 5:
        without = name[:-3]
        if (without + "f") in ALL_WORDS:
            return without + "f"
        if (without + "fe") in ALL_WORDS:
            return without + "fe"
    # -sses / -xes / -zes / -ches / -shes → remove -es (businesses, boxes, watches)
    if name.endswith(("sses", "xes", "zes", "ches", "shes")) and len(name) > 5:
        return name[:-2]
    # -es → -e or strip (services → service, values → value, courses → course)
    if name.endswith("es") and len(name) > 4:
        without_s  = name[:-1]  # strip just the s
        without_es = name[:-2]  # strip es
        if without_s in ALL_WORDS:
            return without_s
        if without_es in ALL_WORDS:
            return without_es
    # plain -s (cars, jobs, doctors, lawyers)
    if name.endswith("s") and len(name) > 3:
        singular = name[:-1]
        if singular in ALL_WORDS:
            return singular
    return name


# ━━━━━━━━━━━━ Geo Market Quality ━━━━━━━━━━━━
# How active is the English .com domain resale market in this city/region?
#   1 = Premium  — English-native market, high domain investment culture
#   2 = Strong   — International hub, English widely used in business
#   3 = Moderate — Emerging market, partial domain activity
#   4 = Weak     — Minimal English .com domain resale market
#
# Key question: "Would a US/EU domainer realistically find a buyer for
# a geo+niche .com domain targeting this city?"
GEO_MARKET_QUALITY = {
    # ── Tier 1 (quality=1): English-native premium markets ──
    # USA major metros
    "miami": 1, "newyork": 1, "losangeles": 1, "chicago": 1, "houston": 1,
    "dallas": 1, "sanfrancisco": 1, "seattle": 1, "boston": 1, "denver": 1,
    "austin": 1, "phoenix": 1, "lasvegas": 1, "sandiego": 1, "portland": 1,
    "nashville": 1, "atlanta": 1, "charlotte": 1, "orlando": 1, "tampa": 1,
    "detroit": 1, "minneapolis": 1, "philadelphia": 1, "manhattan": 1,
    "brooklyn": 1, "hollywood": 1,
    "sacramento": 1, "memphis": 1, "louisville": 1, "richmond": 1,
    "pittsburgh": 1, "cincinnati": 1, "milwaukee": 1, "raleigh": 1,
    "jacksonville": 1, "tucson": 1, "albuquerque": 1, "tulsa": 1,
    "cleveland": 1, "omaha": 1, "honolulu": 1, "sarasota": 1,
    "scottsdale": 1, "savannah": 1, "charleston": 1, "boise": 1,
    "bethesda": 1, "pasadena": 1, "irvine": 1, "naperville": 1, "mesa": 1,
    "fresno": 1, "bakersfield": 1, "aurora": 1, "annapolis": 1, "plano": 1,
    # USA states
    "texas": 1, "california": 1, "florida": 1, "illinois": 1, "ohio": 1,
    "georgia": 1, "michigan": 1, "arizona": 1, "colorado": 1, "virginia": 1,
    "carolina": 1, "indiana": 1, "tennessee": 1, "maryland": 1, "missouri": 1,
    "wisconsin": 1, "minnesota": 1, "nevada": 1, "utah": 1, "oregon": 1,
    "jersey": 1, "hampshire": 1, "dakota": 1, "penn": 1, "mass": 1,
    # Canada
    "toronto": 1, "vancouver": 1, "montreal": 1, "calgary": 1, "ottawa": 1,
    "winnipeg": 1, "edmonton": 1, "halifax": 1, "victoria": 1, "quebec": 1,
    # UK
    "london": 1, "manchester": 1, "birmingham": 1, "liverpool": 1,
    "edinburgh": 1, "glasgow": 1, "bristol": 1, "leeds": 1,
    "sheffield": 1, "oxford": 1, "cambridge": 1,
    # Australia
    "sydney": 1, "melbourne": 1, "brisbane": 1, "perth": 1,
    "adelaide": 1, "darwin": 1, "hobart": 1, "canberra": 1,
    # New Zealand
    "auckland": 1, "wellington": 1, "christchurch": 1,
    # Ireland
    "dublin": 1,
    # Country-level (English-speaking)
    "usa": 1, "america": 1, "canada": 1, "australia": 1, "zealand": 1,
    "uk": 1, "britain": 1, "england": 1, "scotland": 1, "ireland": 1,
    "newengland": 1, "sunbelt": 1, "midwest": 1, "bayarea": 1,

    # ── Tier 2 (quality=2): International hubs + high English business penetration ──
    # UAE — fully international, English is the business language
    "dubai": 2, "abudhabi": 2,
    # Singapore + Hong Kong — English primary for business
    "singapore": 2, "hongkong": 2,
    # India — English is de facto tech/business language + huge domain market
    "bangalore": 2, "mumbai": 2, "delhi": 2, "hyderabad": 2,
    "chennai": 2, "pune": 2, "kolkata": 2, "india": 2,
    # Japan + South Korea — strong domain culture despite non-English primary
    "tokyo": 2, "osaka": 2, "kyoto": 2, "nagoya": 2, "sapporo": 2,
    "seoul": 2, "busan": 2, "incheon": 2, "daegu": 2,
    "japan": 2, "korea": 2, "taiwan": 2, "taipei": 2,
    # Western Europe — strong digital economies + high English proficiency
    "amsterdam": 2, "rotterdam": 2, "antwerp": 2, "brussels": 2,
    "stockholm": 2, "gothenburg": 2, "malmo": 2,
    "oslo": 2, "copenhagen": 2, "helsinki": 2,
    "zurich": 2, "geneva": 2,
    "berlin": 2, "frankfurt": 2, "munich": 2, "hamburg": 2,
    "cologne": 2, "dusseldorf": 2, "stuttgart": 2,
    "paris": 2, "lyon": 2, "marseille": 2, "toulouse": 2,
    "barcelona": 2, "madrid": 2, "seville": 2, "valencia": 2, "bilbao": 2,
    "milan": 2, "rome": 2, "florence": 2, "venice": 2, "naples": 2,
    "lisbon": 2, "porto": 2,
    "vienna": 2,
    "prague": 2,
    # Latin America major hubs
    "buenosaires": 2, "santiago": 2, "saopaulo": 2, "rio": 2, "brasilia": 2,
    # Country-level
    "germany": 2, "france": 2, "spain": 2, "italy": 2, "netherlands": 2,
    "sweden": 2, "norway": 2, "denmark": 2, "finland": 2,
    "switzerland": 2, "austria": 2, "belgium": 2,
    "europe": 2, "nordic": 2, "alpine": 2,

    # ── Tier 3 (quality=3): Emerging/partial markets ──
    # Middle East — major commercial cities (Arabic-primary but growing digital)
    "riyadh": 3, "jeddah": 3, "dammam": 3,
    "doha": 3, "muscat": 3, "kuwait": 3,
    "cairo": 3, "giza": 3, "alexandria": 3,
    "amman": 3, "beirut": 3,
    "istanbul": 3, "ankara": 3,
    # Southeast/East Asia — significant but non-English-primary
    "bangkok": 3, "kualalumpur": 3, "penang": 3,
    "jakarta": 3, "manila": 3, "cebu": 3,
    "hochiminh": 3, "hanoi": 3,
    "beijing": 3, "shanghai": 3, "shenzhen": 3, "guangzhou": 3,
    "chengdu": 3, "hangzhou": 3, "nanjing": 3, "wuhan": 3,
    # South Asia
    "karachi": 3, "lahore": 3, "islamabad": 3,
    "dhaka": 3, "colombo": 3, "kathmandu": 3,
    # North Africa — major cities
    "casablanca": 3, "rabat": 3, "marrakech": 3,
    "tunis": 3, "algiers": 3,
    # Sub-Saharan Africa — major English-speaking hubs
    "lagos": 3, "nairobi": 3, "accra": 3,
    "capetown": 3, "johannesburg": 3,
    # Eastern Europe
    "warsaw": 3, "krakow": 3, "budapest": 3, "bucharest": 3,
    "belgrade": 3, "zagreb": 3, "sofia": 3, "athens": 3,
    "moscow": 3,
    # Latin America secondary
    "mexicocity": 3, "guadalajara": 3, "monterrey": 3,
    "bogota": 3, "medellin": 3, "lima": 3, "arequipa": 3,
    "montevideo": 3, "quito": 3, "lapaz": 3,
    # Country-level emerging
    "china": 3, "turkey": 3, "russia": 3, "ukraine": 3,
    "thailand": 3, "malaysia": 3, "indonesia": 3, "philippines": 3,
    "vietnam": 3, "pakistan": 3, "bangladesh": 3,
    "egypt": 3, "morocco": 3, "tunisia": 3, "algeria": 3,
    "jordan": 3, "lebanon": 3, "qatar": 3, "oman": 3, "bahrain": 3,
    "nigeria": 3, "kenya": 3, "ghana": 3, "southafrica": 3,
    "colombia": 3, "peru": 3, "chile": 3, "argentina": 3, "brazil": 3,
    "mexico": 3, "latin": 3, "caribbean": 3,
    "greece": 3, "poland": 3, "hungary": 3, "romania": 3,
    "arabia": 3, "arabian": 3, "gulf": 3,
    "africa": 3, "asia": 3, "pacific": 3, "oceania": 3,
    "southeast": 3, "southwest": 3, "northeast": 3, "northwest": 3, "central": 3,
    "mediterranean": 3, "atlantic": 3,

    # ── Tier 4 (quality=4): Minimal English .com domain resale market ──
    # Saudi secondary / religious cities
    "mecca": 4, "medina": 4, "tabuk": 4, "abha": 4, "khobar": 4,
    # UAE micro-emirates (tiny population)
    "sharjah": 4, "ajman": 4, "fujairah": 4, "rasalkhaimah": 4,
    # Bahrain (very small market)
    "manama": 4,
    # Oman secondary
    "salalah": 4,
    # Jordan secondary cities
    "zarqa": 4, "aqaba": 4,
    # Syria (conflict zone)
    "damascus": 4, "aleppo": 4,
    # Iraq (all cities)
    "baghdad": 4, "basra": 4, "erbil": 4,
    # Sudan
    "khartoum": 4, "omdurman": 4,
    # North Africa secondary
    "sfax": 4, "oran": 4, "fez": 4, "luxor": 4, "aswan": 4,
    # Lebanon second city
    "tripoli": 4,
    # Pakistan secondary
    "peshawar": 4,
    # Sub-Saharan Africa secondary
    "addisababa": 4, "dakar": 4, "abuja": 4, "durban": 4, "pretoria": 4,
    "tananarive": 4,
    # Country-level negligible
    "iraq": 4, "syria": 4, "iran": 4, "sudan": 4,
    "sahara": 4, "arctic": 4, "siberia": 4,
}


def get_geo_market_quality(geo_name: str) -> int:
    """
    Returns the domain market quality score for a geo location.
    1 = Premium English-native market (highest value)
    4 = Minimal English .com domain resale market (lowest value)
    Default = 3 for unknown geos (conservative middle ground).
    """
    if not geo_name:
        return 3
    return GEO_MARKET_QUALITY.get(geo_name.lower(), 3)

