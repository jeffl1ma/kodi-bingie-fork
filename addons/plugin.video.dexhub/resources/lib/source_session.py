# -*- coding: utf-8 -*-
"""Unified short-lived source result sessions.

The UI and source-switch paths share this module so switching never re-runs
provider searches merely because a window property was cleared.
"""
from . import cache_store

_BUCKET = 'stream_session'
_TTL_HOURS = 6

def create(entries, done=False, version=1):
    return cache_store.put(_BUCKET, {
        'entries': list(entries or []),
        'done': bool(done),
        'version': int(version or 1),
    }, ttl_hours=_TTL_HOURS)

def update(session_key, payload):
    if not session_key:
        return False
    return cache_store.update(_BUCKET, session_key, dict(payload or {}))

def get(session_key, default=None):
    if not session_key:
        return default
    try:
        value = cache_store.get(_BUCKET, session_key)
    except Exception:
        return default
    return value if value is not None else default
