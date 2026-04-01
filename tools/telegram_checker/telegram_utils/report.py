from telegram_checker.llm_utils.constants import SKIP_LV1, SKIP_LV2, REPORT_TREE_DEFAULT
import json
from pathlib import Path
from inspect import currentframe
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.helpers import print_debug, sleep_with_progress
from telegram_checker.utils.logger import get_logger
from telethon.errors import InviteHashExpiredError, InviteHashInvalidError, FloodWaitError
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
from telegram_checker.telegram_utils.exceptions import TelegramUtilsReportError
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import ReportResultChooseOption, ReportResultAddComment, ReportResultReported
from telegram_checker.telegram_utils.constants import REPORT_TREE_PATH

LOG = get_logger()


def load_report_tree(default=REPORT_TREE_DEFAULT) -> dict[str, list]:
    user_path = REPORT_TREE_PATH
    if user_path.exists():
        with open(user_path, encoding='utf-8') as f:
            raw = json.load(f)
    else:
        raw = default
    tree = {
        lv1: [lv2 for lv2 in subs if lv2.lower() not in SKIP_LV2]
        for lv1, subs in raw.items()
        if lv1.lower() not in SKIP_LV1
    }
    tree["Harmless"] = ["No report"]
    return tree


def get_report_tree_str():
    return json.dumps(load_report_tree(), ensure_ascii=False, indent=2)


def resolve_entity(client, identifier: str):
    """
    Resolve a Telegram entity from an identifier (ID, invite, username).
    Returns the entity object, or raises ValueError if resolution fails.
    Mirrors the resolution logic of entity_fetcher.fetch_entity_info.
    """
    if isinstance(identifier, int):
        identifier = str(identifier)

    if identifier.lstrip('+').isdecimal() or (identifier.lstrip('-').isdecimal()):
        numeric_id = int(identifier)
        LOG.info(f"Resolving entity by ID: {numeric_id}", EMOJI['id'])
        for peer_type in (PeerChannel, PeerUser, PeerChat):
            try:
                return client.get_entity(peer_type(numeric_id))
            except Exception as e:
                # ToDo: add exceptions like ValueError and invite not valide,
                #       then use print_debug() with the right error message.
                pass  # print_debug(e, currentframe().f_code.co_name)
        # Last resort
        return client.get_entity(numeric_id)

    elif '+' in identifier:
        invite_hash = identifier.split('+')[-1]
        LOG.info(f"Resolving entity by invite: {identifier}", EMOJI['invite'])
        try:
            return client.get_entity(f'https://t.me/+{invite_hash}')
        except ValueError as e:
            if "Cannot get entity from a channel" in str(e):
                # Not a member — we cannot fetch messages, report is impossible
                raise ValueError(
                    f"You are not a member of this entity. "
                    f"Join the channel/group before running the script."
                ) from e
            raise
        except InviteHashExpiredError:
            raise ValueError("Invite link has expired.") from None
        except InviteHashInvalidError:
            raise ValueError("Invite link is invalid.") from None

    else:
        if not identifier.startswith('@'):
            identifier = '@' + identifier
        LOG.info(f"Resolving entity by username: {identifier}", EMOJI['handle'])
        return client.get_entity(identifier)


