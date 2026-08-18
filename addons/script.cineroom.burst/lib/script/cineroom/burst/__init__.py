# -*- coding: utf-8 -*-
"""
Cineroom Burst - Biblioteca de Scrapers
========================================

API pública para integração com addons de streaming.

Exemplo de uso:
    >>> import script.cineroom.burst as burst
    >>> 
    >>> # Modo individual (compatibilidade)
    >>> provider_data = {"url": "https://brazuca.life", "configurable": False}
    >>> item_data = {"imdb_id": "tt1234567", "media_type": "movie", "title": "Filme"}
    >>> sources = burst.scrape("Brazuca", provider_data, item_data)
    >>> 
    >>> # Modo paralelo (NOVO - otimizado)
    >>> def on_progress(done, total, name):
    ...     print(f"Progresso: {done}/{total} - {name}")
    >>> 
    >>> all_sources = burst.scrape_all_sources(item_data, on_progress)
    >>> for provider, sources in all_sources.items():
    ...     print(f"{provider}: {len(sources)} fontes")

Versão: 2.1.0
Autor: Gael
Licença: GPL-3.0
"""

__version__ = "2.1.0"
__author__ = "Gael"
__license__ = "GPL-3.0"

from .core.router import scrape_provider_sources, scrape_all_sources
from .config import (
    get_enabled_providers,
    get_all_providers,
    is_provider_enabled,
    get_scraper_timeout,
    is_cache_enabled,
    get_cache_duration,
    get_max_workers
)

# Alias para compatibilidade
scrape = scrape_provider_sources

__all__ = [
    'scrape_provider_sources',
    'scrape_all_sources',
    'scrape',
    'get_enabled_providers',
    'get_all_providers',
    'is_provider_enabled',
    'get_scraper_timeout',
    'is_cache_enabled',
    'get_cache_duration',
    'get_max_workers',
    '__version__',
    '__author__',
    '__license__'
]