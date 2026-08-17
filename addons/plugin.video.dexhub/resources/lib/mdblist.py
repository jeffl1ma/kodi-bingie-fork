# -*- coding: utf-8 -*-
import json
import re
import urllib.parse
import urllib.request

import xbmc
import xbmcaddon

# --- dexhub-401-patch ---
try:
    from .settings_cache import cached_addon as _dh_cached_addon
except Exception:
    try:
        from settings_cache import cached_addon as _dh_cached_addon
    except Exception:
        _dh_cached_addon = None
ADDON = _dh_cached_addon() if _dh_cached_addon else xbmcaddon.Addon()
API = 'https://api.mdblist.com'
_URL_RE = re.compile(r'^/lists/(?P<username>[^/]+)/(?P<slug>[^/?#]+)')
_CACHE = {}
_CACHE_TTL = 300


def _setting(key, default=''):
    try:
        return ADDON.getSetting(key) or default
    except Exception:
        return default


def _headers():
    return {
        'Accept': 'application/json',
        'User-Agent': 'DexHub/%s (Kodi)' % (ADDON.getAddonInfo('version') or '3.8.9'),
    }


def _request(path, params=None, timeout=20):
    import time as _time
    params = dict(params or {})
    api_key = (_setting('mdblist_api_key', '') or '').strip()
    if api_key and 'apikey' not in params:
        params['apikey'] = api_key
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    cache_key = url
    cached = _CACHE.get(cache_key)
    if cached and (_time.time() - cached[0]) <= _CACHE_TTL:
        return cached[1], cached[2]
    req = urllib.request.Request(url, headers=_headers(), method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8', 'ignore')
        data = json.loads(body) if body else {}
        has_more = str(resp.headers.get('X-Has-More') or '').strip().lower() == 'true'
        _CACHE[cache_key] = (_time.time(), data, has_more)
        return data, has_more


def parse_list_url(url):
    url = (url or '').strip()
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or '').lower()
    if 'mdblist.com' not in host:
        return None
    match = _URL_RE.match(parsed.path or '')
    if not match:
        return None
    username = urllib.parse.unquote(match.group('username') or '').strip()
    slug = urllib.parse.unquote(match.group('slug') or '').strip()
    if not username or not slug:
        return None
    return {
        'username': username,
        'slug': slug,
        'url': 'https://mdblist.com/lists/%s/%s' % (
            urllib.parse.quote(username), urllib.parse.quote(slug)
        ),
    }


def fetch_list(username, slug):
    data, _ = _request('/lists/%s/%s' % (
        urllib.parse.quote(str(username or '').strip()),
        urllib.parse.quote(str(slug or '').strip()),
    ))
    if isinstance(data, list) and data:
        return data
    if isinstance(data, dict):
        return [data]
    return []


def fetch_items(username, slug, media_filter='auto', cursor='', limit=100):
    username = str(username or '').strip()
    slug = str(slug or '').strip()
    mf = str(media_filter or 'auto').strip().lower()
    params = {'limit': int(limit or 100)}
    if cursor:
        params['cursor'] = cursor
    if mf in ('movie', 'movies'):
        path = '/lists/%s/%s/items/movie' % (urllib.parse.quote(username), urllib.parse.quote(slug))
    elif mf in ('show', 'shows', 'series', 'tv', 'anime'):
        path = '/lists/%s/%s/items/show' % (urllib.parse.quote(username), urllib.parse.quote(slug))
    else:
        path = '/lists/%s/%s/items' % (urllib.parse.quote(username), urllib.parse.quote(slug))
        params['unified'] = 'true'
    data, has_more = _request(path, params=params)
    rows = []
    next_cursor = ''
    if isinstance(data, dict):
        next_cursor = str(data.get('next_cursor') or data.get('cursor') or '').strip()
        for row in (data.get('movies') or []):
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault('_type', 'movie')
                rows.append(item)
        for row in (data.get('shows') or []):
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault('_type', 'show')
                rows.append(item)
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault('_type', 'movie' if mf in ('movie', 'movies') else 'show')
                rows.append(item)
    return rows, (next_cursor if (next_cursor or has_more) else '')
