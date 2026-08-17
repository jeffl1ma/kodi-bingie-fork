from tmdbbingiehelper.lib.files.ftools import cached_property
from tmdbbingiehelper.lib.addon.dialog import BusyDialog
from tmdbbingiehelper.lib.script.sync.basic import ItemWatched, ItemUnwatched, ItemWatchlist, ItemCollection, ItemFavorites, ItemDropped
from tmdbbingiehelper.lib.script.sync.rating import ItemRating, ItemLike, ItemDislike, ItemReset
from tmdbbingiehelper.lib.script.sync.comments import ItemComments
from tmdbbingiehelper.lib.script.sync.userlist import ItemUserList, ItemMDbList
from tmdbbingiehelper.lib.script.sync.progress import ItemProgress
from xbmcgui import Dialog


class MenuAttributes:
    """
    choices
    """
    @cached_property
    def choices(self):
        return self.get_choices()

    def get_choices(self):
        from tmdbbingiehelper.lib.addon.thread import ParallelThread

        def _threaditem(i):
            return i(self.tmdb_type, self.tmdb_id, self.season, self.episode).get_self()

        with BusyDialog():
            with ParallelThread([v for _, v in self.items.items()], _threaditem) as pt:
                item_queue = pt.queue
            choices = [i for i in item_queue if i]

        return choices

    """
    trakt_api
    """
    @cached_property
    def trakt_api(self):
        return self.get_trakt_api()

    def get_trakt_api(self):
        from tmdbbingiehelper.lib.api.trakt.api import TraktAPI
        return TraktAPI()


class Menu(MenuAttributes):
    items = {
        'watched': ItemWatched,
        'unwatched': ItemUnwatched,
        'watchlist': ItemWatchlist,
        'collection': ItemCollection,
        'favorites': ItemFavorites,
        'userlist': ItemUserList,
        'mdblistuser': ItemMDbList,
        'progress': ItemProgress,
        'comments': ItemComments,
        'dropped': ItemDropped,
        'rating': ItemRating,
    }

    rating_items = {
        'like': ItemLike,
        'dislike': ItemDislike,
        'reset': ItemReset,
    }

    def __init__(self, tmdb_type, tmdb_id, season=None, episode=None):
        self.tmdb_type = tmdb_type
        self.tmdb_id = tmdb_id
        self.season = season
        self.episode = episode

    def choose(self):
        if not self.choices:
            return -1
        if len(self.choices) == 1:
            return 0
        return Dialog().contextmenu([i.name for i in self.choices])

    def select(self, sync_type=None):
        if sync_type:
            cls = self.items.get(sync_type) or self.rating_items.get(sync_type)
            if not cls:
                return
            item = cls(self.tmdb_type, self.tmdb_id, self.season, self.episode).get_self()
            if item:
                item.sync()
            return
        x = self.choose()
        if x == -1:
            return
        self.choices[x].sync()


def sync_trakt_item(tmdb_type, tmdb_id, season=None, episode=None, sync_type=None):
    menu = Menu(tmdb_type, tmdb_id, season, episode)
    menu.select(sync_type)
