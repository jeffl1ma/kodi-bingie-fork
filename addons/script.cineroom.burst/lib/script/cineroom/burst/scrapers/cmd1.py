# -*- coding: utf-8 -*-
import re
import urllib.parse
import xbmc
import requests
from bs4 import BeautifulSoup
from .scraper_config import get_url

_CMD1_BASE = get_url('cmd1', fallback='https://cmd1.site')

# Timeout por request, configurável via settings.xml (scraper.timeout).
_TIMEOUT = 15


class _FakeMagnet:
    """
    Simula um elemento BeautifulSoup para magnets extraídos via regex do HTML bruto.
    Usado quando soup.find_all('a', href=...) não encontra os links diretamente.
    """
    def __init__(self, url):
        self._url = url

    def get(self, attr, default=None):
        return self._url if attr == "href" else default

    def find_parent(self):
        return None

def search_cmd1(imdb_id=None, title=None, season=None, episode=None, media_type="movie"):
    """
    Busca no cmd1.site usando IMDB ID (preferencial) ou título
    COM SUPORTE PARA PORTUGUÊS
    """
    base_url = _CMD1_BASE
    
    # --- BUSCAS OTIMIZADAS PARA SÉRIES EM PORTUGUÊS ---
    search_terms = []
    
    if imdb_id:
        search_terms.append(imdb_id)
    
    if title:
        # Remove ano se houver
        clean_title = re.sub(r'\s*\(\d{4}\)', '', title).strip()
        
        # 1. Título original
        search_terms.append(clean_title)
        
        # 2. Para séries, adiciona buscas específicas em português
        if media_type == "tvshow" and season:
            try:
                season_num = int(season)
                
                # Formato: "2ª Temporada" (com ª)
                search_terms.append(f"{clean_title} {season_num}ª Temporada")
                
                # Formato: "2a Temporada" (com a)
                search_terms.append(f"{clean_title} {season_num}a Temporada")
                
                # Formato: "Temporada 2"
                search_terms.append(f"{clean_title} Temporada {season_num}")
                
                # Formato: "Season 2" (inglês)
                search_terms.append(f"{clean_title} Season {season_num}")
                
                # Formato: "S02" (padrão internacional)
                search_terms.append(f"{clean_title} S{season_num:02d}")
                
                # Formato: "S2" (sem zero)
                search_terms.append(f"{clean_title} S{season_num}")
                
            except ValueError:
                # Se season não é número, usa como está
                search_terms.append(f"{clean_title} {season}")
    
    # Remove duplicados mantendo ordem
    unique_terms = []
    for term in search_terms:
        if term not in unique_terms:
            unique_terms.append(term)
    
    xbmc.log(f"[CMD1] Termos de busca: {unique_terms}", xbmc.LOGDEBUG)
    
    # Tenta cada termo de busca
    for search_term in unique_terms:
        search_url = f"{base_url}/?s={urllib.parse.quote_plus(search_term)}"
        xbmc.log(f"[CMD1] Buscando: {search_term}", xbmc.LOGINFO)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9',
            'Referer': base_url
        }

        try:
            response = requests.get(search_url, headers=headers, timeout=_TIMEOUT)
            if response.status_code == 200:
                # Verifica se encontrou resultados reais
                soup = BeautifulSoup(response.content, "html.parser")
                
                # Procura por posts/articles
                articles = soup.find_all("article")
                posts = soup.find_all("div", class_="post")
                
                # Também verifica se há resultados na página
                no_results = soup.find_all(text=re.compile(r"Nenhum resultado|Nada encontrado|0 resultados", re.IGNORECASE))
                
                if (articles or posts) and not no_results:
                    count = len(articles) if articles else len(posts)
                    xbmc.log(f"[CMD1] Encontrados {count} resultados com: {search_term}", xbmc.LOGINFO)
                    return response.content
                elif no_results:
                    xbmc.log(f"[CMD1] Nenhum resultado com: {search_term}", xbmc.LOGDEBUG)
                    
        except Exception as e:
            xbmc.log(f"[CMD1] Erro de busca: {str(e)}", xbmc.LOGERROR)
    
    xbmc.log("[CMD1] Nenhum termo de busca retornou resultados", xbmc.LOGWARNING)
    return None


