# -*- coding: utf-8 -*-
import re
import unicodedata
import requests
import xbmc
import traceback
import time
from urllib.parse import urlparse, urlencode, parse_qs
from bs4 import BeautifulSoup

from .session import USER_AGENT
from .utils import guess_quality_from_name, get_anime_search_codes, format_size, normalize_for_compare


class ScraperConfig:
    REQUEST_TIMEOUT = 15  # sobrescrito em runtime por scrape() a partir das settings
    MAX_RETRIES     = 2
    MAX_RESULTS     = 2


def with_retry(max_retries=2, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.Timeout,
                        requests.exceptions.ConnectionError):
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay * (attempt + 1))
            return None
        return wrapper
    return decorator


@with_retry(max_retries=ScraperConfig.MAX_RETRIES, delay=1)
def _post_to_animezey(url, payload):
    headers = {
        "accept":           "*/*",
        "accept-language":  "pt-BR,pt;q=0.9",
        "content-type":     "application/json",
        "Referer":          url,
        "User-Agent":       USER_AGENT,
    }
    try:
        r = requests.post(url, headers=headers, json=payload,
                          timeout=ScraperConfig.REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        xbmc.log(f"[animezey] Erro POST {url}: {e}", xbmc.LOGWARNING)
        return None


class AnimeZeyScraper:

    _TITLE_END_RE = re.compile(
        r'(?:'
        r's\d{1,2}e\d{1,2}'
        r'|\[?\d{3,4}p\]?'
        r'|(?:19|20)\d{2}'
        r'|ep?\s*\d+'
        r'|episode\s*\d+'
        r'|\[(?:dual|dub|leg|sub|pt[\-.]br|bluray|bdrip|webrip'
        r'|web[\-.]dl|hdtv|x264|x265|hevc|aac|mkv|mp4|avi|wmv|mov)\]'
        r'|(?:dual|dub|leg|sub|pt[\-.]br|bluray|bdrip|webrip'
        r'|web[\-.]dl|hdtv|x264|x265|hevc|aac|mkv|mp4|avi|wmv|mov)'
        r'|\[\d+'
        r'|\s-\s\d+'
        r')',
        re.IGNORECASE,
    )

    def __init__(self, provider_url, item_data):
        self.provider_url = provider_url
        self.item_data    = item_data
        self.log_prefix   = "[animezey]"
        self._setup_item_data()
        self._setup_domains()

    # ------------------------------------------------------------------
    # Normalização ASCII
    # ------------------------------------------------------------------

    def _remove_accents(self, text):
        """Remove acentos/diacríticos e retorna string ASCII pura."""
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_item_data(self):
        self.title          = (self.item_data.get('title')          or '').strip()
        self.original_title = (self.item_data.get('original_title') or '').strip()
        self.romaji_title   = (self.item_data.get('romaji_title')   or '').strip()
        self.media_type     = (self.item_data.get('media_type')     or '').lower()

        try:
            self.year = int(self.item_data.get('year'))
        except Exception:
            self.year = None

        if self.media_type == 'tvshow':
            try:
                self.season  = int(self.item_data.get('season',  1))
                self.episode = int(self.item_data.get('episode', 1))
            except Exception:
                self.season  = 1
                self.episode = 1

            raw_abs = self.item_data.get('absolute_episode')
            try:
                self.abs_ep = int(raw_abs) if raw_abs not in (None, '', 'None') else None
            except (ValueError, TypeError):
                self.abs_ep = None
        else:
            self.season  = None
            self.episode = None
            self.abs_ep  = None

        xbmc.log(
            f"{self.log_prefix} 🎯 Busca: title='{self.title}' "
            f"abs_ep={self.abs_ep} is_anime={self._is_anime()}",
            xbmc.LOGINFO,
        )

    def _setup_domains(self):
        parsed = urlparse(self.provider_url)
        self.base_domain     = parsed.netloc or "1.animezey23112022.workers.dev"
        self.download_domain = "animezey16082023.animezey16082023.workers.dev"

    # ------------------------------------------------------------------
    # Heurística: anime vs série ocidental
    # ------------------------------------------------------------------

    def _is_anime(self):
        if self.romaji_title and self.romaji_title != self.original_title:
            return True
        for field in (self.romaji_title, self.original_title, self.title):
            if field and re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', field):
                return True
        return False

    def _is_flat_series(self):
        """
        Séries brasileiras indexadas com número puro: '- 001', '- 01', '[001]'.
        Ativa quando NÃO é anime e season == 1.
        Não requer abs_ep — usa o próprio self.episode.
        """
        return (
            not self._is_anime()
            and self.media_type == 'tvshow'
            and self.season == 1
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def scrape(self):
        try:
            if self.media_type == 'movie':
                return self._search_movies()
            elif self.media_type == 'tvshow':
                return self._search_episodes()
            else:
                return []
        except Exception as e:
            xbmc.log(f"{self.log_prefix} ❌ Erro: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)
            return []

    # ------------------------------------------------------------------
    # Busca de episódios
    # ------------------------------------------------------------------

    def _search_episodes(self):

        episodes  = []
        seen_ids  = set()
        queries   = self._generate_episode_queries()[:10]

        if not queries:
            return []

        search_url = f"https://{self.base_domain}/1:search"

        for query in queries:
            try:
                payload = {"q": query, "page_token": None, "page_index": 0}
                result  = _post_to_animezey(search_url, payload)

                if not (result and 'data' in result and 'files' in result['data']):
                    continue

                for item in result['data']['files']:
                    item_id = item.get('id')
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    if not self._is_video_file(item):
                        continue
                    

                    name = item.get('name', '')
                    if self._is_correct_episode(name):
                        episodes.append(item)

                        if len(episodes) >= ScraperConfig.MAX_RESULTS:
                            return self._process_results(episodes)

            except Exception as e:
                continue

        if episodes:
            return self._process_results(episodes)

        return []

    # ------------------------------------------------------------------
    # Geração de queries para episódios
    # ------------------------------------------------------------------

    def _generate_episode_queries(self):
        queries    = []
        base_names = self._get_base_names()
        if not base_names:
            return []

        top_names    = base_names[:4]
        search_codes = get_anime_search_codes(self.season, self.episode)
        is_anime     = self._is_anime()

        # Derivados de nome — sempre sem acentos para o servidor
        def _variants(name):
            clean = self._remove_accents(re.sub(r"[',\\.:]", "", name))
            clean = re.sub(r'\s*-\s*', ' ', clean)                      # hífen → espaço
            clean = clean.strip()
            dots  = clean.replace(' ', '.')
            raw      = re.sub(r"[',\\.:]", "", name)
            raw      = re.sub(r'\s*-\s*', ' ', raw).strip()
            dots_raw = raw.replace(' ', '.')
            return clean, dots, raw, dots_raw

        # ── 1. SxxExx
        sxey = f"S{self.season:02d}E{self.episode:02d}"
        for name in top_names:
            clean, dots, raw, dots_raw = _variants(name)
            queries.append(f"{dots_raw}.{sxey}")   # com acento — prioritário
            queries.append(f"{dots}.{sxey}")
            queries.append(f"{raw} {sxey}")
            queries.append(f"{clean} {sxey}")

        # ── 1b. Flat "- NNN" para novelas/séries brasileiras (season 1, não-anime)
        if self._is_flat_series():
            for name in top_names:
                clean, dots, raw, dots_raw = _variants(name)
                queries.append(f"{clean} - {self.episode:03d}")   # "Avenida Brasil - 001"
                queries.append(f"{clean} - {self.episode:02d}")   # "Avenida Brasil - 01"
                queries.append(f"{dots}.{self.episode:03d}")       # "Avenida.Brasil.001"
                queries.append(f"{dots}.{self.episode:02d}")       # "Avenida.Brasil.01"
                queries.append(f"{clean} {self.episode:03d}")      # "Avenida Brasil 001"

        # ── 2. Absoluto — só para anime quando abs_ep difere do episode
        use_absolute = (
            is_anime
            and self.abs_ep is not None
            and self.abs_ep != self.episode
        )
        if use_absolute:
            for name in top_names:
                clean, dots, raw, dots_raw = _variants(name)
                queries.append(f"{clean} - {self.abs_ep:02d}")
                queries.append(f"{clean} - {self.abs_ep:03d}")
                queries.append(f"{dots}.{self.abs_ep:02d}")
                queries.append(f"{dots}.{self.abs_ep:03d}")
                
        # ── 2b. Anime season > 1 sem abs_ep: usa episode como número flat
        # Cobre casos como One Piece S17E693 onde o ep já é o absoluto
        if is_anime and self.season > 1 and self.abs_ep is None:
            for name in top_names:
                clean, dots, raw, dots_raw = _variants(name)
                queries.append(f"{clean} - {self.episode:03d}")
                queries.append(f"{clean} - {self.episode:02d}")
                queries.append(f"{dots}.{self.episode:03d}")
                queries.append(f"{dots}.{self.episode:02d}")        

        # ── 3. Flat " - 01" — só para anime season 1
        if is_anime and self.season == 1:
            for name in top_names:
                clean, dots, raw, dots_raw = _variants(name)
                queries.append(f"{clean} - {self.episode:02d}")
                queries.append(f"{clean} - {self.episode:03d}")
                queries.append(f"{dots} - {self.episode:02d}")
                queries.append(f"{dots}-{self.episode:02d}")

        # ── 4. Códigos do utils
        for name in top_names:
            clean, dots, raw, dots_raw = _variants(name)
            if is_anime and self.season == 1:
                codes = [c for c in search_codes if c.isdigit()]
            else:
                codes = search_codes[:4]

            for code in codes:
                queries.append(f"{dots}.{code}")
                if not code.upper().startswith('S'):
                    queries.append(f"{clean} {code}")

        # ── 5. Com ano (fallback)
        if self.year and self.year > 1900:
            for name in top_names[:2]:
                clean, dots, raw, dots_raw = _variants(name)
                for code in search_codes[:2]:
                    queries.append(f"{dots}.{self.year}.{code}")
                if is_anime and self.season == 1:
                    queries.append(f"{clean} {self.year} - {self.episode:02d}")

        # Deduplica mantendo ordem
        seen   = set()
        unique = []
        for q in queries:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(q)

        return unique

    # ------------------------------------------------------------------
    # Validação de episódio
    # ------------------------------------------------------------------

    def _is_correct_episode(self, filename):
        filename_lower       = filename.lower()
        filename_ascii_lower = self._remove_accents(filename_lower)

        if not self._matches_series_in_filename(filename_lower):
            return False

        # ── Detecta se o filename já tem padrão SxxExx explícito
        # Se tiver, ele é a fonte da verdade — nenhum outro match é aceito
        sxey_present = re.search(r's\d{2}e\d{2}|\d+x\d{2}', filename_ascii_lower)

        # ── 1. SxxExx — verifica o match correto primeiro
        sxey_patterns = [
            f"s{self.season:02d}e{self.episode:02d}",
            f"{self.season}x{self.episode:02d}",
        ]
        for p in sxey_patterns:
            if p in filename_ascii_lower:
                return True

        # Se filename tem SxxExx mas não bateu acima → episódio errado, rejeita imediatamente
        if sxey_present:
            return False

        # A partir daqui: filename NÃO tem padrão SxxExx — podemos usar outros critérios

        # ── 2. Códigos do utils (ex: "1x03", "103", "e03")
        for code in get_anime_search_codes(self.season, self.episode):
            if re.search(r'(?<!\d)' + re.escape(code.lower()) + r'(?!\d)', filename_ascii_lower):
                return True

        # ── 3. Anime season > 1 sem abs_ep: valida episode como número flat
        if self._is_anime() and self.season > 1 and self.abs_ep is None:
            ep_patterns = [
                f" - {self.episode:02d}",
                f" - {self.episode:03d}",
                f"- {self.episode:02d}",
                f"- {self.episode:03d}",
                f" {self.episode:03d}.",
                f" {self.episode:03d} ",
                f"[{self.episode:03d}]",
            ]
            for p in ep_patterns:
                if p in filename_ascii_lower:
                    return True

        # Bloco ── 4. Absoluto para anime
        if self._is_anime() and self.abs_ep is not None:
            abs_patterns = [
                rf' - {self.abs_ep:02d}(?!\d)',
                rf' - {self.abs_ep:03d}(?!\d)',
                rf'- {self.abs_ep:02d}(?!\d)',
                rf'- {self.abs_ep:03d}(?!\d)',
                rf' {self.abs_ep:02d} ',
                rf' {self.abs_ep:03d} ',
                rf' {self.abs_ep:02d}\.',
                rf' {self.abs_ep:03d}\.',
                rf'\[{self.abs_ep:02d}\]',
                rf'\[{self.abs_ep:03d}\]',
            ]
            for p in abs_patterns:
                if re.search(p, filename_ascii_lower):
                    return True

        # ── 5. Flat para novelas brasileiras (season 1, não-anime)
        if self._is_flat_series():
            flat_novela = [
                rf' - {self.episode:03d}(?!\d)',   # " - 001" não bate em " - 0010"
                rf' - {self.episode:02d}(?!\d)',   # " - 01"  não bate em " - 010"
                rf'- {self.episode:03d}(?!\d)',
                rf'- {self.episode:02d}(?!\d)',
                rf'\[{self.episode:03d}\]',
                rf'\[{self.episode:02d}\]',
                rf' {self.episode:03d}\.',
                rf' {self.episode:02d}\.',
                rf' {self.episode:03d} ',
                rf' {self.episode:02d} ',
            ]
            for p in flat_novela:
                if re.search(p, filename_ascii_lower):
                    return True

        return False

    # ------------------------------------------------------------------
    # Match de nome de série no filename
    # ------------------------------------------------------------------

    def _normalize_fn(self, s):
        s = self._remove_accents(s.lower())
        s = re.sub(r'[\.\-_\+,:]', ' ', s)
        s = re.sub(r'[\[\]()\{\}]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    # Palavras de conteúdo que, se aparecerem ANTES do título no filename,
    # indicam que é um título diferente (ex: "fear" em "fear the walking dead").
    _IGNORABLE_PREFIX_WORDS = frozenset({
        'the', 'a', 'an', 'o', 'a', 'os', 'as', 'de', 'do', 'da', 'dos', 'das',
        'em', 'no', 'na', 'nos', 'nas', 'um', 'uma',
    })

    def _title_match(self, title, filename):
        title_n = self._normalize_fn(title)
        fn_n    = self._normalize_fn(filename)

        if not title_n:
           return False

        has_sxey = bool(re.search(r's\d{2}e\d{2}|\d+x\d{2}', fn_n))

        pattern = r'(?<![a-z0-9])' + re.escape(title_n) + r'(?=[^a-z0-9]|$)'
        for m in re.finditer(pattern, fn_n):
            after = fn_n[m.end():].strip()

            after_ok = (
                not after
                or self._TITLE_END_RE.match(after)
                or re.match(r'^[\-\u2013\u2014]?\s*\d', after)
            )

            # NOVO: só libera via has_sxey se o trecho entre o título e o
            # SxxExx não tiver palavras de conteúdo (ex: "Desire")
            if not after_ok and has_sxey:
                sxey_m = re.search(r's\d{2}e\d{2}|\d+x\d{2}', after)
                if sxey_m:
                    between = after[:sxey_m.start()]
                    between_words = [
                        w for w in between.split()
                        if not re.fullmatch(
                            r'\d{4}|[a-z0-9]+(?:p|k)|bluray|bdrip|webrip|web|hdtv'
                            r'|x264|x265|hevc|aac|mkv|mp4|avi|wmv|mov|hdr|sdr|remux'
                            r'|dual|dub|dublado|leg|legendado|sub|pt[\-.]?br'
                            r'|nf|netflix|hbo|max|hbomax|disney|amazon|prime'
                            r'|copia|copy|sample|extras?',
                            w, re.IGNORECASE
                        )
                    ]
                    after_ok = not between_words

            if not after_ok:
                continue

            before = fn_n[:m.start()].strip()
            if not before:
                return True

            before_words = before.split()
            content_words = [
                w for w in before_words
                if not re.fullmatch(
                    r'\d{4}|[a-z0-9]+'
                    r'(?:p|k)|bluray|bdrip|webrip|web|hdtv|x264|x265|hevc'
                    r'|aac|mkv|mp4|avi|wmv|mov|hdr|sdr|remux'
                    r'|Aenianos & Kirinashi|anitsu|hbo|max|hbomax|netflix|disney|disneyplus|amazon|prime'
                    r'|paramount|peacock|hulu|apple|appletv|star|globoplay'
                    r'|telecine|crunchyroll|funimation|youtube|vix|pluto'
                    r'|copia|copy|sample|extras?',
                    w, re.IGNORECASE
                )
                and w not in self._IGNORABLE_PREFIX_WORDS
            ]

            if not content_words:
                return True

        return False

    def _matches_series_in_filename(self, filename_lower):
        base_names  = self._get_base_names()[:8]
        fn_norm     = normalize_for_compare(self._remove_accents(filename_lower))

        for name in base_names:
            name_ascii = self._remove_accents(name)
            name_norm  = normalize_for_compare(name_ascii)

            if ':' in name_ascii:
                parts = [p.strip() for p in name_ascii.split(':')]
                if all(
                    len(p) <= 2
                    or self._title_match(p, filename_lower)
                    or self._title_match(normalize_for_compare(p), fn_norm)
                    for p in parts
                ):
                    return True
            else:
                if (self._title_match(name_ascii, filename_lower)
                        or self._title_match(name_norm, fn_norm)):
                    return True

        return False

    # ------------------------------------------------------------------
    # Nomes base
    # ------------------------------------------------------------------

    def _get_base_names(self):
        names = []
        
        if self._is_anime():
            fields = (self.romaji_title, self.original_title, self.title)
        else:
            fields = (self.title, self.original_title, self.romaji_title)

        for field in fields:
            if not field:
                continue
            clean = field.strip()
            if clean not in names:
                names.append(clean)
            if ':' in clean:
                short = clean.split(':')[0].strip()
                if short not in names:
                    names.append(short)

        if not names:
            return []

        final = []
        for name in names:
            final.append(name)
            if "'" in name:
                final.append(name.replace("'", ""))
            if ':' not in name:
                lower = name.lower()
                for art in ('the ', 'a ', 'an ', 'o ', 'os ', 'as '):
                    if lower.startswith(art):
                        rest = name[len(art):]
                        if rest not in final:
                            final.append(rest)
                        break

        seen   = set()
        unique = []
        for n in final:
            if n and n not in seen:
                seen.add(n)
                unique.append(n)

        return unique

    # ------------------------------------------------------------------
    # Busca de filmes
    # ------------------------------------------------------------------

    def _search_movies(self):

        movies    = []
        seen_ids  = set()
        queries   = self._generate_movie_queries()[:8]
        search_url = f"https://{self.base_domain}/1:search"

        for query in queries:
            try:
                result = _post_to_animezey(search_url, {"q": query})
                if not (result and 'data' in result and 'files' in result['data']):
                    continue

                for item in result['data']['files']:
                    item_id = item.get('id')
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    if self._is_video_file(item) and self._is_correct_movie(item.get('name', '')):
                        movies.append(item)

                        if len(movies) >= 5:
                            return self._process_results(movies)

            except Exception as e:
                xbmc.log(f"{self.log_prefix} ⚠️ Erro query '{query}': {e}", xbmc.LOGDEBUG)
                continue

        if movies:
            return self._process_results(movies)
        
        return []

    def _generate_movie_queries(self):
        queries    = []
        base_names = self._get_base_names()[:5]

        for name in base_names:
            clean = self._remove_accents(re.sub(r"[',\\.:]", "", name))
            clean = re.sub(r'\s*-\s*', ' ', clean)   # "Spider-Man" → "Spider Man"
            clean = clean.strip()
            dots  = clean.replace(' ', '.')
            if self.year:
                queries.append(f"{dots}.{self.year}")
                queries.append(f"{clean} {self.year}")
            queries.append(dots)
            queries.append(clean)

        # ── NOVO: original_title sem remoção de acentos (ex: títulos em japonês)
        if self.original_title:
            raw_orig = re.sub(r"[',\.\-]", "", self.original_title).strip()
            if self.year:
                queries.append(f"{raw_orig} {self.year}")
            queries.append(raw_orig)

        seen   = set()
        unique = []
        for q in queries:
            if q and q not in seen:
                seen.add(q)
                unique.append(q)
                
        return unique


    def _is_correct_movie(self, filename):
        base_names = self._get_base_names()
        fn_lower   = filename.lower()
        fn_norm    = normalize_for_compare(self._remove_accents(fn_lower))

        for name in base_names:
            name_ascii = self._remove_accents(name)
            name_norm  = normalize_for_compare(name_ascii)

            # Usa apenas _title_match (com guarda de prefixo) para evitar
            # falsos positivos do tipo "Fear The Walking Dead" -> "The Walking Dead"
            matched = (
                self._title_match(name_ascii, fn_lower)
                or self._title_match(name_norm, fn_norm)
            )

            if matched:
                if self.year:
                    return str(self.year) in fn_lower
                return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_video_file(self, item):
        name = item.get('name', '')
        mime = item.get('mimeType', '')
        return (
            'video' in mime
            or name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'))
        )

    def _process_results(self, items):
        results    = []
        seen_links = set()

        for item in items:
            url = self._extract_player_url(item)
            if not url or url in seen_links:
                continue
            seen_links.add(url)
            results.append(self._create_result_item(item, url))

        quality_order = {'4K': 0, '2160p': 0, '1080p': 1, '720p': 2, 'HD': 3, 'SD': 4}
        results.sort(key=lambda x: quality_order.get(x['quality'], 99))
        return results

    def _extract_player_url(self, item):
        try:
            link_part = item.get('link', '')
            if not link_part:
                return None

            # /download.aspx já é o link final — não tem página HTML para parsear
            if '/download.aspx' in link_part:
                return self._build_download_link(link_part)

            view_url = f"https://{self.base_domain}{link_part}"
            if 'a=view' not in view_url:
                sep = '&' if '?' in view_url else '?'
                view_url += f'{sep}a=view'

            headers = {
                'User-Agent':      USER_AGENT,
                'Accept':          'text/html,application/xhtml+xml',
                'Accept-Language': 'pt-BR,pt;q=0.9',
                'Referer':         f'https://{self.base_domain}/',
            }
            response = requests.get(view_url, headers=headers,
                                timeout=ScraperConfig.REQUEST_TIMEOUT)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            source_tag = soup.find('source', {'src': True})
            if source_tag:
                return source_tag['src']

            return self._build_download_link(link_part)

        except Exception as e:
            xbmc.log(f"{self.log_prefix} ❌ Erro ao extrair URL do player: {e}", xbmc.LOGERROR)
            return self._build_download_link(item.get('link'))

    def _build_download_link(self, link_part):
        if not link_part or not link_part.startswith('/'):
            return None
        try:
            path_part, query_string = link_part.split('?', 1)
            params      = parse_qs(query_string)
            file_id     = params.get('file', [None])[0]
            if not file_id:
                return None

            query_params = {'file': file_id}
            for param in ('expiry', 'mac'):
                val = params.get(param, [None])[0]
                if val:
                    query_params[param] = val

            return f"https://{self.download_domain}{path_part}?{urlencode(query_params)}"

        except Exception as e:
            xbmc.log(f"{self.log_prefix} ⚠️ Erro construindo link fallback: {e}", xbmc.LOGWARNING)
            return None

    def _create_result_item(self, file_data, download_url):
        file_name = file_data.get('name', '')
        quality   = guess_quality_from_name(file_name) or 'HD'

        fn_lower = file_name.lower()
        if any(x in fn_lower for x in ('dual', 'multi')):
            language = 'DUAL'
        elif any(x in fn_lower for x in ('dublado', 'dub ', 'pt-br')):
            language = 'PT-BR'
        elif any(x in fn_lower for x in ('legendado', 'leg', 'sub', 'eng')):
            language = 'LEG'
        else:
            language = 'PT-BR'
            

        return {
            'url':           download_url,
            'quality':       quality,
            'type':          'Direto',
            'title':         file_name,
            'release_title': file_name,
            'label':         f"{file_name} [{quality}]",
            'size':          format_size(file_data.get('size', 0)),
            'peers':         'N/A',
            'seeders':       'N/A',
            'provider':      'AnimeZey',
            'languages':     language,
        }


def scrape(provider_url, item_data, timeout=None):
    try:
        if timeout:
            ScraperConfig.REQUEST_TIMEOUT = timeout
        return AnimeZeyScraper(provider_url, item_data).scrape()
    except Exception as e:
        xbmc.log(f"[animezey.scrape] ❌ Erro: {e}", xbmc.LOGERROR)
        return []