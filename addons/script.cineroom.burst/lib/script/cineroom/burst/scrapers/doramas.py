# -*- coding: utf-8 -*-
"""
Scraper para Doramas Online — CineRoom Lite (Burst)

Fluxo completo:
  1. doramasonline.co/serie/{slug}   → extrai iframe seriesboa.live/embed/{tmdb_id}
  2. seriesboa.live/embed/{tmdb_id}  → lista episódios com data-episode-id
  3. seriesboa.live/episodio/{id}    → botões data-show-player com data-source
  4. Resolve cada data-source (iframe embed) para URL de stream

Providers suportados:
  - embedplay.ezplayer.me  (VidStack-like, iframe)
  - embedplayleg.p2pstream.vip  (VidStack-like, iframe)
  - vsembed.ru  (TMDB direto, mais confiável)
"""

import re
import xbmc
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote

WEBSITE    = 'Doramas'
from .scraper_config import get_url
BASE_URL   = get_url('doramas', fallback='https://doramasonline.co')
PLAYER_URL = get_url('doramas', key='player_url', fallback='https://seriesboa.live')
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

_session = requests.Session()
_session.headers.update({
    'User-Agent':      USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Referer':         BASE_URL + '/',
})


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _get(url, referer=None, timeout=15):
    """GET com tratamento de erro centralizado."""
    headers = {}
    if referer:
        headers['Referer'] = referer
    try:
        r = _session.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        xbmc.log(f'[Doramas] GET falhou {url}: {e}', xbmc.LOGWARNING)
        return None


def _soup(response):
    """Converte response em BeautifulSoup."""
    if not response:
        return None
    return BeautifulSoup(response.text, 'html.parser')


def _build_stream_string(stream_url, referer_url):
    """Monta 'url|headers' no formato inputstream.adaptive."""
    parsed = urlparse(referer_url)
    origin = f'{parsed.scheme}://{parsed.netloc}'
    headers = {
        'User-Agent': USER_AGENT,
        'Referer':    referer_url,
        'Origin':     origin,
    }
    header_str = '&'.join(f'{k}={quote(v)}' for k, v in headers.items())
    return f'{stream_url}|{header_str}'


# ---------------------------------------------------------------------------
# Etapa 1 — Busca da série no doramasonline.co
# ---------------------------------------------------------------------------

def _search_serie(query):
    """
    Busca a série no doramasonline.co.
    Retorna a URL da página da série ou None.
    """
    url = f'{BASE_URL}/?s={quote(query)}'
    r   = _get(url)
    doc = _soup(r)
    if not doc:
        return None

    for item in doc.select('ul.post-lst li'):
        a = item.select_one('a.lnk-blk')
        if a and '/serie/' in a.get('href', ''):
            return a['href']
    return None


def _get_embed_id(serie_url):
    """
    Extrai o ID do embed seriesboa.live da página da série.
    Ex: <iframe src="https://seriesboa.live/embed/310024"> → '310024'
    """
    r   = _get(serie_url)
    doc = _soup(r)
    if not doc:
        return None

    iframe = doc.select_one('iframe[src*="seriesboa.live/embed/"]')
    if not iframe:
        return None

    src = iframe.get('src', '')
    m   = re.search(r'/embed/(\d+)', src)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Etapa 2 — Lista de episódios do embed
# ---------------------------------------------------------------------------

def _get_episode_id(embed_id, target_season, target_episode):
    """
    Acessa seriesboa.live/embed/{embed_id} e encontra o data-episode-id
    correspondente à temporada/episódio solicitados.

    O embed organiza episódios por card (ex: "Legendado", "Dublado").
    Cada <li> tem data-season-id e data-episode-id.
    Retorna o primeiro data-episode-id compatível.
    """
    url = f'{PLAYER_URL}/embed/{embed_id}'
    r   = _get(url, referer=BASE_URL + '/')
    doc = _soup(r)
    if not doc:
        return None

    # Mapeia data-season-id → número da temporada
    season_map = {}
    for li in doc.select('ul.header-navigation li[data-season-id]'):
        sid  = li.get('data-season-id', '')
        snum = li.get('data-season-number', '1')
        try:
            season_map[sid] = int(snum)
        except ValueError:
            season_map[sid] = 1

    # Percorre episódios e encontra o correto
    episode_counter = {}  # season_id → contador de episódios vistos
    for li in doc.select('li[data-episode-id]'):
        sid    = li.get('data-season-id', '')
        ep_id  = li.get('data-episode-id', '')
        if not ep_id or sid not in season_map:
            continue

        snum = season_map[sid]
        if snum != int(target_season):
            continue

        # Incrementa contador de episódios desta temporada
        episode_counter[sid] = episode_counter.get(sid, 0) + 1
        ep_num = episode_counter[sid]

        # Tenta também extrair número do texto do link
        link_text = li.get_text(strip=True)
        m = re.search(r'\d+', link_text)
        if m:
            ep_num = int(m.group(0))

        if ep_num == int(target_episode):
            xbmc.log(
                f'[Doramas] Episódio encontrado: S{target_season:02d}E{target_episode:02d} '
                f'→ episode_id={ep_id}',
                xbmc.LOGDEBUG
            )
            return ep_id

    return None


