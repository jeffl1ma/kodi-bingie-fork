#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys
import xbmcgui
import xbmc
import xbmcvfs
import xbmcaddon
import sys
import requests
import traceback
from traceback import format_exc
from urllib.parse import unquote
import unicodedata
import datetime
import time
import xml.etree.ElementTree as ET

try:
    import simplejson as json
except Exception:
    import json


ADDON_ID = "script.bingie.widgets"
KODI_LANGUAGE = xbmc.getLanguage(xbmc.ISO_639_1)
if not KODI_LANGUAGE:
    KODI_LANGUAGE = "en"
KODI_VERSION = int(xbmc.getInfoLabel("System.BuildVersion").split(".")[0])

FORCE_DEBUG_LOG = False
try:
    ADDON = xbmcaddon.Addon(ADDON_ID)
    FORCE_DEBUG_LOG = ADDON.getSetting('debug_log') == 'true'
    del ADDON
except Exception:
    pass

def log_msg(msg, loglevel=xbmc.LOGDEBUG):
    ''' log message to kodi logfile '''
    if loglevel == xbmc.LOGDEBUG and FORCE_DEBUG_LOG:
        loglevel = xbmc.LOGINFO
    xbmc.log("%s --> %s" % (ADDON_ID, msg), level=loglevel)

def log_exception(modulename, exceptiondetails):
    ''' helper to properly log an exception '''
    exc_type, exc_value, exc_traceback = sys.exc_info()
    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    log_msg("Exception details: Type: %s Value: %s Traceback: %s" % (exc_type.__name__, exc_value, ''.join(line for line in lines)), xbmc.LOGWARNING)
    log_msg("Exception in %s ! --> %s" % (modulename, exceptiondetails), xbmc.LOGERROR)

def rate_limiter(rl_params):
    ''' A very basic rate limiter which limits to 1 request per X seconds to the api '''
    # Please respect the parties providing these free api's to us and do not modify this code.
    # If I suspect any abuse I will revoke all api keys and require all users
    # to have a personal api key for all services.
    # Thank you
    if not rl_params:
        return
    monitor = xbmc.Monitor()
    win = xbmcgui.Window(10000)
    rl_name = rl_params[0]
    rl_delay = rl_params[1]
    cur_timestamp = int(time.mktime(datetime.datetime.now().timetuple()))
    prev_timestamp = try_parse_int(win.getProperty("ratelimiter.%s" % rl_name))
    if (prev_timestamp + rl_delay) > cur_timestamp:
        sec_to_wait = (prev_timestamp + rl_delay) - cur_timestamp
        log_msg(
            "Rate limiter active for %s - delaying request with %s seconds - "
            "Configure a personal API key in the settings to get rid of this message and the delay." %
            (rl_name, sec_to_wait), xbmc.LOGINFO)
        while sec_to_wait and not monitor.abortRequested():
            monitor.waitForAbort(1)
            # keep setting the timestamp to create some sort of queue
            cur_timestamp = int(time.mktime(datetime.datetime.now().timetuple()))
            win.setProperty("ratelimiter.%s" % rl_name, "%s" % cur_timestamp)
            sec_to_wait -= 1
    # always set the timestamp
    cur_timestamp = int(time.mktime(datetime.datetime.now().timetuple()))
    win.setProperty("ratelimiter.%s" % rl_name, "%s" % cur_timestamp)
    del monitor
    del win

def get_json(url, params=None, retries=0, ratelimit=None, headers=None):
    ''' get info from a rest api '''
    result = {}
    if not params:
        params = {}
    # apply rate limiting if needed
    rate_limiter(ratelimit)
    if not headers:
        headers = {} 
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if response and response.content and response.status_code == 200:
            result = json.loads(response.content)
            if "results" in result:
                result = result["results"]
            elif "result" in result:
                result = result["result"]
        elif response.status_code in (429, 503, 504):
            raise Exception('Read timed out')
    except Exception as exc:
        result = None
        if "Read timed out" in str(exc) and retries < 5 and not ratelimit:
            # retry on connection error or http server limiting
            monitor = xbmc.Monitor()
            if not monitor.waitForAbort(2):
                result = get_json(url, params, headers, retries + 1)
            del monitor
        else:
            log_exception(__name__, exc)
    # return result
    return result

def try_encode(text, encoding="utf-8"):
    ''' helper to encode a string to utf-8 '''
    try:
        return text
    except Exception:
        return text

def try_decode(text, encoding="utf-8"):
    ''' helper to decode a string to unicode '''
    try:
        return text
    except Exception:
        return text

def process_method_on_list(method_to_run, items):
    ''' helper method that processes a method on each listitem with pooling if the system supports it '''
    all_items = []
    if items is not None:
        try:
            all_items = [method_to_run(item) for item in list(items)]
        except Exception:
            log_msg(format_exc(sys.exc_info()))
        all_items = list(filter(None, all_items))
    return all_items

def get_clean_image(image):
    ''' helper to strip all kodi tags/formatting of an image path/url '''
    if not image:
        return ""
    if image and "image://" in image:
        image = image.replace("image://", "")
        image = unquote(image)
        if image.endswith("/"):
            image = image[:-1]
    return image

def try_parse_int(string):
    ''' helper to parse int from string without erroring on empty or misformed string '''
    try:
        return int(string)
    except Exception:
        return 0

def extend_dict(org_dict, new_dict, allow_overwrite=None):
    ''' Create a new dictionary with a's properties extended by b,
    without overwriting existing values. '''
    if not new_dict:
        return org_dict
    if not org_dict:
        return new_dict
    if sys.version_info.major == 3:
        for key, value in new_dict.items():
            if value:
                if not org_dict.get(key):
                    # orginal dict doesn't has this key (or no value), just overwrite
                    org_dict[key] = value
                else:
                    # original dict already has this key, append results
                    if isinstance(value, list):
                        # make sure that our original value also is a list
                        if isinstance(org_dict[key], list):
                            for item in value:
                                if item not in org_dict[key]:
                                    org_dict[key].append(item)
                        # previous value was str, combine both in list
                        elif isinstance(org_dict[key], str):
                            org_dict[key] = org_dict[key].split(" / ")
                            for item in value:
                                if item not in org_dict[key]:
                                    org_dict[key].append(item)
                    elif isinstance(value, dict):
                        org_dict[key] = extend_dict(org_dict[key], value, allow_overwrite)
                    elif allow_overwrite and key in allow_overwrite:
                        # value may be overwritten
                        org_dict[key] = value
                    else:
                        # conflict, leave alone
                        pass
    return org_dict
    