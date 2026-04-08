import re
from collections import Counter

# ============================================
# CONFIG
# ============================================
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep
UI_HORIZONTAL_LINE = f"{60 * "—"}"
AI_REPORT_FIELD = "reports"
AI_REPORT_FIELD_NAME = 'ai'
AI_LEGIT_FIELD = "legit"
THROTTLE_TIME = 0.2

# ============================================
# CONSTANTS
# ============================================

MDML_BOOL_TRUE_SET = {"true", "yes", "1"}
MDML_BOOL_FALSE_SET = {"false", "no", "0", "unknown"}

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

STATS_INIT = {
    'report': [
        'analyzed', 'reported_auto', 'reported_manual', 'skipped_manual',
        'skipped_error', 'log_only', 'harmless', 'low_confidence', 'errors'
    ],
    'mass_report': [
        'processed', 'skipped', 'skipped_type', 'skipped_time', 'skipped_status',
        'skipped_error', 'skipped_field', 'skipped_user', 'skipped_no_identifier',
        'analyzed', 'reported_auto', 'reported_manual', 'skipped_manual',
        'log_only', 'harmless', 'low_confidence', 'errors', 'llm_error',
        'report_error', "report_error_resolution", "report_error_fetch", "report_error_filter", "report_error_flood"
    ],
    'check': [
        'total', 'active', 'banned', 'deleted', 'id_mismatch', 'unknown',
        'skipped', 'skipped_time', 'skipped_status', 'skipped_no_identifier',
        'skipped_type', 'skipped_error', 'skipped_user', 'error', 'ignored'
    ],
}

STATS_INIT_EXTRA = {
    'report':      lambda: {'tags': Counter()},
    'mass_report': lambda: {'tags': Counter()},
    'check':       lambda: {'method': {'id': 0, 'username': 0, 'invite': 0}},
}


def make_stats(purpose):
    return {k: 0 for k in STATS_INIT[purpose]} | STATS_INIT_EXTRA[purpose]()

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
REGEX_STATUS_ENTRY_FULL = re.compile(pattern=r'^\s*-\s*`([^`]+)`\s*,\s*`(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})`', flags=re.MULTILINE)
REGEX_STATUS_BLOCK_PATTERN = re.compile(pattern=r'^\s*-\s*`[^`]+`,\s*`\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}`', flags=re.MULTILINE)
REGEX_STATUS_SUB_ITEM = re.compile(pattern=r'^\s{2,}-\s')
REGEX_NEXT_FIELD = re.compile(pattern=r'^[a-z_]+:\s', flags=re.MULTILINE)
REGEX_INVITE_LINK_RAW = re.compile(r"^https?://(t\.me|telegram\.me|telegram\.dog)/\+[a-zA-Z0-9_-]{10,32}$")
REGEX_USERNAME_RAW = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$')
REGEX_INVITE_HASH = re.compile(r'^\+[a-zA-Z0-9_-]{10,32}$')
