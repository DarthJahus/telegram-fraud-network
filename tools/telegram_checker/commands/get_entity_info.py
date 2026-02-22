from inspect import currentframe

from telegram_checker.commands.exceptions import CommandsGetInfoError
from telegram_checker.config.constants import EMOJI
from telegram_checker.mdml_utils.mdml_formatter import format_entity_mdml
from telegram_checker.telegram_utils.entity_fetcher import fetch_entity_info
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger

LOG = get_logger()


def get_entity_info(client, identifier):
    """
    Main function to fetch and output entity information as MDML.
    """
    try:
        info = fetch_entity_info(client, identifier)
        if info:
            mdml = format_entity_mdml(info)
            return mdml
        else:
            LOG.error(f"Failed to fetch entity information.", EMOJI['error'])
    except Exception as e:
        LOG.error(f"Error generating MDML: {e}", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)

    raise CommandsGetInfoError('Failed to get entity info.')
