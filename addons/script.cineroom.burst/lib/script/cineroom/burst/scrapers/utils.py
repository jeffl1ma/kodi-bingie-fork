# Em: resources/lib/scrapers/utils.py
import re
import xbmc
import urllib.parse
from bs4 import BeautifulSoup
import unicodedata


def normalize_for_compare(text):
    """
    Normaliza o texto para comparação:
    - Converte para string
    - Remove acentos (ex: "Missão" -> "Missao")
    - Converte para minúsculas
    - Remove todos os caracteres não alfanuméricos
    """
    if not text:
        return ""
    try:
        text = str(text)
        # Remove acentos (Normalização NFKD)
        nfkd_form = unicodedata.normalize('NFKD', text)
        # Usando 'ascii' com 'ignore' para remover caracteres não-ASCII após a normalização
        text_ascii = nfkd_form.encode('ascii', 'ignore').decode('ascii')
        text = text_ascii # Usa a versão sem acentos se a conversão funcionou
    except Exception as e:
        # Em caso de erro (raro), loga e usa o texto original normalizado
        xbmc.log(f"Erro ao remover acentos: {e}. Usando texto original: {text}", xbmc.LOGWARNING)
        pass # Mantém o texto original em caso de erro

    text = text.lower()
    # Remove tudo que não for letra ou número
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

# --- ✅ Função guess_quality_from_name (VERSÃO COMPLETA) ✅ ---
# Nota: Removido o '_' inicial para ser uma função pública do módulo
def guess_quality_from_name(name):
    """ Tenta adivinhar a qualidade a partir de um nome/texto. """
    if not name: return None
    n = name.lower()
    # Checa do maior para o menor
    if '2160p' in n or '4k' in n or 'uhd' in n: return '4K'
    if '1080p' in n or 'fullhd' in n or 'full hd' in n: return '1080p' # Adiciona fullhd
    if '720p' in n: return '720p'
    # Termos genéricos de HD
    if 'hdtv' in n or 'webdl' in n or 'web-dl' in n or 'webrip' in n or 'hdrip' in n or 'bluray' in n or 'bdrip' in n: return 'HD'
    # Termos de SD
    if 'dvdrip' in n or 'sd' in n or '480p' in n or 'tvrip' in n: return 'SD'
    # Default para HD se não achar nada específico
    return 'HD'

# --- ✅ Funções get_anime_search_patterns e get_anime_search_codes ✅ ---
# (Necessárias para o filtro de episódios)

def get_anime_search_patterns(season, episode):
    """ 
    (HELPER v2 - Lógica 'split-cour' de S2->S1 removida) 
    Gera padrões SXXEXX (tuplas). Mantém a lógica S1->S2 para alguns animes.
    """
    patterns = set()
    # Adiciona sempre o padrão S/E exato solicitado
    patterns.add( (season, episode) ) 
    
    # Mantém a lógica para casos onde S01E13+ pode ser tratado como S02E01+
    # (Pode ser refinado/removido se causar problemas em animes)
    if season == 1 and episode > 11:
        for offset in [12, 13]: # Tenta offsets comuns de split-cour
            if episode > offset: 
                patterns.add( (2, episode - offset) )
                
    # --- BLOCO REMOVIDO ---
    # O bloco 'elif season > 1:' foi removido pois estava gerando 
    # S01Exx incorretamente ao pedir S02Exx para séries normais.
    # --- FIM DA REMOÇÃO ---
            
    return list(patterns)

# Nota: Removido o '_' inicial
def get_anime_search_codes(season, episode):
    """ (HELPER) Gera códigos de busca (strings) S01E21, 21, 021, S02E09 etc. """
    patterns = get_anime_search_patterns(season, episode)
    codes = set()
    for s, e in patterns:
        codes.add(f"S{s:02d}E{e:02d}")
        codes.add(f"{s:02d}x{e:02d}")
        codes.add(f"{s}.{e:02d}")
        if s == 1 and e != 1:
            codes.add(f"{e:02d}")
            codes.add(f"{e:03d}")
            codes.add(f"ep{e:02d}")
            codes.add(f"e{e:02d}")
    return list(codes)

def format_size(size_bytes):
    """ (HELPER) Formata bytes em KB, MB, GB. """
    try:
        size_bytes = int(size_bytes)
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MB"
        else:
            return f"{size_bytes / (1024**3):.2f} GB"
    except Exception:
        return "N/A"
    


def extract_magnets(html, title, target_episode=None, season=None, media_type="movie", provider_name="Torrent"):
    """
    Extrai magnet links de uma página HTML.
    Compartilhado por ComandoTop, ApacheTorrent e FilmesMaster.
    """
    magnets = []
    if not html:
        return magnets

    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=re.compile(r"^magnet:\?"))

    for link in links:
        url = link['href']
        parent = link.find_parent()
        parent_text = parent.get_text() if parent else ""
        container_text = parent_text.lower()

        # ── Determina áudio e legenda pela CLASSE do botão ──
        link_classes = link.get('class', [])
        
        if 'btn-success' in link_classes:
            # Botão verde = Dual Áudio
            audio = "DUAL"
            subtitle = "DUAL"
        elif 'btn-danger' in link_classes:
            # Botão vermelho = Legendado
            audio = "LEG"
            subtitle = "LEG"
        else:
            # Fallback para outros sites/situações
            if "dual" in container_text:
                audio = "DUAL"
                subtitle = "DUAL"
            elif "legendad" in container_text:
                audio = "LEG"
                subtitle = "LEG"
            elif "dublado" in container_text:
                audio = "DUB"
                subtitle = "DUB"
            else:
                audio = "LEG"
                subtitle = "LEG"

        # ── Extrai nome do release ──
        dn_match = re.search(r'dn=([^&]+)', url)
        release_name = urllib.parse.unquote(dn_match.group(1)).replace('.', ' ') if dn_match else title

        # ── Qualidade ──
        if "2160p" in container_text or "4k" in container_text:
            quality = "4K"
        elif "1080p" in container_text:
            quality = "1080p"
        elif "720p" in container_text:
            quality = "720p"
        else:
            quality = "HD"

        # ── Tipo (EP ou PACK) ──
        if any(x in container_text for x in ["volume", "completa", "temporada"]):
            type_label = "PACK"
        else:
            type_label = "EP"

        # ── Seeds ──
        seeds = 0
        seed_match = re.search(r'(\d+)\s*SEEDS', parent_text, re.IGNORECASE)
        if seed_match:
            seeds = int(seed_match.group(1))

        # ── Tamanho ──
        size = "N/A"
        size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB))', parent_text, re.IGNORECASE)
        if size_match:
            size = size_match.group(1)

        # ── Código do episódio ──
        ep_number = ""
        if season and target_episode:
            ep_number = f"S{int(season):02d}E{int(target_episode):02d}"

        # ── Label formatado ──
        label = f"Torrent: {quality} | {audio} | {subtitle} [{type_label}] (S:{seeds})"

        magnets.append({
            "url": url,
            "quality": quality,
            "type": "torrent",
            "provider": provider_name,
            "release_title": release_name,
            "label": label,
            "seeds": seeds,
            "size": size,
            "subtitle": subtitle,
            "languages": audio,
            "episode_code": ep_number,
            "media_type": media_type,
        })

    return magnets