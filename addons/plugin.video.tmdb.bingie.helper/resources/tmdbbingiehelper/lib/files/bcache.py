from tmdbbingiehelper.lib.addon.logger import kodi_traceback
from tmdbbingiehelper.lib.files.scache import SimpleCache
import bingie.bcache

use_simple_cache = bingie.bcache.use_simple_cache


class BasicCache(bingie.bcache.BasicCache):
    _queue_limit = 250
    _simplecache = SimpleCache

    @staticmethod
    def kodi_traceback(exc, log_msg):
        kodi_traceback(exc, log_msg)


class BasicCacheService(BasicCache):
    _queue_limit = 20
