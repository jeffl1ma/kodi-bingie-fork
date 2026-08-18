# -*- coding: utf-8 -*-
# resources/lib/scrapers/stremio.py - VERSÃO OTIMIZADA

import re
import requests
import xbmc
from .session import USER_AGENT
from .utils import get_anime_search_patterns

# Streams com "download" em qualquer forma geralmente não reproduzem
# (ex: "[Download]", "10Gbps Download Only"). PMZ é permitido normalmente.
DOWNLOAD_TAG_PATTERN = re.compile(r'download', re.I)


def scrape(provider_url, is_configurable, imdb_id, media_type, season, episode, item_data=None, timeout=None):
    """
    Scraper Stremio unificado e otimizado.
    
    Melhorias:
    - Validação centralizada de parâmetros
    - Construção inteligente de URLs
    - Deduplicação eficiente
    - Logs concisos
    """
    
    # ========================================
    # 1. VALIDAÇÃO E NORMALIZAÇÃO
    # ========================================
    if not provider_url:
        return []
    
    # Normaliza season/episode APENAS se não forem None
    season = _safe_int(season)
    episode = _safe_int(episode)
    
    # Valida requisitos mínimos
    if not imdb_id and "animezey" not in provider_url.lower():
        xbmc.log(f"[Stremio] Sem IMDB ID para {provider_url}", xbmc.LOGDEBUG)
        return []
    
    # ========================================
    # 2. CONSTRUÇÃO DE ENDPOINTS
    # ========================================
    endpoints = _build_endpoints(media_type, imdb_id, season, episode)
    
    if not endpoints:
        xbmc.log(f"[Stremio] Nenhum endpoint válido para {media_type}", xbmc.LOGWARNING)
        return []
    
    # ========================================
    # 3. CONFIGURAÇÃO TORRENTIO
    # ========================================
    config_prefix = ""
    if is_configurable:
        try:
            from ..utils import build_torrentio_config_string
            config_prefix = build_torrentio_config_string()
        except Exception as e:
            xbmc.log(f"[Stremio] Config error: {e}", xbmc.LOGDEBUG)
    
    # ========================================
    # 4. BUSCA E DEDUPLICAÇÃO
    # ========================================
    if timeout is None:
        timeout = 15

    streams = []
    seen_ids = set()
    skipped_download = 0
    
    for endpoint in endpoints:
        url = f"{provider_url}/{config_prefix}{endpoint}" if config_prefix else f"{provider_url}{endpoint}"
        
        found = _fetch_streams(url, timeout=timeout)
        if not found:
            continue
        
        # Deduplica e adiciona release_title
        for stream in found:
            # Descarta streams marcados como [Download] -- não são reproduzíveis
            if _is_download_stream(stream):
                skipped_download += 1
                continue

            stream_id = stream.get('url') or stream.get('infoHash')
            
            if stream_id and stream_id in seen_ids:
                continue
            
            # Adiciona título de lançamento se não existir
            if 'release_title' not in stream:
                stream['release_title'] = _generate_release_title(
                    item_data, media_type, season, episode
                )
            
            streams.append(stream)
            
            if stream_id:
                seen_ids.add(stream_id)

    if skipped_download:
        xbmc.log(f"[Stremio] {skipped_download} stream(s) [Download] descartado(s)", xbmc.LOGDEBUG)

    xbmc.log(f"[Stremio] {len(streams)} streams de {provider_url.split('/')[2]}", xbmc.LOGINFO)
    return streams


# ============================================
# FUNÇÕES AUXILIARES (INTERNAS)
# ============================================

def _is_download_stream(stream):
    """Verifica se o stream contém 'download' em qualquer forma (título, nome, descrição ou filename)."""
    filename = stream.get('behaviorHints', {}).get('filename') or ''
    fields = (
        stream.get('title') or '',
        stream.get('name') or '',
        stream.get('description') or '',
        filename,
    )
    return any(DOWNLOAD_TAG_PATTERN.search(field) for field in fields)


