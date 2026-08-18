# -*- coding: utf-8 -*-
import re
import html as html_lib
import unicodedata
import traceback
import requests
import xbmc
from urllib.parse import urljoin, urlparse

from .session import USER_AGENT
from .utils import guess_quality_from_name, format_size


class ScraperConfig:
    REQUEST_TIMEOUT = 15
    MAX_RESULTS = 10
    MOVIES_ROOT_PATH = "/movies/"
    TVS_ROOT_PATH = "/tvs/"


# Extrai name / url / size (em bytes, via data-sort) de cada <tr data-entry="true" ...>
# sem precisar montar árvore DOM (BeautifulSoup) -- crítico pra páginas de 9MB+.
ENTRY_PATTERN = re.compile(
    r'data-name="(?P<name>.*?)"\s+data-url="(?P<url>.*?)"(?:(?!<tr).)*?data-sort="(?P<size>-?\d+)"',
    re.DOTALL
)

VIDEO_EXT_PATTERN = re.compile(r'\.(mkv|mp4|m3u8|avi|webm|mov)$', re.I)
DOWNLOAD_TAG_PATTERN = re.compile(r'\[download\]', re.I)


class DahmerMoviesScraper:
    def __init__(self, provider_url, item_data):
        self.provider_url = provider_url.rstrip('/')
        self.item_data = item_data
        self.log_prefix = "[dahmermovies]"
        self._setup_item_data()

    def _setup_item_data(self):
        self.title = self.item_data.get('title', '').strip()
        self.original_title = self.item_data.get('original_title', '').strip()
        self.media_type = self.item_data.get('media_type', '').lower()

        try:
            self.year = int(self.item_data.get('year', 0)) or None
        except (ValueError, TypeError):
            self.year = None

        if self.media_type == 'tvshow':
            try:
                self.season = int(self.item_data.get('season', 1))
                self.episode = int(self.item_data.get('episode', 1))
            except (ValueError, TypeError):
                self.season = 1
                self.episode = 1
        else:
            self.season = None
            self.episode = None

    def _log(self, msg, level=xbmc.LOGINFO):
        # NOTE: LOGINFO ligado de propósito pra esta fase de teste.
        # Quando confirmar que está estável, trocar as linhas de fluxo normal
        # para xbmc.LOGDEBUG e manter só erros/avisos em LOGWARNING/LOGERROR.
        xbmc.log(f"{self.log_prefix} {msg}", level)

    def scrape(self):
        """Ponto de entrada principal"""
        try:
            if self.media_type == 'movie':
                return self._search_movies()
            elif self.media_type == 'tvshow':
                return self._search_episodes()
            else:
                return []
        except Exception as e:
            self._log(f"❌ Erro: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
            return []

    # ------------------------------------------------------------------
    # Normalização e extração (regex, sem BeautifulSoup)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(s):
        nfkd = unicodedata.normalize('NFKD', s)
        s = ''.join(c for c in nfkd if not unicodedata.combining(c))
        s = re.sub(r'[^\w\s\(\)]', '', s)
        s = re.sub(r'\s+', ' ', s).strip().lower()
        return s

    def _extract_entries(self, html_content):
        """Extrai todas as entradas (name, url, size_bytes) de uma página de índice."""
        entries = []
        for m in ENTRY_PATTERN.finditer(html_content):
            name = html_lib.unescape(m.group('name'))
            url = html_lib.unescape(m.group('url'))
            raw_size = m.group('size')
            size_bytes = int(raw_size) if raw_size and raw_size != '-1' else None
            entries.append({'name': name, 'url': url, 'size_bytes': size_bytes})
        return entries

    def _resolve_url(self, href, base_url):
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        return urljoin(base_url, href)

    def _find_folder(self, html_content, base_url):
        """
        Acha a pasta do filme/série dentro de um índice, priorizando:
        1) match exato "titulo (ano)"
        2) match "solto" (palavra inteira + ano em algum ponto do nome)
        """
        entries = self._extract_entries(html_content)
        candidates = [c for c in (self.original_title, self.title) if c]

        exact, loose = [], []

        for entry in entries:
            name_norm = self._normalize(entry['name'])
            matched = False

            for cand in candidates:
                cand_norm = self._normalize(cand)

                if self.year:
                    expected = self._normalize(f"{cand} ({self.year})")
                    if name_norm == expected:
                        exact.append(entry)
                        matched = True
                        break
                    pattern = re.compile(
                        rf'(?<!\w){re.escape(cand_norm)}(?!\w).*\({self.year}\)'
                    )
                    if pattern.search(name_norm):
                        loose.append(entry)
                        matched = True
                        break
                else:
                    if name_norm == cand_norm:
                        exact.append(entry)
                        matched = True
                        break
                    if cand_norm in name_norm:
                        loose.append(entry)
                        matched = True
                        break

            if matched:
                continue

        chosen = exact or loose
        if not chosen:
            self._log(
                f"⚠️ Nenhuma pasta encontrada para candidatos={candidates} ano={self.year} "
                f"(total de entradas no índice: {len(entries)})",
                xbmc.LOGWARNING
            )
            return None

        entry = chosen[0]
        match_type = "EXATO" if entry in exact else "aproximado"
        self._log(f"📁 Pasta encontrada ({match_type}): '{entry['name']}' -> {entry['url']}")
        return self._resolve_url(entry['url'], base_url)

    def _extract_video_files(self, html_content):
        """Extrai todos os arquivos de vídeo de dentro de uma pasta, com tamanho.
        Ignora entradas marcadas como '[Download]' (link duplicado, não é o arquivo em si)."""
        entries = self._extract_entries(html_content)
        videos = [
            e for e in entries
            if VIDEO_EXT_PATTERN.search(e['name']) and not DOWNLOAD_TAG_PATTERN.search(e['name'])
        ]
        return videos

    def _find_series_folder(self, html_content, base_url):
        """
        Acha a pasta da série dentro do índice /tvs/. Diferente de filmes,
        aqui a pasta NÃO tem ano no nome (ex: "Dark", não "Dark (2017)").
        """
        entries = self._extract_entries(html_content)
        candidates = [c for c in (self.original_title, self.title) if c]

        exact, loose = [], []
        for entry in entries:
            name_norm = self._normalize(entry['name'])
            for cand in candidates:
                cand_norm = self._normalize(cand)
                if name_norm == cand_norm:
                    exact.append(entry)
                    break
                if cand_norm in name_norm:
                    loose.append(entry)
                    break

        chosen = exact or loose
        if not chosen:
            self._log(
                f"⚠️ Pasta da série não encontrada para candidatos={candidates} "
                f"(total de entradas: {len(entries)})",
                xbmc.LOGWARNING
            )
            return None

        entry = chosen[0]
        match_type = "EXATO" if entry in exact else "aproximado"
        self._log(f"📁 Série encontrada ({match_type}): '{entry['name']}' -> {entry['url']}")
        return self._resolve_url(entry['url'], base_url)

    def _find_season_folder(self, html_content, base_url):
        """Acha a pasta da temporada certa (ex: 'Season 1', 'Season 01') dentro da pasta da série."""
        entries = self._extract_entries(html_content)
        pattern = re.compile(rf'season\s*0*{self.season}\b', re.I)

        for entry in entries:
            if pattern.search(entry['name']):
                self._log(f"📁 Temporada encontrada: '{entry['name']}' -> {entry['url']}")
                return self._resolve_url(entry['url'], base_url)

        self._log(
            f"⚠️ Temporada {self.season} não encontrada entre {[e['name'] for e in entries]}",
            xbmc.LOGWARNING
        )
        return None

    # ------------------------------------------------------------------
    # Filmes
    # ------------------------------------------------------------------

    def _search_movies(self):
        results = []
        root_url = f"{self.provider_url}{ScraperConfig.MOVIES_ROOT_PATH}"

        self._log(f"🔍 Buscando índice raiz: {root_url}")
        response = self._make_request(root_url)
        if not response:
            self._log(f"⚠️ Falha ao acessar índice raiz: {root_url}", xbmc.LOGWARNING)
            return results

        self._log(f"📦 Índice raiz recebido: {len(response.text) / 1024 / 1024:.2f} MB")

        folder_url = self._find_folder(response.text, root_url)
        if not folder_url:
            return results

        self._log(f"➡️ Entrando na pasta: {folder_url}")
        folder_response = self._make_request(folder_url)
        if not folder_response:
            self._log(f"⚠️ Falha ao acessar pasta: {folder_url}", xbmc.LOGWARNING)
            return results

        video_entries = self._extract_video_files(folder_response.text)
        self._log(f"🎬 {len(video_entries)} arquivo(s) de vídeo encontrado(s) na pasta")

        # Mostra TODOS os arquivos da pasta (até o limite de resultados), com tamanho
        for entry in video_entries[:ScraperConfig.MAX_RESULTS]:
            results.append(self._create_result_item(entry, folder_url))

        return results

    # ------------------------------------------------------------------
    # Séries
    # ------------------------------------------------------------------

    def _search_episodes(self):
        results = []
        root_url = f"{self.provider_url}{ScraperConfig.TVS_ROOT_PATH}"

        # Nível 1: índice raiz de séries -> pasta da série (sem ano)
        self._log(f"🔍 Buscando índice de séries: {root_url}")
        response = self._make_request(root_url)
        if not response:
            self._log(f"⚠️ Falha ao acessar índice de séries: {root_url}", xbmc.LOGWARNING)
            return results

        series_url = self._find_series_folder(response.text, root_url)
        if not series_url:
            return results

        # Nível 2: pasta da série -> pasta da temporada certa
        self._log(f"➡️ Entrando na pasta da série: {series_url}")
        series_response = self._make_request(series_url)
        if not series_response:
            self._log(f"⚠️ Falha ao acessar pasta da série: {series_url}", xbmc.LOGWARNING)
            return results

        season_url = self._find_season_folder(series_response.text, series_url)
        if not season_url:
            return results

        # Nível 3: pasta da temporada -> arquivos de episódio
        self._log(f"➡️ Entrando na pasta da temporada: {season_url}")
        season_response = self._make_request(season_url)
        if not season_response:
            self._log(f"⚠️ Falha ao acessar pasta da temporada: {season_url}", xbmc.LOGWARNING)
            return results

        entries = self._extract_entries(season_response.text)
        video_entries = [
            e for e in entries
            if VIDEO_EXT_PATTERN.search(e['name'])
            and not DOWNLOAD_TAG_PATTERN.search(e['name'])
            and self._is_correct_episode(e['name'])
        ]

        self._log(f"🎬 {len(video_entries)} episódio(s) correspondente(s) encontrado(s) "
                   f"(S{self.season:02d}E{self.episode:02d})")

        for entry in video_entries[:ScraperConfig.MAX_RESULTS]:
            results.append(self._create_result_item(entry, season_url))

        return results

    def _is_correct_episode(self, filename):
        filename_lower = filename.lower()

        sxey_pattern = f"s{self.season:02d}e{self.episode:02d}"
        if sxey_pattern in filename_lower:
            return True

        ep_pattern = f"e{self.episode:02d}"
        if ep_pattern in filename_lower:
            return True

        if f" - {self.episode:02d}" in filename_lower:
            return True

        return False

    # ------------------------------------------------------------------
    # Request / resultado
    # ------------------------------------------------------------------

    def _make_request(self, url):
        headers = {
            'User-Agent': USER_AGENT,
            'Referer': self.provider_url + '/',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'pt-BR,pt;q=0.9',
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=ScraperConfig.REQUEST_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()
            return response
        except Exception as e:
            self._log(f"⚠️ Erro ao acessar {url}: {e}", xbmc.LOGWARNING)
            return None

    @staticmethod
    def _format_size(size_bytes):
        """Formata bytes em string legível (KB/MB/GB/TB)."""
        if size_bytes is None or size_bytes < 0:
            return 'N/A'
        try:
            # Reaproveita format_size do utils.py se ele aceitar bytes (int).
            # Se o utils.format_size tiver assinatura diferente, cai no fallback abaixo.
            return format_size(size_bytes)
        except Exception:
            step = 1024.0
            units = ['B', 'KB', 'MB', 'GB', 'TB']
            value = float(size_bytes)
            for unit in units:
                if value < step:
                    return f"{value:.1f} {unit}"
                value /= step
            return f"{value:.1f} PB"

    def _create_result_item(self, entry, base_url):
        name = entry['name']
        url = self._resolve_url(entry['url'], base_url)
        size_str = self._format_size(entry.get('size_bytes'))

        quality = guess_quality_from_name(name) or 'HD'

        name_lower = name.lower()
        if 'dual' in name_lower or 'multi' in name_lower:
            language = 'DUAL'
        elif 'dublado' in name_lower or 'pt-br' in name_lower or 'ptbr' in name_lower:
            language = 'PT-BR'
        elif 'legendado' in name_lower or ' leg' in name_lower:
            language = 'LEG'
        else:
            # DahmerMovies serve principalmente áudio original (en/etc) com
            # legenda -- não dublagem PT-BR -- então o fallback é LEG, não PT-BR.
            language = 'LEG'

        self._log(f"   ✓ {name} [{quality}] {size_str}")

        return {
            'url': url,
            'quality': quality,
            'type': 'Direto',
            'title': name,
            'release_title': name,
            'label': f"{name} [{quality}] {size_str}",
            'size': size_str,
            'peers': 'N/A',
            'seeders': 'N/A',
            'provider': 'DahmerMovies',
            'languages': language,
        }


def scrape(provider_url, item_data, timeout=None):
    """Função exportada para o router"""
    try:
        if timeout:
            ScraperConfig.REQUEST_TIMEOUT = timeout
        return DahmerMoviesScraper(provider_url, item_data).scrape()
    except Exception as e:
        xbmc.log(f"[dahmermovies.scrape] ❌ Erro: {e}", xbmc.LOGERROR)
        return []