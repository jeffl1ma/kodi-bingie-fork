import xbmc
from tmdbbingiehelper.lib.script.sync.item import ItemSync
from tmdbbingiehelper.lib.addon.plugin import get_localized
from tmdbbingiehelper.lib.addon.dialog import BusyDialog
from xbmcgui import Dialog

THUMBSUP_VALUE_SETTING_ID = 'ThumbsUpRateValue'
THUMBSDOWN_VALUE_SETTING_ID = 'ThumbsDownRateValue'

class ItemRating(ItemSync):
    allow_episodes = True
    localized_name_add = 32485
    localized_name_rem = 32489
    trakt_sync_key = 'rating'

    def get_name_remove(self):
        return f'{get_localized(self.localized_name_rem)} ({self.trakt_sync_value})'

    @staticmethod
    def refresh_containers():
        pass  # Override

    def get_dialog_header(self):
        rating = self.sync_item.get('rating')
        if rating == 0:
            return get_localized(32530)  # Remove rating
        if self.name == get_localized(32485):
            return f'{get_localized(32485)} ({rating})'  # Add Rating (rating)
        return f'{get_localized(32489)} ({rating})'  # Change Rating (rating)

    def get_sync_response(self):
        # Ask user for rating
        try:
            x = int(Dialog().numeric(0, f'{self.name} (0-10)'))
        except ValueError:
            return

        if x < 0 or x > 10:
            return

        self.sync_item['rating'] = x

        # Sync rating
        with BusyDialog():
            sync = self.trakt_api.post_response('sync', 'ratings/remove' if x == 0 else 'ratings', postdata={f'{self.trakt_type}s': [self.sync_item]})
        return sync

class ItemLike(ItemSync):
    allow_episodes = True
    localized_name_add = 32485
    localized_name_rem = 32489
    trakt_sync_key = 'rating'

    def get_name_remove(self):
        return f'{get_localized(self.localized_name_rem)} ({self.trakt_sync_value})'

    @staticmethod
    def refresh_containers():
        pass  # Override

    def get_dialog_header(self):
        rating = self.sync_item.get('rating')
        if rating == 0:
            return get_localized(32530)  # Remove rating
        if self.name == get_localized(32485):
            return f'{get_localized(32485)} ({rating})'  # Add Rating (rating)
        return f'{get_localized(32489)} ({rating})'  # Change Rating (rating)

    def get_sync_response(self):
        # Ask user for rating
        try:
            x = int(xbmc.getInfoLabel("Skin.String(%s)" % THUMBSUP_VALUE_SETTING_ID))
        except ValueError:
            return

        if x < 0 or x > 10:
            return

        self.sync_item['rating'] = x

        # Sync rating
        with BusyDialog():
            sync = self.trakt_api.post_response('sync', 'ratings/remove' if x == 0 else 'ratings', postdata={f'{self.trakt_type}s': [self.sync_item]})
        return sync

class ItemDislike(ItemSync):
    allow_episodes = True
    localized_name_add = 32485
    localized_name_rem = 32489
    trakt_sync_key = 'rating'

    def get_name_remove(self):
        return f'{get_localized(self.localized_name_rem)} ({self.trakt_sync_value})'

    @staticmethod
    def refresh_containers():
        pass  # Override

    def get_dialog_header(self):
        rating = self.sync_item.get('rating')
        if rating == 0:
            return get_localized(32530)  # Remove rating
        if self.name == get_localized(32485):
            return f'{get_localized(32485)} ({rating})'  # Add Rating (rating)
        return f'{get_localized(32489)} ({rating})'  # Change Rating (rating)

    def get_sync_response(self):
        # Ask user for rating
        try:
            x = int(xbmc.getInfoLabel("Skin.String(%s)" % THUMBSDOWN_VALUE_SETTING_ID))
        except ValueError:
            return

        if x < 0 or x > 10:
            return

        self.sync_item['rating'] = x

        # Sync rating
        with BusyDialog():
            sync = self.trakt_api.post_response('sync', 'ratings/remove' if x == 0 else 'ratings', postdata={f'{self.trakt_type}s': [self.sync_item]})
        return sync

class ItemReset(ItemSync):
    allow_episodes = True
    localized_name_add = 32485
    localized_name_rem = 32489
    trakt_sync_key = 'rating'

    def get_name_remove(self):
        return f'{get_localized(self.localized_name_rem)} ({self.trakt_sync_value})'

    @staticmethod
    def refresh_containers():
        pass  # Override

    def get_dialog_header(self):
        rating = self.sync_item.get('rating')
        if rating == 0:
            return get_localized(32530)  # Remove rating
        if self.name == get_localized(32485):
            return f'{get_localized(32485)} ({rating})'  # Add Rating (rating)
        return f'{get_localized(32489)} ({rating})'  # Change Rating (rating)

    def get_sync_response(self):
        # Ask user for rating
        try:
            x = 0
        except ValueError:
            return

        if x < 0 or x > 10:
            return

        self.sync_item['rating'] = x

        # Sync rating
        with BusyDialog():
            sync = self.trakt_api.post_response('sync', 'ratings/remove' if x == 0 else 'ratings', postdata={f'{self.trakt_type}s': [self.sync_item]})
        return sync
