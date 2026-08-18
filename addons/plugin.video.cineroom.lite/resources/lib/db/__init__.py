# -*- coding: utf-8 -*-
"""
resources/lib/db/__init__.py

✅ Herança múltipla correta
✅ FavoritesDatabase com suporte a perfis
✅ HistoryDatabase: free (sem profile_id) e VIP (com profile_id)
✅ Watchlist removida
"""

from .movies_db import MoviesDatabase
from .tvshows_db import TVShowsDatabase
from .favorites_db import FavoritesDatabase
from .history_db import HistoryDatabase
import xbmc


class Database(MoviesDatabase, TVShowsDatabase, FavoritesDatabase, HistoryDatabase):
    """
    Classe principal do banco de dados.
    Herda de todas as classes especializadas.
    """
    def __init__(self):
        super().__init__()


# ============ INSTÂNCIA GLOBAL ============
db = Database()


# ============ FUNÇÕES DE COMPATIBILIDADE ============

def get_watched_movies():
    return db.get_watched_movies()


def get_watched_tvshows():
    return db.get_watched_tvshows()


def add_to_favorites(tmdb_id, media_type, profile_id=None):
    return db.add_to_favorites(tmdb_id, media_type, profile_id=profile_id)


def remove_from_favorites(tmdb_id, media_type, profile_id=None):
    return db.remove_from_favorites(tmdb_id, media_type, profile_id=profile_id)


def is_favorite(tmdb_id, media_type, profile_id=None):
    return db.is_favorite(tmdb_id, media_type, profile_id=profile_id)


def get_all_favorites(profile_id=None):
    return db.get_all_favorites(profile_id=profile_id)


def get_movie_by_id(tmdb_id):
    return db.get_movie_by_id(tmdb_id)


def get_tvshow_by_id(tmdb_id):
    return db.get_tvshow_by_id(tmdb_id)


def update_movie_playcount(tmdb_id, playcount, last_played=None):
    return db.update_movie_playcount(tmdb_id, playcount, last_played)


def update_tvshow_playcount(tmdb_id, last_played=None):
    return db.update_tvshow_playcount(tmdb_id, last_played)


def mark_movie_as_watched(tmdb_id):
    return db.mark_movie_as_watched(tmdb_id)


# ============ HISTÓRICO ============

def add_to_history(tmdb_id, media_type, profile_id=None,
                   season=None, episode=None, progress=0.0):
    """
    Free: chame sem profile_id → histórico global.
    VIP:  chame com profile_id → histórico isolado por perfil.
    """
    return db.add_to_history(tmdb_id, media_type, profile_id=profile_id,
                             season=season, episode=episode, progress=progress)


def get_history(profile_id=None, limit=50):
    return db.get_history(profile_id=profile_id, limit=limit)


def get_movie_progress(tmdb_id, profile_id=None):
    return db.get_movie_progress(tmdb_id, profile_id=profile_id)


def is_watched(tmdb_id, media_type, profile_id=None,
               season=None, episode=None, min_progress=75.0):
    return db.is_watched(tmdb_id, media_type, profile_id=profile_id,
                         season=season, episode=episode, min_progress=min_progress)


# ============ EXPORTAÇÃO ============
__all__ = [
    'db',
    'Database',
    'MoviesDatabase',
    'TVShowsDatabase',
    'FavoritesDatabase',
    'HistoryDatabase',
    # favorites
    'get_watched_movies',
    'get_watched_tvshows',
    'add_to_favorites',
    'remove_from_favorites',
    'is_favorite',
    'get_all_favorites',
    'get_movie_by_id',
    'get_tvshow_by_id',
    'update_movie_playcount',
    'update_tvshow_playcount',
    'mark_movie_as_watched',
    # history
    'add_to_history',
    'get_history',
    'get_movie_progress',
    'is_watched',
]