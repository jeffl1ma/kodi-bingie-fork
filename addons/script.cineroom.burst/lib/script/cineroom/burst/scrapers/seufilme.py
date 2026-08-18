# -*- coding: utf-8 -*-
"""
Scraper para Seufilme (DLE)
Suporta 2 tipos de página:
  1. Filme  → <div class="audio_block"> com <div class="item" data-src="...">
  2. Série  → var playlist_lang = {"links": {...}, "dublado": [...], "legendado": [...]}
"""
import re
import json
import xbmc
import requests
from bs4 import BeautifulSoup

from .scraper_config import get_url

BASE_URL = get_url('seufilme', fallback='https://seufilme.mom')
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


# ---------------------------------------------------------------------------
# Sessão / requests
# ---------------------------------------------------------------------------

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def _get(url, timeout=10):
    try:
        r = _get_session().get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        xbmc.log(f"[Seufilme] Erro na request {url}: {e}", xbmc.LOGERROR)
        return None


def _post(url, data, timeout=10):
    try:
        r = _get_session().post(url, data=data, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        xbmc.log(f"[Seufilme] Erro no POST {url}: {e}", xbmc.LOGERROR)
        return None


# ---------------------------------------------------------------------------
# Helpers de validação de título (mesmo padrão do Starck)
# ---------------------------------------------------------------------------

_SERIE_PATTERNS = re.compile(
    r'\b(\d+[aªº°]\s*temporada|temporada\s*\d+|t\d+\b|season\s*\d+|episod)\b',
    re.IGNORECASE
)


def _titulo_parece_serie(texto):
    return bool(_SERIE_PATTERNS.search(texto or ''))


def _normalizar_titulo(texto):
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', texto or '')
    s = ''.join(c for c in nfkd if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[',\.\-_:]", ' ', s)
    s = re.sub(r'\b(the|a|an|o|a|os|as|de|do|da|um|uma)\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _titulo_compativel(titulo_pagina, titulo_busca, is_serie=False):
    if not is_serie and _titulo_parece_serie(titulo_pagina):
        return False

    norm_pagina = _normalizar_titulo(titulo_pagina)
    norm_busca  = _normalizar_titulo(titulo_busca)

    if not norm_busca:
        return True

    pattern = r'^' + re.escape(norm_busca) + r'(\s|$)'
    if re.match(pattern, norm_pagina):
        return True

    tokens_busca  = norm_busca.split()
    tokens_pagina = norm_pagina.split()
    if not tokens_busca:
        return True

    matches = sum(1 for t in tokens_busca if t in tokens_pagina)
    ratio   = matches / len(tokens_busca)
    threshold = 1.0 if len(tokens_busca) <= 3 else 0.90
    if ratio < threshold:
        xbmc.log(
            f"[Seufilme] Rejeitado (título incompatível): '{titulo_pagina}' vs '{titulo_busca}' "
            f"(ratio={ratio:.2f})",
            xbmc.LOGDEBUG
        )
        return False

    idx = norm_pagina.find(norm_busca)
    if idx > 0:
        prefix_words = [
            w for w in norm_pagina[:idx].split()
            if w not in {'the', 'a', 'an', 'o', 'os', 'as', 'de', 'do', 'da',
                 'in', 'of', 'and', 'em', 'no', 'na', 'nos', 'nas', 'e'}
        ]
        if prefix_words:
            xbmc.log(
                f"[Seufilme] Rejeitado (palavras antes do título): {prefix_words} em '{titulo_pagina}'",
                xbmc.LOGDEBUG
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------

def _eh_serie_card(article):
    """Olha o <li> de Gêneros e checa se aponta pra /series*"""
    for li in article.select('ul.details-lst li'):
        span = li.find('span')
        if span and 'gêneros' in span.get_text(strip=True).lower():
            link_span = span.find_next_sibling('span')
            if link_span and link_span.find('a', href=re.compile(r'^/series')):
                return True
    return False


def _buscar_paginas(query, max_results=5, titulo_busca='', apenas_series=None):
    data = {
        'do': 'search',
        'subaction': 'search',
        'search_start': '0',
        'full_search': '0',
        'result_from': '1',
        'story': query,
    }
    r = _post(BASE_URL + '/index.php?do=search', data)
    if r is None:
        return []

    soup  = BeautifulSoup(r.text, 'html.parser')
    itens = []

    for article in soup.select('article.post.dfx.fcl.movies'):
        h2 = article.find('h2', class_='entry-title')
        a  = article.find('a', class_='lnk-blk')
        if not h2 or not a:
            continue

        titulo = h2.get_text(strip=True)
        url    = a.get('href', '')
        if not url:
            continue

        if apenas_series is not None and _eh_serie_card(article) != apenas_series:
            continue

        if titulo_busca:
            norm_card  = _normalizar_titulo(titulo)
            norm_busca = _normalizar_titulo(titulo_busca)
            tokens_busca = norm_busca.split()
            tokens_card  = norm_card.split()
            if tokens_busca:
                matches = sum(1 for t in tokens_busca if t in tokens_card)
                if matches / len(tokens_busca) < 1.0:
                    xbmc.log(
                        f"[Seufilme] Card descartado: '{titulo}' vs '{titulo_busca}'",
                        xbmc.LOGDEBUG
                    )
                    continue

        if not url.startswith('http'):
            url = BASE_URL + url

        itens.append((titulo, url))
        if len(itens) >= max_results:
            break

    return itens


# ---------------------------------------------------------------------------
# Resolver GoodStream
# ---------------------------------------------------------------------------

import json
import base64

def resolver_goodstream(embed_url, referer="https://gscdn.cam/"):
    from .goodstream_proxy import start_proxy
    from urllib.parse import quote as urlquote

    session = _get_session()
    headers = dict(HEADERS)
    headers['Referer'] = 'https://gscdn.cam/'
    headers['Origin']  = 'https://gscdn.cam'

    try:
        r = session.get(embed_url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        xbmc.log(f"[GoodStream] Erro embed {embed_url}: {e}", xbmc.LOGERROR)
        return None

    m = re.search(r'sources:\s*\[\{file:"([^"]+\.m3u8[^"]*)"', r.text)
    if not m:
        xbmc.log(f"[GoodStream] m3u8 não encontrado em {embed_url}", xbmc.LOGERROR)
        return None

    m3u8_url    = m.group(1).replace('&amp;', '&')
    cookies_b64 = base64.b64encode(
        json.dumps(dict(session.cookies)).encode()
    ).decode()

    port      = start_proxy()
    proxy_url = (
        f"http://127.0.0.1:{port}/proxy"
        f"?url={urlquote(m3u8_url, safe='')}"
        f"&cookies={urlquote(cookies_b64, safe='')}"
    )
    xbmc.log(f"[GoodStream] proxy_url: {proxy_url}", xbmc.LOGINFO)
    return proxy_url


# ---------------------------------------------------------------------------
# Busca de FILME
# ---------------------------------------------------------------------------

def _extrair_players_filme(soup):
    """Extrai embeds de <div class="audio_block"> (filmes)."""
    resultados = []
    for block_id, idioma in [('dublado_block', 'DUBLADO'), ('legendado_block', 'LEGENDADO')]:
        block = soup.find('div', id=block_id)
        if not block:
            continue
        for item in block.find_all('div', class_='item'):
            data_src = item.get('data-src', '')
            if not data_src:
                continue
            if data_src.startswith('//'):
                data_src = 'https:' + data_src
            resultados.append({'embed_url': data_src, 'idioma': idioma})
    return resultados


def buscar_filme(item_data):
    titulo          = item_data.get('title', '')
    titulo_original = item_data.get('original_title', '')
    ano             = item_data.get('year', '')

    if not titulo:
        return []

    queries = [titulo]
    if titulo_original and titulo_original.lower() != titulo.lower():
        queries.append(titulo_original)

    sources = []

    for query in queries:
        for _titulo_card, url in _buscar_paginas(query, max_results=5, titulo_busca=titulo, apenas_series=False):
            r = _get(url)
            if r is None:
                continue
            soup = BeautifulSoup(r.text, 'html.parser')

            h2 = soup.find('h2', class_='entry-title')
            titulo_pagina = h2.get_text(strip=True) if h2 else titulo

            if not _titulo_compativel(titulo_pagina, titulo, is_serie=False):
                continue

            for player in _extrair_players_filme(soup):
                xbmc.log(f"[Seufilme] embed_url extraído: {player['embed_url']}", xbmc.LOGINFO)
                resolved = resolver_goodstream(
                    player['embed_url'],
                    referer=player['embed_url'] 
                )    
                if not resolved:
                    continue
                sources.append({
                    'url':       resolved,
                    'title':     titulo_pagina,
                    'quality':   '1080p',
                    'size':      'N/A',
                    'type':      'Direct',
                    'seeders':   0,
                    'extras':    [],
                    'languages': player['idioma'],
                })

            if sources:
                break
        if sources:
            break

    return sources


# ---------------------------------------------------------------------------
# Busca de SÉRIE
# ---------------------------------------------------------------------------

def _extrair_playlist_lang(html):
    m = re.search(r'var playlist_lang\s*=\s*(\{.*?\});', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception as e:
        xbmc.log(f"[Seufilme] Erro ao parsear playlist_lang: {e}", xbmc.LOGDEBUG)
        return None


def buscar_serie(item_data, season, episode):
    titulo          = item_data.get('title', '')
    titulo_original = item_data.get('original_title', '')

    if not titulo or season is None or episode is None:
        return []

    s_num = int(season)
    e_num = int(episode)

    queries = [titulo]
    if titulo_original and titulo_original.lower() != titulo.lower():
        queries.append(titulo_original)

    sources = []

    for query in queries:
        for _titulo_card, url in _buscar_paginas(query, max_results=8, titulo_busca=titulo, apenas_series=True):
            base = url.rstrip('/')
            ep_url = f"{base}/{s_num}-temporada/{e_num}-episodio"

            r = _get(ep_url)
            if r is None:
                continue

            soup = BeautifulSoup(r.text, 'html.parser')
            h2 = soup.find('h2', class_='entry-title')
            titulo_pagina = h2.get_text(strip=True) if h2 else titulo

            if not _titulo_compativel(titulo_pagina, titulo, is_serie=True):
                xbmc.log(f"[Seufilme] Rejeitado (título): '{titulo_pagina}' vs '{titulo}'", xbmc.LOGDEBUG)
                continue

            playlist = _extrair_playlist_lang(r.text)
            if not playlist:
                xbmc.log(f"[Seufilme] playlist_lang não encontrado em {ep_url}", xbmc.LOGDEBUG)
                continue

            for lang_key, embed_id in playlist.get('links', {}).items():
                if not embed_id:
                    continue

                disponiveis = playlist.get(lang_key, [])
                if disponiveis and e_num not in disponiveis:
                    continue

                embed_url = f"https://gscdn.cam/video/embed/{embed_id}"
                resolved  = resolver_goodstream(embed_url, referer=embed_url)
                if not resolved:
                    continue

                idioma = 'DUBLADO' if lang_key == 'dublado' else 'LEGENDADO'
                sources.append({
                    'url':       resolved,
                    'title':     f"{titulo_pagina} S{s_num:02d}E{e_num:02d}",
                    'quality':   '1080p',
                    'size':      'N/A',
                    'type':      'Direct',
                    'seeders':   0,
                    'extras':    [],
                    'languages': idioma,
                })

            if sources:
                break
        if sources:
            break

    return sources


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def scrape(provider_url, item_data, season=None, episode=None):
    xbmc.log("[Seufilme] Iniciando scraper...", xbmc.LOGINFO)
    media_type = item_data.get('media_type', 'movie')

    if media_type == 'movie':
        return buscar_filme(item_data)
    elif media_type == 'tvshow':
        return buscar_serie(item_data, season, episode)

    return []