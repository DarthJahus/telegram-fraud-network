import re
from collections import Counter

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

REGEX_INVITE_LINK_RAW = re.compile(r"^https?://(t\.me|telegram\.me|telegram\.dog)/\+[a-zA-Z0-9_-]{10,32}$")

REGEX_USERNAME_RAW = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$')

REGEX_INVITE_HASH = re.compile(r'^\+[a-zA-Z0-9_-]{10,32}$')

# ============================================
# Variables & other constants
# ============================================
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep

UI_HORIZONTAL_LINE = f"{60 * "—"}"

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
    "log":         "📰",
    "list_bugs":   ["🦋", "🦟", "🐛", "🐜", "🐝", "🐞", "🦗"],
    'llm':         "🤖",
    'harmless':    "💚",
    'report':      "📤",
    'analyzed':    "🔍",
    'tag':         "🎫",
    'connection':  "📶"
}
STATS_INIT_REPORT = {
    'analyzed':        0,
    'reported_auto':   0,
    'reported_manual': 0,
    'skipped_manual':  0,
    'skipped_error':   0,
    'log_only':        0,
    'harmless':        0,
    'low_confidence':  0,
    'errors':          0,
    'tags':            Counter()
}
STATS_INIT_MASS_REPORT = {
        'processed': 0,
        'skipped': 0,
        'skipped_type': 0,
        'skipped_time': 0,
        'skipped_status': 0,
        'skipped_error': 0,
        'skipped_field': 0,
        'skipped_no_identifier': 0,
        'analyzed': 0,
        'reported_auto': 0,
        'reported_manual': 0,
        'skipped_manual': 0,
        'log_only': 0,
        'harmless': 0,
        'low_confidence': 0,
        'errors': 0,
        'llm_error': 0,
        'report_error': 0,
        'tags': Counter()
    }
STATS_INIT_CHECKER = {
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
    'skipped_error': 0,
    'error': 0,
    'ignored': 0,
    'method': {
        'id': 0,
        'username': 0,
        'invite': 0
    }
}
