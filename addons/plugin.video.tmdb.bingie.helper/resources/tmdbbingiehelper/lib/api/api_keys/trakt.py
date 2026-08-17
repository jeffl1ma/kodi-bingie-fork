from tmdbbingiehelper.lib.addon.permissions import __access__
from tmdbbingiehelper.lib.api.api_keys.tokenhandler import TokenHandler

if __access__.has_access('internal'):
    CLIENT_ID = '72d5a8a4e069577ca37021207557a7c083da148d4d7937d9d760828291141341'
    CLIENT_SECRET = '77088c63f992369fdfa9207559894c8fd6efb22266c60c99d325113711f84a6d'
    USER_TOKEN = TokenHandler('trakt_token', store_as='setting')

elif __access__.has_access('trakt'):
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    USER_TOKEN = TokenHandler('trakt_token', store_as='setting')

else:
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    USER_TOKEN = TokenHandler()
