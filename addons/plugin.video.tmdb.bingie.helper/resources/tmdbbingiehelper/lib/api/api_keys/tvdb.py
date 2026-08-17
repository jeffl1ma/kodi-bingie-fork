from tmdbbingiehelper.lib.addon.permissions import __access__
from tmdbbingiehelper.lib.api.api_keys.tokenhandler import TokenHandler
from bingie.parser import load_in_data

if __access__.has_access('internal'):
    API_KEY = load_in_data(
        b'vS\x15GTK\x15\x03N\x15_\x14\x0e\x03\x14q_\x0fYB\x0f]\r]QG\\\nB\x00Blu|\x04z',
        b'Be respectful. Dont jeopardise TMDbBingieHelper access to this data by stealing API keys or changing item limits.'
    ).decode()
    USER_TOKEN = TokenHandler('tvdb_token', store_as='property')

elif __access__.has_access('tvdb'):
    API_KEY = ''
    USER_TOKEN = TokenHandler('tvdb_token', store_as='property')

else:
    API_KEY = ''
    USER_TOKEN = TokenHandler()
