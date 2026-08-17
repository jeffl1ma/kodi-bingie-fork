#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys
from resources.lib.utils import log_msg
import xbmc
import time
import json


class KodiMonitor(xbmc.Monitor):
    ''' Monitor all events in Kodi '''
    update_widgets_busy = False
    last_mediatype = ""

    def __init__(self, **kwargs):
        xbmc.Monitor.__init__(self)
        self.win = kwargs.get("win")
        self.addon = kwargs.get("addon")

    def onDatabaseUpdated(self, database):
        ''' builtin function for the xbmc.Monitor class '''
        log_msg("Kodi_Monitor: %s database updated" % database)

        self.refresh_video_widgets("")

    def onNotification(self, sender, method, data):
        ''' builtin function for the xbmc.Monitor class '''
        try:
            log_msg("Kodi_Monitor: sender %s - method: %s  - data: %s" % (sender, method, data))
            data = json.loads(data)
            mediatype = ""
            if data and isinstance(data, dict):
                if data.get("item"):
                    mediatype = data["item"].get("type", "")
                elif data.get("type"):
                    mediatype = data["type"]

            if method == "VideoLibrary.OnUpdate":
                if not mediatype:
                    mediatype = self.last_mediatype # temp hack
                self.refresh_video_widgets(mediatype)

            if method == "Player.OnStop":
                self.last_mediatype = mediatype
                if mediatype in ["movie", "episode"]:
                    if self.addon.getSetting("aggresive_refresh") == "true":
                        self.refresh_video_widgets(mediatype)

        except Exception as exc:
            log_msg("Exception in KodiMonitor: %s" % exc, xbmc.LOGERROR)

    def refresh_video_widgets(self, media_type):
        ''' refresh video widgets '''
        log_msg("Video database changed - type: %s - refreshing widgets...." % media_type)
        timestr = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        self.win.setProperty("widgetreload", timestr)
        if media_type:
            self.win.setProperty("widgetreload-%ss" % media_type, timestr)
            if "episode" in media_type:
                self.win.setProperty("widgetreload-tvshows", timestr)

    def onSettingsChanged(self):
        ''' called by Kodi when the addon settings are changed '''
        timestr = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        self.win.setProperty("widgetreload", timestr)
        self.win.setProperty("widgetreload2", timestr)
        for media_type in ["episodes", "tvshows", "movies"]:
            self.win.setProperty("widgetreload-%s" % media_type, timestr)
