# -*- coding: utf-8 -*-
import re
import urllib.parse
import xbmc
import requests
from bs4 import BeautifulSoup

from .utils import extract_magnets
from .scraper_config import get_url

# Timeout por request, configurável via settings.xml (scraper.timeout).
_TIMEOUT = 15

def search_comando_top(query):
    base_url = get_url('comando', fallback='https://comandofilmestop.site')
    search_url = f"{base_url}/?s={urllib.parse.quote_plus(query)}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        xbmc.log(f"[comando.top] Buscando por: {query}", xbmc.LOGINFO)
        response = requests.get(search_url, headers=headers, timeout=_TIMEOUT)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        xbmc.log(f"[comando.top] Erro de busca: {str(e)}", xbmc.LOGERROR)
    return None


def find_content_url(html, title, year, season=None, imdb_id=None):
    if not html: 
        return None
    soup = BeautifulSoup(html, "html.parser")
    
    articles = soup.find_all("article", class_=re.compile(r"movie-card"))
    
    for article in articles:
        link_tag = article.find("a", href=True)
        if not link_tag:
            continue
        
        img_tag = link_tag.find("img")
        post_title = img_tag.get("alt", "").lower() if img_tag else ""
        
        if season:
            season_pattern = rf"{season}ª?\s*temporada"
            if not re.search(season_pattern, post_title):
                continue

        if imdb_id:
            return link_tag["href"]
        if title.lower() in post_title:
            return link_tag["href"]
            
    return None


def scrape(provider_url, item_data, season=None, episode=None, timeout=None):
    global _TIMEOUT
    if timeout:
        _TIMEOUT = timeout

    title = item_data.get("title")
    year = item_data.get("year")
    media_type = item_data.get("media_type", "movie")

    # --- Monta a query de busca ---
    if media_type == "tvshow" and season:
        query = f"{title} {season} temporada"
    else:
        query = title

    # Busca no ComandoTop
    html_search = search_comando_top(query)

    # Encontra a URL do post correto
    post_url = find_content_url(html_search, title, year, season=season)

    if post_url:
        xbmc.log(f"[comando.top] Post validado encontrado: {post_url}", xbmc.LOGINFO)
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(post_url, headers=headers, timeout=_TIMEOUT)
        # Extrai os magnets filtrando pelo episódio se houver
        return extract_magnets(response.content, title, target_episode=episode, season=season, media_type=media_type, provider_name="ComandoTop")

    return []

