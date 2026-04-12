"""
telegram_checker/commands/report.py

Command: --report <identifier>

Fetches the last 100 messages from a Telegram channel/group, passes each one
to a local LLM for classification, then reports flagged messages to Telegram
via the Telethon API — one report per message.
"""
from statistics import mean
from collections import Counter
from inspect import currentframe
from datetime import datetime
from time import time, sleep
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import CheckChatInviteRequest
from telegram_checker.config.api import SLEEP_BETWEEN_REPORTS
from telegram_checker.config.constants import (
    EMOJI,
    AI_REPORT_FIELD,
    AI_REPORT_FIELD_NAME,
    UI_HORIZONTAL_LINE,
    AI_LEGIT_FIELD,
    make_stats
)
from telegram_checker.llm_utils.constants import LLM_DEFAULT, MIN_WORD_COUNT, FETCH_LIMIT
from telegram_checker.llm_utils.interface import call_llm
from telegram_checker.llm_utils.exceptions import (
    LLMRequestError,
    LLMResponseParseError,
    LLMUnexpectedStructureError,
)
from telegram_checker.mdml_utils.mdml_file import append_report_to_md
from telegram_checker.telegram_utils.entity_fetcher import iter_md_entities, SkipReasonType
from telegram_checker.telegram_utils.exceptions import TelegramUtilsReportNoReport, TelegramUtilsReportSkippedByUser
from telegram_checker.utils.helpers import print_debug, get_text_preview, seconds_to_time, sleep_with_progress
from telegram_checker.utils.logger import get_logger, create_progress_bar
from telegram_checker.telegram_utils.report import send_report
from telegram_checker.commands.exceptions import (
    ReportError, ReportLLMError, ReportErrorFloodWait,
    ReportErrorEntityResolution, ReportErrorFetch, ReportErrorFilter
)
from difflib import get_close_matches
from telegram_checker.telegram_utils.constants import REPORT_TREE_PATH
from telegram_checker.telegram_utils.report import load_report_tree
from telegram_checker.utils.output_display import print_stats_report

LOG = get_logger()


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


def display_result(result: dict, message_text: str, action_label: str, padding=0) -> None:
    """Pretty-print a single classification result via LOG.output."""
    confidence  = float(result.get("confidence", 0.0))
    category    = f"{result.get('lv1', '?')} / {result.get('lv2', '?')}"
    tag         = result.get("tag", "None")
    report_text = result.get("report_text", "")
    msg_id      = result.get("message_id", "?")

    content_preview = get_text_preview(
        message_text,
        initial_indent=17+padding,
        initial_padding=0,
        padding=17+padding,
        multiline=True,
        max_lines=3,
        line_limit=80
    )

    report_preview = get_text_preview(
        report_text,
        initial_indent=17 + padding,
        initial_padding=0,
        padding=17 + padding,
        multiline=True,
        line_limit=80
    )

    LOG.info(UI_HORIZONTAL_LINE, padding=padding)
    LOG.info(f"Message ID  : {msg_id}",                                       emoji=EMOJI['id'], padding=padding)
    LOG.info(f"Content     : {content_preview}",                              emoji=EMOJI['text'], padding=padding)
    LOG.info(f"Category    : {category}",                                     emoji=EMOJI['analyzed'], padding=padding)
    LOG.info(f"Tag         : {tag}",                                          emoji=EMOJI['tag'], padding=padding)
    LOG.info(f"Confidence  : {confidence:.0%}  {confidence_bar(confidence)}", emoji=EMOJI['stats'], padding=padding)
    LOG.info(f"Report text : {report_preview}",                               emoji=EMOJI['reason'], padding=padding)
    LOG.info(f"Action      : {action_label}",                                 emoji=EMOJI['report'], padding=padding)
    LOG.info(UI_HORIZONTAL_LINE, padding=padding)


