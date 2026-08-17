#!/usr/bin/python
# -*- coding: utf-8 -*-
import bingie.scache
from tmdbbingiehelper.lib.addon.logger import kodi_log
from tmdbbingiehelper.lib.addon.plugin import get_setting
from tmdbbingiehelper.lib.files.futils import FileUtils


class SimpleCache(bingie.scache.SimpleCache):
    _basefolder = get_setting('cache_location', 'str') or ''
    _fileutils = FileUtils()  # Import to use plugin addon_data folder not the module one

    @staticmethod
    def kodi_log(msg, level=0):
        kodi_log(msg, level)
