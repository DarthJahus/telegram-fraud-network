"""
telegram_checker/llm_utils/interface.py

Low-level interface to a local LLM (LM Studio / Ollama / any OpenAI-compatible
endpoint).  Each call is stateless: no history is carried between messages.
"""

import json
import time

import requests

from telethon.tl.functions.messages import ReportRequest  # noqa – imported for type reference
from telegram_checker.llm_utils.constants import FRAUD_LEXICON
from telegram_checker.config.constants import EMOJI
from telegram_checker.llm_utils.exceptions import (
    LLMRequestError,
    LLMResponseParseError,
    LLMUnexpectedStructureError,
)
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger

LOG = get_logger()

# ── Categories ────────────────────────────────────────────────────────────────
# Maps each category name to its corresponding Telethon InputReportReason.
# HARMLESS maps to None (no report is sent).

LEXICON_STR = "\n".join(f"- {term}: {definition}" for term, definition in FRAUD_LEXICON.items())
TAGS: list[str] = [
    "None",
    "bank_accounts",
    "credit_cards",
    "debit_cards",
    "bank_checks",
    "drugs",
    "guns",
    "fake_money",
]
CATEGORIES: list = [
    "CHILD_ABUSE_SEXUAL",
    "CHILD_ABUSE_PHYSICAL",
    "VIOLENCE_INSULTS_OR_FALSE_INFORMATION",
    "VIOLENCE_GRAPHIC_OR_DISTURBING",
    "VIOLENCE_EXTREME",
    "VIOLENCE_HATE_SPEECH",
    "VIOLENCE_CALLING",
    "VIOLENCE_ORGANIZED_CRIME",
    "VIOLENCE_TERRORISM",
    "VIOLENCE_ANIMAL_ABUSE",
    "ILLEGAL_GOODS_AND_SERVICES_WEAPONS",
    "ILLEGAL_GOODS_AND_SERVICES_DRUGS",
    "ILLEGAL_GOODS_AND_SERVICES_FAKE_DOCS",
    "ILLEGAL_GOODS_AND_SERVICES_COUNTERFEIT_MONEY",
    "ILLEGAL_GOODS_AND_SERVICES_HACKING_TOOLS_MALWARE",
    "ILLEGAL_GOODS_AND_SERVICES_COUNTERFEIT_MERCHANDISE",
    "ILLEGAL_GOODS_AND_SERVICES_OTHER_GOODS_SERVICES",
    "ILLEGAL_ADULT_CONTENT_CHILD_ABUSE",
    "ILLEGAL_ADULT_CONTENT_ILLEGAL_SEXUAL_SERVICES",
    "ILLEGAL_ADULT_CONTENT_ANIMAL_ABUSE",
    "ILLEGAL_ADULT_CONTENT_NON_CONSENSUAL_SEXUAL_IMAGERY",
    "ILLEGAL_ADULT_CONTENT_PORNOGRAPHY",
    "ILLEGAL_ADULT_CONTENT_OTHER_SEXUAL_CONTENT",
    "PERSONAL_DATA_PRIVATE_IMAGES",
    "PERSONAL_DATA_PHONE_NUMBER",
    "PERSONAL_DATA_ADDRESS",
    "PERSONAL_DATA_STOLEN_DATA_OR_CREDENTIALS",
    "PERSONAL_DATA_OTHER",
    "SCAM_OR_FRAUD_IMPERSONATION",
    "SCAM_OR_FRAUD_DECEPTIVE_OR_UNREALISTIC_FINANCIAL_CLAIMS",
    "SCAM_OR_FRAUD_MALWARE_PHISHING",
    "SCAM_OR_FRAUD_FRAUDULENT_SELLER_PRODUCT_OR_SERVICE",
    "COPYRIGHT",
    "SPAM_INSULTS_OR_FALSE_INFORMATION",
    "SPAM_ILLEGAL_CONTENT_PROMOTION",
    "SPAM_OTHER_CONTENT_PROMOTION",
    "HARMLESS"
]

# ── System prompt ─────────────────────────────────────────────────────────────

CATEGORIES_STR = ", ".join(CATEGORIES)
TAGS_STR       = ", ".join(TAGS)

