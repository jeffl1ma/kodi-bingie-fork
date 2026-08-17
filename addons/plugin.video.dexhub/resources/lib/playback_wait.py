# -*- coding: utf-8 -*-
"""
DexHub Playback Wait Window v5.

Key changes vs v4:
- Poster / clearlogo / fanart are applied via setImage() on named control IDs
  instead of Window.Property() + $INFO bindings. This is the same approach
  source_browser.py uses for its poster control (200) and is the ONLY reliable
  method for URL-based images (Plex tokenized URLs, PlexBridge, Plexio) in a
  Kodi WindowXMLDialog. $INFO bindings inside <texture> tags cache on the first
  frame and require a full skin reload to update — setImage() pushes immediately.
- Title / meta / plot / provider are set via setLabel() on named control IDs.
- ctx is always authoritative — TMDb Helper DB is only consulted for MISSING
  fields (fast-path when ctx already has all three art fields).
- Wave bars + progress bar properties go on Window(10000) so the $INFO bindings
  in the XML read them correctly across re-renders (global window, always stable).
- open() stall is 80ms (was 60ms) to give the GUI thread enough time to call
  onInit() before the main thread continues with setResolvedUrl / Player.play.
"""
import threading

import xbmc
import xbmcaddon
import xbmcgui

ADDON      = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')

# Control IDs (must match playback_wait.xml)
_CTRL_POSTER    = 500
_CTRL_CLEARLOGO = 501
_CTRL_FANART    = 502
_CTRL_TITLE     = 510
_CTRL_META      = 511
_CTRL_PLOT      = 512
_CTRL_PROVIDER  = 513   # label inside chip group
_CTRL_CHIP_GRP  = 520   # provider chip group (setVisible)

_DEFAULT_POSTER = 'special://home/addons/plugin.video.dexhub/resources/media/default_video.png'
_DEFAULT_FANART = 'special://home/addons/plugin.video.dexhub/resources/media/fanart.jpg'


def _resolve_art(ctx):
    """Return (poster, clearlogo, fanart, plot).

    ctx is always authoritative. TMDb Helper DB is consulted only to fill
    in fields that are missing from ctx. Zero I/O when ctx already has all
    three art fields.
    """
    poster    = str(ctx.get('poster')    or '').strip()
    clearlogo = str(ctx.get('clearlogo') or '').strip()
    fanart    = str(ctx.get('background') or ctx.get('fanart') or '').strip()
    plot      = str(ctx.get('plot') or ctx.get('description') or '').strip()

    # Fast path — no I/O needed.
    if poster and clearlogo and fanart:
        return poster, clearlogo, fanart, plot

    tmdb_id = str(ctx.get('tmdb_id') or '').strip()
    imdb_id = str(ctx.get('imdb_id') or '').strip()
    mt      = str(ctx.get('media_type') or 'movie').strip().lower()
    mt_norm = 'tv' if mt in ('series', 'anime', 'tv', 'show', 'tvshow') else 'movie'

    if tmdb_id or imdb_id:
        try:
            from . import tmdbhelper as _th
            bundle = _th.get_art_bundle_from_db(
                tmdb_id=tmdb_id, imdb_id=imdb_id,
                media_type=mt_norm,
            ) or {}
            poster    = poster    or bundle.get('poster')    or ''
            clearlogo = clearlogo or bundle.get('clearlogo') or ''
            fanart    = fanart    or bundle.get('fanart')    or bundle.get('landscape') or ''
        except Exception:
            pass

    if not fanart and poster:
        fanart = poster
    return poster, clearlogo, fanart, plot


def _format_meta_line(ctx):
    year = str(ctx.get('year') or '').strip()
    mt   = str(ctx.get('media_type') or '').strip().lower()
    label_map = {
        'movie': 'MOVIE', 'film': 'MOVIE',
        'series': 'TV SHOW', 'show': 'TV SHOW', 'tv': 'TV SHOW', 'tvshow': 'TV SHOW',
        'anime': 'ANIME',
    }
    mt_label = label_map.get(mt, mt.upper() if mt else '')
    parts = []
    if year:
        parts.append(year)
    if mt_label:
        parts.append(mt_label)
    try:
        s = ctx.get('season')
        e = ctx.get('episode')
        if s and e:
            parts.append('S%02dE%02d' % (int(s), int(e)))
    except Exception:
        pass
    return '  ·  '.join(parts)


