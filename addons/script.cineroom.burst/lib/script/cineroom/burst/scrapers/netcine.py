# -*- coding: utf-8 -*-
"""
Scraper para NetCine — CineRoom Lite (Burst)
Resolve a URL do player HLS diretamente, sem depender do resolveurl.fork.
"""

import re
import difflib
import xbmc
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, quote, unquote, urlsplit, urlunsplit
from html import unescape
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WEBSITE = 'NetCine'
from .scraper_config import get_url
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/130.0.0.0 Safari/537.36'
)
ORIGINAL_BASE = get_url('netcine', fallback='https://eee1.lat')

_session = requests.Session()
_session.verify = False
_session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Referer': ORIGINAL_BASE + '/',
})

# Timeout por request, configurável via settings.xml (scraper.timeout).
# Atualizado no início de cada scrape(); usado como default por todas as
# chamadas internas deste módulo.
_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _normalize_url(url):
    if not url:
        return url
    try:
        url = unescape(url).strip()
        parts = urlsplit(url)
        path = quote(unquote(parts.path), safe='/:%')
        query = quote(unquote(parts.query), safe='=&?/:+')
        return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
    except Exception:
        return url


def _get_host(base_url):
    try:
        r = _session.get(base_url, allow_redirects=True, timeout=_TIMEOUT)
        final = r.url.rstrip('/')
        if 'netcine' in final.lower() or 'eee' in final.lower() or 'nnn' in final.lower():
            return final + '/'
    except Exception:
        pass
    return base_url.rstrip('/') + '/'


def _clean_title(title):
    return re.sub(r'[:\-—]', ' ', title).strip()


def _find_titles_from_item(item_data):
    """
    Obtém título PT, título original e ano via TMDB.
    Usa item_data como fallback imediato se a chamada TMDB falhar.
    """
    title_pt       = item_data.get('title', '')
    original_title = item_data.get('original_title', '') or item_data.get('romaji_title', '')
    year           = str(item_data.get('year', ''))
    tmdb_id        = item_data.get('tmdb_id')
    media_type     = item_data.get('media_type', 'movie')

    if tmdb_id:
        try:
            import xbmcaddon
            api_key = xbmcaddon.Addon('plugin.video.cineroom.lite').getSetting('tmdb_api_key')
            if api_key:
                endpoint = 'movie' if media_type == 'movie' else 'tv'
                r = _session.get(
                    f'https://api.themoviedb.org/3/{endpoint}/{tmdb_id}',
                    params={'api_key': api_key, 'language': 'pt-BR'},
                    timeout=_TIMEOUT
                )
                if r.ok:
                    data = r.json()
                    title_pt       = data.get('title') or data.get('name') or title_pt
                    original_title = data.get('original_title') or data.get('original_name') or original_title
                    release        = data.get('release_date') or data.get('first_air_date') or ''
                    year           = release[:4] or year
        except Exception:
            pass

    return title_pt, original_title, year


def _get_players(page_url, host):
    sources = []
    try:
        r = _session.get(page_url, timeout=_TIMEOUT)
        soup = BeautifulSoup(r.text, 'html.parser')
        tabs = soup.select('#player-container .player-menu li a')
        for tab in tabs:
            text = tab.get_text(strip=True).upper()
            tab_id = tab['href'].lstrip('#')
            iframe = soup.select_one(f'#{tab_id} iframe')
            if not iframe or not iframe.get('src'):
                continue
            src = iframe['src']
            if src.startswith('//'):
                src = 'https:' + src
            elif not src.startswith('http'):
                src = urljoin(page_url, src)
            lang = (
                'DUBLADO'
                if any(x in text for x in ['DUBLAD', 'DUB', 'ÁUDIO'])
                else 'LEGENDADO'
            )
            sources.append((lang, src))
    except Exception as e:
        xbmc.log(f'[NetCine] Erro ao extrair players de {page_url}: {e}', xbmc.LOGERROR)
    return sources


