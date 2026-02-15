import re

# ============================================
# REGEX
# ============================================

REGEX_ID = re.compile(pattern=r'^id:\s*`?(\d+)`?', flags=re.MULTILINE)
REGEX_TYPE = re.compile(pattern=r'^type:\s*(\w+)', flags=re.MULTILINE)

REGEX_USERNAME_INLINE = re.compile(pattern=r'^username:\s*`?@([a-zA-Z0-9_]{5,32})`?', flags=re.MULTILINE)
REGEX_USERNAME_BLOCK_START = re.compile(pattern=r'^username:\s*$', flags=re.MULTILINE)
REGEX_USERNAME_ENTRY = re.compile(pattern=r'-\s*`@([a-zA-Z0-9_]{5,32})`')

REGEX_INVITE_INLINE = re.compile(pattern=r'^invite:\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', flags=re.MULTILINE)
REGEX_INVITE_BLOCK_START = re.compile(pattern=r'^invite:\s*$', flags=re.MULTILINE)
REGEX_INVITE_LINK = re.compile(pattern=r'-\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)')

REGEX_STATUS_BLOCK_START = re.compile(pattern=r'^status:\s*$', flags=re.MULTILINE)
REGEX_STATUS_ENTRY_FULL = re.compile(pattern=r'^\s*-\s*`([^`]+)`\s*,\s*`(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})`',
                                     flags=re.MULTILINE)
REGEX_STATUS_BLOCK_PATTERN = re.compile(pattern=r'^\s*-\s*`[^`]+`,\s*`\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}`',
                                        flags=re.MULTILINE)
REGEX_STATUS_SUB_ITEM = re.compile(pattern=r'^\s{2,}-\s')

REGEX_NEXT_FIELD = re.compile(pattern=r'^[a-z_]+:\s', flags=re.MULTILINE)

# ============================================
# Variables & other constants
# ============================================
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep

UI_HORIZONTAL_LINE = f"\n{60 * "•"}\n"

EMOJI = {
    'active':      "🔥",
    'banned':      "🔨",
    'deleted':     "🗑️",
    'id_mismatch': "🧩",
    'unknown':     "❓",
    'error':       "❌",
    'skip':        "⏭️",
    'id':          "🆔",
    'time':        "⏰",
    'no_emoji':    "🚫",
    'ignored':     "🙈",
    'folder':      "📂",
    'file':        "🧻",
    'dry-run':     "👓",
    'connecting':  "📡",
    'fallback':    "📨",
    'handle':      "👤",
    'stats':       "📊",
    'success':     "✅",
    'warning':     "🚨",
    'info':        "ℹ️",
    'saved':       "💾",
    'reason':      "📋",
    'text':        "💬",
    'methods':     "💊",
    'invite':      "⏳",
    'change':      "🔄",
    "pause":       "⏸️",
    "log":         "📰"
}

STATS_INIT = {
    'total': 0,
    'active': 0,
    'banned': 0,
    'deleted': 0,
    'id_mismatch': 0,
    'unknown': 0,
    'skipped': 0,
    'skipped_time': 0,
    'skipped_status': 0,
    'skipped_no_identifier': 0,
    'skipped_type': 0,
    'error': 0,
    'ignored': 0,
    'method': {
        'id': 0,
        'username': 0,
        'invite': 0
    }
}
