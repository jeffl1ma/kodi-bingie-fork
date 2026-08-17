from tmdbbingiehelper.lib.addon.thread import SafeThread
from bingie.ftools import cached_property

CRONJOB_POLL_TIME = 600


class CronJobMonitor(SafeThread):

    _poll_time = CRONJOB_POLL_TIME

    def __init__(self, parent, update_hour=0):
        SafeThread.__init__(self)
        self.exit = False
        self.update_hour = update_hour
        self.update_monitor = parent.update_monitor

    def _on_startup(self):
        self._do_delete_old_databases()
        self._do_recache_kodidb()
        self._do_trakt_authorization()

    def _on_poll(self):
        self._do_library_update_check()
        self._do_reset_trakt_lastactivities()

    @cached_property
    def trakt_api(self):
        from tmdbbingiehelper.lib.api.trakt.api import TraktAPI
        return TraktAPI()

    @staticmethod
    def _do_delete_old_databases():
        from tmdbbingiehelper.lib.script.method.maintenance import clean_old_databases
        clean_old_databases()

    @staticmethod
    def _do_recache_kodidb():
        from tmdbbingiehelper.lib.script.method.maintenance import recache_kodidb
        recache_kodidb(notification=False)

    def _do_trakt_authorization(self):
        from bingie.window import get_property
        self.trakt_api.authorize()
        self.update_monitor.waitForAbort(1)
        if not get_property('TraktIsAuth', is_type=float):
            return
        from tmdbbingiehelper.lib.script.method.trakt import get_stats
        get_stats()

    def _do_reset_trakt_lastactivities(self):
        from bingie.window import get_property
        from tmdbbingiehelper.lib.addon.consts import LASTACTIVITIES_DATA
        get_property(LASTACTIVITIES_DATA, clear_property=True)

    def _do_library_update(self):
        from tmdbbingiehelper.lib.addon.plugin import executebuiltin
        from tmdbbingiehelper.lib.addon.tmdate import get_datetime_now, get_timedelta
        executebuiltin('RunScript(plugin.video.tmdb.bingie.helper,library_autoupdate)')
        executebuiltin(f'Skin.SetString(TMDbBingieHelper.AutoUpdate.LastTime,{get_datetime_now().strftime("%Y-%m-%dT%H:%M:%S")})')
        self.library_update_next += get_timedelta(hours=24)  # Set next update for tomorrow

    def _do_library_update_check(self):
        from bingie.parser import try_int
        from tmdbbingiehelper.lib.addon.tmdate import convert_timestamp, get_datetime_now, get_timedelta, get_datetime_today, get_datetime_time, get_datetime_combine
        from tmdbbingiehelper.lib.addon.plugin import get_setting, get_infolabel
        if not get_setting('library_autoupdate'):
            return
        self.library_update_next = get_datetime_combine(get_datetime_today(), get_datetime_time(try_int(self.update_hour)))
        self.library_update_last = get_infolabel('Skin.String(TMDbBingieHelper.AutoUpdate.LastTime)')
        self.library_update_last = convert_timestamp(self.library_update_last) if self.library_update_last else None

        # If we've already updated the library today then set a new next update time for tomorrow
        if self.library_update_last and self.library_update_last > self.library_update_next:
            self.library_update_next += get_timedelta(hours=24)

        # If the next update timestamp has elapsed then we should update the library
        if get_datetime_now() > self.library_update_next:
            self._do_library_update()

    def run(self):
        self._on_startup()

        while not self.update_monitor.abortRequested() and not self.exit:
            self.update_monitor.waitForAbort(self._poll_time)
            self._on_poll()
