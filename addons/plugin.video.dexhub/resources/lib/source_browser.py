# -*- coding: utf-8 -*-
import html
import json
import re
import threading
import time
import unicodedata
try:
    from urllib.request import Request, urlopen
except Exception:  # pragma: no cover - Kodi runtime fallback
    Request = None
    urlopen = None
from .log import log

import xbmc
import xbmcaddon
import xbmcgui

from . import cache_store, source_session
from . import tmdbhelper as _tmdb_art_db
from . import tmdb_direct as _tmdb_direct
from .i18n import tr

# --- dexhub-401-patch ---
try:
    from .settings_cache import cached_addon as _dh_cached_addon
except Exception:
    try:
        from settings_cache import cached_addon as _dh_cached_addon
    except Exception:
        _dh_cached_addon = None
ADDON = _dh_cached_addon() if _dh_cached_addon else xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')

ACTION_SELECT = {7, 100}
ACTION_INFO = {11}
ACTION_BACK = {9, 10, 92, 216, 247, 257, 275, 61467, 61448}
ACTION_CONTEXT = {117}
ACTION_LEFT = {1}
ACTION_RIGHT = {2}
ACTION_MOVE = {3, 4}

MODE_ASK = 'ask'
MODE_PLAY = 'play'
MODE_PLAY_SUBS = 'play_with_subtitles'

QUALITY_FILTERS = [
    ('Q:2160P', 'QUALITY • 4K / 2160P', ('2160P', '2160', '4K', 'UHD')),
    ('Q:1080P', 'QUALITY • 1080P', ('1080P', '1080', 'FHD')),
    ('Q:720P',  'QUALITY • 720P',  ('720P', '720', 'HD')),
    ('Q:480P',  'QUALITY • 480P / SD', ('480P', '480', 'SD')),
    ('Q:HDR',   'QUALITY • HDR', ('HDR', 'HDR10', 'HDR10+')),
    ('Q:DV',    'QUALITY • Dolby Vision', ('DV', 'DOVI', 'DOLBY VISION')),
    ('Q:REMUX', 'QUALITY • REMUX', ('REMUX', 'BDREMUX')),
]

# Kodi on Android/TV skins commonly ships with fonts that cover Latin/Arabic
# but not CJK/Hangul/emoji/private-use glyphs. When Stremio/Plexio metadata
# returns original Korean/Japanese/Chinese text, Kodi renders it as empty
# square boxes. Keep Arabic/Latin intact, but strip scripts that are very
# likely to render as boxes in the bundled source-picker skin.
_UNSUPPORTED_KODI_FONT_RE = re.compile(
    r'[\u1100-\u11FF\u2E80-\u2EFF\u2F00-\u2FDF\u3040-\u30FF'
    r'\u3100-\u312F\u31A0-\u31BF\u3400-\u4DBF\u4E00-\u9FFF'
    r'\uA960-\uA97F\uAC00-\uD7AF\uF900-\uFAFF\U0001F300-\U0001FAFF\uE000-\uF8FF]'
)
_VISIBLE_RE = re.compile(r'\S')
_MARKUP_RE = re.compile(r'\[/?(?:COLOR|B|I|UPPERCASE|LOWERCASE|LIGHT)\b[^\]]*\]', re.I)


