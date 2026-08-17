# -*- coding: utf-8 -*-
"""Account and cloud-sync routes.

This module owns Nuvio/Stremio login/logout/sync UI so the main plugin router
no longer carries account state and dialog orchestration.
"""
from __future__ import absolute_import


def qr_login(service):
    from resources.lib.qr_pair import qr_pair
    return qr_pair(service)


def login(service, addon, tr):
    import xbmcgui
    from resources.lib.dexhub import nuvio_stremio_sync as sync
    dlg = xbmcgui.Dialog()
    email = (addon.getSetting('%s_email' % service) or '').strip()
    password = addon.getSetting('%s_password' % service) or ''
    if not email or not password:
        dlg.ok('Dex Hub', tr('اكتب البريد وكلمة المرور في الإعدادات أولاً.'))
        return False
    try:
        if service == 'nuvio':
            sync.Nuvio.login(email, password)
        else:
            sync.Stremio.login(email, password)
        try:
            addon.setSetting('%s_password' % service, '')
        except Exception:
            pass
        # v4.0.0: linking implies the user wants sync — enable the master
        # toggle so "Sync now" works right away instead of a dead end.
        try:
            addon.setSetting('%s_sync_enabled' % service, 'true')
        except Exception:
            pass
        dlg.notification('Dex Hub', tr('تم تسجيل الدخول ✓'), xbmcgui.NOTIFICATION_INFO, 4000)
        return True
    except Exception as exc:
        dlg.ok('Dex Hub', tr('فشل تسجيل الدخول:') + '\n' + str(exc))
        return False


def logout(service, tr):
    import xbmcgui
    from resources.lib.dexhub import nuvio_stremio_sync as sync
    if service == 'nuvio':
        sync.Nuvio.clear()
    else:
        sync.Stremio.clear()
    xbmcgui.Dialog().notification('Dex Hub', tr('تم تسجيل الخروج'), xbmcgui.NOTIFICATION_INFO, 3000)
    return True


def direction(addon):
    raw = addon.getSetting('cloud_sync_direction') or 'Two-way'
    if raw in ('Upload only', 'رفع فقط'):
        return 'push'
    if raw in ('Download only', 'سحب فقط'):
        return 'pull'
    return 'both'


def sync_now(addon, tr, only=None):
    import xbmcgui
    from resources.lib.dexhub import nuvio_stremio_sync as sync
    dlg = xbmcgui.Dialog()
    targets = sync.enabled_targets()
    if only:
        targets = [t for t in targets if t == only]
        if not targets:
            dlg.ok('Dex Hub', tr('لا يوجد حساب مفعّل لهذه الخدمة.'))
            return False
    if not targets:
        dlg.ok('Dex Hub', tr('فعّل حساب Nuvio أو Stremio وسجّل الدخول أولاً.'))
        return False
    pd = xbmcgui.DialogProgressBG()
    pd.create('Dex Hub', tr('مزامنة الحسابات…'))
    try:
        pd.update(15, tr('تحضير المزامنة…'))
        # v4.0.0: direction and sections resolve per service from settings.
        result = sync.run_sync(targets=targets, force_full=False)
        pd.update(95, tr('حفظ النتائج…'))
    finally:
        pd.close()
    if not result or not result.get('ok'):
        errors = []
        for row in (result or {}).get('report', []):
            for name, section in (row.get('sections') or {}).items():
                if not section.get('ok'):
                    errors.append('%s/%s: %s' % (row.get('service'), name, section.get('error', '')))
        dlg.ok('Dex Hub', tr('فشلت المزامنة:') + '\n' + ('\n'.join(errors) or str((result or {}).get('error', ''))))
        return False
    ok_services = [r['service'] for r in result.get('report', []) if r.get('ok')]
    wb = result.get('writeback', {})
    msg = tr('تمت المزامنة')
    if ok_services:
        msg += ' • ' + ', '.join(ok_services)
    msg += ' • ' + tr('+%d إضافة، %d متابعة') % (
        wb.get('providers', 0), wb.get('progress', 0))
    dlg.notification('Dex Hub', msg, xbmcgui.NOTIFICATION_INFO, 6000)
    errors = []
    for row in result.get('report', []):
        for name, section in (row.get('sections') or {}).items():
            if not section.get('ok'):
                errors.append('%s/%s: %s' % (row.get('service'), name, section.get('error', '')))
    if errors:
        dlg.ok('Dex Hub • Sync details', '\n'.join(errors))
    return True