def _resolve_player(iframe_url):
    iframe_url = _normalize_url(iframe_url)

    if 'hlsarchive.php' in iframe_url or 'nv32.php' in iframe_url:
        parsed_tmp = urlparse(iframe_url)
        params = parse_qs(parsed_tmp.query)
        n = params.get('n', [''])[0]
        p = params.get('p', [''])[0]
        if n and p:
            iframe_url = _normalize_url(
                f'{parsed_tmp.scheme}://{parsed_tmp.netloc}'
                f'/media-player/hls/hls.php?n={n}&p={p}'
            )

    elif 'nv32mono.php' in iframe_url or 'mono.php' in iframe_url:
        parsed_tmp = urlparse(iframe_url)
        params = parse_qs(parsed_tmp.query)
        n = params.get('n', [''])[0]
        p = params.get('p', [''])[0]
        if n and p:
            iframe_url = _normalize_url(
                f'{parsed_tmp.scheme}://{parsed_tmp.netloc}'
                f'/media-player/dist/playermono.php?n={n}&p={p}'
            )

    parsed = urlparse(iframe_url)
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': f'{parsed.scheme}://{parsed.netloc}/',
        'Origin': f'{parsed.scheme}://{parsed.netloc}',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    }

    try:
        r = _session.get(iframe_url, headers=headers, timeout=_TIMEOUT)
        html = r.text
    except Exception as e:
        xbmc.log(f'[NetCine] Erro ao obter player {iframe_url}: {e}', xbmc.LOGERROR)
        return ''

    # 1. <source type="application/x-mpegURL"> — ambas as ordens de atributos
    hls_match = re.search(
        r'<source[^>]+type=["\']application/x-mpegURL["\'][^>]+src=["\']([^"\']+)["\']',
        html, re.I
    ) or re.search(
        r'<source[^>]+src=["\']([^"\']+)["\'][^>]+type=["\']application/x-mpegURL["\']',
        html, re.I
    )
    if hls_match:
        hls_url = _normalize_url(hls_match.group(1))
        xbmc.log(f'[NetCine] HLS via <source>: {hls_url[:80]}', xbmc.LOGINFO)
        return _build_stream_string(hls_url, parsed)

    # 2. Qualquer <source src="...">
    sources = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if sources:
        chosen = _normalize_url(sources[-1])
        xbmc.log(f'[NetCine] HLS via <source> genérico: {chosen[:80]}', xbmc.LOGINFO)
        return _build_stream_string(chosen, parsed)

    # 3. Fallback: playerhls.php
    try:
        params = parse_qs(parsed.query)
        n = params.get('n', [''])[0]
        p = params.get('p', [''])[0]
        if n and p:
            fallback_url = _normalize_url(
                f'{parsed.scheme}://{parsed.netloc}/media-player/dist/playerhls.php?n={n}&p={p}'
            )
            xbmc.log(f'[NetCine] Tentando fallback: {fallback_url}', xbmc.LOGDEBUG)
            try:
                fb = _session.get(fallback_url, headers=headers, timeout=_TIMEOUT)
                text = fb.text
            except Exception:
                text = ''

            if text.strip().startswith('#EXTM3U'):
                xbmc.log(f'[NetCine] HLS via playerhls.php: {fallback_url[:80]}', xbmc.LOGINFO)
                return _build_stream_string(fallback_url, parsed)

            mp4 = re.findall(r'(https?://[^\s"\']+?\.mp4(?:\?[^\s"\']+)?)', text, re.I)
            if mp4:
                xbmc.log(f'[NetCine] MP4 via fallback: {mp4[-1][:80]}', xbmc.LOGINFO)
                return _build_stream_string(mp4[-1], parsed)
    except Exception as e:
        xbmc.log(f'[NetCine] Erro no fallback: {e}', xbmc.LOGWARNING)

    xbmc.log(f'[NetCine] Não resolvido: {iframe_url[:80]}', xbmc.LOGWARNING)
    return ''


def _build_stream_string(stream_url, parsed_player):
    """Monta 'url|headers' no formato inputstream.adaptive."""
    phpsessid = _session.cookies.get('PHPSESSID', '')
    h = {
        'User-Agent': USER_AGENT,
        'Referer': f'{parsed_player.scheme}://{parsed_player.netloc}/',
        'Origin': f'{parsed_player.scheme}://{parsed_player.netloc}',
    }
    if phpsessid:
        h['Cookie'] = f'PHPSESSID={phpsessid}'
    header_str = '&'.join(f'{k}={quote(v)}' for k, v in h.items())
    return f'{stream_url}|{header_str}'