def _kodi_safe_text(value, fallback=''):
    """Return text that the bundled Kodi skin is likely able to render.

    This is intentionally UI-only; it never changes the playable stream URL or
    cached metadata. It removes unsupported CJK/Hangul/emoji glyphs that show
    up as □□□ boxes in Kodi fonts, then falls back to a clean title when the
    remaining text would be mostly empty.
    """
    raw = html.unescape(str(value or ''))
    raw = _MARKUP_RE.sub(' ', raw)
    raw = raw.replace('\u200f', ' ').replace('\u200e', ' ').replace('\xa0', ' ')
    raw = ''.join(ch for ch in unicodedata.normalize('NFKC', raw) if ch == '\n' or ch == '\t' or ord(ch) >= 32)
    visible = len(_VISIBLE_RE.findall(raw))
    if not raw or not visible:
        return str(fallback or '')
    unsupported = len(_UNSUPPORTED_KODI_FONT_RE.findall(raw)) + raw.count('□') + raw.count('�')
    cleaned = _UNSUPPORTED_KODI_FONT_RE.sub(' ', raw)
    cleaned = cleaned.replace('□', ' ').replace('�', ' ')
    cleaned = re.sub(r'[\u25A0-\u25FF]+', ' ', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n\s*\n+', '\n', cleaned).strip(' -|_/\\\n\t')
    if unsupported and (not cleaned or len(_VISIBLE_RE.findall(cleaned)) < max(4, int(visible * 0.35))):
        return str(fallback or '')
    return cleaned


def _kodi_safe_meta_text(value, fallback=''):
    text = _kodi_safe_text(value, fallback='')
    if text:
        return text
    return _kodi_safe_text(fallback, fallback='')



def _row_quality_blob(row):
    bits = []
    for key in ('quality', 'highlight', 'badges', 'video_bits', 'audio_bits', 'extraInfo', 'extraInfo2', 'name', 'label2', 'formatter_summary', 'source_info'):
        value = (row or {}).get(key)
        if isinstance(value, (list, tuple)):
            bits.extend([str(v) for v in value if v])
        elif value:
            bits.append(str(value))
    return ' '.join(bits).upper()


# Elite-style image badges for the custom Dex Hub source results XML.
# These are lightweight URL properties only; Kodi's texture cache handles
# fetching/caching them and the text-chip fallback remains active if a badge
# image cannot be resolved.
_ELITE_BADGE_DEFAULT_JSON_URL = 'https://raw.githubusercontent.com/9mousaa/BetterFormatter/main/presets/mono-bgb-sep-nodv.json'
_ELITE_BADGE_BASE = 'https://raw.githubusercontent.com/leonevz/Elite-Badges/main/Badges/'
_ELITE_BADGE_RULE_CACHE = {'url': '', 'ts': 0.0, 'rules': None}
_ELITE_GROUP_LIMITS = {
    'source': 1,
    'resolution': 1,
    'video-tech': 2,
    'video-codec': 1,
    'bit-depth': 1,
    'audio-tech': 2,
    'audio-channels': 1,
}
_ELITE_BADGE_RULES = [
    ('source', r'\bremux\b', 'remux.png'),
    ('source', r'\b(blu[\s._-]?ray|bluray|bdrip|bdremux)\b', 'blu_ray_disc.png'),
    ('source', r'\b(web[\s._-]?dl|webdl)\b', 'WEBDL_transparent_4x.png'),
    ('source', r'\b(web[\s._-]?rip|webrip)\b', 'WEBRip_transparent_4x.png'),
    ('source', r'\bhdtv\b', 'HDTV_transparent_4x.png'),
    ('source', r'\b(dvd[\s._-]?rip|dvdrip)\b', 'DVD_RIP_transparent_4x.png'),
    ('resolution', r'\b(4k|2160p|uhd|ultra\s*hd)\b', '4k_ultra_hd.png'),
    ('resolution', r'\b(1080p|fhd|full\s*hd)\b', '1080p_full_hd.png'),
    ('resolution', r'\b720p\b', '720p_hd.png'),
    ('resolution', r'\b480p\b', '480p_sd.png'),
    ('video-tech', r'\b(imax[\s._-]*enhanced)\b', 'imax_enhanced.png'),
    ('video-tech', r'\b(imax)\b(?![\s._-]*enhanced)', 'imax.png'),
    ('video-tech', r'\b(dolby\s*vision|dovi|dv)\b', 'dolby_vision.png'),
    ('video-tech', r'\b(hdr10\+|hdr10\s*plus\b|hdr\s*10\s*\+)', 'hdr10_plus.png'),
    ('video-tech', r'\b(hdr10|hdr\s*10)\b(?!\s*\+|\s*plus)', 'hdr10.png'),
    ('video-tech', r'\bhdr\b', 'hdr.png'),
    ('video-tech', r'\bsdr\b', 'SDR_transparent_4x.png'),
    ('video-codec', r'\b(hevc|h[\s._-]?265|x265)\b', 'HEVC_transparent_4x.png'),
    ('video-codec', r'\b(avc|h[\s._-]?264|x264)\b', 'AVC_transparent_4x.png'),
    ('bit-depth', r'\b(10[\s._-]?bit|10b|hi10p)\b', '10Bit_transparent_4x.png'),
    ('bit-depth', r'\b(8[\s._-]?bit|8b)\b', '8Bit_transparent_4x.png'),
    ('audio-tech', r'\b(dolby\s*atmos|atmos)\b', 'dolby_atmos.png'),
    ('audio-tech', r'\b(truehd|true\s*hd|dolby\s*truehd)\b', 'truehd.png'),
    ('audio-tech', r'\b(ddp[\s._-]*[0-9][\s._-]*[0-9]|ddp|dd\+|dolby[\s._-]*digital[\s._-]*plus|e-?ac-?3)(?![a-z])', 'dolby_digital_plus.png'),
    ('audio-tech', r'\b(dd[\s._-]*[0-9][\s._-]*[0-9]|dd|dolby[\s._-]*digital|ac-?3)(?![\s._-]*plus|\+|p|[a-z])', 'dolby_digital.png'),
    ('audio-tech', r'\b(dts[:\s._-]*x)\b', 'dts_x.png'),
    ('audio-tech', r'\b(dts[\s._-]*hd[\s._-]*ma|dtshd\s*ma|dts[\s._-]*hd[\s._-]*master)\b', 'dts_hd_master_audio.png'),
    ('audio-tech', r'\b(dts[\s._-]*hd|dtshd)(?![\s._-]*(ma|master)|ma)\b', 'dts_hd.png'),
    ('audio-tech', r'\bdts\b(?![\s._:-]*(x|hd))', 'dts.png'),
    ('audio-channels', r'\b(7\.1|7-1|8ch|8\s*channel)\b', '7_1_audio.png'),
    ('audio-channels', r'\b(5\.1|5-1|6ch|6\s*channel)\b', '5_1_audio.png'),
]


def _elite_badge_blob(row, tags=None):
    bits = []
    for value in (row.get('name'), row.get('label2'), row.get('provider'), row.get('addon'), row.get('source_site'),
                  row.get('badges'), row.get('extraInfo'), row.get('extraInfo2'), row.get('formatter_summary'), row.get('source_info')):
        if value:
            bits.append(str(value))
    for seq_key in ('video_bits', 'audio_bits'):
        for item in (row.get(seq_key) or []):
            if item:
                bits.append(str(item))
    for tag in (tags or []):
        if isinstance(tag, dict) and tag.get('text'):
            bits.append(str(tag.get('text')))
    return ' '.join(bits)


def _elite_builtin_badge_rules():
    return [(group, pattern, _ELITE_BADGE_BASE + filename) for group, pattern, filename in _ELITE_BADGE_RULES]


def _elite_badge_setting_url():
    try:
        return (xbmcaddon.Addon().getSetting('elite_badges_json_url') or '').strip()
    except Exception:
        return ''


def _elite_rules_from_json_blob(blob):
    try:
        data = json.loads(blob or '{}')
    except Exception:
        return []
    filters = data.get('filters') if isinstance(data, dict) else []
    if not isinstance(filters, list):
        return []
    out = []
    seen = set()
    for item in filters:
        if not isinstance(item, dict):
            continue
        if item.get('isEnabled') is False:
            continue
        group = str(item.get('groupId') or item.get('group') or item.get('category') or 'other').strip() or 'other'
        pattern = str(item.get('pattern') or '').strip()
        image = str(item.get('imageURL') or item.get('imageUrl') or item.get('image') or '').strip()
        if not pattern or not image:
            continue
        key = (group, pattern, image)
        if key in seen:
            continue
        seen.add(key)
        out.append((group, pattern, image))
    return out


def _elite_badge_rules():
    """Rules for image badges.

    The bundled/default Elite rules stay instant and offline. If the user pastes
    a different badges.json URL in settings, fetch it once per Kodi process and
    fall back to the bundled rules if the URL is slow, invalid, or unavailable.
    """
    url = _elite_badge_setting_url()
    if not url or url == _ELITE_BADGE_DEFAULT_JSON_URL:
        return _elite_builtin_badge_rules()

    now = time.monotonic()
    cached_url = _ELITE_BADGE_RULE_CACHE.get('url')
    cached_rules = _ELITE_BADGE_RULE_CACHE.get('rules')
    cached_ts = float(_ELITE_BADGE_RULE_CACHE.get('ts') or 0.0)
    if cached_url == url and cached_rules and (now - cached_ts) < 3600:
        return list(cached_rules)

    rules = []
    try:
        if Request is None or urlopen is None:
            raise RuntimeError('urllib unavailable')
        req = Request(url, headers={'User-Agent': 'DexHub/%s Kodi' % (ADDON.getAddonInfo('version') or '3')})
        with urlopen(req, timeout=3.0) as resp:
            raw = resp.read(1024 * 512)
        try:
            text = raw.decode('utf-8')
        except Exception:
            text = raw.decode('utf-8', 'ignore')
        rules = _elite_rules_from_json_blob(text)
    except Exception as exc:
        log.silent('ELITE_BADGES_JSON', exc)
        rules = []

    if rules:
        _ELITE_BADGE_RULE_CACHE.update({'url': url, 'ts': now, 'rules': list(rules)})
        return rules
    return _elite_builtin_badge_rules()


def _elite_pattern_matches(pattern, text):
    try:
        return re.search(pattern, text) is not None
    except Exception:
        try:
            cleaned = str(pattern or '').replace('(?i)', '')
            return re.search(cleaned, text, re.I) is not None
        except Exception:
            return False


def _elite_badge_images(row, tags=None, max_items=8):
    text = _elite_badge_blob(row or {}, tags=tags)
    if not text:
        return []
    out = []
    used_images = set()
    group_counts = {}
    for group, pattern, image_url in _elite_badge_rules():
        if image_url in used_images:
            continue
        if group_counts.get(group, 0) >= _ELITE_GROUP_LIMITS.get(group, 1):
            continue
        if not _elite_pattern_matches(pattern, text):
            continue
        out.append(image_url)
        used_images.add(image_url)
        group_counts[group] = group_counts.get(group, 0) + 1
        if len(out) >= max_items:
            break
    return out


# --- dexhub-407-patch ---
# Sort modes for the results drawer. Kept separate from QUALITY_FILTERS so a
# filter and a sort can be active at the same time.
SORT_MODES = [
    ('S:DEFAULT',  'SORT \u2022 RECOMMENDED'),
    ('S:SIZE',     'SORT \u2022 SIZE'),
    ('S:QUALITY',  'SORT \u2022 QUALITY'),
    ('S:PROVIDER', 'SORT \u2022 SOURCE'),
    ('S:NAME',     'SORT \u2022 NAME'),
]

_SORT_QUALITY_RANK = (
    (('2160', '4K', 'UHD'), 5),
    (('1080', 'FHD'), 4),
    (('720', 'HD'), 3),
    (('480', 'SD'), 2),
)


def _sort_mode_label(value):
    for key, label in SORT_MODES:
        if key == value:
            return tr(label)
    return tr(SORT_MODES[0][1])


def _sort_size_bytes(row):
    """Parse the human size label ("12.4 GB") into bytes for ordering."""
    text = str((row or {}).get('size_label') or '').upper().replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB|MB|KB|B)\b', text)
    if not m:
        return -1.0
    try:
        value = float(m.group(1))
    except (TypeError, ValueError):
        return -1.0
    return value * {'TB': 1024.0 ** 4, 'GB': 1024.0 ** 3,
                    'MB': 1024.0 ** 2, 'KB': 1024.0, 'B': 1.0}[m.group(2)]