def resolve_llm_params(args) -> dict[str, str]:
    """Return (llm_url, llm_model), prompting the user if either is not set."""
    llm_url   = getattr(args, 'llm_url',   None) or ""
    llm_model = getattr(args, 'llm_model', None) or ""

    if not llm_url.strip():
        default = LLM_DEFAULT['endpoint']
        llm_url = input(
            f"  LLM endpoint ({default}): "
        ).strip()

    if not llm_model.strip():
        default = LLM_DEFAULT['model']
        llm_model = input(
            f"  LLM model ({default}): "
        ).strip()
        print()

    return {
        "endpoint": llm_url or LLM_DEFAULT['endpoint'],
        "model": llm_model or LLM_DEFAULT['model']
    }

def report_message(client, entity, msg, llm_url, llm_model, report_tree, interactive, all_interactive, stats, padding=0):
    text = msg.text.strip()
    message_id = msg.id

    LOG.info(UI_HORIZONTAL_LINE, padding=padding)
    LOG.info(f"Analyzing message {message_id}…", EMOJI['llm'], padding=padding)

    # Call LLM
    result = call_llm(text, message_id, llm_url, llm_model, padding=padding)

    stats['llm_time'].append(result['llm_time'])

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
        LOG.info(f"lv1 corrected: {lv1!r} → {lv1_match[0]!r}", EMOJI['info'], padding=padding)
        lv1 = lv1_match[0]
    if lv1 in report_tree:
        lv2_candidates = report_tree[lv1]
        lv2_match = get_close_matches(lv2, lv2_candidates, n=1, cutoff=0.82)
        if lv2_match and lv2_match[0] != lv2:
            LOG.info(f"lv2 corrected: {lv2!r} → {lv2_match[0]!r}", EMOJI['info'], padding=padding)
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

    display_result(result, text, action_label, padding=padding)

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
        # ToDo: Get matched report options to use in statistics (counter stats['report_path'], with path being "Opt1/Opt2")
        success = send_report(client, entity, message_id, lv1, lv2, report_text, padding=padding)
        if success:
            if ask_user:
                stats['reported_manual'] += 1
            else:
                stats['reported_auto'] += 1
        else:
            stats['errors'] += 1

    # Small pause between reports to respect Telegram rate limits
    sleep(SLEEP_BETWEEN_REPORTS)


