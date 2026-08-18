# -*- coding: utf-8 -*-
"""
Scraper para Starck Filmes
"""
import re
import time
import xbmc
import requests
from bs4 import BeautifulSoup

from .scraper_config import get_url
BASE_URL   = get_url('starckfilmes', fallback='https://www.starckfilmes-v19.com')
SEARCH_URL = BASE_URL + "/?s={query}"
HEADERS    = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

# ---------------------------------------------------------------------------
# Sessão compartilhada + bypass do gate de "verificação"
# ---------------------------------------------------------------------------

_session = None

# Timeout por request, configurável via settings.xml (scraper.timeout).
_TIMEOUT = 15


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        xbmc.log("[Starck] Nova sessão criada", xbmc.LOGINFO)
    return _session


def _eh_pagina_verificacao(html):
    """Detecta a página fake de 'Verificação de Segurança'."""
    resultado = ('id="verifyBox"' in html) or ('Verificação de Segurança' in html) or ('Comunicado Importante' in html)
    return resultado


def _resolver_verificacao(session, url):
    """
    Replica o handshake da página de verificação:
      1. Aguarda 5.5s (o JS do gate checa se passaram 5000ms)
      2. POST /current-address com {"timeMonit": "14542588"}
      3. GET na mesma URL com cookies da sessão
    """
    xbmc.log("[Starck] Gate detectado — aguardando 5.5s (timer do JS)...", xbmc.LOGINFO)
    time.sleep(5.5)

    try:
        post_url = BASE_URL + "/current-address"
        resp_post = session.post(
            post_url,
            json={"timeMonit": "14542588"},
            timeout=_TIMEOUT
        )
        xbmc.log(f"[Starck] POST status: {resp_post.status_code} | body: {resp_post.text[:200]}", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"[Starck] Erro no POST de verificação: {e}", xbmc.LOGERROR)

    try:
        r = session.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        r.encoding = 'utf-8'
        return r
    except Exception as e:
        xbmc.log(f"[Starck] Erro ao revalidar após verificação: {e}", xbmc.LOGERROR)
        return None


def _get(url, timeout=None, max_tentativas=2):
    """
    Substitui requests.get(url, headers=HEADERS).
    Mantém sessão/cookies e resolve o gate de verificação se aparecer.
    """
    if timeout is None:
        timeout = _TIMEOUT
    session = _get_session()
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        r.encoding = 'utf-8'
    except Exception as e:
        return None


    tentativas = 0
    while _eh_pagina_verificacao(r.text) and tentativas < max_tentativas:
        nova = _resolver_verificacao(session, url)
        if nova is None:
            xbmc.log("[Starck] _resolver_verificacao retornou None", xbmc.LOGERROR)
            return None
        r = nova
        tentativas += 1

    if _eh_pagina_verificacao(r.text):
        return None

    return r


# ---------------------------------------------------------------------------
# Decodificador do magnet embaralhado
# ---------------------------------------------------------------------------

def unshuffle_string(shuffled):
    try:
        length   = len(shuffled)
        original = [''] * length
        used     = [False] * length
        step     = 3
        index    = 0
        for i in range(length):
            while used[index]:
                index = (index + 1) % length
            used[index]  = True
            original[i]  = shuffled[index]
            index        = (index + step) % length
        result = ''.join(original)
        return result
    except Exception as e:
        xbmc.log(f"[Starck] unshuffle erro: {e}", xbmc.LOGERROR)
        return None

# ---------------------------------------------------------------------------
# Helpers de validação
# ---------------------------------------------------------------------------

