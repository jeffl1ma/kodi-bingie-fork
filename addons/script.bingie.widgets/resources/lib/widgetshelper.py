#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys
import helpers.kodi_constants as kodi_constants
from resources.lib.helpers.utils import log_msg, ADDON_ID
from simplecache import use_cache, SimpleCache
import xbmcvfs
import xbmcaddon

if sys.version_info.major == 3:
    from urllib.parse import quote_plus
else:
    from urllib import quote_plus


class WidgetsHelper(object):
    '''
        Provides all kind of mediainfo for kodi media, returned as dict with details
    '''
    _close_called, _kodidb, _process_method_on_list, _extend_dict, _get_clean_image = [None] * 5
    cache = None


    def __init__(self):
        ''' Initialize and load all our helpers '''
        self.cache = SimpleCache()
        log_msg("Initialized")

    def process_method_on_list(self, *args, **kwargs):
        ''' expose our process_method_on_list method to public '''
        if not self._process_method_on_list:
            from helpers.utils import process_method_on_list
            self._process_method_on_list = process_method_on_list
        return self._process_method_on_list(*args, **kwargs)

    def extend_dict(self, *args, **kwargs):
        ''' expose our extend_dict method to public '''
        if not self._extend_dict:
            from helpers.utils import extend_dict
            self._extend_dict = extend_dict
        return self._extend_dict(*args, **kwargs)

    def get_clean_image(self, *args, **kwargs):
        ''' expose our get_clean_image method to public '''
        if not self._get_clean_image:
            from helpers.utils import get_clean_image
            self._get_clean_image = get_clean_image
        return self._get_clean_image(*args, **kwargs)
        
    @property
    def kodidb(self):
        ''' public kodidb object - for lazy loading '''
        if not self._kodidb:
            from helpers.kodidb import KodiDb
            self._kodidb = KodiDb()
        return self._kodidb

    def close(self):
        ''' Cleanup instances '''
        self._close_called = True
        if self.cache:
            self.cache.close()
            del self.cache
        log_msg("Exited")

    def __del__(self):
        ''' make sure close is called '''
        if not self._close_called:
            self.close()
