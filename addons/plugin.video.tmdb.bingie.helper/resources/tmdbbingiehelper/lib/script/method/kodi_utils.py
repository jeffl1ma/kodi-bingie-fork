# Module: default
# Author: jurialmunkey,matke
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html


def container_refresh():
    from tmdbbingiehelper.lib.addon.tmdate import set_timestamp
    from bingie.window import get_property
    from tmdbbingiehelper.lib.addon.plugin import executebuiltin
    executebuiltin('Container.Refresh')
    get_property('Widgets.Reload', set_property=f'{set_timestamp(0, True)}')


def split_value(split_value, separator=None, **kwargs):
    """ Split string values and output to window properties """
    from bingie.window import get_property
    if not split_value:
        return
    v = f'{split_value}'
    s = separator or ' / '
    p = kwargs.get("property") or "TMDbBingieHelper.Split"
    for x, i in enumerate(v.split(s)):
        get_property(f'{p}.{x}', set_property=i, prefix=-1)


def kodi_setting(kodi_setting, **kwargs):
    """ Get Kodi setting value and output to window property """
    from tmdbbingiehelper.lib.api.kodi.rpc import get_jsonrpc
    from bingie.window import get_property
    method = "Settings.GetSettingValue"
    params = {"setting": kodi_setting}
    response = get_jsonrpc(method, params)
    get_property(
        name=kwargs.get('property') or 'KodiSetting',
        set_property=f'{response.get("result", {}).get("value", "")}')