_SERIE_PATTERNS = re.compile(
    r'\b(\d+[aªº°]\s*temporada|temporada\s*\d+|t\d+\b|season\s*\d+|'
    r'episod|completo\s+\d+|parte\s+\d+)\b',
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
                f"[Starck] Rejeitado (palavras antes do título): {prefix_words} em '{titulo_pagina}'",
                xbmc.LOGDEBUG
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Helpers de idioma
# ---------------------------------------------------------------------------

def _idioma_do_texto(texto):
    t = (texto or '').lower()
    if 'dual' in t:
        return 'DUAL'
    if 'dublado' in t:
        return 'DUBLADO'
    if 'legendado' in t:
        return 'LEGENDADO'
    return 'PT-BR'


def _idioma_btn_down(btn):
    text_span = btn.find('span', class_='text')
    if not text_span:
        return 'PT-BR'
    filhos = text_span.find_all('span', recursive=False)
    if not filhos:
        return 'PT-BR'
    return _idioma_do_texto(filhos[0].get_text(separator=' '))


# ---------------------------------------------------------------------------
# Parsers da página de conteúdo
# ---------------------------------------------------------------------------

def _get_titulo_limpo(soup):
    h2 = soup.find('h2', class_='post-title')
    if h2:
        return h2.get_text(strip=True)
    h1 = soup.find('h1')
    if h1:
        t = h1.get_text(strip=True)
        return re.sub(r'\s*[Tt]orrent.*$', '', t).strip()
    return ''


def _get_ano(soup):
    desc = soup.find('div', class_='post-description')
    if not desc:
        return ''
    for p in desc.find_all('p'):
        spans = p.find_all('span')
        if len(spans) >= 2 and 'lançamento' in spans[0].get_text().lower():
            return spans[1].get_text(strip=True)
    return ''


def _get_qualidade(soup):
    span = soup.find('span', class_='sl-quality')
    if not span:
        return 'HD'
    return {'FHD': '1080p', 'UHD': '4K', 'HD': '720p', 'SD': '480p'}.get(
        span.get_text(strip=True).upper(), span.get_text(strip=True)
    )


def _get_tamanho(soup):
    desc = soup.find('div', class_='post-description')
    if not desc:
        return 'N/A'
    for p in desc.find_all('p'):
        spans = p.find_all('span')
        if len(spans) >= 2 and 'tamanho' in spans[0].get_text().lower():
            return spans[1].get_text(strip=True)
    return 'N/A'


def _parse_btn_down(btn, qualidade_fallback='HD', tamanho_fallback='N/A'):
    link = btn.find('a')
    if not link:
        xbmc.log("[Starck] btn-down sem <a>", xbmc.LOGDEBUG)
        return None
    data_u = link.get('data-u', '')
    if not data_u:
        xbmc.log("[Starck] <a> sem data-u", xbmc.LOGDEBUG)
        return None
    magnet = unshuffle_string(data_u)
    if not magnet or 'magnet:' not in magnet:
        return None

    idioma    = _idioma_btn_down(btn)
    qualidade = qualidade_fallback
    tamanho   = tamanho_fallback

    text_span = btn.find('span', class_='text')
    if text_span:
        filhos = text_span.find_all('span', recursive=False)
        if len(filhos) >= 3:
            texto_res = filhos[2].get_text(strip=True)
            m_q = re.search(r'(4K|2160p|1080p|720p|480p)', texto_res, re.IGNORECASE)
            if m_q:
                qualidade = m_q.group(1)
            m_s = re.search(r'\(([^)]+(?:GB|MB))\)', texto_res, re.IGNORECASE)
            if m_s:
                tamanho = m_s.group(1)

    return {'url': magnet, 'idioma': idioma, 'qualidade': qualidade, 'tamanho': tamanho}


# ---------------------------------------------------------------------------
# Busca no site
# ---------------------------------------------------------------------------

def _executar_busca(query):
    """Faz o GET de busca e retorna a lista de cards (.sub-item) encontrados."""
    search_url = SEARCH_URL.format(query=requests.utils.quote(query))
    r = _get(search_url)
    if r is None:
        xbmc.log("[Starck] _get retornou None na busca", xbmc.LOGERROR)
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    return soup.select('.sub-item')


def _buscar_paginas(query, max_results=5, titulo_busca=''):
    cards = _executar_busca(query)

    itens = []
    for i, card in enumerate(cards):
        a_pai = card.find('a', href=re.compile(r'/catalog/'))
        if not a_pai:
            continue
        url    = a_pai.get('href', '')
        titulo = a_pai.get('title', '') or a_pai.get_text(strip=True)

        if not url or not titulo:
            continue

        if titulo_busca:
            norm_card  = _normalizar_titulo(titulo)
            norm_busca = _normalizar_titulo(titulo_busca)
            tokens_busca = norm_busca.split()
            tokens_card  = norm_card.split()
            if tokens_busca:
                matches = sum(1 for t in tokens_busca if t in tokens_card)
                ratio   = matches / len(tokens_busca)
                if ratio < 1.0:
                    xbmc.log(
                        f"[Starck] Card descartado: '{titulo}' vs '{titulo_busca}' (ratio={ratio:.2f})",
                        xbmc.LOGDEBUG
                    )
                    continue

        itens.append((titulo, url))
        if len(itens) >= max_results:
            break

    return itens


def _fetch_pagina(url):
    r = _get(url)
    if r is None:
        return None
    return BeautifulSoup(r.text, 'html.parser')


def _ano_ok(soup, ano_esperado):
    if not ano_esperado:
        return True
    ano_pagina = _get_ano(soup)
    try:
        ok = abs(int(ano_pagina) - int(ano_esperado)) <= 1
        return ok
    except Exception:
        xbmc.log(f"[Starck] Ano: não foi possível comparar (página='{ano_pagina}' esperado='{ano_esperado}')", xbmc.LOGDEBUG)
        return True


# ---------------------------------------------------------------------------
# Busca de FILME
# ---------------------------------------------------------------------------

def buscar_filme(item_data):
    titulo          = item_data.get('title', '')
    titulo_original = item_data.get('original_title', '')
    ano             = item_data.get('year', '')


    if not titulo:
        xbmc.log("[Starck] buscar_filme: título vazio, abortando", xbmc.LOGERROR)
        return []

    queries = [titulo]
    if titulo_original and titulo_original.lower() != titulo.lower():
        queries.append(titulo_original)

    sources = []

    for query in queries:
        paginas = _buscar_paginas(query, titulo_busca=titulo)

        for _titulo_card, url in paginas:
            soup = _fetch_pagina(url)
            if not soup:
                continue

            if not _ano_ok(soup, ano):
                continue

            titulo_limpo = _get_titulo_limpo(soup) or titulo

            if not _titulo_compativel(titulo_limpo, titulo, is_serie=False):
                xbmc.log(f"[Starck] Título incompatível: '{titulo_limpo}' vs '{titulo}'", xbmc.LOGDEBUG)
                continue

            qualidade = _get_qualidade(soup)
            tamanho   = _get_tamanho(soup)

            btns = soup.find_all('span', class_='btn-down')

            for btn in btns:
                parsed = _parse_btn_down(btn, qualidade, tamanho)
                if not parsed:
                    continue
                stream = {
                    'url':       parsed['url'],
                    'title':     titulo_limpo,
                    'quality':   parsed['qualidade'],
                    'size':      parsed['tamanho'],
                    'type':      'Torrent',
                    'seeders':   0,
                    'extras':    [],
                    'languages': parsed['idioma'],
                }
                sources.append(stream)

            if sources:
                break

        if sources:
            break

    return sources


# ---------------------------------------------------------------------------
# Busca de SÉRIE
# ---------------------------------------------------------------------------

def buscar_serie(item_data, season, episode):
    titulo          = item_data.get('title', '')
    titulo_original = item_data.get('original_title', '')


    if not titulo or season is None or episode is None:
        xbmc.log("[Starck] buscar_serie: parâmetros inválidos, abortando", xbmc.LOGERROR)
        return []

    s_num = int(season)
    e_num = int(episode)
    s_pad = str(s_num).zfill(2)
    e_pad = str(e_num).zfill(2)

    queries = [titulo]
    if titulo_original and titulo_original.lower() != titulo.lower():
        queries.append(titulo_original)

    sources = []

    for query in queries:
        for _titulo_card, url in _buscar_paginas(query, max_results=8, titulo_busca=titulo):
            soup = _fetch_pagina(url)
            if not soup:
                continue

            titulo_pagina = _get_titulo_limpo(soup).lower()

            # CASO A: episódios separados
            epsodios_div = soup.find('div', class_='epsodios')
            if epsodios_div:
                padrao_temporada = re.search(
                    rf'({s_num}[aªº°]?\s*temporada|temporada\s*{s_num})',
                    titulo_pagina, re.IGNORECASE
                )
                if not padrao_temporada:
                    continue

                h3 = epsodios_div.find('h3')
                idioma_ep = _idioma_do_texto(h3.get_text() if h3 else '')

                qualidade    = _get_qualidade(soup)
                tamanho      = _get_tamanho(soup)
                titulo_limpo = _get_titulo_limpo(soup) or titulo

                if not _titulo_compativel(titulo_limpo, titulo, is_serie=True):
                    continue

                paragrafos = epsodios_div.find_all('p')

                for p in paragrafos:
                    strong = p.find('strong')
                    if not strong:
                        continue

                    ep_text = strong.get_text().lower()
                    episodio_encontrado = False

                    # Verifica episódio único: "EPISÓDIO 03" ou "EPISÓDIOS 03"
                    if re.search(rf'episódios?\s+0?{e_num}\b', ep_text):
                        episodio_encontrado = True

                    # Verifica range: "EPISÓDIOS 01 E 02"
                    if not episodio_encontrado:
                        m = re.search(r'episódios?\s+0?(\d+)\s+(?:e|ao)\s+0?(\d+)', ep_text)
                        if m and int(m.group(1)) <= e_num <= int(m.group(2)):
                            episodio_encontrado = True

                    if not episodio_encontrado:
                        continue

                    # Pega TODOS os links com data-u (múltiplas qualidades)
                    links = p.find_all('a', attrs={'data-u': True})
                    if not links:
                        xbmc.log("[Starck] Episódio sem links com data-u", xbmc.LOGDEBUG)
                        continue


                    for link in links:
                        data_u = link.get('data-u', '')
                        magnet = unshuffle_string(data_u)
                        if not magnet or 'magnet:' not in magnet:
                            continue

                        q_link = link.get_text(strip=True)
                        q_ep = qualidade  # fallback da qualidade da página
                        m_q = re.search(r'(4K|2160p|1080p|720p|480p)', q_link, re.IGNORECASE)
                        if m_q:
                            q_ep = m_q.group(1)

                        stream = {
                            'url':       magnet,
                            'title':     f"{titulo_limpo} S{s_pad}E{e_pad}",
                            'quality':   q_ep,
                            'size':      tamanho,
                            'type':      'Torrent',
                            'seeders':   0,
                            'extras':    [],
                            'languages': idioma_ep,
                        }
                        sources.append(stream)

                    # Sai do loop de parágrafos após processar o episódio encontrado
                    break

                if sources:
                    break
                continue

            # CASO B: temporada inteira com btn-down
            padrao_temporada = re.search(
                rf'({s_num}[aªº°]?\s*temporada|temporada\s*{s_num})',
                titulo_pagina, re.IGNORECASE
            )
            if not padrao_temporada:
                continue

            titulo_limpo = _get_titulo_limpo(soup) or titulo
            qualidade    = _get_qualidade(soup)
            tamanho      = _get_tamanho(soup)

            btns = soup.find_all('span', class_='btn-down')

            for btn in btns:
                parsed = _parse_btn_down(btn, qualidade, tamanho)
                if not parsed:
                    continue
                stream = {
                    'url':       parsed['url'],
                    'title':     titulo_limpo,
                    'quality':   parsed['qualidade'],
                    'size':      parsed['tamanho'],
                    'type':      'Torrent',
                    'seeders':   0,
                    'extras':    [],
                    'languages': parsed['idioma'],
                }
                sources.append(stream)

            if sources:
                break

        if sources:
            break

    return sources


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def scrape(provider_url, item_data, season=None, episode=None, timeout=None):
    global _TIMEOUT
    if timeout:
        _TIMEOUT = timeout

    media_type = item_data.get('media_type', 'movie')

    if media_type == 'movie':
        result = buscar_filme(item_data)
    elif media_type == 'tvshow':
        result = buscar_serie(item_data, season, episode)
    else:
        result = []

    xbmc.log(f"[Starck] ===== SCRAPE FINALIZADO: {len(result)} fonte(s) =====", xbmc.LOGINFO)
    return result