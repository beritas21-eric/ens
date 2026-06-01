#!/usr/bin/env python3
"""
RabbitMQ Monitor - 통합 웹 서버
================================
rabbitmq-monitor.html 을 서빙하고 RabbitMQ Management API 를 프록시합니다.
Python 3 표준 라이브러리만 사용 (pip install 불필요)

[실행]
    python rabbitmq-server.py

[접속]
    http://localhost:8080

[파일 구조]
    같은 폴더 안에 rabbitmq-monitor.html 이 있어야 합니다.
"""

import ssl
import urllib.request
import urllib.error
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── 설정 ──────────────────────────────────────────────────────────────────────
PORT      = 8080
HTML_FILE = Path(__file__).parent / 'rabbitmq-monitor.html'

# SSL 인증서 검증 무시 (자체 서명 인증서 환경 대응)
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode    = ssl.CERT_NONE


# ── 요청 핸들러 ───────────────────────────────────────────────────────────────
class MonitorHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        try:
            parts  = args[0].split('"')
            method = parts[1].split()[0] if len(parts) > 1 else '?'
            path   = parts[1].split()[1] if len(parts) > 1 else '?'
            status = args[1]
            prefix = '[PROXY]' if path.startswith('/api/') else '[HTTP] '
            print(f'  {prefix} {method:6s} {path:<40s} {status}')
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        base = self.path.split('?')[0]
        if base in ('/', '/index.html', '/rabbitmq-monitor.html'):
            self._serve_html()
        elif self.path.startswith('/api/'):
            self._proxy_to_rabbitmq()
        else:
            self.send_response(404)
            self.end_headers()

    # ── HTML 파일 서빙 ────────────────────────────────────────────────────────
    def _serve_html(self):
        if not HTML_FILE.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(
                f'Not found: {HTML_FILE}'.encode('utf-8'))
            print(f'\n  ⚠️  {HTML_FILE} 파일이 없습니다.\n')
            return

        content = HTML_FILE.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',   'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control',  'no-cache')
        self.end_headers()
        self.wfile.write(content)

    # ── RabbitMQ API 프록시 ───────────────────────────────────────────────────
    def _proxy_to_rabbitmq(self):
        rmq_url = self.headers.get('X-RabbitMQ-URL', '').rstrip('/')
        if not rmq_url:
            self.send_response(400)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(b'X-RabbitMQ-URL header missing')
            return

        target = rmq_url + self.path
        auth   = self.headers.get('Authorization', '')

        req = urllib.request.Request(
            target,
            headers={'Authorization': auth, 'Accept': 'application/json'},
        )

        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as r:
                body   = r.read()
                status = r.status
                ct     = r.headers.get('Content-Type', 'application/json')
        except urllib.error.HTTPError as e:
            body, status, ct = e.read(), e.code, 'application/json'
        except Exception as e:
            body, status, ct = str(e).encode(), 502, 'text/plain'

        self.send_response(status)
        self.send_header('Content-Type',   ct)
        self.send_header('Content-Length', str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Authorization, Content-Type, X-RabbitMQ-URL')


# ── 진입점 ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print()
    print('=' * 58)
    print('  🐇  RabbitMQ Monitor 서버')
    print('=' * 58)
    print(f'  주소   : http://localhost:{PORT}')
    print(f'  HTML   : {HTML_FILE}')
    print(f'  Python : {sys.version.split()[0]}')
    print('=' * 58)

    if not HTML_FILE.exists():
        print(f'\n  ⚠️  {HTML_FILE.name} 파일이 없습니다. 서버는 시작되나 404 반환.\n')

    try:
        server = HTTPServer(('localhost', PORT), MonitorHandler)
        print(f'\n  서버 실행 중 ... (종료: Ctrl+C)\n')
        server.serve_forever()
    except OSError as e:
        if getattr(e, 'errno', 0) in (98, 10048):
            print(f'\n  ❌ 포트 {PORT} 이미 사용 중. start-rabbitmq-monitor.bat 으로 실행하세요.\n')
        else:
            print(f'\n  ❌ 서버 시작 실패: {e}\n')
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n\n  서버를 종료합니다.\n')
        server.server_close()
