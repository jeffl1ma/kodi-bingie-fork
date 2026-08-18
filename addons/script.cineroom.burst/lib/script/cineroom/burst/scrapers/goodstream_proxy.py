# -*- coding: utf-8 -*-
import json
import base64
import threading
import requests
import xbmc
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

_proxy_server = None
_proxy_lock   = threading.Lock()
_proxy_port   = 19876

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


class _ProxyHandler(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed      = urlparse(self.path)
        params      = parse_qs(parsed.query)
        target_url  = unquote(params.get('url',     [''])[0])
        cookies_b64 = unquote(params.get('cookies', [''])[0])

        if not target_url:
            self.send_error(400)
            return

        cookies = {}
        if cookies_b64:
            try:
                cookies = json.loads(base64.b64decode(cookies_b64).decode())
            except Exception:
                pass

        try:
            r = requests.get(
                target_url,
                headers={
                    'User-Agent': _UA,
                    'Referer':    'https://gscdn.cam/',
                    'Origin':     'https://gscdn.cam',
                },
                cookies=cookies,
                timeout=20,
                stream=True,
            )

            content_type = r.headers.get('content-type', '')
            is_m3u8 = (
                'mpegurl' in content_type.lower()
                or target_url.split('?')[0].endswith('.m3u8')
            )

            if is_m3u8:
                # Reescreve URLs dentro do m3u8 para passarem pelo proxy
                body = r.content.decode('utf-8', errors='replace')
                body = self._rewrite_m3u8(body, target_url, cookies_b64)
                data = body.encode('utf-8')

                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                # Segmento binário (.ts) — passa direto
                self.send_response(r.status_code)
                for k, v in r.headers.items():
                    if k.lower() in ('content-type', 'content-length'):
                        self.send_header(k, v)
                self.end_headers()
                for chunk in r.iter_content(chunk_size=65536):
                    self.wfile.write(chunk)

        except Exception as e:
            xbmc.log(f"[GSProxy] Erro: {e}", xbmc.LOGERROR)
            try:
                self.send_error(502)
            except Exception:
                pass

    def _rewrite_m3u8(self, content, base_url, cookies_b64):
        """Reescreve URLs relativas e absolutas no m3u8 para passarem pelo proxy."""
        from urllib.parse import urljoin, quote

        lines = content.splitlines()
        result = []

        for line in lines:
            stripped = line.strip()

            # Ignora linhas de diretiva que não são URLs
            if not stripped or stripped.startswith('#'):
                result.append(line)
                continue

            # Resolve URL relativa → absoluta
            if stripped.startswith('http'):
                abs_url = stripped
            else:
                abs_url = urljoin(base_url, stripped)

            # Substitui por URL do proxy
            proxy_url = (
                f"http://127.0.0.1:{_proxy_port}/proxy"
                f"?url={quote(abs_url, safe='')}"
                f"&cookies={quote(cookies_b64, safe='')}"
            )
            result.append(proxy_url)

        return '\n'.join(result)


def start_proxy():
    global _proxy_server
    with _proxy_lock:
        if _proxy_server is not None:
            return _proxy_port
        try:
            _proxy_server = HTTPServer(('127.0.0.1', _proxy_port), _ProxyHandler)
            t = threading.Thread(target=_proxy_server.serve_forever, daemon=True)
            t.start()
            xbmc.log(f"[GSProxy] Iniciado na porta {_proxy_port}", xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f"[GSProxy] Falha: {e}", xbmc.LOGERROR)
    return _proxy_port