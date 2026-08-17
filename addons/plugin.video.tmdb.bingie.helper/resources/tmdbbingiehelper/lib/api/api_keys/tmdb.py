from tmdbbingiehelper.lib.addon.permissions import __access__
from tmdbbingiehelper.lib.api.api_keys.tokenhandler import TokenHandler

if __access__.has_access('internal'):
    API_KEY = '4f13072a99739d0780f37a524c15941d'
    API_READ_ACCESS_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI0ZjEzMDcyYTk5NzM5ZDA3ODBmMzdhNTI0YzE1OTQxZCIsIm5iZiI6MS42MDM5MTg3ODQ0OTUwMDAxZSs5LCJzdWIiOiI1Zjk5ZGJjMDZlZWNlZTAwMzc4ZGFkZjUiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.foP_fi3SFVf_G6EG-L2pOLs7-M-G484VyH4Z0vshwYk'
    USER_TOKEN = TokenHandler('tmdb_user_token', store_as='setting')
else:
    API_KEY = ''
    API_READ_ACCESS_TOKEN = ''
    USER_TOKEN = TokenHandler()
