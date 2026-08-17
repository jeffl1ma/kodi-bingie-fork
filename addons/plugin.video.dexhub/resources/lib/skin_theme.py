# -*- coding: utf-8 -*-
"""
DexHub skin-aware theming engine.

Reads the *active* Kodi skin's accent colour and derives a full, mathematically
consistent palette from it, then publishes the palette as Home-window
properties that DexHub's WindowXML dialogs bind to. The result: DexHub adopts
the host skin's identity instead of looking like a foreign add-on.

Supported skins get their real accent read directly; any unknown skin falls
back to the DexWorld brand palette so nothing ever looks broken.

Published properties (Window 10000):
    dexhub.theme.accent        AARRGGBB  primary accent
    dexhub.theme.accent_soft   AARRGGBB  ~70% accent (sub-accents, icons)
    dexhub.theme.accent_dim    AARRGGBB  ~28% accent (fills, hovers)
    dexhub.theme.accent_glow   AARRGGBB  lightened accent (highlights/sheen)
    dexhub.theme.secondary     AARRGGBB  complementary/secondary accent
    dexhub.theme.surface       AARRGGBB  deep surface background
    dexhub.theme.surface_card  AARRGGBB  raised card surface
    dexhub.theme.text          AARRGGBB  primary text
    dexhub.theme.muted         AARRGGBB  muted/secondary text
    dexhub.theme.ok            AARRGGBB  success/cached green (kept stable)
    dexhub.theme.skin          string    active skin id
    dexhub.theme.ready         '1' once published
"""

import xbmc
import xbmcgui


HOME = xbmcgui.Window(10000)

# DexWorld brand palette — the fallback identity when the skin is unknown
# or exposes no usable accent.
BRAND_ACCENT = 'FF7C3AED'    # purple
BRAND_SECONDARY = 'FF33D8F7'  # cyan
BRAND_SURFACE = 'FF12141C'
BRAND_SURFACE_CARD = 'FF1B2030'
BRAND_TEXT = 'FFE7E7EF'
BRAND_MUTED = 'FF8E94A6'
BRAND_OK = 'FF4AEDA0'


# --------------------------------------------------------------------------- #
#  Colour maths (pure stdlib — operates on AARRGGBB / RRGGBB hex strings)      #
# --------------------------------------------------------------------------- #

def _parse_hex(value):
    """Return (a, r, g, b) ints from an AARRGGBB or RRGGBB hex string, or None."""
    if not value:
        return None
    v = value.strip().lstrip('#')
    # Kodi colours are AARRGGBB; some skins store RRGGBB.
    if len(v) == 6:
        v = 'FF' + v
    if len(v) != 8:
        return None
    try:
        a = int(v[0:2], 16)
        r = int(v[2:4], 16)
        g = int(v[4:6], 16)
        b = int(v[6:8], 16)
        return (a, r, g, b)
    except ValueError:
        return None


def _to_hex(a, r, g, b):
    clamp = lambda x: max(0, min(255, int(round(x))))
    return '%02X%02X%02X%02X' % (clamp(a), clamp(r), clamp(g), clamp(b))


def _with_alpha(argb, alpha):
    a, r, g, b = argb
    return _to_hex(alpha, r, g, b)


def _scale(argb, factor):
    """Lighten (factor>1) or darken (factor<1) the RGB channels."""
    a, r, g, b = argb
    return _to_hex(a, r * factor, g * factor, b * factor)


def _mix(argb, tint, ratio):
    """Mix argb toward a tint (r,g,b) by ratio 0..1, keeping argb's alpha."""
    a, r, g, b = argb
    tr, tg, tb = tint
    nr = r + (tr - r) * ratio
    ng = g + (tg - g) * ratio
    nb = b + (tb - b) * ratio
    return _to_hex(a, nr, ng, nb)


def _luminance(argb):
    _, r, g, b = argb
    # Rec. 601 luma
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _complement(argb):
    """A pleasing secondary: rotate toward a cooler/warmer partner.

    We don't do full HSL rotation (overkill); instead we swap emphasis between
    channels to get a harmonious, distinct secondary that still feels related.
    """
    a, r, g, b = argb
    # Emphasise the two lower channels, damp the dominant one a touch.
    mx = max(r, g, b)
    nr = b if r == mx else r
    ng = r if g == mx else g
    nb = g if b == mx else b
    return _to_hex(a, (nr + b) / 2, (ng + r) / 2, (nb + g) / 2)


# --------------------------------------------------------------------------- #
#  Skin accent detection                                                      #
# --------------------------------------------------------------------------- #

