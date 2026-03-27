"""
telegram_checker/commands/report.py

Command: --report <identifier>

Fetches the last 100 messages from a Telegram channel/group, passes each one
to a local LLM for classification, then reports flagged messages to Telegram
via the Telethon API — one report per message.
"""
from collections import Counter
from inspect import currentframe
from datetime import datetime
import time
from telegram_checker.config.api import SLEEP_BETWEEN_REPORTS
from telegram_checker.config.constants import EMOJI
from telegram_checker.llm_utils.interface import call_llm
from telegram_checker.llm_utils.exceptions import (
    LLMRequestError,
    LLMResponseParseError,
    LLMUnexpectedStructureError,
)
from telegram_checker.mdml_utils.mdml_file import append_report_to_md
from telegram_checker.telegram_utils.exceptions import TelegramUtilsReportNoReport, TelegramUtilsReportSkippedByUser
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger
from telegram_checker.telegram_utils.report import send_report
from telegram_checker.commands.exceptions import ReportError, ReportLLMError
from difflib import get_close_matches
from telegram_checker.telegram_utils.constants import REPORT_TREE_PATH
from telegram_checker.telegram_utils.report import load_report_tree

LOG = get_logger()
FETCH_LIMIT    = 100
MIN_WORD_COUNT = 3
LINE_THIN     = "─" * 64
LINE_THICK    = "═" * 64


