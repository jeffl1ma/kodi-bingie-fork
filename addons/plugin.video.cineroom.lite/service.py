# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon

import traceback
from datetime import datetime, timezone

ADDON   = xbmcaddon.Addon()
MONITOR = xbmc.Monitor()


def log(msg):
    xbmc.log(f"[CR Lite Service] {msg}", level=xbmc.LOGINFO)

def _parse_interval_setting(setting_value):
    value_map = {
        "Desativado": 0, "A cada 3 horas": 3, "A cada 5 horas": 5,
        "A cada 12 horas": 12, "A cada 24 horas (Diariamente)": 24
    }
    return value_map.get(setting_value, 0)

def _parse_last_update(last_update_str):
    """
    Parseia o valor de last_update_check de forma robusta.
    Suporta o formato salvo atualmente ('YYYY-MM-DDTHH:MM:SS'),
    timestamps Unix legados, e strings ISO com offset/Z que possam
    ter sido gravadas por versões antigas do serviço.
    Retorna datetime UTC ou None se não for possível parsear.
    """
    if not last_update_str:
        return None
    # Formato padrão atual: 'YYYY-MM-DDTHH:MM:SS' (sem offset)
    try:
        return datetime.strptime(
            last_update_str[:19], '%Y-%m-%dT%H:%M:%S'
        ).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    # Fallback: timestamp Unix (legado)
    try:
        return datetime.fromtimestamp(
            int(float(last_update_str)), tz=timezone.utc
        )
    except Exception:
        pass
    return None


# ========================================
# UPDATE CHECK (conteúdo)
# ========================================

def run_update_check():
    if MONITOR.abortRequested():
        return

    log('Iniciando verificação de novo conteúdo...')
    try:
        from resources.lib.indexer import check_for_updates_silently

        new_count = check_for_updates_silently(ADDON)

        if new_count and new_count > 0:
            import xbmcgui
            xbmcgui.Dialog().notification(
                'Cineroom',
                f'{new_count} novo(s) título(s) disponível(is)!',
                xbmcgui.NOTIFICATION_INFO,
                4000,
            )
            log(f'{new_count} novos títulos adicionados.')
        else:
            log('Nenhum conteúdo novo encontrado.')

        # Sincroniza o DB local com a Biblioteca do Kodi (arquivos .strm)
        if ADDON.getSetting('sync_auto_library') == 'true':
            try:
                from resources.lib.library import sync_library_silently
                log('Sincronização automática ativa. Verificando arquivos .strm...')
                sync_library_silently()
                xbmc.executebuiltin('UpdateLibrary(video)')
            except Exception as e_lib:
                log(f'Erro na sincronização da biblioteca: {e_lib}\n{traceback.format_exc()}')
        else:
            log('Sincronização automática ignorada (desativada nas configurações).')

        # Limpeza de cache antigo
        conn = None
        try:
            from resources.lib.db import db
            conn = db._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_cache WHERE timestamp < datetime('now', '-48 hours')")
            conn.commit()
            log('Cache antigo limpo.')
        except Exception as e_cache:
            log(f'Erro ao limpar cache: {e_cache}\n{traceback.format_exc()}')
        finally:
            try:
                if conn:
                    db._release_conn(conn)
            except Exception:
                pass

        try:
            from resources.lib.trending_tracker import get_trending_content_from_supabase
            for content_type in ('movie', 'tv'):
                get_trending_content_from_supabase(content_type=content_type, limit=20)
            log('Cache de trending renovado.')
        except Exception as e_trending:
            log(f'Erro ao renovar cache de trending: {e_trending}')

        # Backup automático (VIP — silencioso, só roda se configurado)
        run_auto_backup()

        # Salva sem offset (+00:00) para garantir compatibilidade com
        # datetime.strptime no Python 3.6/3.7 usado em Android TV (Kodi 19/20).
        ADDON.setSetting(
            'last_update_check',
            datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        )
        log('Verificação concluída com sucesso.')

    except Exception as e:
        log(f"Ocorreu um erro geral: {e}\n{traceback.format_exc()}")


