from pathlib import Path
from telegram_checker.config.constants import EMOJI, API_ID, API_HASH
from telethon.sync import TelegramClient
from telegram_checker.utils.logger import get_logger
LOG = get_logger()


def connect_to_telegram(user):
    # Load phone number for user
    session_dir = Path('.secret')
    session_dir.mkdir(exist_ok=True)
    mobile_file = session_dir / f'{user}.mobile'

    if not mobile_file.exists():
        LOG.error("Mobile file not found: {mobile_file}", EMOJI["error"])
        LOG.info(f"  Create it with:")
        LOG.info(f"    echo '+1234567890' > {mobile_file}")
        return

    phone = mobile_file.read_text(encoding='utf-8').strip()

    # Connect to Telegram
    session_file = session_dir / user
    LOG.info(f"User: {user}", EMOJI["handle"])
    LOG.info("Connecting to Telegram...", EMOJI["connecting"])
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    client.start(phone=phone)
    LOG.info("Connected!\n", EMOJI["success"])
    return client
