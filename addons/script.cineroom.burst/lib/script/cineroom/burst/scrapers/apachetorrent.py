# -*- coding: utf-8 -*-
import re
import urllib.parse
import unicodedata
import xbmc
import requests
from bs4 import BeautifulSoup

from .utils import extract_magnets
from .scraper_config import get_url

_APACHE_BASE = get_url('apachetorrent', fallback='https://apachetorrent.com')

# Timeout por request, configurável via settings.xml (scraper.timeout).
_TIMEOUT = 15

# -------------------------------------------------------------------
# NORMALIZAÇÃO DE TEXTO
# -------------------------------------------------------------------

def normalize_for_compare(text):
    """Normaliza texto para comparação: minusculo, sem acentos, sem pontuação."""
    if not text:
        return ""
    
    text = text.lower()
    
    try:
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ASCII', 'ignore').decode('utf-8')
    except:
        pass
    
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Mapa de palavras numéricas PT/EN → algarismos
_NUM_WORDS_PT = {
    r'\bum\b': '1', r'\buma\b': '1',
    r'\bdois\b': '2', r'\bduas\b': '2',
    r'\btres\b': '3', r'\bquatro\b': '4',
    r'\bcinco\b': '5', r'\bseis\b': '6',
    r'\bsete\b': '7', r'\boito\b': '8',
    r'\bnove\b': '9', r'\bdez\b': '10',
    r'\bone\b': '1', r'\btwo\b': '2',
    r'\bthree\b': '3', r'\bfour\b': '4',
    r'\bfive\b': '5', r'\bsix\b': '6',
    r'\bseven\b': '7', r'\beight\b': '8',
    r'\bnine\b': '9', r'\bten\b': '10',
}


def normalize_title_for_search(title):
    """Converte palavras numéricas para algarismos e limpa o título."""
    t = title.lower()
    for pattern, num in _NUM_WORDS_PT.items():
        t = re.sub(pattern, num, t, flags=re.IGNORECASE)
    return t.strip()


def clean_query(query):
    """Limpa a query para URL de busca."""
    if not query:
        return ""
    
    try:
        query = unicodedata.normalize('NFKD', query)
        query = query.encode('ASCII', 'ignore').decode('utf-8')
    except:
        pass
    
    query = query.replace(":", " ")
    query = re.sub(r"[^\w\s]", "", query)
    query = re.sub(r"\s+", "+", query)
    return query.strip()


# -------------------------------------------------------------------
# BUSCA E PARSE
# -------------------------------------------------------------------

def search_apache_torrent(query):
    """Busca no ApacheTorrent."""
    query_clean = clean_query(query)
    search_url = f"https://apachetorrent.com/index.php?s={query_clean}"
    

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        'Referer': _APACHE_BASE + '/'
    }

    try:
        response = requests.get(search_url, headers=headers, timeout=_TIMEOUT)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            return response.content

            
    except Exception as e:
        xbmc.log(f"[apachetorrent] Erro na busca: {str(e)}", xbmc.LOGERROR)
    
    return None


def parse_search_results(html):
    """Parseia os resultados da busca."""
    if not html:
        return []
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Seletor principal: div.capaname
        results = soup.find_all("div", class_="capaname")
        
            
    except Exception as e:
        xbmc.log(f"[apachetorrent] Erro ao parsear HTML: {str(e)}", xbmc.LOGERROR)
    
    return []


def find_apache_post_url(html, title):
    """Encontra o link do post correspondente ao título."""
    if not html:
        return None
    
    results = parse_search_results(html)
    
    if not results:
        return None
    
    title_norm = normalize_title_for_search(title)
    title_norm = normalize_for_compare(title_norm)
    
    for idx, result in enumerate(results):
        link_tag = result.find("a", href=True)
        if not link_tag:
            continue
            
        href = link_tag.get("href", "")
        post_title = link_tag.get("title", "") or ""
        
        # Limpeza do título do post
        post_title = re.sub(r'\s*Torrent.*', '', post_title, flags=re.IGNORECASE)
        post_title = re.sub(r'\s*Download.*', '', post_title, flags=re.IGNORECASE)
        post_title = re.sub(r'\s*Dublad[oa].*', '', post_title, flags=re.IGNORECASE)
        post_title = re.sub(r'\s*Legendad[oa].*', '', post_title, flags=re.IGNORECASE)
        post_title = re.sub(r'\s*Dual.*', '', post_title, flags=re.IGNORECASE)
        post_title = re.sub(r'\s*\(.*?\)', '', post_title)
        post_title = post_title.strip()
        
        post_norm = normalize_title_for_search(post_title)
        post_norm = normalize_for_compare(post_norm)
        
        # Correspondência bidirecional
        if title_norm in post_norm or post_norm in title_norm:
            xbmc.log(f"[apachetorrent] CORRESPONDÊNCIA ENCONTRADA: {post_title}", xbmc.LOGINFO)
            return href
    
    return None


# -------------------------------------------------------------------
# SCRAPER PRINCIPAL (APENAS FILMES)
# -------------------------------------------------------------------

def scrape_apache(provider_url, item_data, season=None, episode=None, timeout=None):
    """
    Scraper do ApacheTorrent - EXCLUSIVO PARA FILMES.
    """
    global _TIMEOUT
    if timeout:
        _TIMEOUT = timeout

    title = item_data.get("title", "")
    media_type = item_data.get("media_type", "movie")
    year = item_data.get("year", "")

    # ═══ IGNORA SÉRIES ═══
    if media_type != "movie":
        return []

    title_search = normalize_title_for_search(title)

    # Queries para filmes: com ano → sem ano → primeira palavra
    queries = []
    if year:
        queries.append(f"{title_search} {year}")
    queries.append(title_search)
    
    first_word = title_search.split()[0] if title_search.split() else title_search
    if first_word != title_search:
        queries.append(first_word)

    # Busca
    html = None
    for q in queries:
        candidate = search_apache_torrent(q)
        if candidate and parse_search_results(candidate):
            html = candidate
            break

    if not html:
        xbmc.log(f"[apachetorrent] Nenhum resultado", xbmc.LOGWARNING)
        return []

    # Encontra o post
    post_url = find_apache_post_url(html, title)

    if not post_url:
        xbmc.log(f"[apachetorrent] Nenhum post encontrado", xbmc.LOGWARNING)
        return []

    # Corrige URL relativa
    if not post_url.startswith('http'):
        post_url = _APACHE_BASE + (post_url if post_url.startswith('/') else f'/{post_url}')


    # Acessa o post
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': _APACHE_BASE + '/'
    }

    try:
        response = requests.get(post_url, headers=headers, timeout=_TIMEOUT)
        if response.status_code != 200:
            xbmc.log(f"[apachetorrent] Erro ao acessar post: {response.status_code}", xbmc.LOGWARNING)
            return []

        magnets = extract_magnets(
            response.content, title,
            target_episode=episode, season=season, media_type=media_type,
            provider_name="ApacheTorrent"
        )

        if magnets:
            dual_count = sum(1 for m in magnets if m.get('languages') == 'DUAL')
            leg_count = sum(1 for m in magnets if m.get('languages') == 'LEG')
        else:
            xbmc.log(f"[apachetorrent] Nenhum magnet encontrado", xbmc.LOGWARNING)
        
        return magnets or []

    except Exception as e:
        xbmc.log(f"[apachetorrent] Erro ao acessar post: {str(e)}", xbmc.LOGERROR)
        return []