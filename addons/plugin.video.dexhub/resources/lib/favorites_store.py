# -*- coding: utf-8 -*-
"""Local favorites store.

Lightweight SQLite-backed favourites/watchlist for users who don't have Trakt
linked, AND a stable mirror cache for users who do (so the home-screen
"المفضلة" row stays instant even when Trakt is slow/offline).

Schema mirrors the Continue Watching shape so the same row-rendering code in
plugin.py can consume both.
"""
import os
import sqlite3
import time

from .dexhub.common import profile_path

DB_PATH = os.path.join(profile_path(), 'favorites.db')
_DB_READY = False

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS favorites (
    media_type TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    title TEXT,
    poster TEXT,
    background TEXT,
    clearlogo TEXT,
    year INTEGER,
    plot TEXT,
    source TEXT NOT NULL DEFAULT 'local',
    added_at INTEGER,
    PRIMARY KEY (media_type, canonical_id, source)
)
"""


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
    except Exception:
        pass
    return conn


def _table_sql(conn, name):
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row[0] if row and row[0] else ''
    except Exception:
        return ''


def _needs_migration(conn):
    sql = (_table_sql(conn, 'favorites') or '').lower().replace('\n', ' ')
    if not sql:
        return False
    return 'primary key (media_type, canonical_id, source)' not in sql


def _migrate_schema(conn):
    if not _needs_migration(conn):
        return
    conn.execute('ALTER TABLE favorites RENAME TO favorites_legacy')
    conn.execute(CREATE_SQL)
    conn.execute(
        """
        INSERT OR REPLACE INTO favorites (
            media_type, canonical_id, title, poster, background,
            clearlogo, year, plot, source, added_at
        )
        SELECT
            media_type,
            canonical_id,
            title,
            poster,
            background,
            clearlogo,
            year,
            plot,
            COALESCE(NULLIF(source, ''), 'local') AS source,
            added_at
        FROM favorites_legacy
        """
    )
    conn.execute('DROP TABLE favorites_legacy')


def _ensure_db():
    global _DB_READY
    if _DB_READY:
        return
    conn = _connect()
    try:
        if _table_sql(conn, 'favorites'):
            _migrate_schema(conn)
        else:
            conn.execute(CREATE_SQL)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fav_added ON favorites(added_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fav_source ON favorites(source)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fav_identity ON favorites(media_type, canonical_id)')
        conn.commit()
    finally:
        conn.close()
    _DB_READY = True


def add(media_type, canonical_id, title, poster='', background='', clearlogo='',
        year=0, plot='', source='local'):
    _ensure_db()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO favorites (media_type, canonical_id, title, poster, background,
                                   clearlogo, year, plot, source, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(media_type, canonical_id, source) DO UPDATE SET
                title=excluded.title,
                poster=CASE WHEN excluded.poster != '' THEN excluded.poster ELSE favorites.poster END,
                background=CASE WHEN excluded.background != '' THEN excluded.background ELSE favorites.background END,
                clearlogo=CASE WHEN excluded.clearlogo != '' THEN excluded.clearlogo ELSE favorites.clearlogo END,
                year=CASE WHEN excluded.year > 0 THEN excluded.year ELSE favorites.year END,
                plot=CASE WHEN excluded.plot != '' THEN excluded.plot ELSE favorites.plot END,
                added_at=excluded.added_at
            """,
            (media_type or 'movie', canonical_id or '', title or canonical_id or '',
             poster or '', background or '', clearlogo or '', int(year or 0),
             plot or '', source or 'local', int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def remove(media_type, canonical_id, source=None):
    _ensure_db()
    conn = _connect()
    try:
        if source:
            conn.execute(
                "DELETE FROM favorites WHERE media_type=? AND canonical_id=? AND source=?",
                (media_type or '', canonical_id or '', source or ''),
            )
        else:
            conn.execute(
                "DELETE FROM favorites WHERE media_type=? AND canonical_id=?",
                (media_type or '', canonical_id or ''),
            )
        conn.commit()
    finally:
        conn.close()


def is_favorite(media_type, canonical_id):
    _ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE media_type=? AND canonical_id=? LIMIT 1",
            (media_type or '', canonical_id or ''),
        ).fetchone()
    finally:
        conn.close()
    return bool(row)




