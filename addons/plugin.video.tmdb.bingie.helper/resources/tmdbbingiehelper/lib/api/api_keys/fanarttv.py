from tmdbbingiehelper.lib.addon.permissions import __access__
from tmdbbingiehelper.lib.addon.plugin import get_setting

if __access__.has_access('internal'):
    API_KEY = 'ffd38b4a7bc5ab6894595b772da4c7cc'
    CLIENT_KEY = get_setting('fanarttv_clientkey', 'str')

elif __access__.has_access('fanarttv'):
    API_KEY = ''
    CLIENT_KEY = get_setting('fanarttv_clientkey', 'str')

else:
    API_KEY = ''
    CLIENT_KEY = ''

