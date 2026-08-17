# Kodi Bingie Suite - Custom Fork & Translations (PT-BR) 🎬🍿

Repositório personalizado e unificado contendo a suíte completa da **Skin Bingie** para Kodi, com suporte aprimorado, correções de interface, **tradução 100% integral em Português do Brasil (PT-BR)** e integração total do **Up Next** com **TMDb Bingie Helper** e **Delux Hub**.

---

## 📦 Conteúdo do Repositório

Este repositório contém as versões prontas para uso e os códigos-fonte dos seguintes complementos:

1. **`skin.bingie`** (Fork da skin oficial por *matke-84*)
   * Tradução completa e rigorosa de todas as **579 strings** (`pt_br` e `pt_pt`).
   * Correção dos botões de hubs (`Personalizar hub de filmes`, `Personalizar hub de séries`, `Novos e Populares`, etc.).
   * Correção do status de progresso (`62% restante` em vez de rótulo secundário).
   * Restauração das telas de aviso do **Up Next** integradas na skin.
   * Correção de largura e texto dos botões do Up Next (`380px`), eliminando travamentos ou tremedeiras de rolagem (*marquee scrolling*).

2. **`plugin.video.tmdb.bingie.helper`**
   * Tradução completa de todas as **609 strings** em Português (`pt_br` e `pt_pt`).
   * Player oficial do Delux Hub já integrado com fila automática (`make_playlist: upnext`).

3. **`service.upnext`**
   * Compatibilidade estendida com os botões personalizados da Skin Bingie (IDs `3097` e `3096`).
   * Disparo direto via `Player.Open` e sinais de streaming externo quando o contador zera ou o usuário clica em assistir agora.

4. **`plugin.video.dexhub`**
   * Add-on Delux Hub integrado com suporte a streaming e metadados.

---

## 🚀 Como Instalar no Kodi

### Opção 1: Instalação rápida via Arquivo ZIP
Na pasta [`zips/`](zips/), você encontrará os arquivos instaláveis para o Kodi:
* `skin.bingie.zip`
* `plugin.video.tmdb.bingie.helper.zip`
* `service.upnext.zip`
* `plugin.video.dexhub.zip`

**No Kodi:**
1. Vá em **Configurações ⚙️ -> Add-ons -> Instalar a partir de um arquivo zip**.
2. Selecione os arquivos zip que deseja instalar.

### Opção 2: Cópia Direta de Pastas
Basta copiar o conteúdo da pasta `addons/` diretamente para o diretório de dados do seu Kodi:
* **Windows:** `%APPDATA%\Kodi\addons\`
* **Android:** `/Android/data/org.xbmc.kodi/files/.kodi/addons/`
* **Linux:** `~/.kodi/addons/`
* **macOS:** `~/Library/Application Support/Kodi/addons/`

---

## 🔄 Como Atualizar Tudo Automaticamente (Upstream Sync)

Quando os desenvolvedores oficiais (da Skin Bingie ou do Delux Hub) lançarem atualizações:

Basta executar o script:
```bash
python update_from_upstream.py
```

**O que esse script faz sozinho:**
1. Conecta-se aos repositórios oficiais no GitHub (`matke-84/skin.bingie` e `6ahd/plugin.video.dexhub`).
2. Baixa o código mais recente lançado pelos desenvolvedores.
3. **Reaplica automaticamente todas as nossas traduções e correções do Up Next** sem perder nada.
4. Gera novos arquivos `.zip` atualizados na pasta `zips/`.

---

## 🛠️ Como Gerar Novos ZIPs Manualmente

Se você fizer alguma alteração manual nos arquivos locais e quiser apenas recriar os ZIPs:
```bash
python build_zips.py
```

---

## 📤 Como Publicar no seu GitHub

Para subir este repositório para a sua própria conta no GitHub:

1. Crie um novo repositório no seu GitHub (ex: `kodi-bingie-fork`).
2. No seu terminal dentro desta pasta, execute:
```bash
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git branch -M main
git push -u origin main
```
