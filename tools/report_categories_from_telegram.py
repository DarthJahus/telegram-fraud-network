"""
Usage:
    --user username --peer @username --message-id 12345
"""

import argparse
import json
from telethon.sync import TelegramClient
from telegram_checker.config.api import API_ID, API_HASH
from telegram_checker.telegram_utils.report import get_categories_from_telegram


def main():
    parser = argparse.ArgumentParser(description='Explore Telegram report option tree')
    parser.add_argument('--user',       default='default')
    parser.add_argument('--peer',       required=True,  help='Channel/group username or ID')
    parser.add_argument('--message-id', required=True,  type=int)
    parser.add_argument('--out',        default=None,   help='Optional JSON output file')
    args = parser.parse_args()

    with TelegramClient(f'.secret/{args.user}.session', API_ID, API_HASH) as client:
        peer = client.get_entity(args.peer)
        tree = get_categories_from_telegram(client, peer, args.message_id)

    print("\n\nFull tree (JSON):")
    print(json.dumps(tree, indent=2, ensure_ascii=False))

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(tree, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to {args.out}")


if __name__ == '__main__':
    main()