def find_post_urls(html, season=None, media_type="movie"):
    """
    Extrai URLs dos posts encontrados na busca
    COM SUPORTE PARA PADRÕES EM PORTUGUÊS
    """
    if not html:
        return []
    
    soup = BeautifulSoup(html, "html.parser")
    post_urls = []
    base_url = _CMD1_BASE
    
    # Procura por links com rel="bookmark" E também por posts/articles
    links = soup.find_all("a", rel="bookmark", href=True)
    
    # Também procura em h2 > a (comum em themes WordPress)
    h2_links = soup.select("h2.entry-title a, h2.post-title a, h2.title a")
    links.extend(h2_links)
    
    # Procura também em elementos de post
    post_divs = soup.find_all("div", class_=["post", "article", "item"])
    for div in post_divs:
        link = div.find("a", href=True)
        if link:
            links.append(link)
    
    for link in links:
        post_url = link.get("href", "")
        post_title = link.get_text().strip()
        
        # Ignora posts vazios
        if not post_url or not post_title:
            continue
            
        # Converte URL relativa para absoluta
        if post_url.startswith('/'):
            post_url = base_url + post_url
        elif not post_url.startswith('http'):
            continue
        
        # Ignora páginas administrativas
        ignore_paths = ['/area-de-pedidos', '/contato', '/sobre', '/politica', 
                       '/autor/', '/category/', '/tag/', '/page/', '/feed/']
        if any(x in post_url for x in ignore_paths):
            xbmc.log(f"[CMD1] Ignorando página administrativa: {post_title}", xbmc.LOGDEBUG)
            continue
        
        # --- FILTRO INTELIGENTE POR TEMPORADA EM PORTUGUÊS ---
        if media_type == "tvshow" and season:
            try:
                season_num = int(season)
                
                # Padrões de temporada em português
                port_season_patterns = [
                    rf'{season_num}[ªa]\s*[Tt]emporada',      # 2ª Temporada ou 2a Temporada
                    rf'[Tt]emporada\s*{season_num}',         # Temporada 2
                    rf'S{season_num:02d}(?!E\d{{2}})',       # S02 (mas não S02E01)
                    rf'S{season_num}(?!E\d{{2}})',           # S2 (mas não S2E01)
                    rf'Season\s*{season_num}',               # Season 2
                    rf'Parte\s*{season_num}',                # Parte 2
                    rf'Volume\s*{season_num}',               # Volume 2
                    rf'\b{season_num}\s*º',                 # 2º (ordinal)
                    rf'\b{season_num}\s*°',                 # 2° (ordinal)
                ]
                
                # Verifica se algum padrão corresponde
                found_season = False
                for pattern in port_season_patterns:
                    if re.search(pattern, post_title, re.IGNORECASE):
                        found_season = True
                        xbmc.log(f"[CMD1] Post corresponde à temporada {season}: {post_title}", xbmc.LOGDEBUG)
                        break
                
                # Se não encontrou a temporada no título, ainda pode aceitar
                # (alguns posts têm temporada no conteúdo, não no título)
                if not found_season:
                    # Verifica se tem "Completa" ou "Pack" sem especificar temporada
                    if re.search(r'completa|pack|season|temporada', post_title, re.IGNORECASE):
                        xbmc.log(f"[CMD1] Post genérico (aceitando): {post_title}", xbmc.LOGDEBUG)
                    else:
                        xbmc.log(f"[CMD1] Pulando post (não é temp {season}): {post_title}", xbmc.LOGDEBUG)
                        continue
                        
            except ValueError:
                # Se season não é número, usa busca textual
                if season.lower() not in post_title.lower():
                    xbmc.log(f"[CMD1] Pulando post (não contém '{season}'): {post_title}", xbmc.LOGDEBUG)
                    continue
        
        xbmc.log(f"[CMD1] Post encontrado: {post_title}", xbmc.LOGINFO)
        post_urls.append({
            'url': post_url,
            'title': post_title
        })
    
    return post_urls


