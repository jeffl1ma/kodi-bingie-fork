# -*- coding: utf-8 -*-
import os
import sqlite3
import threading
import time

from .common import profile_path

DB_PATH = os.path.join(profile_path(), 'playback.db')
_DB_READY = False
_DB_LOCK = threading.RLock()


_ID_COLUMNS = (
    ('tmdb_id', 'TEXT'),
    ('imdb_id', 'TEXT'),
    ('tvdb_id', 'TEXT'),
    # Episode rows normally carry the series TMDb id.  Keep it separately so
    # a TMDb Helper episode handoff can match even when a provider uses an
    # opaque id for both canonical_id and video_id.
    ('show_tmdb_id', 'TEXT'),
    # Native server identity lets Continue Watching reopen the exact Plex or
    # Emby object even when a translated show title has no usable external ID.
    ('native_server_id', 'TEXT'),
    ('native_item_id', 'TEXT'),
)


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
    except Exception:
        pass
    return conn


def _ensure_db():
    global _DB_READY
    if _DB_READY:
        return
    # Kodi can keep the plugin interpreter alive and invoke it from more than
    # one thread.  Serialising the one-time migration prevents concurrent
    # ALTER TABLE calls on slower CoreELEC/Android storage.
    with _DB_LOCK:
        if _DB_READY:
            return
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback (
                    media_type TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    title TEXT,
                    provider_name TEXT,
                    poster TEXT,
                    background TEXT,
                    clearlogo TEXT,
                    season INTEGER,
                    episode INTEGER,
                    position REAL,
                    duration REAL,
                    percent REAL,
                    stream_url TEXT,
                    event_type TEXT,
                    updated_at INTEGER,
                    tmdb_id TEXT,
                    imdb_id TEXT,
                    tvdb_id TEXT,
                    show_tmdb_id TEXT,
                    native_server_id TEXT,
                    native_item_id TEXT,
                    PRIMARY KEY (media_type, canonical_id, video_id)
                )
                """
            )
            # Existing installations already have the original table.  SQLite
            # migrations are additive, so no Continue Watching rows are lost.
            columns = set(row[1] for row in conn.execute('PRAGMA table_info(playback)').fetchall())
            for name, kind in _ID_COLUMNS:
                if name not in columns:
                    conn.execute('ALTER TABLE playback ADD COLUMN %s %s' % (name, kind))
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_updated ON playback(updated_at DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_percent ON playback(percent)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_imdb ON playback(imdb_id, updated_at DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_tmdb ON playback(tmdb_id, updated_at DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_show_tmdb ON playback(show_tmdb_id, season, episode, updated_at DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playback_tvdb ON playback(tvdb_id, updated_at DESC)')
            conn.commit()
            _DB_READY = True
        finally:
            conn.close()


def upsert_entry(media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo, season, episode, position, duration, percent, stream_url, event_type, ext_updated_at=None, tmdb_id='', imdb_id='', tvdb_id='', show_tmdb_id='', native_server_id='', native_item_id=''):
    """Insert or update a continue-watching row.

    `ext_updated_at` allows the caller to pass an authoritative timestamp
    (e.g. Trakt's `paused_at`) instead of "now". This keeps Continue Watching
    ordering STABLE across imports — the previous behavior used time.time()
    on every Trakt sync, so the home row reshuffled every few minutes.

    For local playback events, leave it None and we fall back to time.time().
    For local rows we only bump updated_at when the row is genuinely "new
    activity" (position has actually advanced, or this is a freshly inserted
    row); pure UI re-saves no longer reshuffle the row.
    """
    ts = int(ext_updated_at) if ext_updated_at else int(time.time())
    _ensure_db()
    conn = _connect()
    # We avoid clobbering updated_at on no-op updates: when the new position
    # is within ~30s of the stored one, keep the existing updated_at so the
    # home row doesn't bounce around when service.py re-saves the same point.
    existing = conn.execute(
        "SELECT position, updated_at FROM playback WHERE media_type=? AND canonical_id=? AND video_id=?",
        (media_type or '', canonical_id or '', video_id or ''),
    ).fetchone()
    if existing and ext_updated_at is None:
        try:
            old_pos = float(existing[0] or 0.0)
            if abs(float(position or 0.0) - old_pos) < 30.0:
                ts = int(existing[1] or ts)
        except Exception:
            pass
    conn.execute(
        """
        INSERT INTO playback (
            media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo,
            season, episode, position, duration, percent, stream_url, event_type, updated_at,
            tmdb_id, imdb_id, tvdb_id, show_tmdb_id
            , native_server_id, native_item_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(media_type, canonical_id, video_id)
        DO UPDATE SET
            title=excluded.title,
            provider_name=excluded.provider_name,
            poster=excluded.poster,
            background=excluded.background,
            clearlogo=excluded.clearlogo,
            season=excluded.season,
            episode=excluded.episode,
            position=excluded.position,
            duration=excluded.duration,
            percent=excluded.percent,
            stream_url=excluded.stream_url,
            event_type=excluded.event_type,
            updated_at=excluded.updated_at,
            tmdb_id=CASE WHEN excluded.tmdb_id != '' THEN excluded.tmdb_id ELSE playback.tmdb_id END,
            imdb_id=CASE WHEN excluded.imdb_id != '' THEN excluded.imdb_id ELSE playback.imdb_id END,
            tvdb_id=CASE WHEN excluded.tvdb_id != '' THEN excluded.tvdb_id ELSE playback.tvdb_id END,
            show_tmdb_id=CASE WHEN excluded.show_tmdb_id != '' THEN excluded.show_tmdb_id ELSE playback.show_tmdb_id END,
            native_server_id=CASE WHEN excluded.native_server_id != '' THEN excluded.native_server_id ELSE playback.native_server_id END,
            native_item_id=CASE WHEN excluded.native_item_id != '' THEN excluded.native_item_id ELSE playback.native_item_id END
        WHERE excluded.updated_at >= playback.updated_at
        """,
        (
            media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo,
            season, episode, position, duration, percent, stream_url, event_type, ts,
            str(tmdb_id or '').strip(), str(imdb_id or '').strip().lower(),
            str(tvdb_id or '').strip(), str(show_tmdb_id or '').strip(),
            str(native_server_id or '').strip(), str(native_item_id or '').strip(),
        ),
    )
    conn.commit()
    conn.close()


def update_art(media_type, canonical_id, video_id, poster='', background='', clearlogo=''):
    """Update artwork only without touching updated_at so Continue Watching
    ordering stays stable until the user actually watches something new."""
    _ensure_db()
    conn = _connect()
    conn.execute(
        """
        UPDATE playback
        SET
            poster=CASE WHEN ? != '' THEN ? ELSE poster END,
            background=CASE WHEN ? != '' THEN ? ELSE background END,
            clearlogo=CASE WHEN ? != '' THEN ? ELSE clearlogo END
        WHERE media_type=? AND canonical_id=? AND video_id=?
        """,
        (
            poster or '', poster or '',
            background or '', background or '',
            clearlogo or '', clearlogo or '',
            media_type or '', canonical_id or '', video_id or '',
        ),
    )
    conn.commit()
    conn.close()


def list_continue_items(limit=50):
    _ensure_db()
    conn = _connect()
    rows = conn.execute(
        """
        SELECT media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo,
               season, episode, position, duration, percent, updated_at,
               tmdb_id, imdb_id, tvdb_id, show_tmdb_id, native_server_id, native_item_id
        FROM playback
        WHERE percent < 95.0
        ORDER BY updated_at DESC, title COLLATE NOCASE ASC, canonical_id ASC, video_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        out.append({
            'media_type': row[0], 'canonical_id': row[1], 'video_id': row[2], 'title': row[3],
            'provider_name': row[4], 'poster': row[5], 'background': row[6], 'clearlogo': row[7],
            'season': row[8], 'episode': row[9], 'position': row[10], 'duration': row[11],
            'percent': row[12], 'updated_at': row[13],
            'tmdb_id': row[14], 'imdb_id': row[15], 'tvdb_id': row[16], 'show_tmdb_id': row[17],
            'native_server_id': row[18], 'native_item_id': row[19],
        })
    return out


def list_recent_items(limit=200, media_types=None, include_watched=True):
    """Return recent playback rows without forcing the Continue Watching filter.

    Used by Next Up and diagnostics where fully watched episodes must remain
    visible as the base for finding the *next* episode.
    """
    _ensure_db()
    conn = _connect()
    where = []
    params = []
    if media_types:
        mts = [str(x or '').strip().lower() for x in media_types if str(x or '').strip()]
        if mts:
            where.append('media_type IN (%s)' % ','.join(['?'] * len(mts)))
            params.extend(mts)
    if not include_watched:
        where.append('percent < 95.0')
    sql = """
        SELECT media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo,
               season, episode, position, duration, percent, updated_at, event_type, stream_url,
               tmdb_id, imdb_id, tvdb_id, show_tmdb_id, native_server_id, native_item_id
        FROM playback
    """
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += " ORDER BY updated_at DESC, title COLLATE NOCASE ASC, canonical_id ASC, video_id ASC LIMIT ?"
    params.append(int(limit or 200))
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    out = []
    for row in rows:
        out.append({
            'media_type': row[0], 'canonical_id': row[1], 'video_id': row[2], 'title': row[3],
            'provider_name': row[4], 'poster': row[5], 'background': row[6], 'clearlogo': row[7],
            'season': row[8], 'episode': row[9], 'position': row[10], 'duration': row[11],
            'percent': row[12], 'updated_at': row[13], 'event_type': row[14], 'stream_url': row[15],
            'tmdb_id': row[16], 'imdb_id': row[17], 'tvdb_id': row[18], 'show_tmdb_id': row[19],
            'native_server_id': row[20], 'native_item_id': row[21],
        })
    return out


def _row_to_dict(row):
    return {
        'media_type': row[0], 'canonical_id': row[1], 'video_id': row[2], 'title': row[3],
        'provider_name': row[4], 'poster': row[5], 'background': row[6], 'clearlogo': row[7],
        'season': row[8], 'episode': row[9], 'position': row[10], 'duration': row[11],
        'percent': row[12], 'updated_at': row[13], 'tmdb_id': row[14], 'imdb_id': row[15],
        'tvdb_id': row[16], 'show_tmdb_id': row[17],
        'native_server_id': row[18], 'native_item_id': row[19],
    }


def find_resume_entry(media_type='movie', canonical_id='', tmdb_id='', imdb_id='', tvdb_id='', season=None, episode=None):
    """Return the best unfinished row for a TMDb Helper playback request.

    The priority is deliberate: IMDb is globally stable, then TMDb (the show
    id is also checked for episodes), then TVDb, then Dex Hub's legacy
    provider/canonical ids.  Each query is indexed and only asks SQLite for a
    single row, avoiding the old full scan of the latest 500 records.
    """
    _ensure_db()
    mt = str(media_type or 'movie').strip().lower()
    is_episode = mt in ('series', 'anime', 'show', 'tv') or (season not in (None, '', 0, '0') and episode not in (None, '', 0, '0'))
    try:
        season_i = int(season or 0)
        episode_i = int(episode or 0)
    except Exception:
        season_i, episode_i = 0, 0
    base = ['percent < 95.0', '(position > 30.0 OR percent > 1.0)']
    params = []
    if is_episode:
        base.extend(['season=?', 'episode=?'])
        params.extend([season_i, episode_i])
    else:
        base.append("media_type IN ('movie', 'movies', '')")
    select = """
        SELECT media_type, canonical_id, video_id, title, provider_name, poster, background, clearlogo,
               season, episode, position, duration, percent, updated_at,
               tmdb_id, imdb_id, tvdb_id, show_tmdb_id, native_server_id, native_item_id
        FROM playback WHERE %s AND %%s
        ORDER BY updated_at DESC LIMIT 1
    """ % ' AND '.join(base)
    matches = []
    imdb = str(imdb_id or '').strip().lower()
    if imdb.lower().startswith('imdb:'):
        imdb = imdb.split(':', 1)[1].strip()
    if imdb.isdigit():
        imdb = 'tt%s' % imdb
    if imdb:
        matches.append(('LOWER(imdb_id)=?', [imdb]))
    tmdb = str(tmdb_id or '').strip()
    if tmdb:
        matches.append(('(tmdb_id=? OR show_tmdb_id=?)', [tmdb, tmdb]))
    tvdb = str(tvdb_id or '').strip()
    if tvdb:
        matches.append(('tvdb_id=?', [tvdb]))
    canonical = str(canonical_id or '').strip()
    if canonical:
        matches.append(('(canonical_id=? OR video_id=?)', [canonical, canonical]))
    if not matches:
        return None
    conn = _connect()
    try:
        for clause, values in matches:
            row = conn.execute(select % clause, tuple(params + values)).fetchone()
            if row:
                return _row_to_dict(row)
    finally:
        conn.close()
    return None


def delete_entry(media_type, canonical_id, video_id):
    _ensure_db()
    conn = _connect()
    conn.execute(
        "DELETE FROM playback WHERE media_type=? AND canonical_id=? AND video_id=?",
        (media_type or '', canonical_id or '', video_id or ''),
    )
    conn.commit()
    conn.close()


def mark_watched(media_type, canonical_id, video_id):
    """Set percent=100 so the row is filtered out of continue_watching without deleting it."""
    import time as _t
    _ensure_db()
    conn = _connect()
    conn.execute(
        "UPDATE playback SET percent=100.0, updated_at=? WHERE media_type=? AND canonical_id=? AND video_id=?",
        (int(_t.time()), media_type or '', canonical_id or '', video_id or ''),
    )
    conn.commit()
    conn.close()
