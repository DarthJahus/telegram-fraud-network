"""
telegram_checker/commands/report.py

Command: --report <identifier>

Fetches the last 100 messages from a Telegram channel/group, passes each one
to a local LLM for classification, then reports flagged messages to Telegram
via the Telethon API — one report per message.
"""

from inspect import currentframe
import time
from telegram_checker.config.constants import EMOJI
from telegram_checker.llm_utils.interface import CATEGORIES, call_llm
from telegram_checker.llm_utils.exceptions import (
    LLMRequestError,
    LLMResponseParseError,
    LLMUnexpectedStructureError,
)
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger
from telegram_checker.telegram_utils.report import send_report
from telegram_checker.commands.exceptions import ReportError, ReportLLMError

LOG = get_logger()
FETCH_LIMIT    = 100
MIN_WORD_COUNT = 3
LINE_THIN     = "─" * 64
LINE_THICK    = "═" * 64


def decide_action(category: str, confidence: float, interactive: bool, all_interactive: bool) -> tuple[bool, bool]:
    """
    Return (auto_report, ask_user) based on category, confidence and mode.

    Confidence tiers:
      >= 0.90       → auto-report
      0.80 – 0.90   → auto-report, or ask if --interactive
      0.70 – 0.80   → ask if --interactive, else log only
      0.60 – 0.70   → log only (never report)
      < 0.60        → silent skip

    HARMLESS special case:
      confidence < 0.70 AND --interactive → ask (might be misclassified)
      otherwise                           → skip
    """
    if category == "HARMLESS":
        if confidence < 0.70 and (interactive or all_interactive):
            return False, True
        return False, False

    if all_interactive:
        return False, True

    if confidence >= 0.90:
        return True, False

    if confidence >= 0.80:
        return (False, True) if interactive else (True, False)

    if confidence >= 0.70:
        return (False, True) if interactive else (False, False)

    return False, False


