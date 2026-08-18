# -*- coding: utf-8 -*-
"""
Cineroom Burst - Core Utils
============================
Utilitários centrais do Burst (distintos dos scrapers/utils.py).
"""

import xbmc


def build_torrentio_config_string():
    """
    Constrói a string de configuração para o Torrentio configurável.
    Retorna string vazia se não houver configuração extra.
    """
    # Retorna vazio por padrão — Torrentio usa a URL já pré-configurada em config.py
    # Este stub evita ImportError em scrapers que tentam importar daqui.
    return ""