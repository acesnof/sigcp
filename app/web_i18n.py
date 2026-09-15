"""Translations for web presentation; stored values are never rewritten."""

import json
import re
import sqlite3
from pathlib import Path

from app.supabase_store import SupabaseUnavailable


ENGLISH = json.loads(
    (Path(__file__).parent / "translations" / "en.json").read_text(encoding="utf-8")
)


def language():
    from app.i18n import get_language
    try:
        return get_language()
    except (sqlite3.Error, SupabaseUnavailable):
        # Startup and database error pages must remain usable without a database.
        return "pt"


def translate(source, lang=None):
    if not isinstance(source, str) or (language() if lang is None else lang) != "en":
        return source
    if source in ENGLISH:
        return ENGLISH[source]
    for pattern, target in MESSAGE_PATTERNS:
        match = pattern.fullmatch(source)
        if match:
            return re.sub(r"\{(\d+)\}", lambda item: match.group(int(item[1]) + 1), target)
    return source


MESSAGE_PATTERNS = [
    (re.compile(re.sub(r"\\\{\d+\\\}", "(.*?)", re.escape(source)), re.DOTALL), target)
    for source, target in ENGLISH.items()
    if re.search(r"\{\d+\}", source)
]


def translate_messages(payload):
    """Localize explicit message fields, leaving business data and audit content intact."""
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    for key in ("message", "error", "titulo", "mensagem"):
        if isinstance(result.get(key), str):
            result[key] = translate(result[key])
    for key in ("errors", "warnings"):
        if isinstance(result.get(key), list):
            result[key] = [translate(item) if isinstance(item, str) else translate_messages(item) for item in result[key]]
    # Only application-owned message envelopes are traversed, never arbitrary user data.
    for key in ("backup",):
        if isinstance(result.get(key), dict):
            result[key] = translate_messages(result[key])
    return result