def confidence_bar(confidence: float, width: int = 10) -> str:
    filled = round(confidence * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def display_result(result: dict, message_text: str, action_label: str) -> None:
    """Pretty-print a single classification result via LOG.output."""
    confidence  = float(result.get("confidence", 0.0))
    category    = result.get("category", "?")
    tag         = result.get("tag", "None")
    report_text = result.get("report_text", "")
    msg_id      = result.get("message_id", "?")

    preview = repr(message_text[:120] + ("…" if len(message_text) > 120 else ""))

    LOG.output(LINE_THIN)
    LOG.output(f"Message ID  : {msg_id}",                                       emoji=EMOJI['id'])
    LOG.output(f"Content     : {preview}",                                      emoji=EMOJI['text'])
    LOG.output(f"Category    : {category}",                                     emoji=EMOJI['analyzed'])
    LOG.output(f"Tag         : {tag}",                                          emoji=EMOJI['info'])
    LOG.output(f"Confidence  : {confidence:.0%}  {confidence_bar(confidence)}", emoji=EMOJI['stats'])
    LOG.output(f"Report text : {report_text}",                                  emoji=EMOJI['reason'])
    LOG.output(f"Action      : {action_label}",                                 emoji=EMOJI['report'])
    LOG.output(LINE_THIN)


def resolve_llm_params(args) -> tuple[str, str]:
    """Return (llm_url, llm_model), prompting the user if either is not set."""
    llm_url   = getattr(args, 'llm_url',   None) or ""
    llm_model = getattr(args, 'llm_model', None) or ""

    if not llm_url.strip():
        default = "http://localhost:1234/v1/chat/completions"
        llm_url = input(
            f"  LLM endpoint URL (e.g. {default}): "
        ).strip()
        if not llm_url:
            llm_url = default

    if not llm_model.strip():
        default = "openai/gpt-oss-20b"
        llm_model = input(
            f"  LLM model name (e.g. {default}): "
        ).strip()
        if not llm_model:
            llm_model = default

    return llm_url, llm_model


def run_report(client, args):
    """
    Entry point for `--report <identifier>`.

    1. Resolve the entity.
    2. Fetch the last FETCH_LIMIT messages.
    3. Filter out messages with fewer than MIN_WORD_COUNT words.
    4. For each remaining message, call the LLM.
    5. Apply confidence-based action logic.
    6. Report, ask, or log accordingly.
    7. Print a summary.
    """
    identifier  = args.report
    interactive = getattr(args, 'interactive', False)
    all_interactive = getattr(args, 'all_interactive', False)

    llm_url, llm_model = resolve_llm_params(args)

    # 1. Resolve entity
    LOG.info(f"Resolving entity: {identifier}", EMOJI['connecting'])
    try:
        from telegram_checker.telegram_utils.report import resolve_entity
        entity = resolve_entity(client, identifier)
    except ValueError as e:
        LOG.error(str(e), EMOJI['error'])
        raise ReportError(str(e)) from e
    except Exception as e:
        LOG.error(f"Could not resolve '{identifier}': {e}", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)
        raise ReportError(f"Could not resolve entity '{identifier}': {e}") from e

    entity_title = (
        getattr(entity, 'title',    None)
        or getattr(entity, 'username', None)
        or str(identifier)
    )
    LOG.output(f"Entity resolved: {entity_title}", emoji=EMOJI['success'])

    # 2. Fetch messages
    LOG.info(f"Fetching last {FETCH_LIMIT} messages…", EMOJI['info'])
    try:
        messages = list(client.iter_messages(entity, limit=FETCH_LIMIT))
    except Exception as e:
        LOG.error(f"Failed to fetch messages: {e}", EMOJI['error'])
        raise ReportError(f"Failed to fetch messages from '{entity_title}': {e}") from e

    LOG.info(f"Fetched {len(messages)} messages.", EMOJI['info'])

    # 3. Filter
    filtered = [
        msg for msg in messages
        if (msg.text or "").strip()
        and len((msg.text or "").split()) >= MIN_WORD_COUNT
    ]
    removed = len(messages) - len(filtered)
    LOG.output(
        f"{len(filtered)} messages retained after filtering "
        f"({removed} removed — fewer than {MIN_WORD_COUNT} words).",
        emoji=EMOJI['analyzed']
    )

    if not filtered:
        raise ReportError("No messages remaining after filtering.")

    # Header
    LOG.output(LINE_THICK)
    LOG.output(f"Analyzing {len(filtered)} messages from: {entity_title}", emoji=EMOJI['analyzed'])
    LOG.output(f"LLM    : {llm_url}  ({llm_model})",                       emoji=EMOJI['llm'])
    LOG.output(f"Mode   : {'full interactive' if all_interactive else ('interactive' if interactive else 'automatic')}", emoji=EMOJI['info'])
    LOG.output(LINE_THICK)

    # Stats
    stats = {
        'analyzed':        0,
        'reported_auto':   0,
        'reported_manual': 0,
        'skipped_manual':  0,
        'log_only':        0,
        'harmless':        0,
        'low_confidence':  0,
        'errors':          0,
    }

    # 4 & 5. Analyze and act
    for msg in filtered:
        text       = msg.text.strip()
        message_id = msg.id

        LOG.info(LINE_THIN)
        LOG.info(f"Analyzing message {message_id}…", EMOJI['llm'])

        # Call LLM
        try:
            result = call_llm(text, message_id, llm_url, llm_model)
        except (LLMRequestError, LLMResponseParseError, LLMUnexpectedStructureError) as e:
            LOG.error(str(e), EMOJI['error'])
            stats['errors'] += 1
            continue

        stats['analyzed'] += 1

        # Validate category
        category   = result.get('category', 'HARMLESS')
        confidence = float(result.get('confidence', 0.0))

        if category not in CATEGORIES:
            LOG.error(
                f"Unknown category '{category}' for message {message_id} — skipping.",
                EMOJI['error']
            )
            stats['errors'] += 1
            continue

        # Decide action
        auto_report, ask_user = decide_action(category, confidence, interactive, all_interactive)

        # Build the action label for display — also updates stats for
        # the no-report cases right here so we don't fall through again below
        if category == "HARMLESS" and not ask_user:
            action_label = "Harmless — skipped"
            stats['harmless'] += 1
        elif confidence < 0.60:
            action_label = f"Confidence too low ({confidence:.0%}) — skipped"
            stats['low_confidence'] += 1
        elif not auto_report and not ask_user:
            action_label = f"Logged only ({confidence:.0%})"
            stats['log_only'] += 1
        elif auto_report:
            action_label = f"Auto-reporting ({confidence:.0%})"
        else:
            action_label = f"Awaiting your decision ({confidence:.0%})"

        display_result(result, text, action_label)

        # Short-circuit: nothing to report
        if not auto_report and not ask_user:
            continue

        # From here, a report will potentially be sent
        report_text = result.get('report_text', '')
        confirmed   = False

        if ask_user:
            try:
                answer = input(
                    f"\n  {EMOJI['report']} Send report for message {message_id}? [y/N] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                LOG.info("Interrupted by user.", EMOJI['info'])
                break

            confirmed = answer in ('y', 'yes')
            if not confirmed:
                LOG.output(f"Skipped by user — message {message_id}", emoji=EMOJI['skip'])
                stats['skipped_manual'] += 1
                continue

        elif auto_report:
            confirmed = True

        if confirmed:
            success = send_report(client, entity, message_id, category, report_text)
            if success:
                if ask_user:
                    stats['reported_manual'] += 1
                else:
                    stats['reported_auto'] += 1
            else:
                stats['errors'] += 1

        # Small pause between reports to respect Telegram rate limits
        time.sleep(0.5)

    if stats['errors'] > 0 and stats['analyzed'] == 0:
        raise ReportLLMError("LLM failed on all messages — no analysis was completed.")

    # Summary
    total_reported = stats['reported_auto'] + stats['reported_manual']

    LOG.output(LINE_THICK)
    LOG.output(f"Summary — {entity_title}",                              emoji=EMOJI['stats'])
    LOG.output(LINE_THIN)
    LOG.output(f"Fetched          : {len(messages)}",                    emoji=EMOJI['info'])
    LOG.output(f"Analyzed         : {stats['analyzed']}",                emoji=EMOJI['analyzed'])
    LOG.output(f"Reported (auto)  : {stats['reported_auto']}",           emoji=EMOJI['report'])
    LOG.output(f"Reported (manual): {stats['reported_manual']}",         emoji=EMOJI['success'])
    LOG.output(f"Skipped (manual) : {stats['skipped_manual']}",          emoji=EMOJI['skip'])
    LOG.output(f"Logged only      : {stats['log_only']}",                emoji=EMOJI['log'])
    LOG.output(f"Harmless         : {stats['harmless']}",                emoji=EMOJI['harmless'])
    LOG.output(f"Low confidence   : {stats['low_confidence']}",          emoji=EMOJI['unknown'])
    LOG.output(f"Errors           : {stats['errors']}",                  emoji=EMOJI['error'])
    LOG.output(LINE_THIN)
    LOG.output(f"Total reported   : {total_reported}",                   emoji=EMOJI['success'])
    LOG.output(LINE_THICK)