# Per-skin recipe: which Skin.String / Skin.Color holds the accent, and an
# optional explicit fallback accent for that skin family.
_SKIN_ACCENT_SOURCES = {
    'skin.arctic.fuse.3': ['Skin.String(focuscolor.name)'],
    'skin.arctic.fuse.2': ['Skin.String(focuscolor.name)'],
    'skin.arctic.horizon.2': ['Skin.String(focuscolor.name)'],
    'skin.arctic.zephyr.2.resurrection.mod': ['Skin.String(focuscolor.name)'],
    'skin.arctic.zephyr.reloaded': ['Skin.String(focuscolor.name)'],
    'skin.estuary': ['Skin.String(focuscolor.name)'],
}

# Generic skin-string names worth probing on any unknown skin.
_GENERIC_ACCENT_PROBES = [
    'Skin.String(focuscolor.name)',
    'Skin.String(highlightcolor)',
    'Skin.String(accentcolor)',
    'Skin.String(AccentColor)',
    'Skin.String(focuscolor)',
]


def _looks_like_hex(value):
    return _parse_hex(value) is not None


def _read_active_accent(skin_id):
    """Try the skin-specific source first, then generic probes."""
    probes = list(_SKIN_ACCENT_SOURCES.get(skin_id, []))
    for p in _GENERIC_ACCENT_PROBES:
        if p not in probes:
            probes.append(p)

    for probe in probes:
        try:
            val = xbmc.getInfoLabel(probe) or ''
        except Exception:  # pylint: disable=broad-except
            val = ''
        if _looks_like_hex(val):
            argb = _parse_hex(val)
            # Reject near-black / near-white "accents" (skins sometimes store
            # text colours here) — they make a terrible accent.
            lum = _luminance(argb)
            if 0.06 < lum < 0.95:
                return val
    return None


# --------------------------------------------------------------------------- #
#  Palette construction                                                        #
# --------------------------------------------------------------------------- #

def build_palette(accent_hex):
    """Derive a full palette from a single accent hex (AARRGGBB or RRGGBB)."""
    argb = _parse_hex(accent_hex) or _parse_hex(BRAND_ACCENT)
    # Force full opacity on the accent itself.
    a, r, g, b = argb
    accent = _to_hex(255, r, g, b)
    accent_argb = (255, r, g, b)

    lum = _luminance(accent_argb)
    # If the accent is quite dark, lighten the glow more aggressively so the
    # "lit from above" sheen still reads.
    glow_factor = 1.55 if lum < 0.35 else 1.28

    palette = {
        'accent': accent,
        'accent_soft': _with_alpha(accent_argb, 0xB3),   # 70%
        'accent_dim':  _with_alpha(accent_argb, 0x47),   # 28%
        'accent_glow': _scale(accent_argb, glow_factor),
        'secondary':   _complement(accent_argb),
        # Neutral surfaces: very dark, faintly tinted by the accent so the UI
        # feels cohesive rather than a pure-grey slab.
        'surface':      _mix(_parse_hex(BRAND_SURFACE), (r, g, b), 0.06),
        'surface_card': _mix(_parse_hex(BRAND_SURFACE_CARD), (r, g, b), 0.10),
        'text':  BRAND_TEXT,
        'muted': BRAND_MUTED,
        'ok':    BRAND_OK,  # cached/success stays a stable green for meaning
    }
    return palette


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

def current_skin():
    try:
        return xbmc.getSkinDir() or ''
    except Exception:  # pylint: disable=broad-except
        return ''


def resolve_palette():
    """Return (palette_dict, skin_id, accent_source_str)."""
    skin_id = current_skin()
    accent = _read_active_accent(skin_id)
    source = accent if accent else 'brand-fallback'
    if not accent:
        accent = BRAND_ACCENT
    return build_palette(accent), skin_id, source


def publish_theme(window=None, log=None):
    """Compute and publish the theme to the Home window (and optionally a
    specific window). Safe to call repeatedly (e.g. on every dialog onInit).
    """
    palette, skin_id, source = resolve_palette()

    targets = [HOME]
    if window is not None and window is not HOME:
        targets.append(window)

    for win in targets:
        try:
            for key, val in palette.items():
                win.setProperty('dexhub.theme.%s' % key, val)
            win.setProperty('dexhub.theme.skin', skin_id)
            win.setProperty('dexhub.theme.ready', '1')
        except Exception:  # pylint: disable=broad-except
            pass

    if log:
        try:
            log('skin_theme: skin=%s accent=%s source=%s'
                % (skin_id, palette['accent'], source))
        except Exception:  # pylint: disable=broad-except
            pass

    return palette


def clear_theme():
    try:
        for key in ('accent', 'accent_soft', 'accent_dim', 'accent_glow',
                    'secondary', 'surface', 'surface_card', 'text', 'muted',
                    'ok', 'skin', 'ready'):
            HOME.clearProperty('dexhub.theme.%s' % key)
    except Exception:  # pylint: disable=broad-except
        pass
