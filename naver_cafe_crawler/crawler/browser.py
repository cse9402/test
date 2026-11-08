"""Playwright persistent context 기반 브라우저 세션 (사용자 승인 로컬 프로필 사용)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Frame, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from config import Settings
from crawler import selectors as S
from crawler.types import FetchResult, ProfileInUseError, TransientError
from utils.logger import get_logger

log = get_logger("browser")


def secure_dir(path: Path) -> None:
    """프로필(쿠키 저장) 폴더 생성 및 소유자 전용 권한(700) 설정."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, stat.S_IRWXU)


class BrowserSession:
    """
    with BrowserSession(settings) as b:
        result = b.fetch(url)
    - 쿠키/세션은 settings.profile_dir 에만 저장됩니다.
    - 비밀번호 입력, CAPTCHA 해결, 지문 위조 기능은 없습니다.
    """

    def __init__(self, settings: Settings, headless: bool | None = None):
        self.settings = settings
        self.headless = settings.headless if headless is None else headless
        self._pw = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._dialogs: list[str] = []

    # ---------- lifecycle ----------
    def __enter__(self) -> "BrowserSession":
        secure_dir(self.settings.profile_dir)
        self._pw = sync_playwright().start()
        kwargs = dict(user_data_dir=str(self.settings.profile_dir), headless=self.headless,
                      locale="ko-KR", viewport={"width": 1400, "height": 900})
        if self.settings.browser_channel:
            kwargs["channel"] = self.settings.browser_channel
        if self.settings.browser_executable_path:
            kwargs["executable_path"] = self.settings.browser_executable_path
        try:
            self.context = self._pw.chromium.launch_persistent_context(**kwargs)
        except PlaywrightError as exc:
            self._pw.stop()
            msg = str(exc)
            if "ProcessSingleton" in msg or "SingletonLock" in msg or "already in use" in msg:
                raise ProfileInUseError(
                    "브라우저 프로필을 다른 창(로그인 창 또는 다른 수집 작업)이 사용 중입니다. "
                    "열린 크롤러 브라우저 창을 닫은 뒤 다시 시도하세요.") from exc
            raise
        self.context.set_default_timeout(self.settings.page_timeout_ms)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("dialog", self._on_dialog)
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
        finally:
            if self._pw:
                self._pw.stop()
            self.context = self._pw = self.page = None

    # ---------- helpers ----------
    def _on_dialog(self, dialog) -> None:
        # 접근 제한 안내가 alert 로 표시되는 경우가 있어 메시지만 기록하고 닫음
        self._dialogs.append(dialog.message)
        log.info("알림창 감지: %s", dialog.message[:200])
        try:
            dialog.dismiss()
        except PlaywrightError:
            pass

    def _content_frame(self) -> Frame:
        assert self.page is not None
        for name in S.CONTENT_FRAME_NAMES:
            try:
                self.page.wait_for_selector(f"iframe#{name}, iframe[name='{name}']", timeout=4000)
            except PlaywrightTimeout:
                continue
            frame = self.page.frame(name=name)
            if frame is not None:
                try:
                    frame.wait_for_load_state("domcontentloaded", timeout=10000)
                except PlaywrightTimeout:
                    pass
                return frame
        return self.page.main_frame

    def cookie_names(self) -> set[str]:
        """쿠키 '이름'만 반환 (값은 다루지 않음)."""
        assert self.context is not None
        return {c["name"] for c in self.context.cookies(["https://www.naver.com",
                                                          "https://cafe.naver.com"])}

    def is_logged_in(self) -> bool:
        return all(n in self.cookie_names() for n in S.LOGIN_COOKIE_NAMES)

    # ---------- main API ----------
    def fetch(self, url: str, wait_selectors: list[str] | None = None) -> FetchResult:
        assert self.page is not None
        self._dialogs.clear()
        try:
            response = self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout as exc:
            raise TransientError(f"페이지 로딩 시간 초과: {url}") from exc
        except PlaywrightError as exc:
            raise TransientError(f"페이지 요청 실패: {exc}") from exc
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeout:
            pass  # 일부 페이지는 지속 요청이 있어 networkidle 미도달 가능
        frame = self._content_frame()
        if wait_selectors:
            try:
                frame.wait_for_selector(", ".join(wait_selectors), timeout=8000)
            except (PlaywrightTimeout, PlaywrightError):
                pass  # 접근 제한 페이지 등은 요소가 없을 수 있음 → 판정은 파서에서
        try:
            top_html = self.page.content()
            html = frame.content() if frame != self.page.main_frame else top_html
        except PlaywrightError as exc:
            raise TransientError(f"페이지 내용 읽기 실패: {exc}") from exc
        return FetchResult(url=url, final_url=self.page.url,
                           status=response.status if response else None,
                           html=html, top_html=top_html, dialogs=list(self._dialogs),
                           frame_url=frame.url)

    def download(self, url: str, dest: Path) -> Path:
        """현재 계정 권한으로 브라우저가 볼 수 있는 리소스만 저장 (명시적 옵션일 때만 호출)."""
        assert self.context is not None
        resp = self.context.request.get(url, headers={"Referer": "https://cafe.naver.com/"})
        if not resp.ok:
            raise TransientError(f"다운로드 실패 HTTP {resp.status}: {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.body())
        return dest

    def screenshot(self, path: Path) -> None:
        assert self.page is not None
        self.page.screenshot(path=str(path), full_page=True)