# ========================================
# WARMUP DE CACHE DE PESQUISA
# ========================================

def run_search_cache_warmup():
    """Warmup desativado — tracking de queries foi removido do search.py."""
    log("Warmup de cache de busca desativado (sem tracking de queries).")


# ========================================
# FLUSH DE TRACKING PENDENTE
# ========================================

def run_auto_backup():
    """
    Delega ao módulo history_backup o backup silencioso.
    Só executa se o usuário for VIP e tiver backup automático ativado.
    """
    try:
        from resources.lib.history_backup import run_auto_backup as _do_backup
        _do_backup()
    except Exception as e:
        log(f'Erro no auto-backup: {e}')


def run_flush_pending_tracks():
    """
    Envia ao Supabase todos os eventos de tracking acumulados em disco.
    Chamado a cada 30 minutos pelo loop principal.
    Não bloqueia — se a rede falhar, os eventos ficam para a próxima rodada.
    """
    try:
        from resources.lib.trending_tracker import flush_pending_tracks
        flush_pending_tracks()
    except Exception as e:
        log(f"Erro no flush de tracks: {e}")


# ========================================
# TRAKT SERVICE
# ========================================

def run_trakt_service():
    """Executa sincronização automática do Trakt"""
    try:
        from resources.lib.trakt.trakt_sync import TraktSyncService, get_trakt_settings

        settings = get_trakt_settings()
        if not settings.get('access_token'):
            return

        service = TraktSyncService()
        service.start()

        for _ in range(300):  # 5 minutos
            if MONITOR.waitForAbort(1):
                break

        service.stop()

    except Exception as e:
        xbmc.log(f"[Trakt Service] Erro: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)


# ========================================
# SERVIÇO DE NOTIFICAÇÃO
# ========================================

def run_notification_check():
    try:
        from resources.lib.notification import check_and_cache_notification
        check_and_cache_notification()
    except Exception as e:
        log(f'Erro no check de notificação: {e}')


# ========================================
# MAIN SERVICE LOOP
# ========================================

if __name__ == '__main__':
    log('Serviço iniciado.')

    # Espera inicial para rede estabilizar
    if not MONITOR.waitForAbort(30):
        interval = _parse_interval_setting(ADDON.getSetting('update_interval'))

        if interval > 0:
            # Verifica se já passou o intervalo desde o último check antes de rodar no boot
            last_update_str = ADDON.getSetting('last_update_check')
            should_run_now = False

            last_update_dt = _parse_last_update(last_update_str)
            if last_update_dt is None:
                # Nunca rodou antes ou valor corrompido → roda agora
                should_run_now = True
            else:
                elapsed = (datetime.now(timezone.utc) - last_update_dt).total_seconds()
                if elapsed >= (interval * 3600):
                    should_run_now = True
                else:
                    log(f'Boot: último check há {elapsed/3600:.1f}h, intervalo é {interval}h — pulando.')

            if should_run_now:
                run_update_check()

        # Envia tracks que possam ter ficado pendentes do boot anterior
        run_flush_pending_tracks()

        # Verifica notificações no boot
        run_notification_check()

    while not MONITOR.abortRequested():
        # Acorda a cada 1 hora
        if MONITOR.waitForAbort(3600):
            break

        # ── Verificação de conteúdo novo ────────────────────────────────────
        interval_hours = _parse_interval_setting(ADDON.getSetting('update_interval'))

        if interval_hours > 0:
            last_update_str = ADDON.getSetting('last_update_check')
            current_time_dt = datetime.now(timezone.utc)

            try:
                last_update_dt = _parse_last_update(last_update_str) \
                    or datetime(2000, 1, 1, tzinfo=timezone.utc)

                if (current_time_dt - last_update_dt).total_seconds() >= (interval_hours * 3600):
                    run_update_check()

            except Exception as e:
                log(f"Erro no loop de tempo (update): {e}")

        
        run_flush_pending_tracks()


        run_notification_check()

    log('Serviço finalizado.')