def _sort_quality_rank(row):
    blob = _row_quality_blob(row)
    for tokens, rank in _SORT_QUALITY_RANK:
        if any(t in blob for t in tokens):
            return rank
    return 0


def _sorted_rows(rows, mode):
    """Reorder rows for the chosen mode. S:DEFAULT keeps the ranked order."""
    rows = list(rows or [])
    mode = str(mode or 'S:DEFAULT')
    if mode == 'S:SIZE':
        # Rows with no size go last rather than sorting as zero.
        return sorted(rows, key=lambda r: (_sort_size_bytes(r) < 0, -_sort_size_bytes(r)))
    if mode == 'S:QUALITY':
        return sorted(rows, key=lambda r: (-_sort_quality_rank(r), -_sort_size_bytes(r)))
    if mode == 'S:PROVIDER':
        return sorted(rows, key=lambda r: (str(r.get('addon') or r.get('provider') or '').upper(),
                                           -_sort_size_bytes(r)))
    if mode == 'S:NAME':
        return sorted(rows, key=lambda r: str(r.get('name') or '').upper())
    return rows


def _quality_filter_label(value):
    for key, label, _tokens in QUALITY_FILTERS:
        if key == value:
            return tr(label)
    return tr(value or '')


def _filter_label(value):
    value = str(value or 'ALL')
    if value == 'ALL':
        return tr('ALL RESULTS')
    if value.startswith('Q:'):
        return _quality_filter_label(value)
    if value.startswith('P:'):
        return tr('PROVIDER • %s') % value[2:]
    return tr(value)


def _row_matches_quality(row, filter_value):
    blob = _row_quality_blob(row)
    for key, _label, tokens in QUALITY_FILTERS:
        if key != filter_value:
            continue
        if key == 'Q:720P':
            return any(t in blob for t in tokens) and '1080' not in blob and '2160' not in blob and '4K' not in blob
        if key == 'Q:480P':
            return any(t in blob for t in tokens) and '720' not in blob and '1080' not in blob and '2160' not in blob and '4K' not in blob
        return any(t in blob for t in tokens)
    return False


def _row_provider_filter(row):
    provider = str((row or {}).get('addon') or (row or {}).get('source_site') or (row or {}).get('provider') or '').strip().upper()
    return ('P:%s' % provider) if provider else ''


def _looks_arabic_text(value):
    text = str(value or '').strip()
    if not text:
        return False
    for ch in text:
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF:
            return True
    return False


def _source_art_identity_key(payload=None):
    data = payload or {}
    try:
        media_type = str(data.get('media_type') or data.get('type') or '').strip().lower()
        canonical = str(data.get('canonical_id') or data.get('id') or '').strip()
        video_id = str(data.get('video_id') or '').strip()
        tmdb_id = str(data.get('tmdb_id') or '').strip()
        imdb_id = str(data.get('imdb_id') or '').strip()
        tvdb_id = str(data.get('tvdb_id') or '').strip()
        season = str(data.get('season') or '').strip()
        episode = str(data.get('episode') or '').strip()
        title = str(data.get('show_title') or data.get('originaltitle') or data.get('title') or data.get('name') or '').strip().lower()
        return '|'.join([media_type, canonical, video_id, tmdb_id, imdb_id, tvdb_id, season, episode, title])
    except Exception:
        return ''


def _source_meta_backfill(meta):
    """Fast-path metadata enrichment for the source picker window.

    POV-style: NEVER hits the network on this synchronous path. Only consults
    the local TMDb Helper SQLite database (zero-latency on cache hit). The
    expensive tmdb_direct API fallback is moved to a background thread that
    populates the home window properties after the picker is already visible
    — so the picker opens fast even on slow connections.
    """
    meta = dict(meta or {})
    if meta.get('poster') and meta.get('fanart') and meta.get('clearlogo') and meta.get('title'):
        return meta
    tmdb_id = str(meta.get('tmdb_id') or '').strip()
    imdb_id = str(meta.get('imdb_id') or '').strip()
    media_type = str(meta.get('media_type') or meta.get('type') or 'movie').strip().lower()
    if media_type in ('show', 'tv', 'anime', 'series', 'tvshow'):
        media_type = 'series'
    title = str(meta.get('originaltitle') or meta.get('title') or meta.get('name') or '').strip()
    year = str(meta.get('year') or '').strip()
    if not (tmdb_id or imdb_id or title):
        return meta

    source_poster = meta.get('poster') or ''
    source_fanart = meta.get('fanart') or meta.get('background') or source_poster or ''
    source_clearlogo = meta.get('clearlogo') or meta.get('logo') or ''

    bundle = {}
    try:
        bundle = _tmdb_art_db.get_art_bundle_from_db(
            tmdb_id=tmdb_id,
            media_type=media_type,
            imdb_id=imdb_id,
            title=title,
            year=year,
        ) or {}
    except Exception:
        bundle = {}

    tmdb_poster = bundle.get('poster') or ''
    tmdb_clearlogo = bundle.get('clearlogo') or ''
    tmdb_fanart = bundle.get('fanart') or bundle.get('landscape') or ''

    if tmdb_poster:
        meta['poster'] = tmdb_poster
    elif source_poster:
        meta['poster'] = source_poster

    if source_fanart:
        meta['fanart'] = source_fanart
        meta['background'] = source_fanart
    elif tmdb_fanart:
        meta['fanart'] = tmdb_fanart
        meta['background'] = tmdb_fanart

    if tmdb_clearlogo:
        meta['clearlogo'] = tmdb_clearlogo
        meta['logo'] = tmdb_clearlogo
    elif source_clearlogo:
        meta['clearlogo'] = source_clearlogo
        meta['logo'] = source_clearlogo

    try:
        db_title = _tmdb_art_db.get_title_from_db(tmdb_id=tmdb_id, media_type=media_type, imdb_id=imdb_id, title=title, year=year) or ''
    except Exception:
        db_title = ''
    current_title = str(meta.get('title') or '').strip()
    if db_title and (not current_title or _looks_arabic_text(current_title)):
        meta['title'] = db_title

    if not meta.get('fanart') and meta.get('poster'):
        meta['fanart'] = meta.get('poster')
        meta['background'] = meta.get('poster')
    return meta


