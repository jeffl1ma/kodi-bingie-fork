# -*- coding: utf-8 -*-
"""
Cineroom Burst - Script de Teste
=================================
"""

import sys
import os
import xbmc
import xbmcgui

# Adicionar lib ao path
addon_path = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(addon_path, 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)


def test_import():
    """Testa o import do Burst"""
    try:
        import script.cineroom.burst as burst

        version = getattr(burst, '__version__', 'desconhecida')

        if not hasattr(burst, 'scrape_provider_sources'):
            raise ImportError("Função scrape_provider_sources não encontrada")

        xbmcgui.Dialog().ok(
            "Burst - Teste de Import",
            f"[B]✅ SUCESSO![/B]\n\n"
            f"Burst importado corretamente\n"
            f"Versão: {version}\n\n"
            f"Funções disponíveis:\n"
            f"• scrape_provider_sources()\n"
            f"• scrape() [alias]"
        )

        xbmc.log("[Burst] Teste de import: SUCESSO", xbmc.LOGINFO)
        return True

    except ImportError as e:
        import traceback
        xbmcgui.Dialog().ok(
            "Burst - Erro de Import",
            f"[B]❌ FALHA no import[/B]\n\n"
            f"Erro: {str(e)}\n\n"
            f"Verifique:\n"
            f"1. O addon está instalado?\n"
            f"2. O Kodi foi reiniciado?"
        )
        xbmc.log(f"[Burst] Teste de import FALHOU: {e}", xbmc.LOGERROR)
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        return False

    except Exception as e:
        import traceback
        xbmcgui.Dialog().ok(
            "Burst - Erro",
            f"[B]❌ ERRO inesperado[/B]\n\n"
            f"Erro: {str(e)}\n\n"
            f"Verifique o log do Kodi"
        )
        xbmc.log(f"[Burst] Erro inesperado: {e}", xbmc.LOGERROR)
        return False


def health_check_providers():
    """
    Testa se os providers habilitados estão respondendo.
    Faz um HEAD request simples em cada URL — não scrapa nada.
    """
    try:
        import requests
        from script.cineroom.burst.config import get_enabled_providers
    except Exception as e:
        xbmcgui.Dialog().ok("Burst", f"Erro ao carregar config:\n{e}")
        return

    providers = get_enabled_providers()
    if not providers:
        xbmcgui.Dialog().ok("Burst", "Nenhum provider habilitado.")
        return

    # Filtra só providers com URL (XtreamVOD e similares sem URL fixa são ignorados)
    testable = [(name, data) for name, data in providers if data.get('url')]
    skipped  = [(name, data) for name, data in providers if not data.get('url')]

    if not testable:
        xbmcgui.Dialog().ok("Burst", "Nenhum provider com URL configurada para testar.")
        return

    # Progresso visual enquanto testa
    progress = xbmcgui.DialogProgress()
    progress.create("Burst — Testando providers", "Aguarde...")

    results = []
    total = len(testable)

    for i, (name, data) in enumerate(testable):
        if progress.iscanceled():
            break

        pct = int((i / total) * 100)
        progress.update(pct, f"Testando {name}...")
        xbmc.log(f"[Burst][HealthCheck] Testando {name}...", xbmc.LOGINFO)

        url = data.get('url', '')
        status, latency = _ping_url(requests, url)
        results.append((name, status, latency))

        xbmc.log(
            f"[Burst][HealthCheck] {name}: {'OK' if status else 'FALHOU'} ({latency}ms)",
            xbmc.LOGINFO
        )

    progress.update(100, "Concluído.")
    progress.close()

    # Monta o relatório
    lines = []
    online  = [r for r in results if r[1]]
    offline = [r for r in results if not r[1]]

    if online:
        lines.append("[B]Online:[/B]")
        for name, _, latency in sorted(online, key=lambda x: x[2]):
            lines.append(f"[COLOR green]On[/COLOR] {name}  [{latency}ms]")

    if offline:
        lines.append("")
        lines.append("[B]Offline / Sem resposta:[/B]")
        for name, _, _ in offline:
            lines.append(f"[COLOR red]Off[/COLOR] {name}")

    if skipped:
        lines.append("")
        lines.append("[B]Sem URL (nao testados):[/B]")
        for name, _ in skipped:
            lines.append(f"{name}")

    summary = (
        f"[B]Resultado: {len(online)}/{len(results)} online[/B]\n\n"
        + "\n".join(lines)
    )

    # Oferece desativar os offline automaticamente
    if offline:
        desativar = xbmcgui.Dialog().yesno(
            "Burst — Health Check",
            summary + f"\n\nDesativar os {len(offline)} provider(s) offline?",
            nolabel="Nao",
            yeslabel="Desativar"
        )
        if desativar:
            import xbmcaddon
            from script.cineroom.burst.config import PROVIDERS
            addon = xbmcaddon.Addon('script.cineroom.burst')
            desativados = []
            for name, _, _ in offline:
                setting_id = PROVIDERS.get(name, {}).get('setting_id')
                if setting_id:
                    addon.setSettingBool(setting_id, False)
                    desativados.append(name)
            xbmcgui.Dialog().ok(
                "Burst — Health Check",
                f"{len(desativados)} provider(s) desativado(s):\n\n" +
                "\n".join(f"  {n}" for n in desativados)
            )
        return

    xbmcgui.Dialog().ok("Burst — Health Check", summary)


def _ping_url(requests, url, timeout=8):
    """
    Retorna (True, latency_ms) se o host responder com status < 500,
    (False, 0) caso contrário.
    """
    import time
    try:
        t0 = time.time()
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        latency = int((time.time() - t0) * 1000)
        ok = r.status_code < 500
        return ok, latency
    except Exception:
        return False, 0


def show_info():
    """Mostra informações e ferramentas do addon"""
    dialog = xbmcgui.Dialog()

    options = [
        "ℹ️  Sobre o Cineroom Burst",
        "🧪 Testar Import",
        "🩺 Testar Providers (Health Check)",
        "❌ Sair"
    ]

    selected = dialog.select("Cineroom Burst v2.0", options)

    if selected == 0:
        dialog.ok(
            "Cineroom Burst",
            "[B]Módulo de Scrapers v2.0[/B]\n\n"
            "Provedores suportados:\n"
            "• Stremio (Brazuca, Torrentio, etc)\n"
            "• AnimeZey\n"
            "• Comando Top\n"
            "• Apache Torrent\n"
            "• Filmes Master\n"
            "• Starck Filmes\n\n"
            "Para usar: Instale o Cineroom Lite"
        )
    elif selected == 1:
        test_import()
    elif selected == 2:
        health_check_providers()


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == 'health_check':
        health_check_providers()
    else:
        show_info()