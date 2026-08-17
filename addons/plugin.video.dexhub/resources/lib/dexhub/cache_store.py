# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import threading
import time
import uuid

from .common import profile_path

DB_PATH = os.path.join(profile_path(), 'cache.db')

_MEM = {}
_MEM_ORDER = []
_MEM_MAX = 256
_LOCK = threading.RLock()
_DB_READY = False


def _mem_put(kind, cache_key, payload):
    key = '%s:%s' % (kind or '', cache_key or '')
    with _LOCK:
        if key not in _MEM:
            _MEM_ORDER.append(key)
        _MEM[key] = payload
        while len(_MEM_ORDER) > _MEM_MAX:
            old = _MEM_ORDER.pop(0)
            _MEM.pop(old, None)


def _mem_get(kind, cache_key):
    with _LOCK:
        return _MEM.get('%s:%s' % (kind or '', cache_key or ''))


def _conn():
    global _DB_READY
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA busy_timeout=10000')
        conn.execute('PRAGMA temp_store=MEMORY')
    except Exception:
        pass
    if not _DB_READY:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_items (
                cache_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_kind_created ON cache_items(kind, created_at DESC)")
        conn.commit()
        _DB_READY = True
    return conn


def put(kind, payload, ttl_hours=24):
    now = int(time.time())
    key = uuid.uuid4().hex
    encoded = json.dumps(payload, ensure_ascii=False)
    cutoff = now - int(ttl_hours * 3600)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache_items(cache_key, kind, payload, created_at) VALUES(?,?,?,?)",
                (key, kind, encoded, now),
            )
            conn.execute("DELETE FROM cache_items WHERE created_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()
        _mem_put(kind, key, payload)
    return key


def get(kind, cache_key):
    cached = _mem_get(kind, cache_key)
    if cached is not None:
        return cached
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT payload FROM cache_items WHERE kind=? AND cache_key=?", (kind, cache_key)).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        payload = json.loads(row[0])
        _mem_put(kind, cache_key, payload)
        return payload
    except Exception:
        return None


def update(kind, cache_key, payload):
    if not cache_key:
        return None
    now = int(time.time())
    encoded = json.dumps(payload, ensure_ascii=False)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache_items(cache_key, kind, payload, created_at) VALUES(?,?,?,?)",
                (cache_key, kind, encoded, now),
            )
            conn.commit()
        finally:
            conn.close()
        _mem_put(kind, cache_key, payload)
    return cache_key


def clear_all(kind=None):
    with _LOCK:
        conn = _conn()
        try:
            if kind:
                conn.execute("DELETE FROM cache_items WHERE kind=?", (kind,))
            else:
                conn.execute("DELETE FROM cache_items")
            conn.commit()
        finally:
            conn.close()
        if kind:
            prefix = '%s:' % (kind or '')
            for key in list(_MEM.keys()):
                if key.startswith(prefix):
                    _MEM.pop(key, None)
            _MEM_ORDER[:] = [k for k in _MEM_ORDER if not k.startswith(prefix)]
        else:
            _MEM.clear()
            _MEM_ORDER[:] = []
