import bingie.reqapi
from tmdbbingiehelper.lib.addon.plugin import get_setting
from tmdbbingiehelper.lib.addon.logger import kodi_log
from tmdbbingiehelper.lib.files.bcache import BasicCache


class RequestAPI(bingie.reqapi.RequestAPI):
    error_notification = get_setting('connection_notifications')
    _basiccache = BasicCache

    @staticmethod
    def kodi_log(msg, level=0):
        kodi_log(msg, level)