def extract_sources_from_post(post_url, post_title, season=None, episode=None, media_type="movie"):
    """
    Extrai magnets de um post específico com validação correta de episódios
    E SUPORTE PARA PORTUGUÊS
    """
    sources = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://cmd1.site/'
    }
    
    try:
        xbmc.log(f"[CMD1] Acessando post: {post_url}", xbmc.LOGINFO)
        response = requests.get(post_url, headers=headers, timeout=_TIMEOUT)
        
        if response.status_code != 200:
            xbmc.log(f"[CMD1] Erro HTTP {response.status_code} ao acessar post", xbmc.LOGWARNING)
            return sources
        
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        # --- DETECTA ÁUDIO ---
        audio = "Legendado"
        if "dual" in post_title.lower() or "dual" in html.lower():
            audio = "Dual Áudio"
        elif "dublado" in post_title.lower() or "dublado" in html.lower():
            audio = "Dublado"
        
        idioma_match = re.search(r'<strong>(?:Áudio|Idioma)</strong>:\s*([^<]+)', html, re.IGNORECASE)
        if idioma_match:
            idioma_text = idioma_match.group(1).lower()
            if "portugu" in idioma_text and ("|" in idioma_text or "inglês" in idioma_text or "alemão" in idioma_text or "coreano" in idioma_text):
                audio = "Dual Áudio"
        
        xbmc.log(f"[CMD1] Áudio detectado: {audio}", xbmc.LOGDEBUG)
        
        # --- EXTRAI MAGNETS ---
        magnet_links = soup.find_all("a", href=re.compile(r"^magnet:\?"))
        
        if len(magnet_links) == 0:
            raw_magnets = re.findall(r'href="(magnet:\?[^"]+)"', html)
            xbmc.log(f"[CMD1] Encontrados {len(raw_magnets)} magnets no HTML bruto", xbmc.LOGINFO)
            
            magnet_links = [_FakeMagnet(url) for url in raw_magnets]
        
        xbmc.log(f"[CMD1] Encontrados {len(magnet_links)} magnets", xbmc.LOGINFO)
        
        # --- DETECTA SE O POST É DE SÉRIE E QUAL TEMPORADA ---
        detected_seasons = set()
        if media_type == "tvshow":
            # Padrões de temporada em português e inglês
            season_patterns = [
                r'S(\d{1,2})',                      # S01, S1
                r'Temporada\s+(\d+)',               # Temporada 2
                r'(\d+)[ªa]\s*[Tt]emporada',        # 2ª Temporada, 2a Temporada
                r'Season\s+(\d+)',                  # Season 2
                r'Parte\s+(\d+)',                   # Parte 2
                r'Volume\s+(\d+)',                  # Volume 2
            ]
            
            for link in magnet_links:
                magnet_url = link.get("href") if hasattr(link, 'get') else link.url
                # Extrai nome do release
                dn_match = re.search(r'dn=([^&]+)', magnet_url)
                if dn_match:
                    release_name = urllib.parse.unquote(dn_match.group(1))
                    # Procura temporada no release name
                    for pattern in season_patterns:
                        matches = re.findall(pattern, release_name, re.IGNORECASE)
                        for match in matches:
                            if match:
                                try:
                                    detected_seasons.add(int(match))
                                except ValueError:
                                    detected_seasons.add(match)
            
            # Procura também no título do post
            for pattern in season_patterns:
                matches = re.findall(pattern, post_title, re.IGNORECASE)
                for match in matches:
                    if match:
                        try:
                            detected_seasons.add(int(match))
                        except ValueError:
                            detected_seasons.add(match)
            
            xbmc.log(f"[CMD1] Temporadas detectadas no post: {sorted(detected_seasons)}", xbmc.LOGDEBUG)
        
        for link in magnet_links:
            magnet_url = link.get("href") if hasattr(link, 'get') else link.url
            
            # Extrai nome do release
            dn_match = re.search(r'dn=([^&]+)', magnet_url)
            release_name = urllib.parse.unquote(dn_match.group(1)) if dn_match else post_title
            
            # --- VALIDAÇÃO CORRETA DE EPISÓDIO COM SUPORTE PARA PORTUGUÊS ---
            if media_type == "tvshow":
                # Extrai temporada e episódio REAL do magnet
                ep_match = re.search(r'S(\d{1,2})E(\d{1,2})', release_name, re.IGNORECASE)
                
                if ep_match:
                    # Encontrou padrão SXXEXX no magnet
                    magnet_season = int(ep_match.group(1))
                    magnet_episode = int(ep_match.group(2))
                    
                    # Se estamos procurando um episódio específico
                    if episode:
                        # Se estamos procurando uma temporada específica
                        if season:
                            try:
                                target_season = int(season)
                                target_episode = int(episode)
                                
                                # 1. Verifica se é a temporada correta
                                if magnet_season != target_season:
                                    xbmc.log(f"[CMD1] Pulando magnet (temp {magnet_season} != {target_season}): {release_name}", xbmc.LOGDEBUG)
                                    continue
                                
                                # 2. Verifica se é o episódio correto
                                if magnet_episode != target_episode:
                                    xbmc.log(f"[CMD1] Pulando magnet (ep {magnet_episode} != {target_episode}): {release_name}", xbmc.LOGDEBUG)
                                    continue
                                
                                xbmc.log(f"[CMD1] Episódio correto encontrado: S{magnet_season:02d}E{magnet_episode:02d}", xbmc.LOGINFO)
                            except ValueError:
                                # Se season/episode não são números, usa comparação textual
                                if str(season) not in release_name.lower() or str(episode) not in release_name.lower():
                                    xbmc.log(f"[CMD1] Pulando magnet (não corresponde): {release_name}", xbmc.LOGDEBUG)
                                    continue
                        else:
                            # Se não especificou temporada, só verifica episódio
                            try:
                                target_episode = int(episode)
                                if magnet_episode != target_episode:
                                    xbmc.log(f"[CMD1] Pulando magnet (ep {magnet_episode} != {target_episode}): {release_name}", xbmc.LOGDEBUG)
                                    continue
                                xbmc.log(f"[CMD1] Episódio correto encontrado na temp {magnet_season}: S{magnet_season:02d}E{magnet_episode:02d}", xbmc.LOGINFO)
                            except ValueError:
                                # Episode não é número, verifica textualmente
                                if str(episode).lower() not in release_name.lower():
                                    xbmc.log(f"[CMD1] Pulando magnet (não contém '{episode}'): {release_name}", xbmc.LOGDEBUG)
                                    continue
                
                else:
                    # Não tem padrão SXXEXX, pode ser pack ou episódio com formato diferente
                    # Verifica se é pack da temporada correta
                    if season:
                        try:
                            target_season = int(season)
                            
                            # Procura temporada no release name usando múltiplos padrões
                            found_season = False
                            for pattern in season_patterns:
                                match = re.search(pattern, release_name, re.IGNORECASE)
                                if match:
                                    try:
                                        found_season_num = int(match.group(1))
                                        if found_season_num == target_season:
                                            found_season = True
                                            break
                                    except (ValueError, IndexError):
                                        pass
                            
                            # Se não encontrou temporada específica, verifica keywords de pack
                            if not found_season:
                                pack_keywords = ["completa", "complete", "pack", "season", "temporada", "box", "volume", "parte"]
                                has_pack_keyword = any(kw in release_name.lower() for kw in pack_keywords)
                                
                                # Verifica se o release tem número que pode ser temporada
                                has_season_number = str(target_season) in release_name
                                
                                if not (has_pack_keyword or has_season_number):
                                    xbmc.log(f"[CMD1] Pulando magnet (não é pack nem temp {target_season}): {release_name}", xbmc.LOGDEBUG)
                                    continue
                                else:
                                    xbmc.log(f"[CMD1] Pack aceito: {release_name}", xbmc.LOGINFO)
                        except ValueError:
                            # Season não é número, verifica textualmente
                            if str(season).lower() not in release_name.lower():
                                pack_keywords = ["completa", "complete", "pack", "season", "temporada"]
                                has_pack_keyword = any(kw in release_name.lower() for kw in pack_keywords)
                                
                                if not has_pack_keyword:
                                    xbmc.log(f"[CMD1] Pulando magnet (não contém '{season}'): {release_name}", xbmc.LOGDEBUG)
                                    continue
            
            # --- PARA BUSCA DE TEMPORADA COMPLETA (sem episódio) ---
            elif media_type == "tvshow" and season and not episode:
                try:
                    target_season = int(season)
                    
                    # Procura temporada no release name
                    found_season = False
                    for pattern in season_patterns:
                        match = re.search(pattern, release_name, re.IGNORECASE)
                        if match:
                            try:
                                found_season_num = int(match.group(1))
                                if found_season_num == target_season:
                                    found_season = True
                                    break
                            except (ValueError, IndexError):
                                pass
                    
                    if not found_season:
                        # Verifica se menciona a temporada textualmente
                        if str(target_season) not in release_name and f"Temporada {target_season}" not in release_name:
                            xbmc.log(f"[CMD1] Pulando conteúdo de outra temporada: {release_name}", xbmc.LOGDEBUG)
                            continue
                        else:
                            xbmc.log(f"[CMD1] Pack da temp {season} aceito: {release_name}", xbmc.LOGINFO)
                except ValueError:
                    # Season não é número
                    if str(season).lower() not in release_name.lower():
                        xbmc.log(f"[CMD1] Pulando conteúdo (não contém '{season}'): {release_name}", xbmc.LOGDEBUG)
                        continue
            
            # Contexto
            parent = link.find_parent() if hasattr(link, 'find_parent') and callable(link.find_parent) else None
            parent_text = parent.get_text() if parent else ""
            
            if not parent_text:
                magnet_pos = html.find(magnet_url[:50])
                if magnet_pos > 0:
                    context_start = max(0, magnet_pos - 300)
                    context_end = min(len(html), magnet_pos + 300)
                    parent_text = html[context_start:context_end]
            
            # --- EXTRAI QUALIDADE ---
            quality = "SD"
            quality_source = parent_text + post_title + release_name
            
            if "2160p" in quality_source or "4K" in quality_source:
                quality = "4K"
            elif "1080p" in quality_source:
                quality = "1080p"
            elif "720p" in quality_source:
                quality = "720p"
            
            is_full_hd = "FULL HD" in quality_source.upper()
            
            # --- EXTRAI TAMANHO ---
            size = "N/A"
            size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB))', parent_text + post_title, re.IGNORECASE)
            if size_match:
                size = size_match.group(1)
            
            # --- EXTRAI FORMATO ---
            format_match = re.search(r'\b(MP4|MKV|AVI|WEB-DL|WEBRip|BluRay|HDTV)\b', quality_source, re.IGNORECASE)
            video_format = format_match.group(1).upper() if format_match else ""
            
            # --- DETECTA TIPO DE RELEASE ---
            release_type = ""
            ep_match = re.search(r'S(\d{1,2})E(\d{1,2})', release_name, re.IGNORECASE)
            if ep_match:
                ep_season = ep_match.group(1)
                ep_number = ep_match.group(2)
                release_type = f" (S{ep_season}E{ep_number})"
            elif "VOLUME" in release_name.upper():
                vol_match = re.search(r'VOLUME[\.\s]*(\d+)', release_name, re.IGNORECASE)
                if vol_match:
                    release_type = f" (Vol.{vol_match.group(1)})"
            elif re.search(r'S\d{2}(?!E)', release_name.upper()):
                release_type = " (Pack Temporada)"
            elif re.search(r'COMPLETA|COMPLETE|PACK|TEMPORADA', release_name.upper()):
                release_type = " (Pack)"
            
            # --- MONTA LABEL ---
            quality_label = f"{quality} FULL HD" if is_full_hd and quality == "1080p" else quality
            format_label = f" | {video_format}" if video_format else ""
            
            # Adiciona informação de temporada no label
            season_label = ""
            if media_type == "tvshow" and season:
                season_label = f" | Temp {season}"
            
            label = f"CMD1: {quality_label}{season_label} | {audio}{format_label}{release_type} [{size}]"
            
            sources.append({
                "url": magnet_url,
                "quality": quality,
                "type": "torrent",
                "provider": "CMD1",
                "release_title": release_name,
                "label": label,
                "size": size,
                "audio": audio,
                "format": video_format,
                "media_type": media_type,
                "seeds": 0
            })
        
        xbmc.log(f"[CMD1] Extraídas {len(sources)} fontes do post", xbmc.LOGINFO)
        
    except Exception as e:
        xbmc.log(f"[CMD1] Erro ao extrair fontes: {str(e)}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
    
    return sources


def scrape(provider_url, item_data, season=None, episode=None, timeout=None):
    """
    Função principal de scraping para CMD1.site
    """
    global _TIMEOUT
    if timeout:
        _TIMEOUT = timeout

    title = item_data.get("title")
    imdb_id = item_data.get("imdb_id")
    media_type = item_data.get("media_type", "movie")
    all_sources = []
    
    xbmc.log(f"[CMD1] Iniciando scrape para: {title} (IMDB: {imdb_id})", xbmc.LOGINFO)
    xbmc.log(f"[CMD1] Temporada/Episódio: {season}/{episode}", xbmc.LOGINFO)
    
    # 1. Faz a busca com termos otimizados
    html_search = search_cmd1(
        imdb_id=imdb_id, 
        title=title, 
        season=season,
        episode=episode,
        media_type=media_type
    )
    
    if not html_search:
        xbmc.log("[CMD1] Busca não retornou resultados", xbmc.LOGWARNING)
        
        # Tenta busca alternativa sem filtro de temporada
        if media_type == "tvshow":
            xbmc.log("[CMD1] Tentando busca apenas com título...", xbmc.LOGINFO)
            html_search = search_cmd1(imdb_id=imdb_id, title=title, media_type=media_type)
    
    if not html_search:
        return []
    
    # 2. Encontra URLs dos posts com filtro inteligente
    post_data = find_post_urls(html_search, season=season, media_type=media_type)
    
    if not post_data:
        xbmc.log("[CMD1] Nenhum post encontrado", xbmc.LOGWARNING)
        
        # Se não encontrou com filtro de temporada, tenta sem filtro
        if media_type == "tvshow" and season:
            xbmc.log("[CMD1] Tentando busca sem filtro de temporada...", xbmc.LOGINFO)
            post_data = find_post_urls(html_search, media_type=media_type)
    
    if not post_data:
        return []
    
    xbmc.log(f"[CMD1] Encontrados {len(post_data)} posts para processar", xbmc.LOGINFO)
    
    # 3. Extrai fontes de cada post
    for post in post_data:
        sources = extract_sources_from_post(
            post_url=post['url'],
            post_title=post['title'],
            season=season,
            episode=episode,
            media_type=media_type
        )
        all_sources.extend(sources)
    
    # --- BUSCA ALTERNATIVA SE NÃO ENCONTRAR NADA ---
    if len(all_sources) == 0 and media_type == "tvshow":
        xbmc.log(f"[CMD1] Nenhuma fonte encontrada. Tentando busca mais ampla...", xbmc.LOGINFO)
        
        # Processa todos os posts sem filtro de temporada/episódio
        for post in post_data:
            sources = extract_sources_from_post(
                post_url=post['url'],
                post_title=post['title'],
                season=None,
                episode=None,
                media_type=media_type
            )
            
            # Marca como disponível (não filtrado)
            for source in sources:
                source["label"] = f"[DISPONÍVEL] {source['label']}"
                all_sources.append(source)
    
    xbmc.log(f"[CMD1] Total de fontes encontradas: {len(all_sources)}", xbmc.LOGINFO)
    return all_sources