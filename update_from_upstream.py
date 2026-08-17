# -*- coding: utf-8 -*-
"""
Script de Atualizacao Automatica (Upstream Sync)
1. Baixa as versoes mais recentes dos repositorios oficiais dos autores
2. Preserva e reaplica todas as nossas correcoes e traducoes em Portugues
3. Empacota tudo, atualiza o catalogo oficial e faz o push direto para o GitHub
"""

import os
import shutil
import urllib.request
import zipfile
import json
import generate_repo

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.join(ROOT_DIR, "addons")
TEMP_DIR = os.path.join(ROOT_DIR, ".temp_update")

UPSTREAM_REPOS = {
    "skin.bingie": {
        "type": "github_zip",
        "url": "https://github.com/matke-84/skin.bingie/archive/refs/heads/main.zip"
    },
    "plugin.video.dexhub": {
        "type": "github_zip",
        "url": "https://github.com/6ahd/plugin.video.dexhub/archive/refs/heads/main.zip"
    }
}

def download_and_extract_github(url, target_folder):
    os.makedirs(TEMP_DIR, exist_ok=True)
    zip_temp = os.path.join(TEMP_DIR, "temp.zip")
    print(f" -> Baixando atualizacao de: {url}...")
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp, open(zip_temp, 'wb') as out_file:
        out_file.write(resp.read())

    print(" -> Extraindo arquivos...")
    with zipfile.ZipFile(zip_temp, 'r') as zip_ref:
        extract_path = os.path.join(TEMP_DIR, "extracted")
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)
        zip_ref.extractall(extract_path)

        extracted_dirs = [os.path.join(extract_path, d) for d in os.listdir(extract_path) if os.path.isdir(os.path.join(extract_path, d))]
        if extracted_dirs:
            src_dir = extracted_dirs[0]
            for root, dirs, files in os.walk(src_dir):
                rel_path = os.path.relpath(root, src_dir)
                dest_root = os.path.join(target_folder, rel_path)
                os.makedirs(dest_root, exist_ok=True)
                for f in files:
                    # Preservar nossas traducoes em PT e layouts corrigidos do Up Next
                    if f.endswith('strings.po') and any(lang in root for lang in ['pt_br', 'pt_pt']):
                        continue
                    if f.startswith('script-upnext-') and f.endswith('.xml'):
                        continue
                    shutil.copy2(os.path.join(root, f), os.path.join(dest_root, f))

def check_brazucaplay():
    try:
        print("\n[Verificando atualizacoes do Brazuca Play]")
        repo_xml_url = "https://raw.githubusercontent.com/skyrisk/brazucaplay/master/addons/repo/addons_matrix.xml"
        req = urllib.request.Request(repo_xml_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            if 'plugin.video.BrazucaPlay.Matrix' in content:
                print(" -> Conexao com repositorio do Brazuca Play validada com sucesso.")
    except Exception as e:
        print(f" -> Aviso ao checar Brazuca Play: {e}")

def apply_patches():
    print("\n -> Reaplicando correcoes e integracoes personalizadas...")

    # 1. Garantir player dexhub.json no tmdb helper com make_playlist: upnext
    player_path = os.path.join(ADDONS_DIR, "plugin.video.tmdb.bingie.helper", "resources", "players", "dexhub.json")
    if os.path.exists(player_path):
        with open(player_path, 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        pdata['make_playlist'] = "upnext"
        with open(player_path, 'w', encoding='utf-8') as f:
            json.dump(pdata, f, indent=4, ensure_ascii=False)

    # 2. Reaplicar patch nos arquivos do UpNext
    upnext_lib = os.path.join(ADDONS_DIR, "service.upnext", "resources", "lib")
    if os.path.exists(upnext_lib):
        upnext_py = os.path.join(upnext_lib, "upnext.py")
        if os.path.exists(upnext_py):
            with open(upnext_py, 'r', encoding='utf-8') as f:
                t = f.read()
            t = t.replace("if controlId == 3012:", "if controlId in (3012, 3097, 10, 11):")
            t = t.replace("elif controlId == 3013:", "elif controlId in (3013, 3096):")
            with open(upnext_py, 'w', encoding='utf-8') as f:
                f.write(t)

        mgr_py = os.path.join(upnext_lib, "playbackmanager.py")
        if os.path.exists(mgr_py):
            with open(mgr_py, 'r', encoding='utf-8') as f:
                mtxt = f.read()
            old_p = "if source == 'playlist' or self.state.queued:\n            # Play playlist media\n            if should_play_non_default:\n                # Only start the next episode if the user asked for it specifically\n                self.player.playnext()\n        elif self.api.has_addon_data():\n            # Play add-on media\n            self.api.play_addon_item()"
            new_p = "if self.api.has_addon_data():\n            # Play add-on media directly via Player.Open or AddonSignals\n            self.api.play_addon_item()\n        elif source == 'playlist' or self.state.queued:\n            # Play playlist media\n            self.player.playnext()"
            mtxt = mtxt.replace(old_p, new_p)
            with open(mgr_py, 'w', encoding='utf-8') as f:
                f.write(mtxt)

def main():
    print("=" * 65)
    print(" >>> ATUALIZADOR AUTOMATICO DA SUITE COMPLETA (UPSTREAM) <<<")
    print("=" * 65)

    for addon_name, repo_info in UPSTREAM_REPOS.items():
        target = os.path.join(ADDONS_DIR, addon_name)
        if os.path.exists(target):
            try:
                print(f"\n[Atualizando {addon_name}]")
                download_and_extract_github(repo_info["url"], target)
            except Exception as e:
                print(f"Aviso ao baixar {addon_name}: {e}")

    check_brazucaplay()
    apply_patches()

    # Limpar pasta temporaria
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

    # Executar o gerador completo e fazer o push direto pro GitHub
    print("\n[Empacotando e Publicando Atualizacao no GitHub]")
    generate_repo.generate_and_publish(auto_push=True)

    print("\n" + "=" * 65)
    print(" SUCESSO TOTAL! TUDO FOI ATUALIZADO E PUBLICADO NA NUVEM!")
    print(" Os seus aparelhos com Kodi receberao a atualizacao automaticamente.")
    print("=" * 65)

if __name__ == '__main__':
    main()