def _safe_int(value):
    """Converte para int de forma segura."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        xbmc.log(f"[Stremio] Conversão inválida: {value}", xbmc.LOGDEBUG)
        return None


def _build_endpoints(media_type, imdb_id, season, episode):
    """
    Constrói lista de endpoints para tentar.
    
    Retorna:
        list: URLs relativas (ex: ["/stream/movie/tt1234.json"])
    """
    endpoints = []
    
    if media_type == 'movie':
        if imdb_id:
            endpoints.append(f"/stream/movie/{imdb_id}.json")
    
    elif media_type == 'tvshow':
        if season is None or episode is None:
            return []
        
        if not imdb_id:
            return []
        
        # Usa padrões de busca de anime (ex: S01:E01, S1:E1)
        patterns = get_anime_search_patterns(season, episode)
        
        for s, e in patterns:
            endpoints.append(f"/stream/series/{imdb_id}:{s}:{e}.json")
    
    return endpoints


def _fetch_streams(url, timeout=15):
    """
    Faz request e retorna lista de streams.

    Returns:
        list: Streams encontrados ou lista vazia
    """
    try:
        response = requests.get(
            url,
            headers={'User-Agent': USER_AGENT},
            timeout=timeout
        )
        response.raise_for_status()

        data = response.json()
        raw_streams = data.get('streams', [])

        # Filtra streams com "download" em qualquer forma ANTES da sanitização de linhas,
        # porque essa sanitização pode descartar a linha que contém o aviso (ex: "[10Gbps
        # Download Only]" numa linha separada que não é a mais longa do bloco).
        streams = []
        skipped = 0
        for stream in raw_streams:
            filename = stream.get('behaviorHints', {}).get('filename') or ''
            raw_fields = (
                stream.get('title') or '',
                stream.get('name') or '',
                stream.get('description') or '',
                filename,
            )
            if any(DOWNLOAD_TAG_PATTERN.search(f) for f in raw_fields):
                skipped += 1
                continue
            streams.append(stream)

        if skipped:
            xbmc.log(f"[Stremio] {skipped} stream(s) com 'download' descartado(s) em {url.split('/')[-1]}", xbmc.LOGDEBUG)

        # sanitiza campos com \n (ex: FrostStream)
        for stream in streams:
            filename = stream.get('behaviorHints', {}).get('filename')

            for field in ('title', 'name', 'description'):
                value = stream.get(field)

                if value and '\n' in value:
                    lines = [l.strip() for l in value.split('\n') if l.strip()]

                    if not lines:
                        continue

                    if field == 'title' and filename:
                        # filename é confiável e não é tocado pelo split -> preserva o nome do filme
                        stream[field] = filename
                    else:
                        # fallback: linha mais "informativa" (mais longa) em vez de sempre lines[0]
                        stream[field] = max(lines, key=len)

                    if field == 'title' and len(lines) >= 3:
                        lang_line = lines[2].strip()
                        # só trata como hint de idioma se não for a própria linha escolhida
                        if lang_line != stream[field]:
                            stream['_lang_hint'] = lang_line
        
            if not stream.get('title') and stream.get('description'):
                desc_lines = [l.strip() for l in stream['description'].split('\n') if l.strip()]
                if desc_lines:
                    candidate = desc_lines[0].lstrip('🍿').strip()
                    # ignora se for só um IMDB id tipo "tt1234567" (caso do OverFlix)
                    if candidate and not candidate.lower().startswith('tt'):
                        stream['title'] = candidate
                    elif filename:
                        stream['title'] = filename
                    else:
                        # fallback final: usa o item_data (título real do TMDB) depois, via release_title
                        stream['title'] = candidate
                            

        if streams:
            xbmc.log(
                f"[Stremio] ✓ {len(streams)} em {url.split('/')[-1]}",
                xbmc.LOGDEBUG
            )

        return streams

    except requests.Timeout:
        xbmc.log(f"[Stremio] Timeout: {url}", xbmc.LOGWARNING)

    except requests.RequestException as e:
        xbmc.log(f"[Stremio] Erro HTTP: {e}", xbmc.LOGDEBUG)

    except ValueError:
        xbmc.log(f"[Stremio] JSON inválido: {url}", xbmc.LOGWARNING)

    except Exception as e:
        xbmc.log(f"[Stremio] Erro inesperado: {e}", xbmc.LOGERROR)

    return []


def _generate_release_title(item_data, media_type, season, episode):
    """
    Gera título de lançamento padrão.
    
    Ex: "Breaking Bad S01E05" ou "Interstellar"
    """
    if not item_data:
        if media_type == 'tvshow' and season is not None and episode is not None:
            return f"S{season:02d}E{episode:02d}"
        return "Desconhecido"
    
    title = item_data.get('title', 'Desconhecido')
    
    if media_type == 'tvshow' and season is not None and episode is not None:
        return f"{title} S{season:02d}E{episode:02d}"
    
    return title