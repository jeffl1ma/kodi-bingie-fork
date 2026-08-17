# -*- coding: utf-8 -*-
import os
import zipfile

def build():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    addons_dir = os.path.join(root_dir, "addons")
    zips_dir = os.path.join(root_dir, "zips")
    os.makedirs(zips_dir, exist_ok=True)

    print("Construindo pacotes ZIP dos Addons para Kodi...")
    for addon_name in sorted(os.listdir(addons_dir)):
        addon_path = os.path.join(addons_dir, addon_name)
        if os.path.isdir(addon_path) and os.path.exists(os.path.join(addon_path, "addon.xml")):
            zip_name = f"{addon_name}.zip"
            zip_path = os.path.join(zips_dir, zip_name)
            print(f" -> Empacotando {zip_name}...")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(addon_path):
                    for file in files:
                        if file.endswith('.pyc') or '__pycache__' in root:
                            continue
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, addons_dir)
                        zipf.write(file_path, rel_path)
            print(f"    Concluido: {zip_name} ({os.path.getsize(zip_path):,} bytes)")

    print("\nTodos os ZIPs foram gerados com sucesso na pasta 'zips/'!")

if __name__ == '__main__':
    build()
