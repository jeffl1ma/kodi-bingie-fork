# -*- coding: utf-8 -*-
"""
scraper_config.py — Remote config de URLs dos scrapers
=======================================================

Carrega um JSON hospedado no GitHub com a URL base de cada scraper.
Na ausência de conexão, usa o cache local (TTL de 1 dia).
Na ausência de cache, usa os fallbacks embutidos em cada scraper.

Uso nos scrapers:
    from .scraper_config import get_url

    BASE_URL = get_url('assistirfilme', fallback='https://assistirfilmes.biz')
"""

import os
import json
import time
import xbmc

try:
    import requests as _requests
except ImportError:
    _requests = None

# ─── Configurações ────────────────────────────────────────────────────────────

# URL do JSON no GitHub (branch main, arquivo na raiz do repo)
CONFIG_URL = (
    'https://cdn.jsdelivr.net/gh/Gael1303/flixroom@main/cineroom/jsons/scraper_config.json'
)

# TTL do cache local em segundos (padrão: 1 dia)
CACHE_TTL = 86_400

# ─── Paths ────────────────────────────────────────────────────────────────────

def _cache_path():
    try:
        import xbmcaddon
        import xbmcvfs
        profile = xbmcaddon.Addon('script.cineroom.burst').getAddonInfo('profile')
        # Converte special://profile/... para path real do filesystem
        profile = xbmcvfs.translatePath(profile)
    except Exception:
        import tempfile
        profile = tempfile.gettempdir()
    return os.path.join(profile, 'scraper_config.json')


# ─── Estado interno (singleton por processo) ──────────────────────────────────

_config_cache = {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_remote():
    """Baixa o JSON do GitHub. Retorna dict ou None em caso de falha."""
    if not _requests:
        xbmc.log('[ScraperConfig] requests não disponível, pulando fetch remoto.', xbmc.LOGWARNING)
        return None
    try:
        r = _requests.get(CONFIG_URL, timeout=8)
        r.raise_for_status()
        data = r.json()
        _save_cache(data)
        xbmc.log('[ScraperConfig] Config remota carregada com sucesso.', xbmc.LOGDEBUG)
        return data
    except Exception as e:
        xbmc.log(f'[ScraperConfig] Falha ao buscar config remota: {e}', xbmc.LOGWARNING)
        return None


def _save_cache(data):
    """Persiste config + timestamp no perfil do addon."""
    try:
        path = _cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'ts': time.time(), 'data': data}, f)
    except Exception as e:
        xbmc.log(f'[ScraperConfig] Erro ao salvar cache: {e}', xbmc.LOGWARNING)


def _load_cache():
    """Carrega cache local se ainda estiver dentro do TTL. Retorna dict ou None."""
    try:
        with open(_cache_path(), 'r', encoding='utf-8') as f:
            cached = json.load(f)
        age = time.time() - cached.get('ts', 0)
        if age < CACHE_TTL:
            xbmc.log(f'[ScraperConfig] Cache local válido ({age/3600:.1f}h).', xbmc.LOGDEBUG)
            return cached['data']
        xbmc.log('[ScraperConfig] Cache local expirado, buscando remoto.', xbmc.LOGDEBUG)
    except FileNotFoundError:
        xbmc.log('[ScraperConfig] Sem cache local, buscando remoto.', xbmc.LOGDEBUG)
    except Exception as e:
        xbmc.log(f'[ScraperConfig] Erro ao ler cache: {e}', xbmc.LOGWARNING)
    return None


# ─── API pública ──────────────────────────────────────────────────────────────

def get_config():
    """
    Retorna o dict de config completo.
    Ordem de preferência: memória → cache local → remoto.
    """
    global _config_cache
    if _config_cache:
        return _config_cache

    data = _load_cache() or _fetch_remote()
    if data:
        _config_cache = data
    return _config_cache or {}


def get_url(scraper_name, key='base_url', fallback=None):
    """
    Retorna a URL configurada para *scraper_name*[*key*].
    Se não encontrar, devolve *fallback* (valor hardcoded do scraper).

    Args:
        scraper_name (str): Nome do scraper (ex: 'assistirfilme').
        key          (str): Chave dentro do bloco do scraper (default: 'base_url').
        fallback     (str): URL usada se a config não estiver disponível.

    Returns:
        str: URL resolvida.
    """
    cfg = get_config()
    url = cfg.get('scrapers', {}).get(scraper_name, {}).get(key)
    if url:
        return url.rstrip('/')
    if fallback:
        xbmc.log(
            f'[ScraperConfig] "{scraper_name}.{key}" não encontrado, usando fallback.',
            xbmc.LOGDEBUG,
        )
        return fallback.rstrip('/')
    return ''


def invalidate():
    """Força recarga na próxima chamada (útil após atualização manual)."""
    global _config_cache
    _config_cache = {}
    xbmc.log('[ScraperConfig] Cache em memória invalidado.', xbmc.LOGDEBUG)