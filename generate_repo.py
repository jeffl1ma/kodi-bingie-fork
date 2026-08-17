# -*- coding: utf-8 -*-
"""
Gerador de Repositorio Oficial do Kodi
Gera a estrutura completa de repositorio (addons.xml, addons.xml.md5, zips por versao e icones)
"""

import os
import hashlib
import zipfile
import xml.etree.ElementTree as ET
import shutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.join(ROOT_DIR, "addons")
REPO_DIR = os.path.join(ROOT_DIR, "repo")
ZIPS_DIR = os.path.join(ROOT_DIR, "zips")

def generate():
    os.makedirs(REPO_DIR, exist_ok=True)
    os.makedirs(ZIPS_DIR, exist_ok=True)

    print("=" * 60)
    print("GERANDO REPOSITORIO KODI COMPLETO")
    print("=" * 60)

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

            print(f" -> Empacotando {addon_id} (v{addon_version})...")

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
                    # Checar resources/
                    res_src = os.path.join(addon_path, 'resources', asset)
                    if os.path.exists(res_src):
                        asset_src = res_src
                if os.path.exists(asset_src):
                    shutil.copy2(asset_src, os.path.join(addon_repo_dir, asset))

            print(f"    [OK] {versioned_zip}")

        except Exception as e:
            print(f"Erro ao processar {addon_name}: {e}")

    # Gerar addons.xml
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

    print("\n" + "=" * 60)
    print("ESTRUTURA DO REPOSITORIO GERADA COM SUCESSO!")
    print(f"MD5: {md5_hash}")
    print("=" * 60)

if __name__ == '__main__':
    generate()