def run_report(client, args, identifier=None, llm=LLM_DEFAULT, padding=0):
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
    if identifier is None:
        identifier  = args.report
    interactive = getattr(args, 'interactive', False)
    all_interactive = getattr(args, 'all_interactive', False)

    llm_url = llm['endpoint']
    llm_model = llm['model']

    # 1. Resolve entity
    LOG.info(f"Resolving entity: {identifier}", EMOJI['connecting'])
    try:
        from telegram_checker.telegram_utils.report import resolve_entity
        entity = resolve_entity(client, identifier)
    except ValueError as e:
        raise ReportErrorEntityResolution(str(e)) from e
    except FloodWaitError as e:
        if isinstance(e.request, CheckChatInviteRequest):
            raise ReportErrorFloodWait(f"FloodWait {seconds_to_time(e.seconds)} on CheckChatInviteRequest.")
        else:
            sleep_with_progress(e.seconds, emoji=EMOJI["pause"],padding=padding)
            run_report(client, args, identifier, llm, padding)
    except Exception as e:
        raise ReportErrorEntityResolution(f"Could not resolve entity '{identifier}': {e}") from e

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
        raise ReportErrorFetch(f"Failed to fetch messages from '{entity_title}': {e}") from e

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
        raise ReportErrorFilter("No messages remaining after filtering.")

    # Header
    LOG.info(UI_HORIZONTAL_LINE, padding=padding)
    LOG.info(f"Analyzing {len(filtered)} messages from: {entity_title}", emoji=EMOJI['analyzed'], padding=padding)
    LOG.info(f"LLM  : {llm_model} @ {llm_url}", emoji=EMOJI['llm'], padding=padding)
    LOG.info(f"Mode : {'full interactive' if all_interactive else ('interactive' if interactive else 'automatic')}", emoji=EMOJI['info'], padding=padding)
    LOG.info(UI_HORIZONTAL_LINE, padding=padding)

    # Stats
    stats = make_stats('report')

    report_tree = load_report_tree()
    if getattr(args, 'update', False) and filtered:
        from telegram_checker.telegram_utils.report import get_categories_from_telegram
        from telegram_checker.telegram_utils.report import save_report_tree

        LOG.info("Exploring Telegram report tree…", EMOJI['info'], padding=padding)
        tree = get_categories_from_telegram(client, entity, filtered[0].id)

        if interactive or all_interactive:
            LOG.info("Report tree discovered:", emoji=EMOJI['info'], padding=padding)
            for lv1_k, subs in tree.items():
                LOG.info(f"  {lv1_k}: {subs}", emoji=EMOJI['info'], padding=padding )
            try:
                answer = input(f"\n  {EMOJI['report']} Save updated report tree? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = 'n'
            if answer in ('y', 'yes') or args.yes:
                save_report_tree(tree, REPORT_TREE_PATH)
            else:
                LOG.info("Tree update cancelled.", EMOJI['info'], padding=padding)
        else:
            save_report_tree(tree, REPORT_TREE_PATH)

        # Reload
        report_tree = load_report_tree()

    # 4 & 5. Analyze and act
    n = 0
    for msg in filtered:
        n += 1
        try:
            LOG.info(UI_HORIZONTAL_LINE, padding=padding)
            LOG.info(f'Handling message {n:3} of {len(filtered):3}', emoji=EMOJI['file'], padding=padding)
            report_message(client, entity, msg, llm_url, llm_model, report_tree, interactive, all_interactive, stats, padding=padding)
        except (LLMRequestError, LLMResponseParseError, LLMUnexpectedStructureError) as e:
            LOG.error(str(e), EMOJI['error'], padding=padding)
            stats['errors'] += 1
            continue
        except TelegramUtilsReportSkippedByUser:
            LOG.info(f"Skipped by user — message {msg.id}", emoji=EMOJI['skip'], padding=padding)
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

    if args.md:  # and total_reported: (removed: better update files with 0 than re-process legit files unknowingly)
        LOG.info('Generating Markdown report...')
        LOG.info('```')
        LOG.output(f"{AI_REPORT_FIELD}:")
        LOG.output(f"- {f'`{AI_REPORT_FIELD_NAME}`, ' if AI_REPORT_FIELD_NAME else ''}`{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
        LOG.output(f"\t- account: `{args.user[0].upper()}`")
        LOG.output(f"\t- analyzed: `{stats['analyzed']}`")
        LOG.output(f"\t- reported: `{total_reported}`")
        LOG.output("\t- tags: { " + " ; ".join(f"`{tag}`" for tag in stats['tags']) + " }")
        LOG.info('```')

    if args.update_file:  # and total_reported: (removed: better update files with 0 than re-process legit files unknowingly)
        append_report_to_md(
            args.update_file,
            account=args.user[0].upper(),
            analyzed=stats['analyzed'],
            reported=total_reported,
            tags=stats['tags']
        )

    LOG.output(UI_HORIZONTAL_LINE, padding=padding)
    LOG.output(f"Summary for {entity_title!r} — {entity.id}",        emoji=EMOJI['stats'], padding=padding)
    LOG.output(UI_HORIZONTAL_LINE, padding=padding)
    LOG.output(f"Entity           : {entity.id:<16}",                emoji=EMOJI['id'], padding=padding)
    LOG.output(f"Fetched          : {len(messages):.>5}",            emoji=EMOJI['info'], padding=padding)
    LOG.output(f"Analyzed         : {stats['analyzed']:.>5}",        emoji=EMOJI['analyzed'], padding=padding)
    LOG.output(f"LLM time         : {mean(stats['llm_time']):>5.3} s/msg", emoji=EMOJI['time'], padding=padding)
    if stats['tags']:
        LOG.output(
            f"Used tags\n   " + "\n   ".join(
                f"{'' if tag.startswith('#') else '#'}{tag:16}: {count:.>5}" for tag, count in stats['tags'].most_common()
            ),
            emoji=EMOJI['tag'],
            padding=padding
        )
    LOG.output(f"Reported (auto)  : {stats['reported_auto']:.>5}",   emoji=EMOJI['report'], padding=padding)
    LOG.output(f"Reported (manual): {stats['reported_manual']:.>5}", emoji=EMOJI['success'], padding=padding)
    LOG.output(f"Skipped (manual) : {stats['skipped_manual']:.>5}",  emoji=EMOJI['skip'], padding=padding)
    LOG.output(f"Logged only      : {stats['log_only']:.>5}",        emoji=EMOJI['log'], padding=padding)
    LOG.output(f"Harmless         : {stats['harmless']:.>5}",        emoji=EMOJI['harmless'], padding=padding)
    LOG.output(f"Low confidence   : {stats['low_confidence']:.>5}",  emoji=EMOJI['unknown'], padding=padding)
    LOG.output(f"Errors           : {stats['errors']:.>5}",          emoji=EMOJI['error'], padding=padding)
    LOG.output(UI_HORIZONTAL_LINE, padding=padding)
    LOG.output(f"Total reported   : {total_reported:.>5}",           emoji=EMOJI['success'], padding=padding)
    LOG.output(UI_HORIZONTAL_LINE, padding=padding)

    return stats


def mass_report(client, args, md_files, skip_time_seconds):
    stats = make_stats('mass_report')

    llm_params = resolve_llm_params(args)

    progress_bar = create_progress_bar(LOG, md_files, "Reporting")
    progress_bar['bar'].start()

    skip_fields = [
        {
            "field_name": AI_REPORT_FIELD,
            "skip_reason": SkipReasonType.FIELD_TIME,
            "check_value": skip_time_seconds
        },
        {
            "field_name": AI_LEGIT_FIELD,
            "skip_reason": SkipReasonType.FIELD_VALUE_INV,
            "check_value": False
        }
    ]

    try:
        for item in iter_md_entities(args, md_files, stats, skip_fields=skip_fields, progress_bar=progress_bar):
            md_file = item['md_file']
            try:
                args.update_file = md_file
                t_start = time()
                run_stats = run_report(client, args, identifier=item['expected_id'] or item['identifiers'][0], llm=llm_params, padding=2)
                duration = time() - t_start
                LOG.info(f"Done in {duration:.1f}s", padding=2, emoji=EMOJI['time'])

                stats['processed'] += 1
                stats['analyzed'] += run_stats.get('analyzed', 0)
                stats['reported_auto'] += run_stats.get('reported_auto', 0)
                stats['reported_manual'] += run_stats.get('reported_manual', 0)
                stats['skipped_manual'] += run_stats.get('skipped_manual', 0)
                stats['log_only'] += run_stats.get('log_only', 0)
                stats['harmless'] += run_stats.get('harmless', 0)
                stats['low_confidence'] += run_stats.get('low_confidence', 0)
                stats['errors'] += run_stats.get('errors', 0)
                stats['tags'] += run_stats.get('tags', Counter())
                stats['llm_time'].append(mean(run_stats.get('llm_time', [])))

            except ReportLLMError as e:
                stats['llm_error'] += 1
                LOG.error(f"LLM error: {e}", EMOJI['error'])
            except ReportError as e:
                if isinstance(e, ReportErrorEntityResolution): stats['report_error_resolution'] += 1
                elif isinstance(e, ReportErrorFetch): stats['report_error_fetch'] += 1
                elif isinstance(e, ReportErrorFilter): stats['report_error_filter'] += 1
                elif isinstance(e, ReportErrorFloodWait): stats['report_error_flood'] += 1
                else: stats['report_error'] += 1
                LOG.error(f"Report error: {e}", EMOJI['error'])
            except KeyboardInterrupt:
                stats['skipped'] += 1
                stats['skipped_user'] += 1
                LOG.info('CTRL+C detected. Entity skipped by user. Press CTRL+C again to quit.', emoji=EMOJI['skip'])
                try:
                    sleep(2)
                except KeyboardInterrupt:
                    raise
                continue

    finally:
        progress_bar['bar'].stop()
        LOG.set_progress(None)
        LOG.throttle = None
        print_stats_report(stats)