class _WaitWindow(xbmcgui.WindowXMLDialog):

    # v3.9.17: brand-unified pulse — cyan→purple→cyan gradient instead of amber.
    # Alpha values (first byte) drive the visual "wave" intensity sweep across bars.
    _BAR_STEPS = [
        '2240484E', '5A33D8F7', 'AA33D8F7',
        'FF7C3AED', 'AA33D8F7', '5A33D8F7',
    ]
    _BAR_COUNT   = 5
    _BAR_REFRESH = 0.08

    _MARQUEE_STEPS = [
        2, 8, 18, 32, 48, 64, 78, 88, 95, 100,
        100, 100, 100,
        88, 72, 54, 36, 20, 8, 2, 2, 2, 2,
    ]
    _MARQUEE_REFRESH = 0.10

    def __init__(self, *args, **kwargs):
        self._ctx         = kwargs.get('ctx', {})
        self._close_event = threading.Event()
        self._global_win  = None

    def onInit(self):
        try:
            from . import skin_theme
            skin_theme.publish_theme(self)
        except Exception:
            pass
        ctx = self._ctx
        try:
            self._global_win = xbmcgui.Window(10000)
        except Exception:
            self._global_win = None

        poster, clearlogo, fanart, plot = _resolve_art(ctx)
        if plot and len(plot) > 240:
            plot = plot[:237].rstrip() + '...'

        title    = str(ctx.get('title') or ctx.get('show_title') or '')
        meta     = _format_meta_line(ctx)
        provider = str(ctx.get('provider_name') or ctx.get('provider_id') or '')

        # ── Poster ───────────────────────────────────────────────────────
        # Use setImage() — NOT Window.Property($INFO) which has caching
        # issues for URL-based Plex / Plexio / PlexBridge artwork.
        try:
            self.getControl(_CTRL_POSTER).setImage(
                poster or _DEFAULT_POSTER, useCache=False)
        except Exception:
            pass

        # ── Clearlogo ────────────────────────────────────────────────────
        try:
            ctrl_logo = self.getControl(_CTRL_CLEARLOGO)
            if clearlogo:
                ctrl_logo.setImage(clearlogo, useCache=False)
                ctrl_logo.setVisible(True)
                # Hide text title when clearlogo is shown
                try:
                    self.getControl(_CTRL_TITLE).setVisible(False)
                except Exception:
                    pass
            else:
                ctrl_logo.setVisible(False)
                try:
                    self.getControl(_CTRL_TITLE).setLabel('[B]%s[/B]' % title)
                    self.getControl(_CTRL_TITLE).setVisible(True)
                except Exception:
                    pass
        except Exception:
            try:
                self.getControl(_CTRL_TITLE).setLabel('[B]%s[/B]' % title)
            except Exception:
                pass

        # ── Fanart ───────────────────────────────────────────────────────
        try:
            self.getControl(_CTRL_FANART).setImage(
                fanart or _DEFAULT_FANART, useCache=False)
        except Exception:
            pass

        # ── Text labels ──────────────────────────────────────────────────
        try:
            self.getControl(_CTRL_META).setLabel('[UPPERCASE][B]%s[/B][/UPPERCASE]' % meta)
        except Exception:
            pass
        try:
            self.getControl(_CTRL_PLOT).setText(plot or '')
        except Exception:
            try:
                self.getControl(_CTRL_PLOT).setLabel(plot or '')
            except Exception:
                pass

        # ── Provider chip ────────────────────────────────────────────────
        try:
            chip = self.getControl(_CTRL_CHIP_GRP)
            if provider:
                self.getControl(_CTRL_PROVIDER).setLabel(
                    '[UPPERCASE][B]%s[/B][/UPPERCASE]' % provider)
                chip.setVisible(True)
            else:
                chip.setVisible(False)
        except Exception:
            pass

        # ── Seed animation properties on global window ───────────────────
        gw = self._global_win
        if gw:
            try:
                gw.setProperty('dex.marquee_pct', '2')
            except Exception:
                pass
            for i in range(self._BAR_COUNT):
                try:
                    gw.setProperty('dex.bar%d' % (i + 1), self._BAR_STEPS[0])
                except Exception:
                    pass
            # v3.9.1: language-aware status + cancel hint (was hardcoded bilingual
            # in the XML before — now the user only sees their chosen language).
            try:
                from .i18n import is_english
                if is_english():
                    gw.setProperty('dex.wait.status_text', '[B]CONNECTING[/B]')
                    gw.setProperty('dex.wait.cancel_hint', 'Press Back to cancel')
                else:
                    gw.setProperty('dex.wait.status_text', '[B]جاري التشغيل[/B]')
                    gw.setProperty('dex.wait.cancel_hint', 'اضغط رجوع للإلغاء')
            except Exception:
                # Bilingual fallback if i18n import fails
                gw.setProperty('dex.wait.status_text', '[B]CONNECTING · جاري التشغيل[/B]')
                gw.setProperty('dex.wait.cancel_hint', 'Press Back · اضغط رجوع للإلغاء')

        # Start animation threads.
        threading.Thread(target=self._animate_bars,
                         name='DexHubWaitBars', daemon=True).start()
        threading.Thread(target=self._animate_marquee,
                         name='DexHubWaitMarquee', daemon=True).start()

    def _animate_bars(self):
        step = 0
        n = len(self._BAR_STEPS)
        gw = None
        while not self._close_event.wait(self._BAR_REFRESH):
            if gw is None:
                gw = self._global_win
            if gw is None:
                continue
            for i in range(self._BAR_COUNT):
                try:
                    gw.setProperty('dex.bar%d' % (i + 1),
                                   self._BAR_STEPS[(step - i) % n])
                except Exception:
                    return
            step += 1

    def _animate_marquee(self):
        idx = 0
        n = len(self._MARQUEE_STEPS)
        gw = None
        while not self._close_event.wait(self._MARQUEE_REFRESH):
            if gw is None:
                gw = self._global_win
            if gw is None:
                continue
            try:
                gw.setProperty('dex.marquee_pct',
                                str(self._MARQUEE_STEPS[idx % n]))
            except Exception:
                return
            idx += 1

    def onAction(self, action):
        if action.getId() in (10, 92, 13, 9):
            try:
                xbmc.Player().stop()
            except Exception:
                pass
            self.signal_close()

    def signal_close(self):
        self._close_event.set()
        # Clear global window properties to prevent leak.
        gw = self._global_win
        if gw:
            for prop in ('dex.poster', 'dex.clearlogo', 'dex.fanart',
                         'dex.title', 'dex.plot', 'dex.meta', 'dex.provider',
                         'dex.bar1', 'dex.bar2', 'dex.bar3', 'dex.bar4', 'dex.bar5',
                         'dex.marquee_pct'):
                try:
                    gw.clearProperty(prop)
                except Exception:
                    pass
        try:
            self.close()
        except Exception:
            pass

    def run(self):
        self.doModal()