def _search_site(host, search_title, year, want_tvshow):
    clean = _clean_title(search_title)
    search_url = host + 'search/' + quote_plus(clean) + '/'
    try:
        r = _session.get(search_url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('#box_movies .movie')
        for item in items:
            a = item.select_one('.imagen a')
            if not a:
                continue
            href = urljoin(host, a['href'])
            if ('/tvshows/' in href) != want_tvshow:
                continue

            year_span = item.select_one('span.year')
            raw_year = year_span.get_text(strip=True) if year_span else ''
            m = re.search(r'\d{4}', raw_year)
            page_year = m.group(0) if m else raw_year
            if page_year != year:
                continue

            h2 = item.select_one('h2')
            page_title = h2.get_text(strip=True) if h2 else ''
            clean_page = re.sub(
                r'(?i)\s*(dublado|legendado|hd|4k|1080p|720p|cam|ts).*', '', page_title
            ).strip()
            sim = difflib.SequenceMatcher(
                None, search_title.lower(), clean_page.lower()
            ).ratio()
            if sim >= 0.5:
                return href
    except Exception as e:
        xbmc.log(f'[NetCine] Erro na busca "{search_title}": {e}', xbmc.LOGERROR)
    return None


def _build_sources(iframe_list, media_type, season=None, episode=None):
    sources = []
    ep_code = ''
    if media_type == 'tvshow' and season is not None and episode is not None:
        ep_code = f'S{int(season):02d}E{int(episode):02d}'

    for lang, src in iframe_list:
        resolved = _resolve_player(src)
        if not resolved:
            xbmc.log(f'[NetCine] Sem stream resolvido para {src}', xbmc.LOGDEBUG)
            continue

        stream_url, _, headers_str = resolved.partition('|')

        quality = '1080p'
        if any(x in stream_url.lower() for x in ('4k', '2160', 'uhd')):
            quality = '4K'

        sources.append({
            'url':              stream_url,
            'quality':          quality,
            'type':             'Direto',
            'provider':         WEBSITE,
            'languages':        lang,
            'release_title':    ep_code or '',
            'label':            f'{WEBSITE} • {lang} [{quality}]',
            'size':             'N/A',
            'seeders':          0,
            'extras':           [],
            'headers':          headers_str,
            'manifest_type':    'hls',
            'inputstreamaddon': 'inputstream.adaptive',
        })

    return sources


# ---------------------------------------------------------------------------
# Entry point (padrão Burst)
# ---------------------------------------------------------------------------

def scrape(provider_url, item_data, season=None, episode=None, timeout=None):
    global _TIMEOUT
    if timeout:
        _TIMEOUT = timeout

    _session.cookies.clear()
    media_type = item_data.get('media_type', 'movie')

    host = _get_host(provider_url or ORIGINAL_BASE)
    xbmc.log(f'[NetCine] Host resolvido: {host}', xbmc.LOGDEBUG)

    title_pt, original_title, year = _find_titles_from_item(item_data)
    if not year:
        xbmc.log(f'[NetCine] Ano não disponível para tmdb={item_data.get("tmdb_id")}', xbmc.LOGWARNING)
        return []

    xbmc.log(f'[NetCine] Títulos: "{title_pt}" / "{original_title}" ({year})', xbmc.LOGDEBUG)

    search_titles = []
    if title_pt:
        search_titles.append(title_pt)
    if original_title and original_title != title_pt:
        search_titles.append(original_title)

    if not search_titles:
        xbmc.log('[NetCine] Sem títulos para busca, abortando.', xbmc.LOGDEBUG)
        return []

    # ── FILME ────────────────────────────────────────────────────────────────
    if media_type == 'movie':
        for title in search_titles:
            href = _search_site(host, title, year, want_tvshow=False)
            if not href:
                continue
            players = _get_players(href, host)
            if players:
                xbmc.log(f'[NetCine] Filme: {len(players)} player(s) em {href}', xbmc.LOGINFO)
                sources = _build_sources(players, media_type)
                if sources:
                    return sources
        xbmc.log(f'[NetCine] Filme tmdb={item_data.get("tmdb_id")} sem stream resolvido.', xbmc.LOGDEBUG)
        return []

    # ── SÉRIE ─────────────────────────────────────────────────────────────────
    if media_type == 'tvshow':
        if season is None or episode is None:
            xbmc.log('[NetCine] Série sem season/episode, abortando.', xbmc.LOGDEBUG)
            return []

        season_int  = int(season)
        episode_int = int(episode)
        patterns = [
            f'{season_int} - {episode_int}',
            f'{season_int} - {episode_int:02d}',
            f'{season_int}x{episode_int:02d}',
            f'{season_int}x{episode_int}',
        ]

        for title in search_titles:
            series_href = _search_site(host, title, year, want_tvshow=True)
            if not series_href:
                continue

            try:
                r = _session.get(series_href, timeout=_TIMEOUT)
                soup = BeautifulSoup(r.text, 'html.parser')
            except Exception as e:
                xbmc.log(f'[NetCine] Erro ao carregar série {series_href}: {e}', xbmc.LOGERROR)
                continue

            episode_url = None
            for link in soup.select('a[href*="/episode/"]'):
                link_text = link.get_text(strip=True)
                for pat in patterns:
                    if pat in link_text:
                        episode_url = urljoin(host, link['href'])
                        break
                if episode_url:
                    break

            if not episode_url:
                xbmc.log(
                    f'[NetCine] S{season_int:02d}E{episode_int:02d} não encontrado em {series_href}',
                    xbmc.LOGDEBUG
                )
                continue

            players = _get_players(episode_url, host)
            if players:
                sources = _build_sources(players, media_type, season_int, episode_int)
                if sources:
                    xbmc.log(
                        f'[NetCine] Série S{season_int:02d}E{episode_int:02d}: {len(sources)} fonte(s)',
                        xbmc.LOGINFO
                    )
                    return sources

        xbmc.log(
            f'[NetCine] Série tmdb={item_data.get("tmdb_id")} S{season_int:02d}E{episode_int:02d} não encontrada.',
            xbmc.LOGDEBUG
        )
        return []

    return []