SYSTEM_PROMPT = f"""\
You are a content moderation assistant. Your sole task is to analyze Telegram \
messages and classify them for potential policy violations.

You MUST respond ONLY with a valid JSON object. \
No explanation, no markdown, no code fences, no surrounding text — \
just the raw JSON object.

The JSON object must contain exactly these five fields:

  "message_id"   : integer — the message ID provided in the input
  "category"     : string  — MUST be one of: {CATEGORIES_STR}
  "confidence"   : float   — your certainty score, strictly between 0.0 and 1.0
  "report_text"  : string  — a concise, professional report for Telegram \
moderators (maximum 3 sentences, usually 2)
  "tag"          : string  — MUST be one of: {TAGS_STR} (use "None" if nothing fits)

Classification rules:
- Use HARMLESS when the message does not violate any policy.
- confidence must honestly reflect how certain you are about the chosen category.
- report_text must be factual and neutral; avoid subjective or personal language.
- Never output anything outside the JSON object.

- Messages may be in any language (Hindi, Urdu, Bengali, Arabic, English slang, etc.). Classify based on meaning and context, not language.
- The following glossary covers slang commonly found in fraud-related Telegram channels:

{LEXICON_STR}
"""

# ── LLM caller ────────────────────────────────────────────────────────────────

def call_llm(message_text: str, message_id: int, llm_url: str, llm_model: str) -> dict:
    """
    Send a single Telegram message to the LLM for classification.

    Each call is fully stateless: a fresh system prompt is sent every time.
    Returns the parsed JSON dict on success.
    Raises LLMRequestError, LLMResponseParseError, or LLMUnexpectedStructureError
    on failure so the caller can decide how to handle it.
    """
    from inspect import currentframe  # local import to keep module-level imports clean

    user_content = f"MESSAGE_ID: {message_id}\n\nMESSAGE CONTENT:\n{message_text}"

    payload = {
        "model":       llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.1,    # Low temperature for consistent structured output
        "max_tokens":  1024,
    }

    raw = ""
    try:
        t0 = time.time()
        response = requests.post(llm_url, json=payload, timeout=60)
        response.raise_for_status()
        elapsed = time.time() - t0

        LOG.info(f"LLM responded in {elapsed:.2f}s", EMOJI['llm'])

        raw = response.json()["choices"][0]["message"]["content"].strip()

    except requests.RequestException as e:
        print_debug(e, currentframe().f_code.co_name)
        raise LLMRequestError(f"HTTP request to LLM failed for message {message_id}: {e}") from e

    except (KeyError, IndexError) as e:
        print_debug(e, currentframe().f_code.co_name)
        raise LLMUnexpectedStructureError(
            f"Unexpected LLM response structure for message {message_id}: {e}"
        ) from e

    # Strip any prefix before the first { (model-specific tokens, markdown fences, etc.)
    brace_index = raw.find('{')
    if brace_index == -1:
        raise LLMResponseParseError(
            f"LLM response contains no JSON object for message {message_id}\nRaw: {raw[:300]}"
        )
    raw = raw[brace_index:]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print_debug(e, currentframe().f_code.co_name)
        raise LLMResponseParseError(
            f"LLM returned invalid JSON for message {message_id}: {e}\nRaw: {raw[:300]}"
        ) from e

    # Basic structure validation
    required_keys = {"message_id", "category", "confidence", "report_text", "tag"}
    missing = required_keys - parsed.keys()
    if missing:
        raise LLMUnexpectedStructureError(
            f"LLM JSON is missing required keys {missing} for message {message_id}"
        )

    return parsed


CATEGORY_TO_OPTION_KEYWORD: dict[str, str] = {
    "CHILD_ABUSE":              "child abuse",
    "VIOLENCE":                 "violence",
    "ILLEGAL_GOODS":            "illegal goods",
    "ILLEGAL_ADULT":            "illegal adult",
    "PERSONAL_DATA":            "personal data",
    "SCAM_OR_FRAUD":            "scam",
    "COPYRIGHT":                "copyright",
    "SPAM":                     "spam",
}

