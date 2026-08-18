# -*- coding: utf-8 -*-
import re
import urllib.parse
import unicodedata
import xbmc
import requests
from bs4 import BeautifulSoup
from .utils import extract_magnets
from .scraper_config import get_url

class FilmesMasterScraper:
    """
    Scraper otimizado para o Filmes Master.
    """
    
    def __init__(self, timeout=15):
        self.base_url = get_url('filmesmaster', fallback='https://filmesmaster.org')
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8'
        }
    
    def normalize_text(self, text):
        """Normaliza texto para comparação."""
        if not text:
            return ""
        
        # Converte para minúsculas e remove espaços extras
        text = str(text).lower().strip()
        
        # Remove acentos
        try:
            text = unicodedata.normalize('NFKD', text)
            text = text.encode('ASCII', 'ignore').decode('utf-8')
        except:
            pass
        
        # Remove caracteres especiais
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove palavras comuns
        stop_words = {
            'torrent', 'download', 'dublado', 'dual', 'audio', 'legendado',
            'filme', 'serie', 'temporada', 'season', 'episodio', 'episode',
            'baixar', 'assistir', 'online', 'gratis', 'grátis', 'hd', 'fullhd',
            'bluray', '4k', '1080p', '720p', 'o', 'a', 'os', 'as', 'de', 'do',
            'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas', 'com', 'para',
            'por', 'e', 'ou', 'um', 'uma', 'uns', 'umas'
        }
        
        words = text.split()
        filtered_words = [word for word in words if word not in stop_words and len(word) > 1]
        
        return ' '.join(filtered_words)
    
    def generate_search_variations(self, title, year=None, season=None, episode=None, media_type="movie"):
        """
        Gera múltiplas variações de busca para aumentar as chances de acerto.
        """
        variations = []
        
        # Limpa o título
        clean_title = re.sub(r'[^\w\s]', ' ', title).strip()
        simple_title = re.sub(r'\s+', ' ', clean_title)
        
        # Para séries
        if media_type == "tvshow":
            # Variações com temporada/episódio
            if season and episode:
                variations.extend([
                    f"{simple_title} {season}x{episode:02d}",
                    f"{simple_title} S{season:02d}E{episode:02d}",
                    f"{simple_title} temporada {season} episodio {episode}",
                    f"{simple_title} season {season} episode {episode}",
                    f"{simple_title} ep {episode:02d}",
                ])
            
            # Variações apenas com temporada
            if season:
                variations.extend([
                    f"{simple_title} {season}ª temporada",
                    f"{simple_title} temporada {season}",
                    f"{simple_title} season {season}",
                    f"{simple_title} {season} temporada",
                ])
        
        # Variações com ano (para filmes e séries)
        if year:
            variations.extend([
                f"{simple_title} {year}",
                f"{simple_title} ({year})",
            ])
        
        # Variações simples
        variations.extend([
            simple_title,
            self.normalize_text(simple_title),  # Título normalizado
            # Título sem artigos no início
            re.sub(r'^(o|a|os|as|the)\s+', '', simple_title, flags=re.IGNORECASE).strip(),
        ])
        
        # Variações alternativas (útil para títulos longos)
        if len(simple_title.split()) > 2:
            # Pega as primeiras palavras
            words = simple_title.split()
            variations.append(' '.join(words[:3]))  # Primeiras 3 palavras
            variations.append(' '.join(words[:2]))  # Primeiras 2 palavras
        
        # Remove duplicados e limpa
        unique_variations = []
        seen = set()
        for var in variations:
            if var and var not in seen:
                seen.add(var)
                unique_variations.append(var)
        
        xbmc.log(f"[filmesmaster] Variações de busca geradas: {unique_variations}", xbmc.LOGINFO)
        return unique_variations
    
    def search(self, query):
        """Realiza busca no site."""
        # Codifica a query para URL
        query_clean = re.sub(r'[^\w\s]', ' ', query)
        query_clean = re.sub(r'\s+', '+', query_clean.strip())
        
        search_url = f"{self.base_url}/?s={query_clean}"
        xbmc.log(f"[filmesmaster] Buscando: '{query}' -> {search_url}", xbmc.LOGDEBUG)
        
        try:
            response = requests.get(search_url, headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                response.encoding = 'utf-8'
                return response.content
        except Exception as e:
            xbmc.log(f"[filmesmaster] Erro na busca '{query}': {str(e)}", xbmc.LOGERROR)
        
        return None
    
    def parse_search_results(self, html):
        """Parseia os resultados da busca."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Tenta encontrar os resultados
            results = []
            
            # Método 1: div.movies-list > div.col
            movies_list = soup.find("div", class_="movies-list")
            if movies_list:
                items = movies_list.find_all("div", class_="col")
                results.extend(items)
            
            # Método 2: div.item diretamente
            if not results:
                items = soup.find_all("div", class_="item")
                results.extend(items)
            
            # Método 3: qualquer div com link e imagem que pareça resultado
            if not results:
                all_divs = soup.find_all("div")
                for div in all_divs:
                    link = div.find("a", href=True)
                    img = div.find("img")
                    title_div = div.find("div", class_="title")
                    if link and (img or title_div):
                        results.append(div)
            
            return results
            
        except Exception as e:
            xbmc.log(f"[filmesmaster] Erro ao parsear resultados: {str(e)}", xbmc.LOGERROR)
            return []
    
    def extract_item_info(self, item):
        """Extrai informações de um item de resultado."""
        info = {
            'title': '',
            'url': '',
            'year': '',
            'type': 'unknown'
        }
        
        try:
            # URL
            link = item.find("a", href=True)
            if link:
                info['url'] = link.get('href', '')
            
            # Título do título
            title_div = item.find("div", class_="title")
            if title_div:
                title_link = title_div.find("a")
                if title_link:
                    info['title'] = title_link.get_text(strip=True)
            
            # Título da imagem (fallback)
            if not info['title']:
                img = item.find("img")
                if img:
                    info['title'] = img.get('alt', '') or img.get('title', '')
            
            # Ano
            year_span = item.find("span", class_="lancamento")
            if year_span:
                year_text = year_span.get_text(strip=True)
                # Tenta extrair apenas o ano
                year_match = re.search(r'\b(19|20)\d{2}\b', year_text)
                if year_match:
                    info['year'] = year_match.group()
            
            # Determina tipo (série ou filme)
            title_lower = info['title'].lower()
            if any(word in title_lower for word in ['temporada', 'season', 'série', 'serie']):
                info['type'] = 'tvshow'
            else:
                info['type'] = 'movie'
            
        except Exception as e:
            xbmc.log(f"[filmesmaster] Erro ao extrair info: {str(e)}", xbmc.LOGDEBUG)
        
        return info
    
    def calculate_similarity(self, search_title, result_title, search_year=None, result_year=None):
        """
        Calcula similaridade entre títulos.
        Retorna score de 0 a 100.
        """
        # Normaliza os títulos
        norm_search = self.normalize_text(search_title)
        norm_result = self.normalize_text(result_title)
        
        # Se um estiver contido no outro, score alto
        if norm_search in norm_result or norm_result in norm_search:
            base_score = 80
        else:
            # Calcula similaridade por palavras
            search_words = set(norm_search.split())
            result_words = set(norm_result.split())
            
            if not search_words:
                return 0
            
            word_similarity = len(search_words.intersection(result_words)) / len(search_words)
            base_score = word_similarity * 100
        
        # Bônus por ano correspondente
        year_bonus = 0
        if search_year and result_year and search_year == result_year:
            year_bonus = 20
        
        # Penalidade por anos diferentes
        year_penalty = 0
        if search_year and result_year and search_year != result_year:
            year_penalty = -30
        
        final_score = base_score + year_bonus + year_penalty
        return max(0, min(100, final_score))
    
    def find_best_match(self, html, search_title, search_year=None, media_type="movie", season=None):
        """
        Encontra o melhor resultado entre os resultados da busca.
        """
        results = self.parse_search_results(html)
        
        if not results:
            return None
        
        best_match = None
        best_score = 0
        
        for item in results[:20]:  # Limita aos primeiros 20 resultados
            info = self.extract_item_info(item)
            
            if not info['title'] or not info['url']:
                continue
            
            # Verifica se o tipo corresponde
            if media_type == "tvshow" and info['type'] != 'tvshow':
                continue
            elif media_type == "movie" and info['type'] != 'movie':
                continue
            
            # Para séries, verifica temporada
            if media_type == "tvshow" and season:
                title_lower = info['title'].lower()
                season_patterns = [
                    rf'{season}\s*ª?\s*temporada',
                    rf'temporada\s*{season}',
                    rf'season\s*{season}',
                    rf's{season:02d}',
                    rf's{season}\b'
                ]
                
                has_season = False
                for pattern in season_patterns:
                    if re.search(pattern, title_lower, re.IGNORECASE):
                        has_season = True
                        break
                
                if not has_season:
                    continue
            
            # Calcula similaridade
            score = self.calculate_similarity(
                search_title, 
                info['title'], 
                search_year, 
                info.get('year')
            )
            
            xbmc.log(f"[filmesmaster] Resultado: '{info['title']}' ({info.get('year')}) - Score: {score:.1f}", xbmc.LOGDEBUG)
            
            if score > best_score:
                best_score = score
                best_match = info['url']
        
        if best_match and best_score >= 40:  # Threshold mínimo
            xbmc.log(f"[filmesmaster] Melhor match encontrado: Score {best_score:.1f}", xbmc.LOGINFO)
            return best_match
        
        return None
    
    def extract_sources(self, html, title, target_episode=None, season=None, media_type="movie"):
        """
        Extrai fontes da página usando a função existente.
        """
        try:
            sources = extract_magnets(
                html,
                title,
                target_episode=target_episode,
                season=season,
                media_type=media_type
            )
            
            # Adiciona informações extras
            for source in sources:
                if 'info' not in source:
                    source['info'] = {}
                
                if media_type == "tvshow":
                    if season:
                        source['info']['season'] = season
                    if target_episode:
                        source['info']['episode'] = target_episode
                
                source['provider'] = 'Filmesmaster'
            
            return sources
            
        except Exception as e:
            xbmc.log(f"[filmesmaster] Erro ao extrair fontes: {str(e)}", xbmc.LOGERROR)
            return []
    
    def scrape(self, provider_url, item_data, season=None, episode=None):
        """
        Método principal do scraper.
        """
        title = item_data.get("title", "")
        media_type = item_data.get("media_type", "movie")
        year = item_data.get("year", "")
        
        xbmc.log(f"[filmesmaster] === NOVO SCRAPER INICIADO ===", xbmc.LOGINFO)
        xbmc.log(f"[filmesmaster] Título: {title}", xbmc.LOGINFO)
        xbmc.log(f"[filmesmaster] Tipo: {media_type}", xbmc.LOGINFO)
        xbmc.log(f"[filmesmaster] Temporada: {season}", xbmc.LOGINFO)
        xbmc.log(f"[filmesmaster] Episódio: {episode}", xbmc.LOGINFO)
        xbmc.log(f"[filmesmaster] Ano: {year}", xbmc.LOGINFO)
        
        # Gera variações de busca
        search_variations = self.generate_search_variations(
            title, year, season, episode, media_type
        )
        
        # Tenta cada variação
        for search_query in search_variations:
            xbmc.log(f"[filmesmaster] Tentando: '{search_query}'", xbmc.LOGINFO)
            
            # Realiza busca
            html = self.search(search_query)
            if not html:
                continue
            
            # Encontra o melhor match
            post_url = self.find_best_match(html, title, year, media_type, season)
            
            if not post_url:
                continue
            
            # Garante URL completa
            if not post_url.startswith('http'):
                if post_url.startswith('/'):
                    post_url = f"{self.base_url}{post_url}"
                else:
                    post_url = f"{self.base_url}/{post_url}"
            
            xbmc.log(f"[filmesmaster] Post encontrado: {post_url}", xbmc.LOGINFO)
            
            # Acessa o post
            try:
                response = requests.get(post_url, headers=self.headers, timeout=self.timeout)
                if response.status_code != 200:
                    continue
                
                # Extrai as fontes
                sources = self.extract_sources(
                    response.content,
                    title,
                    target_episode=episode,
                    season=season,
                    media_type=media_type
                )
                
                if sources:
                    xbmc.log(f"[filmesmaster] Sucesso! {len(sources)} fontes encontradas", xbmc.LOGINFO)
                    return sources
                
            except Exception as e:
                xbmc.log(f"[filmesmaster] Erro ao acessar post: {str(e)}", xbmc.LOGERROR)
                continue
        
        xbmc.log(f"[filmesmaster] Nenhuma fonte encontrada após todas as tentativas", xbmc.LOGWARNING)
        return []

# Função de compatibilidade
def scrape_filmesmaster(provider_url, item_data, season=None, episode=None, timeout=None):
    scraper = FilmesMasterScraper(timeout=timeout or 15)
    return scraper.scrape(provider_url, item_data, season, episode)