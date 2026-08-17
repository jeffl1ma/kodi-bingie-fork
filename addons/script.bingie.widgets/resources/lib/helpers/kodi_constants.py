#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys
from .utils import KODI_VERSION

FIELDS_BASE = ["dateadded", "file", "lastplayed", "plot", "title", "art", "playcount"]
FIELDS_FILE = FIELDS_BASE + ["streamdetails", "director", "resume", "runtime"]
FIELDS_MOVIES = FIELDS_FILE + ["plotoutline", "sorttitle", "cast", "votes", "showlink", "top250", "trailer", "year",
                               "country", "studio", "set", "genre", "mpaa", "setid", "rating", "tag", "tagline",
                               "writer", "originaltitle",
                               "imdbnumber"]
if KODI_VERSION > 16:
    FIELDS_MOVIES.append("uniqueid")
FIELDS_TVSHOWS = FIELDS_BASE + ["sorttitle", "mpaa", "premiered", "year", "episode", "watchedepisodes", "votes",
                                "rating", "studio", "season", "genre", "cast", "episodeguide", "tag", "originaltitle",
                                "imdbnumber"]
FIELDS_EPISODES = FIELDS_FILE + ["cast", "productioncode", "rating", "votes", "episode", "showtitle", "tvshowid",
                                 "season", "firstaired", "writer", "originaltitle"]
FIELDS_FILES = FIELDS_FILE + ["plotoutline", "sorttitle", "cast", "votes", "trailer", "year", "country", "studio",
                              "genre", "mpaa", "rating", "tagline", "writer", "originaltitle", "imdbnumber",
                              "premiered", "episode", "showtitle",
                              "firstaired", "watchedepisodes", "duration", "season"]

FILTER_UNWATCHED = {"operator": "lessthan", "field": "playcount", "value": "1"}
FILTER_WATCHED = {"operator": "isnot", "field": "playcount", "value": "0"}
FILTER_RATING = {"operator": "greaterthan", "field": "rating", "value": "7"}
FILTER_INPROGRESS = {"operator": "true", "field": "inprogress", "value": ""}
SORT_RATING = {"method": "rating", "order": "descending"}
SORT_RANDOM = {"method": "random", "order": "descending"}
SORT_TITLE = {"method": "title", "order": "ascending"}
SORT_DATEADDED = {"method": "dateadded", "order": "descending"}
SORT_LASTPLAYED = {"method": "lastplayed", "order": "descending"}
SORT_EPISODE = {"method": "episode"}