def _backfill_meta_via_network(meta, window):
    """Background thread: fill remaining art AND text via the TMDb API and
    push fresh values into the source window's properties. Runs only when
    the initial fast-path left art or key text fields empty.

    v3.9.144: upgraded from art_for() to meta_for() — the SAME single
    network call that fetches poster/fanart/logo now also returns the plot,
    year, genres and rating for the hero panel. The addon meta stays the
    base; TMDb only fills blanks (merge_into_meta with addon-priority).
    """
    if not isinstance(meta, dict):
        return
    have_art = meta.get('poster') and meta.get('fanart') and meta.get('clearlogo')
    have_text = meta.get('plot') and meta.get('year') and meta.get('genre')
    if have_art and have_text:
        return
    tmdb_id = str(meta.get('tmdb_id') or '').strip()
    imdb_id = str(meta.get('imdb_id') or '').strip()
    media_type = str(meta.get('media_type') or meta.get('type') or 'movie').strip().lower()
    if media_type in ('show', 'tv', 'anime', 'series', 'tvshow'):
        media_type = 'series'
    title = str(meta.get('originaltitle') or meta.get('title') or meta.get('name') or '').strip()
    year = str(meta.get('year') or '').strip()
    if not (tmdb_id or imdb_id or title):
        return
    try:
        direct = _tmdb_direct.meta_for(
            tmdb_id=tmdb_id, imdb_id=imdb_id,
            media_type=media_type, title=title, year=year,
        ) or {}
    except Exception:
        return
    # v3.9.89: route the resolved poster through clean_poster so the
    # backfill never replaces the TMDb-derived poster with a raw addon
    # URL that might be a logo. Build a synthetic meta dict carrying the
    # ids and the candidate poster so the helper sees both.
    candidate_poster = meta.get('poster') or direct.get('poster') or ''
    try:
        from .art import clean_poster
        poster = clean_poster({
            'poster': candidate_poster,
            'imdb_id': imdb_id,
            'tmdb_id': tmdb_id,
            'media_type': media_type,
        }, media_type=media_type)
    except Exception:
        poster = candidate_poster
    fanart = meta.get('fanart') or direct.get('fanart') or direct.get('landscape') or ''
    clearlogo = meta.get('clearlogo') or direct.get('clearlogo') or ''

    # v3.9.144: derive the hero TEXT, addon value first, TMDb fills blanks.
    plot = str(meta.get('plot') or direct.get('description') or '').strip()
    year_out = str(meta.get('year') or direct.get('year') or '').strip()
    tmdb_genres = direct.get('genres') or []
    genre_out = str(meta.get('genre') or '').strip()
    if not genre_out and tmdb_genres:
        genre_out = ' / '.join([str(g) for g in tmdb_genres[:3] if g])
    rating_out = str(meta.get('rating') or direct.get('imdbRating') or '').strip()
    tmdb_studios = direct.get('studio') or []
    studio_out = str(meta.get('studio') or '').strip()
    if not studio_out and tmdb_studios:
        studio_out = ' / '.join([str(s) for s in tmdb_studios[:2] if s])

    # v3.9.55: namespaced art properties. The plain 'poster'/'fanart'/
    # 'clearlogo' names collided with the global Window(10000) properties
    # that other DexHub code paths set for skin integration, causing
    # stale artwork from a previous item to flash on the results page.
    # By using dexhub.results.* names we guarantee no conflict.
    try:
        # Queue the update for the dialog thread when possible. Kodi GUI
        # controls/properties are not consistently safe from Python worker
        # threads on Android/Matrix/Nexus builds, and this backfill is purely
        # cosmetic. Falling back to direct setProperty preserves legacy behavior
        # for any non-SourcesWindow caller.
        if hasattr(window, '_queue_art_update'):
            window._queue_art_update({
                'poster': poster or '',
                'fanart': fanart or '',
                'clearlogo': clearlogo or '',
                'plot': plot,
                'year': year_out,
                'genre': genre_out,
                'rating': rating_out,
                'studio': studio_out,
            })
        else:
            if poster:
                window.setProperty('dexhub.results.poster', poster)
            if fanart:
                window.setProperty('dexhub.results.fanart', fanart)
            if clearlogo:
                window.setProperty('dexhub.results.clearlogo', clearlogo)
            if plot:
                window.setProperty('plot', plot)
            if year_out:
                window.setProperty('year', year_out)
            if genre_out:
                window.setProperty('genre', genre_out)
            if rating_out:
                window.setProperty('rating', rating_out)
            if studio_out:
                window.setProperty('studio', studio_out)
    except Exception as _silent_exc:
        log.silent('RESULTS_WIN', _silent_exc)
def _normalize_mode(value):
    raw = str(value or '').strip().lower()
    if raw in (MODE_PLAY_SUBS, 'play_with_subtitles', 'with_subtitles', 'with-subs', 'تشغيل مع ترجمة', 'play with subtitles'):
        return MODE_PLAY_SUBS
    # Legacy/empty/ask values all become normal playback. Playback mode is now
    # controlled from settings only; no per-click prompt.
    return MODE_PLAY


class SourcesWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.results = kwargs.get('results') or []
        self.meta = kwargs.get('meta') or {}
        self.selected = None
        self.active_filter = 'ALL'
        # --- dexhub-407-patch ---
        try:
            self.active_sort = str(ADDON.getSetting('source_sort_mode') or 'S:DEFAULT') or 'S:DEFAULT'
        except Exception:
            self.active_sort = 'S:DEFAULT'
        if self.active_sort not in [k for k, _l in SORT_MODES]:
            self.active_sort = 'S:DEFAULT'
        self.filters = []
        self.play_mode = _normalize_mode(kwargs.get('play_mode') or MODE_ASK)
        self.play_with_subtitles = False
        self.session_key = kwargs.get('session_key') or ''
        self._session_version = 0
        self._poll_stop = threading.Event()
        self._poll_thread = None
        self._pending_lock = threading.Lock()
        self._pending_payload = None
        self._pending_art = None
        # Double-dialog guard. Once a stream is chosen and the play-mode
        # picker has been shown, ALL further input is ignored. This kills the
        # symptom where a single OK press fired both onAction(SELECT) AND
        # onClick(2000) — the second event used to re-open the picker after
        # the first had already finalized the selection.
        self._closing = False
        self._mode_dialog_open = False
        self._action_guard = {}
        # v3.9.143: timestamp of the user's last input. The session poll
        # thread auto-applies queued live results only when the user has
        # been idle, so the list fills itself without keypresses while
        # still never mutating controls mid-navigation.
        self._last_input_ts = time.monotonic()

    def onInit(self):
        try:
            from . import skin_theme
            skin_theme.publish_theme(self)
        except Exception:
            pass
        try:
            self.meta = _source_meta_backfill(self.meta)
        except Exception:
            self.meta = dict(self.meta or {})
        # Unify with TMDb Helper's live context: back-fill any missing art and
        # publish the aggregate ratings row (IMDb/TMDb/Trakt/RT) so DexHub shows
        # the same numbers the skin's info screen just showed.
        try:
            from . import tmdbh_context
            self.meta = tmdbh_context.enrich(self, self.meta)
        except Exception:
            pass
        # Push every visual property up-front so the XML can use $INFO
        # bindings (poster/fanart/clearlogo/title/plot). Imperative setImage
        # gets clobbered by static <texture> tags in the skin so we don't
        # rely on it as the primary path.
        _fanart = self.meta.get('fanart') or self.meta.get('background') or ''
        _clearlogo = self.meta.get('clearlogo') or ''
        # v3.9.89: route poster selection through art.clean_poster so the
        # results window uses the same TMDb-first policy as the player
        # overlay. Order: (1) MetaHub/TMDb URL when an IMDb id is known —
        # this is what TMDb Helper, the player overlay, and Cinemeta
        # all use; (2) the addon-provided URL when it's clearly not a
        # logo/icon; (3) the local portrait placeholder. The placeholder
        # is correctly proportioned 2:3 so it never renders as a banner
        # stuck at the top of an empty card.
        try:
            from .art import clean_poster
            _media_type = self.meta.get('media_type') or self.meta.get('type') or 'movie'
            _poster = clean_poster(self.meta, media_type=_media_type)
        except Exception:
            _poster = self.meta.get('poster') or ''
        _title_raw = self.meta.get('title') or self.meta.get('name') or ''
        _fallback_title = self.meta.get('originaltitle') or self.meta.get('english_title') or self.meta.get('name') or _title_raw or ''
        _title = _kodi_safe_meta_text(_title_raw, _fallback_title)
        plot_raw = self.meta.get('plot') or self.meta.get('description') or self.meta.get('overview') or ''
        _plot = _kodi_safe_meta_text(str(plot_raw)[:600], '') if plot_raw else ''
        _year = _kodi_safe_meta_text(self.meta.get('year') or '', '')
        _rating = _kodi_safe_meta_text(self.meta.get('rating') or '', '')
        _genre = _kodi_safe_meta_text(self.meta.get('genre') or '', '')
        _studio = _kodi_safe_meta_text(self.meta.get('studio') or '', '')
        # v3.9.55: namespaced art property names. Always set, even
        # to empty, so we explicitly clear any leftover from a previous
        # session of the results window — this is the fix for the
        # "previous item's poster appears briefly" issue.
        self.setProperty('dexhub.results.fanart', _fanart or '')
        self.setProperty('dexhub.results.clearlogo', _clearlogo or '')
        # v3.9.89: _poster is always either a TMDb URL, a vetted addon
        # URL, or the local portrait placeholder — never empty, never
        # landscape — so no extra fallback is needed here.
        self.setProperty('dexhub.results.poster', _poster or '')
        self.setProperty('title', _title)
        self.setProperty('plot', _plot or '')
        self.setProperty('year', _year)
        self.setProperty('rating', _rating)
        self.setProperty('genre', _genre)
        self.setProperty('studio', _studio)
        try:
            home = xbmcgui.Window(10000)
            home.setProperty('dexhub.source.fanart', _fanart)
            home.setProperty('dexhub.source.clearlogo', _clearlogo)
            home.setProperty('dexhub.source.poster', _poster or _fanart or '')
            home.setProperty('dexhub.source.thumb', _poster or _fanart or '')
            home.setProperty('dexhub.source.title', _title)
            home.setProperty('dexhub.source.plot', _plot)
            home.setProperty('dexhub.source.year', _year)
            home.setProperty('dexhub.source.rating', _rating)
            home.setProperty('dexhub.source.genre', _genre)
            home.setProperty('dexhub.source.studio', _studio)
            home.setProperty('dexhub.source.key', _source_art_identity_key(self.meta))
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
        self.setProperty('filters_visible', 'false')
        # Belt-and-braces: also push the poster image directly. Harmless
        # if the XML uses $INFO; covers skins that only honor setImage.
        try:
            self.getControl(200).setImage(_poster or _fanart or 'special://home/addons/plugin.video.dexhub/resources/media/default_video.png')
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
        self._build_filters()
        self._apply_filter('ALL')
        self._update_play_mode_label()
        self._update_loading_state()
        self._start_session_poll()
        # Defer the slow tmdb_direct API call to a background thread so the
        # picker is interactive immediately. If art comes back, it updates
        # the visible window properties via $INFO bindings.
        # v3.9.144: also fire the backfill when hero TEXT is incomplete, not
        # just art — meta_for fills plot/year/genre/rating in the same call.
        _need_art = not (self.meta.get('poster') and self.meta.get('fanart') and self.meta.get('clearlogo'))
        _need_text = not (self.meta.get('plot') and self.meta.get('year') and self.meta.get('genre'))
        if _need_art or _need_text:
            try:
                threading.Thread(target=_backfill_meta_via_network,
                                 args=(self.meta, self),
                                 name='DexHubSourceArtBackfill', daemon=True).start()
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
        try:
            self.setFocusId(2000)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _update_loading_state(self):
        label = tr('جار جلب نتائج إضافية...') if self.getProperty('loading_more') == 'true' else ''
        self.setProperty('loading_label', label)

    def _apply_session_payload(self, payload):
        if not isinstance(payload, dict):
            return
        rows = payload.get('entries') or []
        if isinstance(rows, list):
            self.results = rows
        done = bool(payload.get('done'))
        self.setProperty('loading_more', 'false' if done else 'true')
        # v3.9.263: live provider tally (Fen Light-style) — "AIOStreams: 12 |
        # Torrentio: 8". Updates as each provider's results stream in, so a
        # silent provider is visible at a glance.
        try:
            from resources.lib.plugin import _provider_stats_line
            stats = _provider_stats_line(self.results)
            self.setProperty('dexhub.results.provider_stats', stats)
            self.setProperty('provider_stats', stats)
        except Exception:
            pass
        self._update_loading_state()
        old_active = self.active_filter or 'ALL'
        self._build_filters()
        active = old_active if old_active in set(self.filters or ['ALL']) else 'ALL'
        self._apply_filter(active)

    def _queue_session_payload(self, payload):
        if not isinstance(payload, dict):
            return
        try:
            with self._pending_lock:
                self._pending_payload = payload
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _queue_art_update(self, art):
        if not isinstance(art, dict):
            return
        try:
            with self._pending_lock:
                self._pending_art = art
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _drain_pending_updates(self):
        payload = None
        art = None
        try:
            with self._pending_lock:
                payload = self._pending_payload
                art = self._pending_art
                self._pending_payload = None
                self._pending_art = None
        except Exception:
            payload = None
            art = None
        if art:
            try:
                # Only overwrite when the async fetch actually produced art —
                # never clobber the carried-over backdrop/logo with empty.
                if art.get('poster'):
                    self.setProperty('dexhub.results.poster', art.get('poster'))
                if art.get('fanart'):
                    self.setProperty('dexhub.results.fanart', art.get('fanart'))
                if art.get('clearlogo'):
                    self.setProperty('dexhub.results.clearlogo', art.get('clearlogo'))
                # v3.9.144: hero TEXT filled from the same TMDb meta_for call.
                if art.get('plot'):
                    self.setProperty('plot', art.get('plot'))
                if art.get('year'):
                    self.setProperty('year', art.get('year'))
                if art.get('genre'):
                    self.setProperty('genre', art.get('genre'))
                if art.get('rating'):
                    self.setProperty('rating', art.get('rating'))
                if art.get('studio'):
                    self.setProperty('studio', art.get('studio'))
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
        if payload:
            try:
                self._apply_session_payload(payload)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
    def _has_pending_updates(self):
        try:
            with self._pending_lock:
                return bool(self._pending_payload or self._pending_art)
        except Exception:
            return False

    def _poll_session(self):
        while not self._poll_stop.is_set():
            try:
                payload = source_session.get(self.session_key) or {}
                version = int(payload.get('version') or 0)
                if payload and version != self._session_version:
                    self._session_version = version
                    # Do not mutate Kodi controls from this worker thread
                    # WHILE the user is navigating. Queue the payload; it is
                    # applied either by onAction/onClick on the dialog thread
                    # or by the idle auto-apply below.
                    self._queue_session_payload(payload)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            # v3.9.143: idle auto-apply. Previously queued payloads were
            # drained ONLY inside onAction/onClick — if the user never
            # pressed a key, live results from slow providers never showed
            # and the list looked incomplete. Apply them automatically once
            # the user has been idle for >=1.2s (no navigation race) and no
            # dialog/drawer is in a sensitive state.
            try:
                if (self._has_pending_updates()
                        and not self._closing
                        and not self._mode_dialog_open
                        and (time.monotonic() - self._last_input_ts) >= 1.2
                        and self.getProperty('filters_visible') != 'true'):
                    self._drain_pending_updates()
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            # 1.0s -> 0.4s: fresh rows reach the visible list faster.
            self._poll_stop.wait(0.4)

    def _start_session_poll(self):
        if not self.session_key:
            self.setProperty('loading_more', 'false')
            return
        try:
            payload = source_session.get(self.session_key) or {}
        except Exception:
            payload = {}
        if payload:
            self._session_version = int(payload.get('version') or 0)
            self._apply_session_payload(payload)
        else:
            self.setProperty('loading_more', 'true')
            self._update_loading_state()
        try:
            self._poll_thread = threading.Thread(target=self._poll_session, name='DexHubSourcePoll', daemon=True)
            self._poll_thread.start()
        except RuntimeError as exc:
            # Thread quota exhausted. Do not crash the picker; show the initial
            # results and mark the live background refresh as finished.
            self._poll_thread = None
            self.setProperty('loading_more', 'false')
            self._update_loading_state()
            try:
                xbmc.log('[DexHub] source picker live poll disabled: %s' % exc, xbmc.LOGWARNING)
            except Exception:
                pass

    def _build_filters(self):
        values = ['ALL']
        seen = {'ALL'}
        # Quality filters first so users can quickly narrow by 4K/1080P/HDR/DV.
        for filter_value, _label, _tokens in QUALITY_FILTERS:
            try:
                if any(_row_matches_quality(row, filter_value) for row in self.results if isinstance(row, dict)):
                    seen.add(filter_value)
                    values.append(filter_value)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
        for row in self.results:
            value = _row_provider_filter(row)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        self.filters = values
        items = []
        # --- dexhub-407-patch --- sort entries head the drawer
        for sort_key, _sort_label in SORT_MODES:
            marker = '> ' if sort_key == self.active_sort else '   '
            label = '%s%s' % (marker, _sort_mode_label(sort_key))
            li = xbmcgui.ListItem(label=label)
            li.setProperty('label', label)
            li.setProperty('filter_value', sort_key)
            items.append(li)
        for name in values:
            li = xbmcgui.ListItem(label=_filter_label(name))
            li.setProperty('label', _filter_label(name))
            li.setProperty('filter_value', name)
            items.append(li)
        try:
            control = self.getControl(2100)
            control.reset()
            control.addItems(items)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _results_for_filter(self, filter_value):
        # --- dexhub-407-patch --- filter first, then apply the active sort
        return _sorted_rows(self._filtered_rows(filter_value), getattr(self, 'active_sort', 'S:DEFAULT'))

    def _filtered_rows(self, filter_value):
        if not filter_value or filter_value == 'ALL':
            return list(self.results)
        if str(filter_value).startswith('Q:'):
            return [row for row in self.results if _row_matches_quality(row, filter_value)]
        if str(filter_value).startswith('P:'):
            wanted = str(filter_value)[2:]
            return [row for row in self.results if _row_provider_filter(row) == ('P:%s' % wanted)]
        return [row for row in self.results if _row_provider_filter(row) == ('P:%s' % str(filter_value).strip().upper())]

    def _apply_filter(self, filter_value):
        # --- dexhub-407-patch --- a sort pick changes the order, never the filter
        if str(filter_value or '').startswith('S:'):
            self.active_sort = filter_value
            try:
                ADDON.setSetting('source_sort_mode', filter_value)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            try:
                self._build_filters()
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            filter_value = self.active_filter or 'ALL'
        self.active_filter = filter_value or 'ALL'
        visible = self._results_for_filter(self.active_filter)
        loading = self.getProperty('loading_more') == 'true'
        total_label = str(len(visible))
        if loading:
            total_label = '%s +' % total_label
        self.setProperty('total_results', total_label)
        # --- dexhub-407-patch --- show filter and sort side by side
        _info_bits = []
        if self.active_filter != 'ALL':
            _info_bits.append(_filter_label(self.active_filter))
        if getattr(self, 'active_sort', 'S:DEFAULT') != 'S:DEFAULT':
            _info_bits.append(_sort_mode_label(self.active_sort))
        self.setProperty('filter_info', (u'| %s' % u'  \u00b7  '.join(_info_bits)) if _info_bits else '')
        previous_key = ''
        previous_pos = 0
        try:
            control = self.getControl(2000)
            previous_pos = int(control.getSelectedPosition())
            current_item = control.getSelectedItem()
            previous_key = current_item.getProperty('stream_key') if current_item else ''
        except Exception:
            control = None
        items = []
        restore_idx = -1
        for idx, row in enumerate(visible):
            li = xbmcgui.ListItem(label=_kodi_safe_text(row.get('name') or ''), label2=_kodi_safe_text(row.get('label2') or ''))
            for key in ('highlight', 'quality', 'provider', 'addon', 'source_site', 'extraInfo', 'extraInfo2', 'size_label', 'count', 'name', 'stream_key', 'badges', 'formatter_summary'):
                value = str(row.get(key) or '')
                # Keep internal stream_key untouched; all other values are UI text.
                li.setProperty(key, value if key == 'stream_key' else _kodi_safe_text(value))
            li.setProperty('video_bits', ' | '.join(row.get('video_bits') or []))
            li.setProperty('audio_bits', ' | '.join(row.get('audio_bits') or []))
            tags = row.get('formatter_tags') or []
            # Native fallback: build tags from video_bits/audio_bits when
            # the formatter preset returns fewer than 2 tags. This ensures
            # HDR / DV / Atmos / 4K badges always show even on first launch
            # before the preset JSON has been fetched.
            if len(tags) < 2:
                vb = row.get('video_bits') or []
                ab = row.get('audio_bits') or []
                # Priority-ordered built-in tag palette.
                _NATIVE_TAGS = [
                    # Coordinated palette: one cohesive dark chip background for
                    # every badge, with muted pastel text at a consistent
                    # lightness. Hues still group by category (resolution=cool,
                    # HDR=warm, codec=sage, audio=lavender, source=soft) but the
                    # saturation is dialed down so nothing looks neon / garish.
                    # Resolution (cool)
                    ('2160P', 'FF1A1E2A', 'FF8AC5DC'), ('4K', 'FF1A1E2A', 'FF8AC5DC'),
                    ('1080P', 'FF1A1B2A', 'FF9AAEDC'), ('720P', 'FF18201E', 'FF8AC8B4'),
                    # HDR / DV (warm, muted amber/mauve)
                    ('DV',    'FF1E1A2A', 'FFBBA6D6'),
                    ('HDR10+','FF221C14', 'FFD8B488'), ('HDR10', 'FF221C14', 'FFD8B488'),
                    ('HDR',   'FF221C14', 'FFD8B488'),
                    # Codec (muted sage / teal)
                    ('HEVC', 'FF181F1A', 'FF96C2A6'), ('AV1', 'FF181F1C', 'FF8CC0AE'),
                    ('H264', 'FF1B1E18', 'FFAEC596'),
                    # Audio (muted lavender family)
                    ('ATMOS',  'FF1C1828', 'FFC2AEDA'),
                    ('TRUEHD', 'FF1C1828', 'FFB6A8D6'),
                    ('DTS-HD', 'FF181C26', 'FF9CB4D6'),
                    ('DTS-X',  'FF181C26', 'FF9CB4D6'),
                    ('DTS',    'FF181C26', 'FF9CB4D6'),
                    ('DD+',    'FF1A1B24', 'FFA6AECE'),
                    ('DD-EX',  'FF1A1B24', 'FFA6AECE'),
                    ('7.1',    'FF1A1B22', 'FFAEB2C6'),
                    ('5.1',    'FF1A1B22', 'FFAEB2C6'),
                    # Source (soft coral / blue / sage)
                    ('REMUX',   'FF231819', 'FFD69C9C'),
                    ('BLURAY',  'FF181C26', 'FF9CB0D6'),
                    ('WEB-DL',  'FF181F1C', 'FF9EC2A8'),
                    ('WEBDL',   'FF181F1C', 'FF9EC2A8'),
                    ('WEBRIP',  'FF1A1F18', 'FFAEC596'),
                    # Other (soft gold / teal)
                    ('DUBBED',  'FF211F16', 'FFD4CC9A'),
                    ('MULTI',   'FF182022', 'FF9AC6C6'),
                    ('SUBS',    'FF182022', 'FF9AC6C6'),
                ]
                seen = {t.get('text', '').upper() for t in tags}
                all_bits_up = [b.upper() for b in (vb + ab)]
                for key, bg, fg in _NATIVE_TAGS:
                    if key in all_bits_up and key not in seen:
                        tags = list(tags) + [{'text': key, 'bg': bg, 'fg': fg}]
                        seen.add(key)
                    if len(tags) >= 8:
                        break
            for tag_idx in range(8):
                tag = tags[tag_idx] if tag_idx < len(tags) and isinstance(tags[tag_idx], dict) else {}
                n = tag_idx + 1
                li.setProperty('fmt%d_text' % n, _kodi_safe_text(tag.get('text') or ''))
                li.setProperty('fmt%d_bg' % n, str(tag.get('bg') or 'FF2B2F3E'))
                li.setProperty('fmt%d_fg' % n, str(tag.get('fg') or 'FFF2F4FB'))
            elite_images = _elite_badge_images(row, tags=tags, max_items=8)
            for badge_idx in range(8):
                li.setProperty('elite_badge%d' % (badge_idx + 1), elite_images[badge_idx] if badge_idx < len(elite_images) else '')
            li.setProperty('source_info', _kodi_safe_text(row.get('source_info') or ''))
            items.append(li)
            if previous_key and str(row.get('stream_key') or '') == previous_key:
                restore_idx = idx
        try:
            control = control or self.getControl(2000)
            control.reset()
            control.addItems(items)
            if items:
                if restore_idx < 0:
                    restore_idx = min(max(previous_pos, 0), len(items) - 1)
                control.selectItem(restore_idx)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _guard_action(self, name, interval=0.6):
        # Bumped from 0.35s to 0.6s to give modal dialogs time to fully
        # transfer focus before the next action is allowed.
        now = time.monotonic()
        prev = float(self._action_guard.get(name) or 0.0)
        if (now - prev) < interval:
            return True
        self._action_guard[name] = now
        return False

    def _play_mode_label(self):
        if self.play_mode == MODE_PLAY_SUBS:
            return tr('تشغيل مع ترجمة')
        return tr('تشغيل')

    def _update_play_mode_label(self):
        self.setProperty('play_mode_label', self._play_mode_label())

    def _pick_play_mode(self):
        if self._closing or self._mode_dialog_open:
            return
        self._mode_dialog_open = True
        try:
            options = [
                (tr('تشغيل فقط'), MODE_PLAY),
                (tr('تشغيل مع ترجمة'), MODE_PLAY_SUBS),
            ]
            idx = xbmcgui.Dialog().select(tr('وضع التشغيل'), [label for label, _ in options])
            if idx >= 0:
                self.play_mode = options[idx][1]
                self._update_play_mode_label()
        finally:
            self._mode_dialog_open = False
            # v3.9.33: re-stamp the 'mode' action guard with NOW so any
            # pending Kodi event for the original OK press (which fired
            # both onAction AND onClick for the same physical button
            # press) is suppressed for the next 0.6s. Without this, if
            # the user spent >0.6s deciding inside the picker, the
            # tail-end onClick(2200) would slip past the guard and
            # reopen the picker immediately. Fixes the "Playmode opens
            # twice" report.
            self._action_guard['mode'] = time.monotonic()
        try:
            self.setFocusId(2000)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def _resolve_choice_mode(self):
        return self.play_mode

    def _choose(self):
        # Hard guards against the OK-press double-event:
        #   1. window is already closing → drop
        #   2. play-mode dialog is currently up → drop (the in-flight call owns it)
        #   3. selection was already finalized → drop
        if self._closing or self._mode_dialog_open or self.selected:
            return
        try:
            item = self.getControl(2000).getSelectedItem()
        except Exception:
            item = None
        stream_key = item.getProperty('stream_key') if item else None
        if not stream_key:
            return
        chosen_mode = self._resolve_choice_mode()
        if not chosen_mode:
            return
        # Re-check after the modal returns — if something else finalized a
        # selection in the meantime, do not double-fire.
        if self._closing or self.selected:
            return
        self.selected = stream_key
        self.play_with_subtitles = (chosen_mode == MODE_PLAY_SUBS)
        self._closing = True
        self._shutdown()
        self.close()

    def _show_info(self):
        try:
            focus_id = self.getFocusId()
        except Exception:
            focus_id = 2000
        if focus_id == 2100:
            text = tr('Filter: %s') % _filter_label(self.active_filter)
            xbmcgui.Dialog().textviewer('Dex Hub', tr(text))
            return
        try:
            item = self.getControl(2000).getSelectedItem()
        except Exception:
            item = None
        if not item:
            return
        text = item.getProperty('source_info') or item.getProperty('name') or ''
        xbmcgui.Dialog().textviewer('Dex Hub', tr(text))

    def _apply_selected_filter(self):
        try:
            item = self.getControl(2100).getSelectedItem()
        except Exception:
            item = None
        filter_value = item.getProperty('filter_value') if item else 'ALL'
        self._apply_filter(filter_value)
        self.setProperty('filters_visible', 'false')
        try:
            self.setFocusId(2000)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def onFocus(self, controlId):
        self._last_input_ts = time.monotonic()
        # v3.9.142: belt-and-braces drawer collapse. If focus lands on any
        # control other than the filters list while the drawer is open
        # (RIGHT, remote shortcut, mouse, whatever route), close it. This
        # guarantees the drawer never stays painted over the results.
        try:
            if controlId != 2100 and self.getProperty('filters_visible') == 'true':
                self.setProperty('filters_visible', 'false')
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)

    def onClick(self, controlId):
        self._last_input_ts = time.monotonic()
        self._drain_pending_updates()
        if self._closing or self._mode_dialog_open:
            return
        if controlId == 2000:
            if not self._guard_action('choose'):
                self._choose()
        elif controlId == 2100:
            if not self._guard_action('filter'):
                self._apply_selected_filter()
        elif controlId == 2200:
            if not self._guard_action('mode'):
                self._pick_play_mode()

    def onAction(self, action):
        self._last_input_ts = time.monotonic()
        self._drain_pending_updates()
        if self._closing or self._mode_dialog_open:
            # While the play-mode picker is up (or after a successful pick),
            # ignore every action to prevent stacked dialogs.
            return
        action_id = action.getId()
        try:
            focus_id = self.getFocusId()
        except Exception:
            focus_id = 2000
        if action_id in ACTION_BACK:
            if focus_id == 2100 and self.getProperty('filters_visible') == 'true':
                self.setProperty('filters_visible', 'false')
                try:
                    self.setFocusId(2000)
                except Exception as _silent_exc:
                    log.silent('RESULTS_WIN', _silent_exc)
                return
            self.selected = None
            self._closing = True
            self._shutdown()
            self.close()
            return
        if action_id in ACTION_INFO or action_id in ACTION_CONTEXT:
            self._show_info()
            return
        if focus_id == 2100 and action_id in ACTION_RIGHT:
            # v3.9.143: RIGHT = close the drawer only and return to the
            # results — do NOT apply the filter under the cursor. Applying
            # on RIGHT surprised users: peeking at the drawer and leaving
            # it silently changed the visible results. Apply happens only
            # on SELECT/click.
            self.setProperty('filters_visible', 'false')
            try:
                self.setFocusId(2000)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            return
        if focus_id == 2100 and action_id in ACTION_SELECT:
            if not self._guard_action('filter'):
                self._apply_selected_filter()
            return
        if focus_id == 2200 and action_id in ACTION_SELECT:
            if not self._guard_action('mode'):
                self._pick_play_mode()
            return
        if focus_id == 2000 and action_id in ACTION_SELECT:
            if not self._guard_action('choose'):
                self._choose()
            return
        if focus_id == 2000 and action_id in ACTION_LEFT and len(self.filters) > 1:
            self.setProperty('filters_visible', 'true')
            xbmc.sleep(20)
            try:
                self.setFocusId(2100)
            except Exception as _silent_exc:
                log.silent('RESULTS_WIN', _silent_exc)
            return

    def _shutdown(self):
        try:
            self._poll_stop.set()
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
        try:
            if self._poll_thread and self._poll_thread.is_alive():
                self._poll_thread.join(0.2)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
        # v3.9.34: clear stale art properties from the home window so the
        # next SourcesWindow opening for a DIFFERENT item doesn't briefly
        # show the previous item's poster/clearlogo/fanart before the
        # new onInit() can populate them. The bug: home window keeps
        # `dexhub.source.poster` etc set between window opens, and the
        # skin reads them as $INFO bindings; if the user picked item A,
        # closed the picker, then opened item B, the half-second between
        # the new picker's open and its onInit setting fresh values
        # showed A's art.
        try:
            home = xbmcgui.Window(10000)
            for key in (
                'dexhub.source.fanart', 'dexhub.source.clearlogo',
                'dexhub.source.poster', 'dexhub.source.thumb',
                'dexhub.source.title',  'dexhub.source.plot',
                'dexhub.source.year',   'dexhub.source.rating',
                'dexhub.source.genre',  'dexhub.source.studio',
            ):
                try:
                    home.clearProperty(key)
                except Exception as _silent_exc:
                    log.silent('RESULTS_WIN', _silent_exc)
        except Exception as _silent_exc:
            log.silent('RESULTS_WIN', _silent_exc)
    def run(self):
        self.doModal()
        self._shutdown()
        return {
            'stream_key': self.selected,
            'play_with_subtitles': self.play_with_subtitles,
            'play_mode': self.play_mode,
        }


def open_sources_window(results, meta, play_mode=MODE_ASK, session_key=''):
    skin_xml = 'sources_results.xml'
    win = SourcesWindow(skin_xml, ADDON_PATH, 'Default', '1080i', results=results, meta=meta, play_mode=play_mode, session_key=session_key)
    try:
        return win.run()
    finally:
        del win