class PlaybackWaiter:
    """Modal wait dialog between source pick and first AV frame."""

    # 40ms (was 80ms): enough for Kodi to schedule onInit() on the GUI
    # thread before the main thread calls setResolvedUrl / Player.play.
    # Halving the stall halves the visible "frozen" time before the wait
    # window appears.
    _OPEN_STALL_MS = 40

    def __init__(self, ctx):
        self._ctx          = ctx
        self._win          = None
        self._monitor_stop = threading.Event()

    def open(self):
        try:
            self._win = _WaitWindow(
                'playback_wait.xml', ADDON_PATH, 'Default', '1080i',
                ctx=self._ctx,
            )
            threading.Thread(target=self._win.run,
                             name='DexHubWaitWin', daemon=True).start()
            xbmc.sleep(self._OPEN_STALL_MS)
        except Exception as exc:
            xbmc.log('[DexHub] PlaybackWaiter.open: %s' % exc, xbmc.LOGWARNING)
            self._win = None

    def close(self):
        self._monitor_stop.set()
        if self._win:
            try:
                self._win.signal_close()
            except Exception:
                pass
            self._win = None

    def close_on_av_start(self, timeout_ms=22000):
        win_ref  = self._win
        if not win_ref:
            return
        stop_ref = self._monitor_stop

        def _monitor():
            player  = xbmc.Player()
            elapsed = 0
            while elapsed < timeout_ms and not stop_ref.is_set():
                xbmc.sleep(150)
                elapsed += 150
                try:
                    if player.isPlayingVideo():
                        xbmc.sleep(400)
                        win_ref.signal_close()
                        return
                except Exception:
                    pass
            win_ref.signal_close()

        threading.Thread(target=_monitor,
                         name='DexHubWaitMon', daemon=True).start()