CATEGORY_TO_SUBOPTION_KEYWORD: dict[str, str] = {
    # Illegal goods sub-options
    "ILLEGAL_GOODS_AND_SERVICES_WEAPONS":                   "weapon",
    "ILLEGAL_GOODS_AND_SERVICES_DRUGS":                     "drug",
    "ILLEGAL_GOODS_AND_SERVICES_FAKE_DOCS":                 "document",
    "ILLEGAL_GOODS_AND_SERVICES_COUNTERFEIT_MONEY":         "counterfeit",
    "ILLEGAL_GOODS_AND_SERVICES_HACKING_TOOLS_MALWARE":     "malware",
    "ILLEGAL_GOODS_AND_SERVICES_COUNTERFEIT_MERCHANDISE":   "merchandise",
    "ILLEGAL_GOODS_AND_SERVICES_OTHER_GOODS_SERVICES":      "other",
    # Illegal adult content sub-options
    "ILLEGAL_ADULT_CONTENT_CHILD_ABUSE":                    "child",
    "ILLEGAL_ADULT_CONTENT_ILLEGAL_SEXUAL_SERVICES":        "service",
    "ILLEGAL_ADULT_CONTENT_ANIMAL_ABUSE":                   "animal",
    "ILLEGAL_ADULT_CONTENT_NON_CONSENSUAL_SEXUAL_IMAGERY":  "consent",
    "ILLEGAL_ADULT_CONTENT_PORNOGRAPHY":                    "pornograph",
    "ILLEGAL_ADULT_CONTENT_OTHER_SEXUAL_CONTENT":           "other",
    # Personal data sub-options
    "PERSONAL_DATA_PRIVATE_IMAGES":                         "image",
    "PERSONAL_DATA_PHONE_NUMBER":                           "phone",
    "PERSONAL_DATA_ADDRESS":                                "address",
    "PERSONAL_DATA_STOLEN_DATA_OR_CREDENTIALS":             "credential",
    "PERSONAL_DATA_OTHER":                                  "other",
    # Scam sub-options
    "SCAM_OR_FRAUD_IMPERSONATION":                          "impersonat",
    "SCAM_OR_FRAUD_DECEPTIVE_OR_UNREALISTIC_FINANCIAL_CLAIMS": "financial",
    "SCAM_OR_FRAUD_MALWARE_PHISHING":                       "phishing",
    "SCAM_OR_FRAUD_FRAUDULENT_SELLER_PRODUCT_OR_SERVICE":   "seller",
    # Violence sub-options
    "VIOLENCE_INSULTS_OR_FALSE_INFORMATION":                "insult",
    "VIOLENCE_GRAPHIC_OR_DISTURBING":                       "graphic",
    "VIOLENCE_EXTREME":                                     "extreme",
    "VIOLENCE_HATE_SPEECH":                                 "hate",
    "VIOLENCE_CALLING":                                     "calling",
    "VIOLENCE_ORGANIZED_CRIME":                             "crime",
    "VIOLENCE_TERRORISM":                                   "terror",
    "VIOLENCE_ANIMAL_ABUSE":                                "animal",
    # Spam sub-options
    "SPAM_INSULTS_OR_FALSE_INFORMATION":                    "insult",
    "SPAM_ILLEGAL_CONTENT_PROMOTION":                       "illegal",
    "SPAM_OTHER_CONTENT_PROMOTION":                         "other",
}


# ToDo: Improve the function that chooses options. Maybe use LLM?
def choose_option(category: str, options: list) -> int:
    """
    Pick the best report option index for a given category.
    Tries sub-option keyword match first (specific), then top-level prefix
    match (broad), then falls back to 0.
    """
    # 1. Try specific sub-option keyword
    sub_keyword = CATEGORY_TO_SUBOPTION_KEYWORD.get(category)
    if sub_keyword:
        for i, opt in enumerate(options):
            if sub_keyword.lower() in opt.text.lower():
                LOG.info(f"Matched sub-option {i}: {opt.text!r} for category {category}", EMOJI['info'])
                return i

    # 2. Try top-level prefix keyword
    for prefix, kw in CATEGORY_TO_OPTION_KEYWORD.items():
        if category.startswith(prefix):
            for i, opt in enumerate(options):
                if kw.lower() in opt.text.lower():
                    LOG.info(f"Matched option {i}: {opt.text!r} for category {category}", EMOJI['info'])
                    return i
            break

    LOG.info(f"No keyword match for {category}, falling back to option 0", EMOJI['info'])
    return 0
