#!/usr/bin/env python3
"""
RabbitMQ Management CORS Proxy
================================
Python 3 표준 라이브러리만 사용 (pip install 불필요)

[실행 방법]
  python rabbitmq-proxy.py

[모니터 HTML 설정]
  프록시 URL 입력란에: http://localhost:15673

[종료]
  Ctrl+C
"""
import ssl
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

RABBITMQ_URL = "https://esdr.skax-sv-ai.com:15672"   # ← RabbitMQ Management URL
PROXY_PORT   = 15673          # ← 로컬 프록시 포트 (변경 가능)

# SSL 인증서 검증 무시 (자체 서명 인증서 환경)
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode    = ssl.CERT_NONE


class CORSProxyHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # 요청 로그 간소화
        print(f"  [{self.command}] {self.path}  →  {RABBITMQ_URL}{self.path}")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-RabbitMQ-URL")
        self.send_header("Access-Control-Max-Age",       "86400")

    def do_OPTIONS(self):
        """CORS preflight 처리"""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """실제 RabbitMQ API 요청 프록시"""
        target = RABBITMQ_URL + self.path
        auth   = self.headers.get("Authorization", "")

        req = urllib.request.Request(
            target,
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                body        = resp.read()
                status      = resp.status
                content_type = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            body         = e.read()
            status       = e.code
            content_type = "application/json"
        except Exception as e:
            body         = str(e).encode()
            status       = 502
            content_type = "text/plain"

        self.send_response(status)
        self.send_header("Content-Type",   content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("localhost", PROXY_PORT), CORSProxyHandler)
    print("=" * 55)
    print(f"  🐇 RabbitMQ CORS Proxy 시작")
    print(f"  로컬 주소 : http://localhost:{PROXY_PORT}")
    print(f"  대상 서버 : {RABBITMQ_URL}")
    print(f"  모니터 HTML 프록시 URL: http://localhost:{PROXY_PORT}")
    print("=" * 55)
    print("  종료하려면 Ctrl+C 를 누르세요")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  프록시 서버를 종료합니다.")
        server.server_close()
