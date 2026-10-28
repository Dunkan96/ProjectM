# -*- coding: utf-8 -*-
from __future__ import annotations

"""
MonikaBrain Streamer.bot normalizer fix v4.

What it does:
- backs up streamerbot_event_normalizer.py
- replaces only streamerbot_event_normalizer.py
- supports flat Streamer.bot Twitch.ChatMessage payloads
- supports nested Streamer.bot payloads where data["message"] is a dict
- avoids treating displayName/login/name as chat text
- py_compile + smoke tests normalizer + AttentionStreamAdapter with temp SQLite DB
- optionally removes old junk attention rows where text == user_name, bucket == ignored, score == 0
- does NOT modify console_chat.py
- does NOT modify attention_safety_guard.py
- does NOT modify attention_stream_adapter.py
- does NOT modify streamerbot_attention_bridge.py
"""

import json
import py_compile
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NORMALIZER = ROOT / "streamerbot_event_normalizer.py"
BRIDGE = ROOT / "streamerbot_attention_bridge.py"
ADAPTER = ROOT / "attention_stream_adapter.py"
SAFETY = ROOT / "attention_safety_guard.py"

NORMALIZER_CODE = r