from pathlib import Path
from sys import executable
from telegram_checker.config.constants import EMOJI
from enum import Enum

REPORT_TREE_PATH = Path(executable).parent / 'report_tree.json'


class JoinResults(Enum):
    JOINED = ("Joined successfully", EMOJI["success"])
    ALREADY_MEMBER = ("Already a member", EMOJI["info"])
    ADDED = ("Contact added", EMOJI["handle"])
    REQUESTED = ("Requested to join", EMOJI["fallback"])
