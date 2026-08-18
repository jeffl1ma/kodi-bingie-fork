# -*- coding: utf-8 -*-
"""
Scraper para GoFlixy — CineRoom Lite (Burst)
Resolve stream via fembed.sx → bysevepoin.com sem depender de resolveurl externo.
"""

import re
import base64
import difflib
import xbmc
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse, quote
from html import unescape
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WEBSITE   = 'GoFlixy'
from .scraper_config import get_url
from .session import USER_AGENT, _IS_ANDROID

BASE_URL  = get_url('goflixy', fallback='https://goflixy.lol')
FEMBED    = get_url('goflixy', key='fembed', fallback='https://fembed.sx')

_session = requests.Session()
_session.verify = False
_session.headers.update({
    'User-Agent':      USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept':          '*/*',
    'Referer':         BASE_URL + '/',
})

# Timeout por request, configurável via settings.xml (scraper.timeout).
_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg, level=xbmc.LOGDEBUG):
    xbmc.log(f'[GoFlixy] {msg}', level)


def _clean_title(title):
    title = unescape(title)
    title = re.sub(r'[:\-—]', ' ', title)
    return re.sub(r'\s+', ' ', title).strip()


def _find_titles_from_item(item_data):
    """Obtém título PT, título original e ano via TMDB (igual ao netcine.py)."""
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
                    timeout=8,
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


def _similarity(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Busca no site
# ---------------------------------------------------------------------------

def _search(query, want_serie=False):
    """
    Retorna a URL da página do título mais similar encontrado.
    want_serie=True filtra por /serie/, False por /filme/.
    """
    path_keyword = '/serie/' if want_serie else '/filme/'
    try:
        r = _session.get(f'{BASE_URL}/buscar?q={quote_plus(query)}', timeout=_TIMEOUT)
        if not r.ok:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        best_url   = None
        best_ratio = 0.0

        for a in soup.find_all('a', class_='card'):
            href = a.get('href', '')
            if path_keyword not in href:
                continue

            title_div = a.find('div', class_='card-title')
            if not title_div:
                continue

            raw        = title_div.get_text(strip=True)
            clean      = re.sub(r'\s*\(\d{4}\)\s*$', '', raw).strip()
            ratio      = _similarity(query, clean)

            if ratio > best_ratio:
                best_ratio = ratio
                best_url   = urljoin(BASE_URL, href)

        if best_ratio >= 0.55 and best_url:
            _log(f'Melhor match "{query}": {best_url} ({best_ratio:.2f})')
            return best_url

    except Exception as e:
        _log(f'Erro na busca "{query}": {e}', xbmc.LOGERROR)
    return None


# ---------------------------------------------------------------------------
# Resolução fembed → bysevepoin → m3u8
# ---------------------------------------------------------------------------

def _resolve_fembed(share_id, lang, cvalue=''):
    """
    Percorre a cadeia fembed.sx → bysevepoin e retorna a URL do player
    bysevepoin ou None se falhar.
    lang: 'DUB' ou 'LEG'
    """
    try:
        page = f'{FEMBED}/e/{share_id}/'
        if cvalue:
            page = f'{FEMBED}/e/{share_id}/{cvalue}'

        r0 = _session.get(page, timeout=_TIMEOUT)
        if not r0.ok:
            _log(f'fembed página falhou: {r0.status_code}', xbmc.LOGWARNING)
            return None

        html    = r0.text
        cookies = r0.cookies

        # Descobre endpoint da API (pode ser customizado no HTML)
        api_match = re.search(r'api\s*=\s*"([^"]+)"', html)
        if api_match:
            api_path = api_match.group(1).replace('\\/', '/')
        else:
            api_path = f'/api.php?s={share_id}&c={cvalue}'
        api_url = urljoin(FEMBED, api_path)

        pdata = {
            'action': 'getPlayer',
            'lang':   lang,
            'key':    base64.b64encode(b'0').decode(),
        }
        r1 = _session.post(
            api_url,
            data=pdata,
            headers={'Referer': page},
            cookies=cookies,
            timeout=_TIMEOUT,
        )
        if not r1.ok:
            _log(f'fembed API falhou ({lang}): {r1.status_code}', xbmc.LOGWARNING)
            return None

        # Extrai URL getAds do HTML retornado
        m = re.search(r'src=["\']([^"\']*action=getAds[^"\']*)["\']', r1.text)
        if not m:
            _log(f'fembed: getAds não encontrado ({lang})', xbmc.LOGWARNING)
            return None

        getads = m.group(1)
        if getads.startswith('//'):
            getads = 'https:' + getads
        elif getads.startswith('/'):
            getads = FEMBED + getads

        r2 = _session.get(
            getads,
            headers={'Referer': page, 'X-Requested-With': 'XMLHttpRequest'},
            cookies=cookies,
            timeout=_TIMEOUT,
        )
        if not r2.ok:
            _log(f'fembed: getAds request falhou ({lang})', xbmc.LOGWARNING)
            return None

        # Extrai URL do bysevepoin
        link = re.search(r'src=["\']([^"\']*bysevepoin\.[^"\']*)["\']', r2.text, re.I)
        if not link:
            _log(f'fembed: bysevepoin URL não encontrada ({lang})', xbmc.LOGWARNING)
            return None

        dirty = link.group(1)
        if dirty.startswith('//'):
            dirty = 'https:' + dirty
        dirty = dirty.replace('http://', 'https://')

        # Limpa parâmetros extras, mantém só /e/{token}
        clean = re.sub(r'(/e/[0-9A-Za-z]+).*', r'\1', dirty)
        _log(f'bysevepoin URL ({lang}): {clean}', xbmc.LOGINFO)
        return clean

    except Exception as e:
        _log(f'_resolve_fembed erro ({lang}): {e}', xbmc.LOGERROR)
        return None


def _b64url_decode(e):
    """Decodifica base64 URL-safe sem padding."""
    import base64
    t = e.replace('-', '+').replace('_', '/')
    pad = 0 if len(t) % 4 == 0 else 4 - len(t) % 4
    return base64.b64decode(t + '=' * pad)


def _join_key_parts(parts):
    """Concatena múltiplas partes base64 em uma chave AES."""
    return b''.join(_b64url_decode(p) for p in parts)


def _aesgcm_decrypt(key, iv, ciphertext_with_tag):
    """
    AES-GCM decrypt — tenta libs nativas primeiro, fallback puro Python.
    ciphertext_with_tag: ciphertext + 16 bytes de tag no final.
    """
    # Tenta pycryptodome
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext_with_tag[:-16], ciphertext_with_tag[-16:])
    except ImportError:
        pass
    # Tenta cryptography
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(iv, ciphertext_with_tag, None)
    except ImportError:
        pass
    # Fallback: AES-GCM puro Python (sem validação de tag)
    return _aesgcm_pure(key, iv, ciphertext_with_tag[:-16])


# ---------------------------------------------------------------------------
# AES-GCM puro Python — sem dependências externas
# Baseado no NIST SP 800-38D (AES-CTR + GHASH, sem verificação de tag)
# ---------------------------------------------------------------------------

def _aes_encrypt_block(key, block):
    """Encripta um bloco AES de 16 bytes usando AES puro Python."""
    # Expansão de chave e cipher via módulo padrão
    # Usa o truque de encriptar via AES-ECB do hashlib se disponível,
    # caso contrário usa implementação manual compacta.
    try:
        from Crypto.Cipher import AES as _AES
        return _AES.new(key, _AES.MODE_ECB).encrypt(block)
    except ImportError:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        c = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        e = c.encryptor()
        return e.update(block) + e.finalize()
    except ImportError:
        pass
    # AES ECB puro Python (rijndael compacto)
    return _rijndael_encrypt(key, block)


def _aesgcm_pure(key, iv, ciphertext):
    """AES-CTR decrypt (núcleo do GCM, sem verificação de tag GHASH)."""
    # Contador inicial J0: IV(12 bytes) + 0x00000002 (bloco 1)
    counter = int.from_bytes(iv + b'\x00\x00\x00\x02', 'big')
    result  = bytearray()
    for i in range(0, len(ciphertext), 16):
        block     = ciphertext[i:i + 16]
        ctr_bytes = counter.to_bytes(16, 'big')
        keystream = _aes_encrypt_block(key, ctr_bytes)
        result   += bytes(a ^ b for a, b in zip(block, keystream[:len(block)]))
        counter  += 1
    return bytes(result)


def _rijndael_encrypt(key, block):
    """AES-128/192/256 ECB puro Python — implementação compacta Rijndael."""
    # S-box
    S = [
        99,124,119,123,242,107,111,197,48,1,103,43,254,215,171,118,202,130,201,125,250,89,71,240,173,
        212,162,175,156,164,114,192,183,253,147,38,54,63,247,204,52,165,229,241,113,216,49,21,4,199,
        35,195,24,150,5,154,7,18,128,226,235,39,178,117,9,131,44,26,27,110,90,160,82,59,214,179,41,
        227,47,132,83,209,0,237,32,252,177,91,106,203,190,57,74,76,88,207,208,239,170,251,67,77,51,
        133,69,249,2,127,80,60,159,168,81,163,64,143,146,157,56,245,188,182,218,33,16,255,243,210,
        205,12,19,236,95,151,68,23,196,167,126,61,100,93,25,115,96,129,79,220,34,42,144,136,70,238,
        184,20,222,94,11,219,224,50,58,10,73,6,36,92,194,211,172,98,145,149,228,121,231,200,55,109,
        141,213,78,169,108,86,244,234,101,122,174,8,186,120,37,46,28,166,180,198,232,221,116,31,75,
        189,139,138,112,62,181,102,72,3,246,14,97,53,87,185,134,193,29,158,225,248,152,17,105,217,
        142,148,155,30,135,233,206,85,40,223,140,161,137,13,191,230,66,104,65,153,45,15,176,84,187,
        22,
    ]
    # Constantes de round
    RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

    def sub_bytes(s):
        return [S[b] for b in s]

    def shift_rows(s):
        return [
            s[0],s[5],s[10],s[15],
            s[4],s[9],s[14],s[3],
            s[8],s[13],s[2],s[7],
            s[12],s[1],s[6],s[11],
        ]

    def xtime(a):
        return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff

    def mix_col(c):
        t = c[0] ^ c[1] ^ c[2] ^ c[3]
        return [
            c[0] ^ t ^ xtime(c[0] ^ c[1]),
            c[1] ^ t ^ xtime(c[1] ^ c[2]),
            c[2] ^ t ^ xtime(c[2] ^ c[3]),
            c[3] ^ t ^ xtime(c[3] ^ c[0]),
        ]

    def mix_rows(s):
        r = []
        for i in range(4):
            r += mix_col(s[i*4:i*4+4])
        return r

    def add_key(s, rk):
        return [a ^ b for a, b in zip(s, rk)]

    # Key expansion
    nk = len(key) // 4
    nr = nk + 6
    w  = list(key)
    for i in range(nk, 4 * (nr + 1)):
        tmp = w[(i-1)*4:i*4]
        if i % nk == 0:
            tmp = [S[tmp[1]] ^ RCON[i//nk-1], S[tmp[2]], S[tmp[3]], S[tmp[0]]]
        elif nk > 6 and i % nk == 4:
            tmp = sub_bytes(tmp)
        prev = w[(i-nk)*4:i*4-(nk-1)*4]
        w   += [a ^ b for a, b in zip(prev, tmp)]

    state = list(block)
    state = add_key(state, w[:16])
    for rd in range(1, nr + 1):
        state = sub_bytes(state)
        state = shift_rows(state)
        if rd < nr:
            state = mix_rows(state)
        state = add_key(state, w[rd*16:(rd+1)*16])
    return bytes(state)


def _resolve_bysevepoin(byse_url):
    """
    Chama a API JSON do bysevepoin/f16px e extrai o .m3u8.
    Endpoint: GET /api/videos/{token}/embed/playback
    Retorna string 'url|headers' ou ''.
    """
    import json as _json

    try:
        parsed = urlparse(byse_url)
        origin = f'{parsed.scheme}://{parsed.netloc}'

        # Extrai token do path  /e/{token}
        m = re.search(r'/e/([0-9A-Za-z]+)', parsed.path)
        if not m:
            _log(f'bysevepoin: token não encontrado em {byse_url}', xbmc.LOGWARNING)
            return ''
        token = m.group(1)

        api_url = f'{origin}/api/videos/{token}/embed/playback'
        headers = {
            'User-Agent':      USER_AGENT,
            'Referer':         origin + '/',
            'Accept':          'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        }

        r = _session.get(api_url, headers=headers, timeout=_TIMEOUT)
        if not r.ok:
            _log(f'bysevepoin API falhou: {r.status_code} — {api_url}', xbmc.LOGWARNING)
            return ''

        data = r.json()
        _log(f'bysevepoin API keys: {list(data.keys())}', xbmc.LOGDEBUG)

        # Caso 1: sources em texto claro
        sources = data.get('sources')
        if sources:
            for s in sources:
                url = s.get('url') or s.get('file') or ''
                if url:
                    if url.startswith('/'):
                        url = origin + url
                    _log(f'bysevepoin: stream direto: {url[:80]}', xbmc.LOGINFO)
                    return _build_stream(url, parsed)

        # Caso 2: playback criptografado com AES-GCM (padrão f16px)
        pd = data.get('playback')
        if pd:
            try:
                iv      = _b64url_decode(pd.get('iv', ''))
                key     = _join_key_parts(pd.get('key_parts', []))
                payload = _b64url_decode(pd.get('payload', ''))

                plaintext = _aesgcm_decrypt(key, iv, payload)
                ct_data   = _json.loads(plaintext.decode('latin-1'))

                sources = ct_data.get('sources', [])
                if sources:
                    url = sources[0].get('url') or sources[0].get('file') or ''
                    if url.startswith('/'):
                        url = origin + url
                    _log(f'bysevepoin: stream AES-GCM: {url[:80]}', xbmc.LOGINFO)
                    return _build_stream(url, parsed)
            except ImportError as e:
                _log(f'bysevepoin: sem lib AES disponível: {e}', xbmc.LOGERROR)
            except Exception as e:
                _log(f'bysevepoin: erro AES-GCM: {e}', xbmc.LOGWARNING)

        _log(f'bysevepoin: nenhuma source em {api_url}', xbmc.LOGWARNING)
        return ''

    except Exception as e:
        _log(f'_resolve_bysevepoin erro: {e}', xbmc.LOGERROR)
        return ''


def _build_stream(stream_url, parsed_player):
    """Monta 'url|headers' no formato inputstream.adaptive."""
    origin = f'{parsed_player.scheme}://{parsed_player.netloc}'
    h = {
        'User-Agent': USER_AGENT,
        'Referer':    origin + '/',
    }
    # Origin causa bloqueio CORS em alguns CDNs no Android
    if not _IS_ANDROID:
        h['Origin'] = origin
    header_str = '&'.join(f'{k}={quote(v)}' for k, v in h.items())
    return f'{stream_url}|{header_str}'


# ---------------------------------------------------------------------------
# Extração de players da página do GoFlixy
# ---------------------------------------------------------------------------

def _get_movie_fembed_id(page_url):
    """Retorna o share_id do fembed a partir da página do filme."""
    try:
        r = _session.get(page_url, timeout=_TIMEOUT)
        if not r.ok:
            return None
        iframe = BeautifulSoup(r.text, 'html.parser').find('iframe', id='player')
        if not iframe:
            return None
        src = iframe.get('src', '')
        if src.startswith('//'):
            src = 'https:' + src
        m = re.search(r'/e/([0-9A-Za-z]+)', src)
        return m.group(1) if m else None
    except Exception as e:
        _log(f'_get_movie_fembed_id erro: {e}', xbmc.LOGERROR)
        return None


def _get_episode_fembed(page_url, season, episode):
    """
    Extrai share_id, cvalue, hasDub e hasLeg do objeto EP na página da série.
    Retorna (share_id, cvalue, has_dub, has_leg) ou (None, None, False, False).
    """
    try:
        r = _session.get(page_url, timeout=_TIMEOUT)
        if not r.ok:
            return None, None, False, False

        m = re.search(r'const EP\s*=\s*(\{[\s\S]*?\});', r.text)
        if not m:
            _log(f'const EP não encontrado em {page_url}', xbmc.LOGWARNING)
            return None, None, False, False

        ep_data = eval(
            m.group(1)
            .replace('true', 'True')
            .replace('false', 'False')
            .replace('null', 'None')
        )

        skey = str(season)
        if skey not in ep_data:
            _log(f'Temporada {skey} não encontrada', xbmc.LOGWARNING)
            return None, None, False, False

        for e in ep_data[skey]:
            if str(e.get('n')) == str(episode):
                url     = e.get('url', '')
                has_dub = bool(e.get('hasDub', False))
                has_leg = bool(e.get('hasLeg', False))

                if url.startswith('//'):
                    url = 'https:' + url

                m2 = re.search(r'/e/([0-9A-Za-z]+)/(.+)', url)
                if m2:
                    return m2.group(1), m2.group(2), has_dub, has_leg

                m3 = re.search(r'/e/([0-9A-Za-z]+)', url)
                if m3:
                    return m3.group(1), '', has_dub, has_leg

        _log(f'Episódio S{season:02d}E{episode:02d} não encontrado no EP object', xbmc.LOGWARNING)
        return None, None, False, False

    except Exception as e:
        _log(f'_get_episode_fembed erro: {e}', xbmc.LOGERROR)
        return None, None, False, False


# ---------------------------------------------------------------------------
# Montagem de sources
# ---------------------------------------------------------------------------

def _build_sources(pairs, media_type, season=None, episode=None):
    """
    pairs: lista de (lang_label, byse_url)
    Resolve cada bysevepoin URL e monta o dict de source.
    """
    sources  = []
    ep_code  = ''
    if media_type == 'tvshow' and season is not None and episode is not None:
        ep_code = f'S{int(season):02d}E{int(episode):02d}'

    for lang, byse_url in pairs:
        resolved = _resolve_bysevepoin(byse_url)
        if not resolved:
            _log(f'Sem stream para {byse_url}', xbmc.LOGDEBUG)
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
            'release_title':    ep_code,
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

    # season/episode podem vir como parâmetro ou dentro do item_data
    if season is None:
        season = item_data.get('season')
    if episode is None:
        episode = item_data.get('episode')

    _log(f'scrape() | type={media_type} | s={season} | e={episode} | tmdb={item_data.get("tmdb_id")} | title={item_data.get("title","")}', xbmc.LOGINFO)

    title_pt, original_title, year = _find_titles_from_item(item_data)
    _log(f'Titulos: pt="{title_pt}" orig="{original_title}" year={year}', xbmc.LOGINFO)

    if not title_pt and not original_title:
        _log('Sem titulo disponivel, abortando.', xbmc.LOGWARNING)
        return []

    search_titles = []
    if title_pt:
        search_titles.append(_clean_title(title_pt))
    if original_title and original_title != title_pt:
        search_titles.append(_clean_title(original_title))

    _log(f'Titulos: {search_titles} | Ano: {year} | Tipo: {media_type}', xbmc.LOGINFO)

    # ── FILME ─────────────────────────────────────────────────────────────
    if media_type == 'movie':
        for title in search_titles:
            page_url = _search(title, want_serie=False)
            if not page_url:
                continue

            share_id = _get_movie_fembed_id(page_url)
            if not share_id:
                _log(f'share_id não encontrado em {page_url}', xbmc.LOGWARNING)
                continue

            pairs = []
            for lang in ('DUB', 'LEG'):
                byse = _resolve_fembed(share_id, lang)
                if byse:
                    label = 'DUBLADO' if lang == 'DUB' else 'LEGENDADO'
                    pairs.append((label, byse))

            if pairs:
                sources = _build_sources(pairs, media_type)
                if sources:
                    _log(f'Filme: {len(sources)} fonte(s) resolvida(s)')
                    return sources

        _log(f'Filme tmdb={item_data.get("tmdb_id")} sem stream resolvido.', xbmc.LOGDEBUG)
        return []

    # ── SÉRIE / ANIME ──────────────────────────────────────────────────────
    if media_type == 'tvshow':
        if season is None or episode is None:
            _log('Série sem season/episode, abortando.', xbmc.LOGDEBUG)
            return []

        season_int  = int(season)
        episode_int = int(episode)

        for title in search_titles:
            page_url = _search(title, want_serie=True)
            if not page_url:
                continue

            share_id, cvalue, has_dub, has_leg = _get_episode_fembed(page_url, season_int, episode_int)
            if not share_id:
                continue

            # Respeita hasDub/hasLeg — evita chamadas inúteis ao fembed
            langs_to_try = []
            if has_dub:
                langs_to_try.append(('DUB', 'DUBLADO'))
            if has_leg:
                langs_to_try.append(('LEG', 'LEGENDADO'))
            if not langs_to_try:  # flags ausentes — tenta os dois
                langs_to_try = [('DUB', 'DUBLADO'), ('LEG', 'LEGENDADO')]

            pairs = []
            for lang, label in langs_to_try:
                byse = _resolve_fembed(share_id, lang, cvalue)
                if byse:
                    pairs.append((label, byse))

            if pairs:
                sources = _build_sources(pairs, media_type, season_int, episode_int)
                if sources:
                    _log(f'Série S{season_int:02d}E{episode_int:02d}: {len(sources)} fonte(s)')
                    return sources

        _log(
            f'Série tmdb={item_data.get("tmdb_id")} '
            f'S{season_int:02d}E{episode_int:02d} não encontrada.',
            xbmc.LOGDEBUG,
        )
        return []

    return []