def favorite_keys():
    _ensure_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT media_type, canonical_id FROM favorites GROUP BY media_type, canonical_id"
        ).fetchall()
    finally:
        conn.close()
    return set((str(r[0] or ''), str(r[1] or '')) for r in rows or [])

def list_favorites(limit=200, source=None):
    _ensure_db()
    conn = _connect()
    try:
        if source:
            rows = conn.execute(
                """
                SELECT media_type, canonical_id, title, poster, background, clearlogo,
                       year, plot, source, added_at
                FROM favorites WHERE source=?
                ORDER BY added_at DESC LIMIT ?
                """,
                (source, limit),
            ).fetchall()
            return [{
                'media_type': row[0], 'canonical_id': row[1], 'title': row[2],
                'poster': row[3], 'background': row[4], 'clearlogo': row[5],
                'year': row[6], 'plot': row[7], 'source': row[8],
                'sources': [row[8]], 'added_at': row[9],
            } for row in rows]

        rows = conn.execute(
            """
            SELECT media_type, canonical_id, title, poster, background, clearlogo,
                   year, plot, source, added_at
            FROM favorites
            ORDER BY added_at DESC, CASE WHEN source='local' THEN 0 ELSE 1 END
            """
        ).fetchall()
    finally:
        conn.close()

    out = []
    seen = {}
    for row in rows:
        media_type, canonical_id = row[0], row[1]
        key = (media_type, canonical_id)
        source_name = row[8] or 'local'
        payload = {
            'media_type': media_type,
            'canonical_id': canonical_id,
            'title': row[2],
            'poster': row[3],
            'background': row[4],
            'clearlogo': row[5],
            'year': row[6],
            'plot': row[7],
            'source': source_name,
            'sources': [source_name],
            'added_at': row[9],
        }
        existing = seen.get(key)
        if not existing:
            seen[key] = payload
            out.append(payload)
            continue
        sources = set(existing.get('sources') or [])
        sources.add(source_name)
        existing['sources'] = sorted(sources)
        if source_name != existing.get('source'):
            existing['source'] = 'mixed'
        for field in ('title', 'poster', 'background', 'clearlogo', 'year', 'plot'):
            if not existing.get(field) and payload.get(field):
                existing[field] = payload.get(field)
        existing['added_at'] = max(int(existing.get('added_at') or 0), int(payload.get('added_at') or 0))

    out.sort(key=lambda row: int(row.get('added_at') or 0), reverse=True)
    if limit:
        return out[: max(0, int(limit or 0))]
    return out


def replace_trakt_mirror(rows):
    """Replace ALL trakt-sourced rows with the latest snapshot from Trakt.

    `rows` is a list of dicts with keys matching `add()` parameters. Local
    rows are untouched; we only rewrite the trakt mirror so disabling Trakt
    or removing items from your Trakt watchlist is reflected in Dex Hub.
    """
    _ensure_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM favorites WHERE source='trakt'")
        for row in rows or []:
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO favorites (media_type, canonical_id, title,
                        poster, background, clearlogo, year, plot, source, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'trakt', ?)
                    """,
                    (
                        row.get('media_type') or 'movie',
                        row.get('canonical_id') or '',
                        row.get('title') or row.get('canonical_id') or '',
                        row.get('poster') or '',
                        row.get('background') or '',
                        row.get('clearlogo') or '',
                        int(row.get('year') or 0),
                        row.get('plot') or '',
                        int(row.get('added_at') or time.time()),
                    ),
                )
            except Exception:
                continue
        conn.commit()
    finally:
        conn.close()


def count(source=None):
    _ensure_db()
    conn = _connect()
    try:
        if source:
            n = conn.execute(
                'SELECT COUNT(*) FROM (SELECT 1 FROM favorites WHERE source=? GROUP BY media_type, canonical_id)',
                (source,),
            ).fetchone()[0]
        else:
            n = conn.execute(
                'SELECT COUNT(*) FROM (SELECT 1 FROM favorites GROUP BY media_type, canonical_id)'
            ).fetchone()[0]
    finally:
        conn.close()
    return int(n or 0)
