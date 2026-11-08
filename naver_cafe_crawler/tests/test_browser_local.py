"""
Playwright 실제 브라우저로 '로컬 테스트 페이지'를 열어 iframe(cafe_main) 처리와
알림창(alert) 감지 로직을 검증합니다. 네이버에 접속하지 않습니다.
Playwright/Chromium 이 없으면 자동으로 건너뜁니다.
"""
import threading
from dataclasses import replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright")

PAGES = {
    "/top.html": "<html><body><h1>top</h1><iframe id='cafe_main' name='cafe_main' "
                 "src='/inner.html'></iframe></body></html>",
    "/inner.html": "<html><body><h3 class='title_text'>프레임 제목</h3>"
                   "<div class='se-main-container'>프레임 본문</div></body></html>",
    "/alert.html": "<html><body><script>alert('등급이 되시면 읽기가 가능한 게시판입니다.')</script>"
                   "</body></html>",
}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write((body or "").encode("utf-8"))

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_iframe_and_dialog(settings, server):
    from crawler.article_parser import detect_access_status, parse_article
    from crawler.browser import BrowserSession
    from crawler.types import AccessStatus
    s = replace(settings, headless=True, page_timeout_ms=15000)
    try:
        session = BrowserSession(s).__enter__()
    except Exception as exc:  # 브라우저 미설치 환경
        pytest.skip(f"브라우저 실행 불가: {exc}")
    try:
        res = session.fetch(f"{server}/top.html", ["h3.title_text"])
        assert res.frame_url.endswith("/inner.html")
        assert detect_access_status(res) == AccessStatus.OK
        assert parse_article(res.html).title == "프레임 제목"
        assert not session.is_logged_in()
        res2 = session.fetch(f"{server}/alert.html")
        assert res2.dialogs and "등급" in res2.dialogs[0]
        assert detect_access_status(res2) == AccessStatus.LEVEL_RESTRICTED
        assert (s.profile_dir.stat().st_mode & 0o777) == 0o700
    finally:
        session.close()