def send_report(client, entity, message_id: int, lv1: str, lv2: str, report_text: str, padding=0) -> bool:
    """
    Send a single-message report to Telegram.

    The MTProto report flow navigates a tree of options:
      1. option=b''     → ReportResultChooseOption (top-level reasons)
      2. option=chosen  → ReportResultChooseOption (sub-options) | ReportResultAddComment | ReportResultReported
      3. Loop until ReportResultAddComment or ReportResultReported
      4. If AddComment: send final request with report_text as message

    Returns True on success, raises TelegramUtilsReportError on unexpected Telegram responses.
    # ToDo: Return matched report options to use in statistics
    """
    try:
        result = client(ReportRequest(peer=entity, id=[message_id], option=b'', message=''))

        if isinstance(result, ReportResultReported):
            LOG.info(f"Reported message {message_id}", emoji=EMOJI['success'])
            return True

        if isinstance(result, ReportResultChooseOption):
            if not result.options:
                LOG.error(f"No report options returned for message {message_id}", EMOJI['error'])
                return False

            from telegram_checker.llm_utils.interface import choose_option
            from telethon.tl.types import ReportResultAddComment

            current_result = result

            # Navigate the option tree until Telegram is satisfied
            depth = 0
            while isinstance(current_result, ReportResultChooseOption):
                if not current_result.options:
                    LOG.error(f"Empty options list for message {message_id}", EMOJI['error'])
                    return False

                LOG.debug(f"Options: {[f'{i}:{opt.text!r}' for i, opt in enumerate(current_result.options)]}")
                label = lv2 if depth > 0 else lv1
                chosen_index, choose_method = choose_option(label, current_result.options)
                LOG.info(choose_method, padding=padding, emoji=EMOJI['tag'])
                chosen = current_result.options[chosen_index].option

                current_result = client(ReportRequest(
                    peer=entity,
                    id=[message_id],
                    option=chosen,
                    message='',
                ))

                depth += 1

            if isinstance(current_result, ReportResultReported):
                LOG.info(f"Reported message {message_id} (no comment)", emoji=EMOJI['success'], padding=padding)
                return True

            if isinstance(current_result, ReportResultAddComment):
                final_result = client(ReportRequest(
                    peer=entity,
                    id=[message_id],
                    option=current_result.option,
                    message=report_text,
                ))
                if isinstance(final_result, (ReportResultReported, ReportResultAddComment)):
                    LOG.info(f"Reported message {message_id}", emoji=EMOJI['success'], padding=padding)
                    return True
                raise TelegramUtilsReportError(
                    f"Unexpected result after comment submission for message {message_id}: {type(final_result).__name__}"
                )

            raise TelegramUtilsReportError(
                f"Unexpected result after option navigation for message {message_id}: {type(current_result).__name__}"
            )

        LOG.error(f"Unexpected report result type for message {message_id}: {type(result)}", EMOJI['error'])
        return False

    except TelegramUtilsReportError:
        raise

    except FloodWaitError as e:
        sleep_with_progress(e.seconds, dest=LOG.error, emoji=EMOJI['pause'], padding=padding)
        return send_report(client, entity, message_id, lv1, lv2, report_text)

    except Exception as e:
        LOG.error(f"Failed to report message {message_id}: {e}", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)
        return False


def save_report_tree(tree: dict, path) -> None:
    Path(path).write_text(json.dumps(tree, indent=2, ensure_ascii=False), encoding='utf-8')
    LOG.info(f"Report tree saved to {path}", EMOJI['success'])


def get_categories_from_telegram(client, peer, message_id: int) -> dict:
    """
    Explores Telegram's report option tree for a given message.
    Sends a report with each LV1 option and captures the LV2 sub-options,
    WITHOUT completing the report (stops before the comment step).

    :param client: connected Telethon client instance
    :param peer: channel or group the test message is in (any existing message would work)
    :param message_id: message to use (any existing message would work)
    :return: Telegram report tree as dict
    """
    tree = {}

    # LV0 : get top-level options
    result = client(ReportRequest(peer=peer, id=[message_id], option=b'', message=''))

    if not isinstance(result, ReportResultChooseOption):
        LOG.error(f"Unexpected initial result: {type(result).__name__}")
        return tree

    lv1_options = result.options
    LOG.info(f"\nLV1 ({len(lv1_options)} options):", emoji=EMOJI['info'])
    for i, opt in enumerate(lv1_options):
        LOG.info(f"  {i}: {opt.text!r} → {opt.option}", emoji=EMOJI['info'])

    # For each LV1 option, probe LV2
    for opt in lv1_options:
        result2 = client(ReportRequest(peer=peer, id=[message_id], option=opt.option, message=''))

        if isinstance(result2, ReportResultChooseOption):
            sub_options = [o.text for o in result2.options]
            LOG.info(f"\n  LV2 for {opt.text!r}:", emoji=EMOJI['info'])
            for i, sub in enumerate(result2.options):
                LOG.info(f"    {i}: {sub.text!r} → {sub.option}", emoji=EMOJI['info'])
            tree[opt.text] = sub_options

        elif isinstance(result2, ReportResultAddComment):
            LOG.info(f"\n  LV2 for {opt.text!r}: → AddComment (no sub-options, optional={result2.optional})", emoji=EMOJI['info'])
            tree[opt.text] = []

        elif isinstance(result2, ReportResultReported):
            # Shouldn't happen mid-exploration but handle it
            LOG.error(f"\n  LV2 for {opt.text!r}: → Reported immediately")
            tree[opt.text] = []

    return tree