# ---------------------------------------------------------------------------
# Etapa 3 — Sources do episódio
# ---------------------------------------------------------------------------

def _get_sources_from_episode(episode_id):
    """
    Acessa seriesboa.live/episodio/{episode_id} e extrai todos os
    data-source dos botões de player.

    Retorna lista de dicts: [{'source': url, 'type': 'iframe', 'label': '...'}]
    """
    url = f'{PLAYER_URL}/episodio/{episode_id}'
    r   = _get(url, referer=f'{PLAYER_URL}/')
    doc = _soup(r)
    if not doc:
        return []

    sources = []
    for btn in doc.select('button[data-show-player][data-source]'):
        src   = btn.get('data-source', '').strip()
        btype = btn.get('data-type', 'iframe').strip()
        label = btn.get_text(strip=True)
        if src:
            sources.append({'source': src, 'type': btype, 'label': label})

    xbmc.log(f'[Doramas] {len(sources)} source(s) em episodio/{episode_id}', xbmc.LOGDEBUG)
    return sources


# ---------------------------------------------------------------------------
# Etapa 4 — Resolvers de embed
# ---------------------------------------------------------------------------

def _resolve_vsembed(source_url):
    """
    vsembed.ru usa parâmetros TMDB diretos.
    Tenta extrair m3u8/mp4 da resposta.
    """
    r = _get(source_url, referer=f'{PLAYER_URL}/')
    if not r:
        return ''

    html = r.text

    # Procura m3u8
    m = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] vsembed m3u8: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, source_url)

    # Procura mp4
    m = re.search(r'["\']([^"\']+\.mp4[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] vsembed mp4: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, source_url)

    xbmc.log(f'[Doramas] vsembed sem stream: {source_url[:80]}', xbmc.LOGWARNING)
    return ''


def _resolve_embedplay(source_url):
    """
    embedplay.ezplayer.me e embedplayleg.p2pstream.vip — VidStack-like.
    Faz GET com Referer correto e procura file/src/m3u8 no HTML/JS.
    """
    parsed  = urlparse(source_url)
    referer = f'{parsed.scheme}://{parsed.netloc}/'

    r = _get(source_url, referer=f'{PLAYER_URL}/')
    if not r:
        return ''

    html = r.text

    # Padrão 1: file: 'url' ou file: "url"
    m = re.search(r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] embedplay file m3u8: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, referer)

    # Padrão 2: src: 'url'
    m = re.search(r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] embedplay src m3u8: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, referer)

    # Padrão 3: qualquer m3u8 na página
    m = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] embedplay genérico m3u8: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, referer)

    # Padrão 4: mp4 fallback
    m = re.search(r'["\']([^"\']+\.mp4[^"\']*)["\']', html, re.I)
    if m:
        stream = m.group(1)
        xbmc.log(f'[Doramas] embedplay mp4: {stream[:80]}', xbmc.LOGINFO)
        return _build_stream_string(stream, referer)

    xbmc.log(f'[Doramas] embedplay sem stream: {source_url[:80]}', xbmc.LOGWARNING)
    return ''


def _resolve_source(source_url):
    """Despacha para o resolver correto baseado no domínio."""
    if 'vsembed.ru' in source_url:
        return _resolve_vsembed(source_url)
    elif 'embedplay' in source_url:
        return _resolve_embedplay(source_url)
    else:
        # Fallback genérico — tenta extrair m3u8 de qualquer iframe
        return _resolve_embedplay(source_url)


# ---------------------------------------------------------------------------
# Montagem de sources no padrão Burst
# ---------------------------------------------------------------------------

def _detect_language(label):
    """Detecta idioma pelo label do botão."""
    label_up = label.upper()
    if any(x in label_up for x in ('DUB', 'DUBLAD', 'ÁUDIO', 'AUDIO')):
        return 'DUBLADO'
    return 'LEGENDADO'


