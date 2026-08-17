# -*- coding: utf-8 -*-
"""Short-lived cache in front of xbmcaddon.Addon().getSetting().

Every getSetting() is a Python->C++ round trip. A single menu render reads
the same handful of settings dozens of times, and with
reuselanguageinvoker=true those modules stay resident, so the reads repeat
for the life of the process.

A 2 second TTL is the compromise: within one invocation every repeat read is
free, while the long-running service.py still picks up a settings change
almost immediately. setSetting() always invalidates.
"""
import time

import xbmcaddon

_TTL = 2.0


class CachedAddon(object):
    """Attribute-transparent proxy. Anything not cached is forwarded."""

    def __init__(self, addon):
        self._addon = addon
        self._cache = {}
        self._stamp = 0.0

    def _fresh(self):
        now = time.time()
        if now - self._stamp > _TTL:
            self._cache.clear()
            self._stamp = now

    def getSetting(self, sid):
        self._fresh()
        if sid in self._cache:
            return self._cache[sid]
        value = self._addon.getSetting(sid)
        self._cache[sid] = value
        return value

    def getSettingBool(self, sid):
        self._fresh()
        key = ('bool', sid)
        if key in self._cache:
            return self._cache[key]
        value = self._addon.getSettingBool(sid)
        self._cache[key] = value
        return value

    def setSetting(self, sid, value):
        self._cache.clear()
        return self._addon.setSetting(sid, value)

    def setSettingBool(self, sid, value):
        self._cache.clear()
        return self._addon.setSettingBool(sid, value)

    def invalidate(self):
        self._cache.clear()

    def __getattr__(self, name):
        return getattr(self._addon, name)


_INSTANCE = None


def cached_addon():
    """One shared proxy per process."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = CachedAddon(xbmcaddon.Addon())
    return _INSTANCE


def invalidate():
    if _INSTANCE is not None:
        _INSTANCE.invalidate()
