# -*- coding: utf-8 -*-
"""
Scraper para Torrent dos Filmes
Extrai magnet links de filmes e séries
"""
import re
import base64
import xbmc
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from .scraper_config import get_url

_TORF_BASE = get_url('torrentdosfilmes', fallback='https://torrentdosfilmes-v1.xyz')


def decode_base64_url(encoded_str):
    """
    Decodifica Base64 URL-safe (igual ao JavaScript do site)
    """
    try:
        # Substitui caracteres URL-safe
        encoded_str = encoded_str.replace('-', '+').replace('_', '/')
        
        # Adiciona padding se necessário
        while len(encoded_str) % 4 != 0:
            encoded_str += '='
        
        # Decodifica
        decoded = base64.b64decode(encoded_str).decode('utf-8')
        return decoded
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro ao decodificar Base64: {e}", xbmc.LOGERROR)
        return None


def extrair_magnet_da_pagina_intermediaria(url):
    """
    Acessa a página intermediária e extrai o magnet do data-download
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://torrentdosfilmes-v1.xyz/'
        }
        
        xbmc.log(f"[TorrentFilmes] Acessando página intermediária: {url}", xbmc.LOGINFO)
        
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procurar o atributo data-download no body
        body = soup.find('body')
        if not body:
            xbmc.log("[TorrentFilmes] Tag <body> não encontrada", xbmc.LOGWARNING)
            return None
        
        data_download = body.get('data-download')
        if not data_download:
            xbmc.log("[TorrentFilmes] Atributo data-download não encontrado", xbmc.LOGWARNING)
            return None
        
        xbmc.log(f"[TorrentFilmes] data-download encontrado: {data_download[:50]}...", xbmc.LOGINFO)
        
        # Decodificar Base64
        magnet = decode_base64_url(data_download)
        
        if magnet and magnet.startswith('magnet:'):
            xbmc.log(f"[TorrentFilmes] Magnet extraído com sucesso!", xbmc.LOGINFO)
            return magnet
        
        xbmc.log(f"[TorrentFilmes] Formato inválido após decodificação: {magnet[:50] if magnet else 'None'}", xbmc.LOGWARNING)
        return None
        
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro ao extrair magnet: {e}", xbmc.LOGERROR)
        return None


def extrair_link_intermediario(soup):
    """
    Extrai o link intermediário (systemads.org ou autotop.net)
    """
    try:
        # Procurar botão com classe customButton ou btn-download
        btn = soup.find('a', class_='customButton')
        if not btn:
            btn = soup.find('a', class_='btn-download')
        
        if not btn:
            xbmc.log("[TorrentFilmes] Botão de download não encontrado", xbmc.LOGWARNING)
            return None
        
        href = btn.get('href')
        if not href:
            xbmc.log("[TorrentFilmes] Href não encontrado no botão", xbmc.LOGWARNING)
            return None
        
        # Verificar se é link válido
        if href.startswith('http'):
            return href
        
        return None
        
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro ao extrair link intermediário: {e}", xbmc.LOGERROR)
        return None


def extrair_informacoes_filme(soup):
    """
    Extrai informações do filme da página de catálogo
    """
    info = {}
    
    try:
        # Título
        h1 = soup.find('h1')
        if h1:
            info['title'] = h1.text.strip()
        
        # Procurar informações no conteúdo
        content = soup.find('div', class_='content')
        if content:
            text = content.get_text()
            
            # Tamanho
            size_match = re.search(r'Tamanho:\s*([^\n]+)', text)
            if size_match:
                info['size'] = size_match.group(1).strip()
            
            # Qualidade
            quality_match = re.search(r'(1080p|720p|4K|2160p)', text, re.IGNORECASE)
            if quality_match:
                info['quality'] = quality_match.group(1).upper()
            
            # IMDB
            imdb_match = re.search(r'IMDb:\s*([^\n]+)', text)
            if imdb_match:
                info['rating'] = imdb_match.group(1).strip()
            
            # Áudio
            if 'Dual Áudio' in text or 'Dual Audio' in text:
                info['audio'] = 'DUAL'
            elif 'Dublado' in text:
                info['audio'] = 'PT-BR'
            elif 'Legendado' in text:
                info['audio'] = 'LEG'
        
        # Categorias
        category_div = soup.find('div', class_='category')
        if category_div:
            links = category_div.find_all('a')
            for link in links:
                text = link.text.strip()
                # Detectar resolução
                if text in ['1080p', '720p', '4K', '2160p']:
                    info['quality'] = text
                # Detectar ano
                elif text.isdigit() and len(text) == 4:
                    info['year'] = text
    
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro ao extrair informações: {e}", xbmc.LOGERROR)
    
    return info


def buscar_filme(item_data):
    """
    Busca um filme no Torrent dos Filmes
    """
    titulo = item_data.get('title', '')
    ano = item_data.get('year', '')
    
    if not titulo:
        return []
    
    try:
        # Normalizar título
        search_query = titulo.lower()
        search_query = re.sub(r'[^\w\s]', '', search_query)
        search_query = search_query.replace(' ', '+')
        
        base_url = _TORF_BASE
        search_url = f"{base_url}/?s={search_query}"
        
        xbmc.log(f"[TorrentFilmes] Buscando: {search_url}", xbmc.LOGINFO)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procurar resultados (podem estar em articles ou divs)
        resultados = soup.find_all('article')
        if not resultados:
            resultados = soup.find_all('div', class_='item')
        
        sources = []
        
        for resultado in resultados[:3]:  # Limitar a 3 resultados
            try:
                # Link do filme
                link_tag = resultado.find('a')
                if not link_tag:
                    continue
                
                filme_url = link_tag.get('href')
                if not filme_url:
                    continue
                
                # Título
                h1 = resultado.find('h1')
                h2 = resultado.find('h2')
                h3 = resultado.find('h3')
                
                filme_titulo = ''
                if h1:
                    filme_titulo = h1.text.strip()
                elif h2:
                    filme_titulo = h2.text.strip()
                elif h3:
                    filme_titulo = h3.text.strip()
                
                if not filme_titulo:
                    continue
                
                # Verificar ano (se disponível)
                if ano and ano not in filme_titulo:
                    # Pode ainda ser o filme certo, mas com outro formato
                    pass
                
                xbmc.log(f"[TorrentFilmes] Processando: {filme_titulo}", xbmc.LOGINFO)
                
                # Acessar página do filme
                filme_response = requests.get(filme_url, headers=headers, timeout=10)
                filme_soup = BeautifulSoup(filme_response.text, 'html.parser')
                
                # Extrair link intermediário
                link_intermediario = extrair_link_intermediario(filme_soup)
                if not link_intermediario:
                    xbmc.log(f"[TorrentFilmes] Link intermediário não encontrado para {filme_titulo}", xbmc.LOGWARNING)
                    continue
                
                # Acessar página intermediária e extrair magnet
                magnet = extrair_magnet_da_pagina_intermediaria(link_intermediario)
                if not magnet:
                    continue
                
                # Extrair informações
                info = extrair_informacoes_filme(filme_soup)
                
                # Montar stream
                stream = {
                    'url': magnet,
                    'title': filme_titulo,
                    'quality': info.get('quality', 'HD'),
                    'size': info.get('size', 'N/A'),
                    'type': 'Torrent',
                    'seeders': 0,  # Site não fornece seeders
                    'extras': []
                }
                
                sources.append(stream)
                
            except Exception as e:
                xbmc.log(f"[TorrentFilmes] Erro ao processar resultado: {e}", xbmc.LOGERROR)
                continue
        
        return sources
        
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro na busca: {e}", xbmc.LOGERROR)
        return []


def buscar_serie(item_data, season, episode):
    """
    Busca um episódio de série no Torrent dos Filmes
    """
    titulo = item_data.get('title', '')
    
    if not titulo or season is None or episode is None:
        return []
    
    try:
        # Normalizar título
        search_query = titulo.lower()
        search_query = re.sub(r'[^\w\s]', '', search_query)
        search_query = search_query.replace(' ', '+')
        
        # Adicionar temporada/episódio
        s = str(season).zfill(2)
        e = str(episode).zfill(2)
        search_query += f"+s{s}e{e}"
        
        base_url = "https://torrentdosfilmes-v1.xyz"
        search_url = f"{base_url}/?s={search_query}"
        
        xbmc.log(f"[TorrentFilmes] Buscando série: {search_url}", xbmc.LOGINFO)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        resultados = soup.find_all('article')
        if not resultados:
            resultados = soup.find_all('div', class_='item')
        
        sources = []
        
        for resultado in resultados[:2]:
            try:
                link_tag = resultado.find('a')
                if not link_tag:
                    continue
                
                ep_url = link_tag.get('href')
                if not ep_url:
                    continue
                
                # Título
                h1 = resultado.find('h1')
                ep_titulo = h1.text.strip() if h1 else ''
                
                # Verificar episódio
                if f"s{s}e{e}" not in ep_titulo.lower():
                    continue
                
                xbmc.log(f"[TorrentFilmes] Processando episódio: {ep_titulo}", xbmc.LOGINFO)
                
                # Acessar página
                ep_response = requests.get(ep_url, headers=headers, timeout=10)
                ep_soup = BeautifulSoup(ep_response.text, 'html.parser')
                
                # Link intermediário
                link_intermediario = extrair_link_intermediario(ep_soup)
                if not link_intermediario:
                    continue
                
                # Magnet
                magnet = extrair_magnet_da_pagina_intermediaria(link_intermediario)
                if not magnet:
                    continue
                
                # Informações
                info = extrair_informacoes_filme(ep_soup)
                
                stream = {
                    'url': magnet,
                    'title': ep_titulo,
                    'quality': info.get('quality', 'HD'),
                    'size': info.get('size', 'N/A'),
                    'type': 'Torrent',
                    'seeders': 0,
                    'extras': []
                }
                
                sources.append(stream)
                
            except Exception as e:
                xbmc.log(f"[TorrentFilmes] Erro ao processar episódio: {e}", xbmc.LOGERROR)
                continue
        
        return sources
        
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro na busca de série: {e}", xbmc.LOGERROR)
        return []


def scrape(provider_url, item_data, season=None, episode=None):
    """
    Função principal do scraper
    """
    xbmc.log("[TorrentFilmes] Iniciando scraper...", xbmc.LOGINFO)
    
    media_type = item_data.get('media_type')
    
    try:
        if media_type == 'movie':
            return buscar_filme(item_data)
        elif media_type == 'tvshow':
            return buscar_serie(item_data, season, episode)
    except Exception as e:
        xbmc.log(f"[TorrentFilmes] Erro geral no scraper: {e}", xbmc.LOGERROR)
    
    return []