def _build_sources(raw_sources, ep_code=''):
    """Converte lista de sources resolvidas no formato padrão Burst."""
    results = []
    for idx, item in enumerate(raw_sources, 1):
        source_url = item['source']
        lang       = _detect_language(item['label'])
        resolved   = _resolve_source(source_url)

        if not resolved:
            continue

        stream_url, _, headers_str = resolved.partition('|')

        quality = '1080p'
        if any(x in stream_url.lower() for x in ('4k', '2160', 'uhd')):
            quality = '4K'

        results.append({
            'url':               stream_url,
            'quality':           quality,
            'type':              'Direto',
            'provider':          WEBSITE,
            'languages':         lang,
            'release_title':     ep_code,
            'label':             f'{WEBSITE} • {lang} [{quality}] (Player {idx})',
            'size':              'N/A',
            'seeders':           0,
            'extras':            [],
            'headers':           headers_str,
            'manifest_type':     'hls',
            'inputstreamaddon':  'inputstream.adaptive',
        })

    return results


# ---------------------------------------------------------------------------
# Entry point (padrão Burst)
# ---------------------------------------------------------------------------

def scrape(provider_url, item_data, season=None, episode=None):
    """
    Entry point chamado pelo router do Burst.

    Args:
        provider_url (str): URL base do provider (não usado — site fixo).
        item_data    (dict): Dados do item (title, tmdb_id, media_type, ...).
        season       (int|str|None): Temporada (apenas para tvshow).
        episode      (int|str|None): Episódio (apenas para tvshow).

    Returns:
        list[dict]: Sources no padrão Burst.
    """
    _session.cookies.clear()

    media_type = item_data.get('media_type', 'movie')
    title      = item_data.get('title', '')
    tmdb_id    = item_data.get('tmdb_id')

    # Doramas Online só tem séries
    if media_type != 'tvshow':
        xbmc.log('[Doramas] Apenas séries são suportadas, abortando.', xbmc.LOGDEBUG)
        return []

    if season is None or episode is None:
        xbmc.log('[Doramas] season/episode obrigatórios para tvshow.', xbmc.LOGDEBUG)
        return []

    season_int  = int(season)
    episode_int = int(episode)
    ep_code     = f'S{season_int:02d}E{episode_int:02d}'

    if not title:
        xbmc.log('[Doramas] Título não informado, abortando.', xbmc.LOGDEBUG)
        return []

    xbmc.log(
        f'[Doramas] Buscando: "{title}" {ep_code} (tmdb={tmdb_id})',
        xbmc.LOGDEBUG
    )

    # ── Etapa 1: encontra embed_id ─────────────────────────────────────────

    embed_id = None

    # Tenta primeiro via TMDB ID direto (mais rápido e confiável)
    if tmdb_id:
        embed_id = str(tmdb_id)
        # Valida: tenta acessar o embed e ver se retorna conteúdo útil
        r = _get(f'{PLAYER_URL}/embed/{embed_id}', referer=BASE_URL + '/')
        if not r or 'data-episode-id' not in r.text:
            xbmc.log(
                f'[Doramas] TMDB ID {embed_id} não encontrado no seriesboa, '
                f'tentando busca por título.',
                xbmc.LOGDEBUG
            )
            embed_id = None

    # Fallback: busca por título no doramasonline.co
    if not embed_id:
        serie_url = _search_serie(title)
        if not serie_url:
            xbmc.log(f'[Doramas] Série "{title}" não encontrada.', xbmc.LOGDEBUG)
            return []

        xbmc.log(f'[Doramas] Série encontrada: {serie_url}', xbmc.LOGDEBUG)
        embed_id = _get_embed_id(serie_url)
        if not embed_id:
            xbmc.log(f'[Doramas] embed_id não encontrado em {serie_url}', xbmc.LOGDEBUG)
            return []

    xbmc.log(f'[Doramas] embed_id={embed_id}', xbmc.LOGDEBUG)

    # ── Etapa 2: encontra episode_id ──────────────────────────────────────

    episode_id = _get_episode_id(embed_id, season_int, episode_int)
    if not episode_id:
        xbmc.log(
            f'[Doramas] {ep_code} não encontrado no embed {embed_id}.',
            xbmc.LOGDEBUG
        )
        return []

    # ── Etapa 3: extrai sources do episódio ───────────────────────────────

    raw_sources = _get_sources_from_episode(episode_id)
    if not raw_sources:
        xbmc.log(f'[Doramas] Nenhuma source em episodio/{episode_id}', xbmc.LOGDEBUG)
        return []

    # ── Etapa 4: resolve e retorna ────────────────────────────────────────

    sources = _build_sources(raw_sources, ep_code)

    xbmc.log(
        f'[Doramas] {ep_code}: {len(sources)} fonte(s) resolvida(s).',
        xbmc.LOGINFO
    )
    return sources