def decide_action(lv1: str, confidence: float, interactive: bool, all_interactive: bool) -> tuple[bool, bool]:
    """
    Return (auto_report, ask_user) based on category, confidence and mode.

    Confidence tiers:
      >= 0.90       → auto-report
      0.80 – 0.90   → auto-report, or ask if --interactive
      0.70 – 0.80   → ask if --interactive, else log only
      0.60 – 0.70   → log only (never report)
      < 0.60        → silent skip

    "Harmless" special case:
      confidence < 0.70 AND --interactive → ask (might be misclassified)
      otherwise                           → skip
    """
    if lv1 == "Harmless":
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
    if not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
        raise ValueError("confidence has to be in [0, 1]")
    if not isinstance(width, int) or width <= 0:
        raise ValueError("width has to be strictly positive")
    filled = int(max(0., confidence - 0.5) * 2 * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def display_result(result: dict, message_text: str, action_label: str) -> None:
    """Pretty-print a single classification result via LOG.output."""
    confidence  = float(result.get("confidence", 0.0))
    category    = f"{result.get('lv1', '?')} / {result.get('lv2', '?')}"
    tag         = result.get("tag", "None")
    report_text = result.get("report_text", "")
    msg_id      = result.get("message_id", "?")

    preview = repr(message_text[:120] + ("…" if len(message_text) > 120 else ""))

    LOG.info(LINE_THIN)
    LOG.info(f"Message ID  : {msg_id}",                                       emoji=EMOJI['id'])
    LOG.info(f"Content     : {preview}",                                      emoji=EMOJI['text'])
    LOG.info(f"Category    : {category}",                                     emoji=EMOJI['analyzed'])
    LOG.info(f"Tag         : {tag}",                                          emoji=EMOJI['tag'])
    LOG.info(f"Confidence  : {confidence:.0%}  {confidence_bar(confidence)}", emoji=EMOJI['stats'])
    LOG.info(f"Report text : {report_text}",                                  emoji=EMOJI['reason'])
    LOG.info(f"Action      : {action_label}",                                 emoji=EMOJI['report'])
    LOG.info(LINE_THIN)


def resolve_llm_params(args) -> tuple[str, str]:
    """Return (llm_url, llm_model), prompting the user if either is not set."""
    llm_url   = getattr(args, 'llm_url',   None) or ""
    llm_model = getattr(args, 'llm_model', None) or ""

    if not llm_url.strip():
        default = "http://localhost:1234/api/v1/chat"
        llm_url = input(
            f"  LLM endpoint ({default}): "
        ).strip()
        if not llm_url:
            llm_url = default

    if not llm_model.strip():
        default = "openai/gpt-oss-20b"
        llm_model = input(
            f"  LLM model ({default}): "
        ).strip()
        print()
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
        LOG.error(str(e))
        raise ReportError(str(e)) from e
    except Exception as e:
        LOG.error(f"Could not resolve '{identifier}': {e}")
        print_debug(e, currentframe().f_code.co_name)
        raise ReportError(f"Could not resolve entity '{identifier}': {e}") from e

    entity_title = (
        getattr(entity, 'title', None)
        or getattr(entity, 'username', None)
        or str(identifier)
    )
    LOG.info(f"Entity resolved: {entity_title}", emoji=EMOJI['success'])

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
    LOG.info(
        f"{len(filtered)} messages retained after filtering "
        f"({removed} removed — fewer than {MIN_WORD_COUNT} words).",
        emoji=EMOJI['analyzed']
    )

    if not filtered:
        raise ReportError("No messages remaining after filtering.")

    # Header
    LOG.info(LINE_THICK)
    LOG.info(f"Analyzing {len(filtered)} messages from: {entity_title}", emoji=EMOJI['analyzed'])
    LOG.info(f"LLM  : {llm_model} @ {llm_url}", emoji=EMOJI['llm'])
    LOG.info(f"Mode : {'full interactive' if all_interactive else ('interactive' if interactive else 'automatic')}", emoji=EMOJI['info'])
    LOG.info(LINE_THICK)

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
        'tags':            Counter()
    }

    report_tree = load_report_tree()
    if getattr(args, 'update', False) and filtered:
        from telegram_checker.telegram_utils.report import get_categories_from_telegram
        from telegram_checker.telegram_utils.report import save_report_tree

        LOG.info("Exploring Telegram report tree…", EMOJI['info'])
        tree = get_categories_from_telegram(client, entity, filtered[0].id)

        if interactive or all_interactive:
            LOG.info("Report tree discovered:", emoji=EMOJI['info'])
            for lv1_k, subs in tree.items():
                LOG.info(f"  {lv1_k}: {subs}", emoji=EMOJI['info'])
            try:
                answer = input(f"\n  {EMOJI['report']} Save updated report tree? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = 'n'
            if answer in ('y', 'yes') or args.yes:
                save_report_tree(tree, REPORT_TREE_PATH)
            else:
                LOG.info("Tree update cancelled.", EMOJI['info'])
        else:
            save_report_tree(tree, REPORT_TREE_PATH)

        # Reload
        report_tree = load_report_tree()

    # 4 & 5. Analyze and act
    n = 0
    for msg in filtered:
        n += 1
        try:
            LOG.info(LINE_THIN)
            LOG.info(f'Handling message {n:3} of {len(filtered):3}', emoji=EMOJI['file'])
            report_message(client, entity, msg, llm_url, llm_model, report_tree, interactive, all_interactive, stats)
        except (LLMRequestError, LLMResponseParseError, LLMUnexpectedStructureError) as e:
            LOG.error(str(e), EMOJI['error'])
            stats['errors'] += 1
            continue
        except TelegramUtilsReportSkippedByUser:
            LOG.info(f"Skipped by user — message {msg.id}", emoji=EMOJI['skip'])
            stats['skipped_manual'] += 1
        except TelegramUtilsReportNoReport:
            continue
        except Exception as e:
            print_debug(e, currentframe().f_code.co_name)
            stats['errors'] += 1

    if stats['errors'] > 0 and stats['analyzed'] == 0:
        raise ReportLLMError("LLM failed on all messages — no analysis was completed.")

    # Summary
    total_reported = stats['reported_auto'] + stats['reported_manual']

    dest = LOG.output

    if args.md and total_reported:
        LOG.info('Generating Markdown report...')
        LOG.info('```')
        LOG.output("reports.ai:")
        LOG.output(f"- `{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
        LOG.output(f"\t- account: `{args.user[0].upper()}`")
        LOG.output(f"\t- analyzed: `{stats['analyzed']}`")
        LOG.output(f"\t- reported: `{total_reported}`")
        LOG.output("\t- tags: { " + " ; ".join(f"`{tag}`" for tag in stats['tags']) + " }")
        LOG.info('```')
        dest = LOG.info

    if args.update_file and total_reported:
        append_report_to_md(
            args.update_file,
            account=args.user[0].upper(),
            analyzed=stats['analyzed'],
            reported=total_reported,
            tags=stats['tags']
        )

    if total_reported == 0:
        dest = LOG.info

    dest(LINE_THICK)
    dest(f"Summary for {entity_title!r} — {entity.id}",        emoji=EMOJI['stats'])
    dest(LINE_THIN)
    dest(f"Entity           : {entity.id:<16}",                emoji=EMOJI['id'])
    dest(f"Fetched          : {len(messages):.>5}",            emoji=EMOJI['info'])
    dest(f"Analyzed         : {stats['analyzed']:.>5}",        emoji=EMOJI['analyzed'])
    if stats['tags']:
        dest(
            f"Used tags\n   " + "\n   ".join(
                f"{'' if tag.startswith('#') else '#'}{tag:16}: {count:.>5}" for tag, count in stats['tags'].most_common()
            ),
            emoji=EMOJI['tag']
        )
    dest(f"Reported (auto)  : {stats['reported_auto']:.>5}",   emoji=EMOJI['report'])
    dest(f"Reported (manual): {stats['reported_manual']:.>5}", emoji=EMOJI['success'])
    dest(f"Skipped (manual) : {stats['skipped_manual']:.>5}",  emoji=EMOJI['skip'])
    dest(f"Logged only      : {stats['log_only']:.>5}",        emoji=EMOJI['log'])
    dest(f"Harmless         : {stats['harmless']:.>5}",        emoji=EMOJI['harmless'])
    dest(f"Low confidence   : {stats['low_confidence']:.>5}",  emoji=EMOJI['unknown'])
    dest(f"Errors           : {stats['errors']:.>5}",          emoji=EMOJI['error'])
    dest(LINE_THIN)
    dest(f"Total reported   : {total_reported:.>5}",           emoji=EMOJI['success'])
    dest(LINE_THICK)


def report_message(client, entity, msg, llm_url, llm_model, report_tree, interactive, all_interactive, stats):
    text = msg.text.strip()
    message_id = msg.id

    LOG.info(LINE_THIN)
    LOG.info(f"Analyzing message {message_id}…", EMOJI['llm'])

    # Call LLM
    result = call_llm(text, message_id, llm_url, llm_model)

    # Get tag
    tag = result.get('tag')
    if tag and tag.lower() != 'none':
        stats['tags'][tag.lower()] += 1

    # Insert message_id
    result['message_id'] = message_id

    stats['analyzed'] += 1

    # Validate category
    lv1 = result.get('lv1', 'Harmless')
    lv2 = result.get('lv2', 'No report')
    confidence = float(result.get('confidence', 0.0))

    # difflib correction on lv1/lv2 against known tree
    lv1_candidates = list(report_tree.keys())
    lv1_match = get_close_matches(lv1, lv1_candidates, n=1, cutoff=0.82)
    if lv1_match and lv1_match[0] != lv1:
        LOG.info(f"lv1 corrected: {lv1!r} → {lv1_match[0]!r}", EMOJI['info'])
        lv1 = lv1_match[0]
    if lv1 in report_tree:
        lv2_candidates = report_tree[lv1]
        lv2_match = get_close_matches(lv2, lv2_candidates, n=1, cutoff=0.82)
        if lv2_match and lv2_match[0] != lv2:
            LOG.info(f"lv2 corrected: {lv2!r} → {lv2_match[0]!r}", EMOJI['info'])
            lv2 = lv2_match[0]
    auto_report, ask_user = decide_action(lv1, confidence, interactive, all_interactive)

    # Build the action label for display — also updates stats for
    # the no-report cases right here so we don't fall through again below
    if lv1 == "Harmless" and not ask_user:
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
        raise TelegramUtilsReportNoReport("Not auto-reporting or nothing to report; and not asking for user's input")

    # From here, a report will potentially be sent
    report_text = result.get('report_text', '')
    confirmed = False

    if ask_user:
        try:
            answer = input(
                f"\n  {EMOJI['report']} Send report for message {message_id}? [y/N] "
            ).strip().lower()
        except EOFError:
            raise TelegramUtilsReportSkippedByUser("User asked. No valid answer. Considering 'skip'")

        confirmed = answer in ('y', 'yes')
        if not confirmed:
            raise TelegramUtilsReportSkippedByUser("User skipped the message.")

    elif auto_report:
        confirmed = True

    if confirmed:
        success = send_report(client, entity, message_id, lv1, lv2, report_text)
        if success:
            if ask_user:
                stats['reported_manual'] += 1
            else:
                stats['reported_auto'] += 1
        else:
            stats['errors'] += 1

    # Small pause between reports to respect Telegram rate limits
    time.sleep(SLEEP_BETWEEN_REPORTS)
