"""Central configuration. Every tunable value and every OPEN decision lives here.

Values marked OPEN are placeholders for decisions not yet made. Do not treat them
as product decisions. See README section "OPEN items".
"""
from __future__ import annotations

import datetime as _dt
import os
from decimal import Decimal

# ---------------------------------------------------------------- data
DATA_DIR = os.environ.get("DUTYDROP_DATA_DIR", os.path.expanduser("~/Claude/hts"))
# Revision tag to load, e.g. "2026_Rev21". Empty means: newest revision found in DATA_DIR.
DATA_REVISION = os.environ.get("DUTYDROP_DATA_REVISION", "")
# Where audit records and the result cache are written.
STATE_DIR = os.environ.get("DUTYDROP_STATE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state"))

# ---------------------------------------------------------------- output text
DISCLAIMER = "Estimate only. Check this with a customs broker. DutyDrop is not a customs broker."
PUBLIC_LINK = "dutydrop.co"
PROVISIONAL_LABEL = "Provisional total, before stacking rules. May overstate."
USMCA_SCENARIO_LABEL = "USMCA rate, if the goods qualify"
MAY_BE_EXEMPT_LABEL = "May be exempt, verify"
BROKER_ROUTE = ("We could not pin down one code. These are the likely candidates. "
                "A licensed customs broker can confirm the classification.")

# ---------------------------------------------------------------- status rules (Spec 2.5)
# Program windows. start is inclusive, end is exclusive: entries ON OR AFTER end are excluded.
# None means the date is not in the data; the engine flags it rather than guessing.
STATUS_RULES = {
    "IEEPA": {
        "start": None,
        "end": _dt.date(2026, 2, 24),
        "basis": "IEEPA duties invalidated; CBP CSMS 67834313 ended collection for entries on or after 2026-02-24",
        "refund_note": ("IEEPA duties paid may be eligible for refund through CBP and the Court of International "
                        "Trade. Eligibility only; this is not a statement that a refund is owed."),
    },
    "Section 122": {
        "start": _dt.date(2026, 2, 24),
        "end": _dt.date(2026, 7, 24),
        "basis": "Section 122 surcharge (Proclamation 11012) ran 2026-02-24 to 2026-07-24",
        "refund_note": ("Section 122 duties paid may be eligible for refund depending on a pending Federal Circuit "
                        "appeal. Eligibility only; this is not a statement that a refund is owed."),
    },
    "Section 301 forced labor": {
        "start": _dt.date(2026, 7, 24),
        "end": None,
        "basis": "Section 301 forced labor duties effective 2026-07-24",
        "refund_note": None,
    },
}

# EU member states. Used only to match an origin to overlays labeled "European Union".
EU_MEMBERS = [
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Czechia", "Denmark", "Estonia",
    "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania",
    "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
    "Spain", "Sweden",
]
ORIGIN_ALIASES = {
    "russia": "russian federation",
    "korea": "south korea",
    "republic of korea": "south korea",
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "viet nam": "vietnam",
    "belarus": "republic of belarus",
    "dprk": "north korea",
}

# ---------------------------------------------------------------- decision thresholds (OPEN item 5)
# Starting defaults. Tune against the golden set once it exists.
STRONG_SCORE = float(os.environ.get("DUTYDROP_STRONG_SCORE", "0.75"))
STRONG_MARGIN = float(os.environ.get("DUTYDROP_STRONG_MARGIN", "0.15"))
MARGINAL_SCORE = float(os.environ.get("DUTYDROP_MARGINAL_SCORE", "0.50"))
BAND_HIGH = STRONG_SCORE
BAND_MEDIUM = MARGINAL_SCORE
MAX_LOOP_ROUNDS = 2
SHORTLIST_SIZE = 10
RETRIEVE_POOL = 60
ATTRIBUTE_WEIGHTS = {"identity": 0.40, "function": 0.25, "material": 0.25, "construction": 0.10}
MODEL_WEIGHT = 0.7      # share of a candidate score from the reasoning call
LEXICAL_WEIGHT = 0.3    # share from code side lexical evidence

# ---------------------------------------------------------------- models and cost (Spec 3A)
PROVIDER = os.environ.get("DUTYDROP_PROVIDER", "deepseek")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "")   # a Qwen Flash class vision model
GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")           # a Gemini Flash class model
# Extra request fields per provider. DeepSeek flash thinks by default, which spent ~220 extra
# output tokens on a trivial call in testing (2026-10-29); disabled here to hold the cost budget.
PROVIDER_EXTRA = {
    "deepseek": {"thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}},
    "openrouter": {"response_format": {"type": "json_object"}},
    "gemini": {"response_format": {"type": "json_object"}},
}

# USD per 1M tokens. Defaults are the spec's reference figures, NOT verified against DeepSeek's
# official pricing page (it did not render for the builder). Set these from the official page and
# set DUTYDROP_PRICES_VERIFIED=1.
PRICE_INPUT_PER_M = Decimal(os.environ.get("DUTYDROP_PRICE_INPUT_PER_M", "0.14"))
PRICE_INPUT_CACHED_PER_M = Decimal(os.environ.get("DUTYDROP_PRICE_INPUT_CACHED_PER_M", "0.14"))
PRICE_OUTPUT_PER_M = Decimal(os.environ.get("DUTYDROP_PRICE_OUTPUT_PER_M", "0.28"))
PRICES_VERIFIED = os.environ.get("DUTYDROP_PRICES_VERIFIED", "0") == "1"

MAX_TOKENS_IDENTIFY = 500
MAX_TOKENS_DECIDE = 400
COST_TARGET_PER_RECEIPT = Decimal("0.005")
COST_CAP_PER_RECEIPT = Decimal("0.02")
# (input tokens, output tokens) projected before a call, used by the cost cap.
PROJECTED_TOKENS = {"identify": (1100, MAX_TOKENS_IDENTIFY), "decide": (2000, MAX_TOKENS_DECIDE)}

IMAGE_MAX_DIM = 1024
IMAGE_JPEG_QUALITY = 85
REQUEST_TIMEOUT_S = 60
