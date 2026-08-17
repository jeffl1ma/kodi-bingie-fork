# -*- coding: utf-8 -*-
"""
Gerador e Publicador Completo do Repositorio Kodi
Executa TUDO de uma vez:
1. Atualiza addons.xml e calcula hash MD5
2. Empacota todos os arquivos ZIP por versao
3. Gera index.html para o GitHub Pages (Gerenciador de Arquivos do Kodi)
4. Faz o commit no Git
5. Envia (push) automaticamente para o GitHub
"""

import os
import hashlib
import zipfile
import xml.etree.ElementTree as ET
import shutil
import subprocess

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.join(ROOT_DIR, "addons")
REPO_DIR = os.path.join(ROOT_DIR, "repo")
ZIPS_DIR = os.path.join(ROOT_DIR, "zips")

def generate_and_publish(auto_push=True):
    os.makedirs(REPO_DIR, exist_ok=True)
    os.makedirs(ZIPS_DIR, exist_ok=True)

    print("=" * 65)
    print(" >>> GERADOR E PUBLICADOR AUTOMATICO DO REPOSITORIO KODI <<<")
    print("=" * 65)

    addons_xml_elements = []

    for addon_name in sorted(os.listdir(ADDONS_DIR)):
        addon_path = os.path.join(ADDONS_DIR, addon_name)
        xml_file = os.path.join(addon_path, "addon.xml")
        
        if not os.path.isdir(addon_path) or not os.path.exists(xml_file):
            continue

        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            addon_id = root.attrib.get('id', addon_name)
            addon_version = root.attrib.get('version', '1.0.0')
            addons_xml_elements.append(root)

            # Criar pasta no repo/<addon_id>/
            addon_repo_dir = os.path.join(REPO_DIR, addon_id)
            os.makedirs(addon_repo_dir, exist_ok=True)

            # Nome do zip no padrao do Kodi: addonid-version.zip
            versioned_zip = f"{addon_id}-{addon_version}.zip"
            versioned_zip_path = os.path.join(addon_repo_dir, versioned_zip)

            # Zip simples para zips/
            simple_zip_path = os.path.join(ZIPS_DIR, f"{addon_id}.zip")

            print(f" -> [1/4] Empacotando {addon_id} (v{addon_version})...")

            # Gerar zip com os arquivos do addon
            for target_zip in [versioned_zip_path, simple_zip_path]:
                with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for r, dirs, files in os.walk(addon_path):
                        for f in files:
                            if f.endswith('.pyc') or '__pycache__' in r:
                                continue
                            fp = os.path.join(r, f)
                            rel_p = os.path.join(addon_id, os.path.relpath(fp, addon_path))
                            zipf.write(fp, rel_p)

            # Copiar icon.png, fanart.jpg, addon.xml para o repo/<addon_id>/
            for asset in ['icon.png', 'fanart.jpg', 'fanart.png', 'addon.xml', 'changelog.txt']:
                asset_src = os.path.join(addon_path, asset)
                if not os.path.exists(asset_src) and asset == 'icon.png':
                    res_src = os.path.join(addon_path, 'resources', asset)
                    if os.path.exists(res_src):
                        asset_src = res_src
                if os.path.exists(asset_src):
                    shutil.copy2(asset_src, os.path.join(addon_repo_dir, asset))

        except Exception as e:
            print(f"Erro ao processar {addon_name}: {e}")

    # Gerar addons.xml
    print("\n -> [2/4] Atualizando catalogo e assinaturas MD5...")
    addons_root = ET.Element('addons')
    for elem in addons_xml_elements:
        addons_root.append(elem)

    addons_xml_path = os.path.join(REPO_DIR, "addons.xml")
    tree_out = ET.ElementTree(addons_root)
    ET.indent(tree_out, space="  ", level=0)
    tree_out.write(addons_xml_path, encoding='utf-8', xml_declaration=True)

    # Gerar addons.xml.md5
    with open(addons_xml_path, 'rb') as f:
        md5_hash = hashlib.md5(f.read()).hexdigest()

    addons_md5_path = os.path.join(REPO_DIR, "addons.xml.md5")
    with open(addons_md5_path, 'w', encoding='utf-8') as f:
        f.write(md5_hash)

    # Copiar o zip do repositorio para zips/
    repo_zip_src = os.path.join(REPO_DIR, "repository.gover.bingie", "repository.gover.bingie-1.0.0.zip")
    if os.path.exists(repo_zip_src):
        shutil.copy2(repo_zip_src, os.path.join(ZIPS_DIR, "repository.gover.bingie.zip"))

    print(f"    MD5 gerado: {md5_hash}")

    # Gerar index.html para GitHub Pages
    print("\n -> [3/4] Gerando pagina HTML do servidor para o Kodi...")
    html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Gover Bingie Suite Repository</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #141414; color: #ffffff; padding: 30px; }
        h1 { color: #e50914; }
        p { color: #aaaaaa; }
        ul { list-style-type: none; padding: 0; }
        li { margin: 12px 0; background: #222; padding: 15px; border-radius: 8px; max-width: 600px; }
        a { color: #00d2ff; text-decoration: none; font-weight: bold; font-size: 18px; }
        a:hover { text-decoration: underline; }
        .size { float: right; color: #888; font-size: 14px; }
    </style>
</head>
<body>
    <h1>Gover Bingie Suite Repository</h1>
    <p>Repositorio personalizado do Kodi com traducoes em PT-BR e suporte ao Up Next.</p>
    <hr style="border: 1px solid #333; margin: 20px 0;">
    <h2>Arquivos Instalaveis (ZIP):</h2>
    <ul>
"""
    for f in sorted(os.listdir(ZIPS_DIR)):
        if f.endswith('.zip'):
            p = os.path.join(ZIPS_DIR, f)
            size_mb = os.path.getsize(p) / (1024 * 1024)
            html_content += f'        <li><a href="zips/{f}">{f}</a> <span class="size">{size_mb:.2f} MB</span></li>\n'

    html_content += """    </ul>
</body>
</html>
"""
    with open(os.path.join(ROOT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    # Git commit e Push automatico
    if auto_push:
        print("\n -> [4/4] Sincronizando com o GitHub...")
        try:
            subprocess.run(["git", "add", "."], cwd=ROOT_DIR, check=True)
            subprocess.run(["git", "commit", "-m", f"Atualizacao do Repositorio Kodi (MD5: {md5_hash[:8]})"], cwd=ROOT_DIR, capture_output=True)
            print("    Enviando para o GitHub (git push)...")
            push_res = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=ROOT_DIR, capture_output=True, text=True)
            if push_res.returncode == 0:
                print("    [SUCESSO] Repositorio publicado no GitHub com sucesso!")
            else:
                info_msg = push_res.stderr.strip() or push_res.stdout.strip()
                print(f"    [INFO GITHUB] {info_msg}")
        except Exception as e:
            print(f"    Aviso Git: {e}")

    print("\n" + "=" * 65)
    print(" CONCLUIDO! TUDO FOI EMPACOTADO E PUBLICADO!")
    print("=" * 65)

if __name__ == '__main__':
    generate_and_publish(auto_push=True)
