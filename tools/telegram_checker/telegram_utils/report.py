from inspect import currentframe
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger
from telethon.errors import InviteHashExpiredError, InviteHashInvalidError
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
from telegram_checker.telegram_utils.exceptions import TelegramReportError

LOG = get_logger()


def resolve_entity(client, identifier: str):
    """
    Resolve a Telegram entity from an identifier (ID, invite, username).
    Returns the entity object, or raises ValueError if resolution fails.
    Mirrors the resolution logic of entity_fetcher.fetch_entity_info.
    """
    if identifier.lstrip('+').isdecimal() or (identifier.lstrip('-').isdecimal()):
        numeric_id = int(identifier)
        LOG.info(f"Resolving entity by ID: {numeric_id}", EMOJI['id'])
        for peer_type in (PeerChannel, PeerUser, PeerChat):
            try:
                return client.get_entity(peer_type(numeric_id))
            except Exception as e:
                print_debug(e, currentframe().f_code.co_name)
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
                    f"Join the channel/group before running --report."
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


def send_report(client, entity, message_id: int, category: str, report_text: str) -> bool:
    """
    Send a single-message report to Telegram.

    The MTProto report flow navigates a tree of options:
      1. option=b''     → ReportResultChooseOption (top-level reasons)
      2. option=chosen  → ReportResultChooseOption (sub-options) | ReportResultAddComment | ReportResultReported
      3. Loop until ReportResultAddComment or ReportResultReported
      4. If AddComment: send final request with report_text as message

    Returns True on success, raises TelegramReportError on unexpected Telegram responses.
    """
    from telethon.tl.functions.messages import ReportRequest
    from telethon.tl.types import ReportResultReported, ReportResultChooseOption

    try:
        result = client(ReportRequest(
            peer=entity,
            id=[message_id],
            option=b'',
            message='',
        ))

        if isinstance(result, ReportResultReported):
            LOG.output(f"Reported message {message_id}", emoji=EMOJI['success'])
            return True

        if isinstance(result, ReportResultChooseOption):
            if not result.options:
                LOG.error(f"No report options returned for message {message_id}", EMOJI['error'])
                return False

            from telegram_checker.llm_utils.interface import choose_option
            from telethon.tl.types import ReportResultAddComment

            current_result = result
            chosen = None

            # Navigate the option tree until Telegram is satisfied
            while isinstance(current_result, ReportResultChooseOption):
                if not current_result.options:
                    LOG.error(f"Empty options list for message {message_id}", EMOJI['error'])
                    return False

                LOG.debug("Options: {[f'{i}:{opt.text!r}' for i, opt in enumerate(current_result.options)]}")
                chosen_index = choose_option(category, current_result.options)
                chosen = current_result.options[chosen_index].option
                LOG.info(f"Matched option {chosen_index}: {current_result.options[chosen_index].text!r}", EMOJI['info'])

                current_result = client(ReportRequest(
                    peer=entity,
                    id=[message_id],
                    option=chosen,
                    message='',
                ))

            if isinstance(current_result, ReportResultReported):
                LOG.output(f"Reported message {message_id} (no comment)", emoji=EMOJI['success'])
                return True

            if isinstance(current_result, ReportResultAddComment):
                final_result = client(ReportRequest(
                    peer=entity,
                    id=[message_id],
                    option=current_result.option,
                    message=report_text,
                ))
                if isinstance(final_result, (ReportResultReported, ReportResultAddComment)):
                    LOG.output(f"Reported message {message_id}", emoji=EMOJI['success'])
                    return True
                raise TelegramReportError(
                    f"Unexpected result after comment submission for message {message_id}: {type(final_result).__name__}"
                )

            raise TelegramReportError(
                f"Unexpected result after option navigation for message {message_id}: {type(current_result).__name__}"
            )

        LOG.error(f"Unexpected report result type for message {message_id}: {type(result)}", EMOJI['error'])
        return False

    except TelegramReportError:
        raise

    except Exception as e:
        import traceback
        traceback.print_exc()
        LOG.error(f"Failed to report message {message_id}: {e}", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)
        return False
