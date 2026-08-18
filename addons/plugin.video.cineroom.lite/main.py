# -*- coding: utf-8 -*-
"""Cineroom Lite - entrypoint

Toda a lógica de routing/handlers está em resources.lib.router.
"""
from resources.lib.router.router import run

if __name__ == "__main__":
    run()
