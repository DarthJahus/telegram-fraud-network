"""
telegram_checker/llm_utils/interface.py

Low-level interface to a local LLM (LM Studio / Ollama / any OpenAI-compatible
endpoint).  Each call is stateless: no history is carried between messages.
"""

import json
import time
from difflib import get_close_matches
import requests
from telegram_checker.llm_utils.constants import SKIP_LV1, SKIP_LV2, TAGS_STR, LEXICON_STR, SYSTEM_PROMPT
from telegram_checker.config.constants import EMOJI
from telegram_checker.llm_utils.exceptions import (
    LLMRequestError,
    LLMResponseParseError,
    LLMUnexpectedStructureError,
)
from telegram_checker.telegram_utils.report import get_report_tree_str
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger

LOG = get_logger()


def get_system_prompt(categories='', tags=TAGS_STR, lexicon=LEXICON_STR):
    return SYSTEM_PROMPT % {'tags': tags, 'categories': categories or get_report_tree_str(), 'lexicon': lexicon}


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
            {"role": "system", "content": get_system_prompt()},
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
    required_keys = {"lv1", "lv2", "confidence", "report_text", "tag"}
    missing = required_keys - parsed.keys()
    if missing:
        raise LLMUnexpectedStructureError(
            f"LLM JSON is missing required keys {missing} for message {message_id}"
        )

    return parsed


def choose_option(category_lv: str, options: list) -> int:
    """
    Match a category label (lv1 or lv2) against live Telegram option texts.
    Uses exact match first, then difflib fallback.
    Never intentionally picks a skip option.
    """
    NEVER_MATCH = SKIP_LV1 | SKIP_LV2

    candidates = [opt.text for opt in options if opt.text.lower() not in NEVER_MATCH]
    labels     = [opt.text for opt in options]

    # Exact match
    for i, opt in enumerate(options):
        if opt.text.lower() == category_lv.lower():
            LOG.info(f"Exact match option {i}: {opt.text!r}", EMOJI['info'])
            return i

    # difflib fallback
    matches = get_close_matches(category_lv, candidates, n=1, cutoff=0.6)
    if matches:
        i = labels.index(matches[0])
        LOG.info(f"Fuzzy match option {i}: {options[i].text!r} for {category_lv!r}", EMOJI['info'])
        return i

    LOG.info(f"No match for {category_lv!r}, falling back to 0", EMOJI['info'])
    return 0
