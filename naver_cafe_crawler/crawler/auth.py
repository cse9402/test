"""로그인 상태 확인과 사용자 직접 로그인 지원. (ID/비밀번호 자동 입력 없음)"""
from __future__ import annotations

import shutil
import time
from dataclasses import asdict, dataclass
from urllib.parse import quote

from config import Settings
from crawler.browser import BrowserSession
from crawler.cafe_parser import is_join_required
from crawler.types import FetchResult
from utils.logger import get_logger

log = get_logger("auth")
LOGIN_URL = "https://nid.naver.com/nidlogin.login?mode=form&url={target}"


@dataclass
class LoginStatus:
    logged_in: bool
    cafe_member: str  # 'member' | 'not_member' | 'unknown'
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_membership(result: FetchResult) -> str:
    if is_join_required(result.html) or is_join_required(result.top_html):
        return "not_member"
    return "unknown"  # 가입 버튼이 없다는 사실만으로 회원 확정 불가 → 수집 시 글별 판정


def check_login_status(settings: Settings, browser: BrowserSession | None = None) -> LoginStatus:
    own = browser is None
    b = browser or BrowserSession(settings).__enter__()
    try:
        logged_in = b.is_logged_in()
        result = b.fetch(settings.cafe_url)
        member = evaluate_membership(result) if logged_in else "unknown"
        if not logged_in:
            msg = "로그인되어 있지 않습니다. 공개 게시글만 수집됩니다. '로그인' 기능으로 직접 로그인하세요."
        elif member == "not_member":
            msg = "로그인되어 있으나 카페 가입 버튼이 보입니다. 이 계정이 카페 회원인지 확인하세요."
        else:
            msg = "로그인 상태입니다. 게시글별 열람 권한은 수집 시 확인됩니다."
        return LoginStatus(logged_in, member, msg)
    finally:
        if own:
            b.close()


def interactive_login(settings: Settings, timeout_seconds: int = 300,
                      poll_seconds: float = 2.0) -> bool:
    """
    화면이 보이는 브라우저를 열고 사용자가 직접 로그인(2단계 인증·보안문자 포함)하도록 대기.
    로그인 쿠키가 생기면 성공. 브라우저 창을 닫거나 시간 초과 시 종료.
    """
    print("\n[안내] 브라우저 창에서 네이버에 직접 로그인하세요.")
    print("       - 아이디/비밀번호는 이 프로그램이 저장하거나 입력하지 않습니다.")
    print("       - 2단계 인증·보안문자도 직접 완료해 주세요.")
    print(f"       - 최대 {timeout_seconds}초 동안 기다립니다.\n")
    with BrowserSession(settings, headless=False) as b:
        assert b.page is not None
        if b.is_logged_in():
            print("이미 로그인되어 있습니다.")
            return True
        b.page.goto(LOGIN_URL.format(target=quote(settings.cafe_url, safe="")))
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if b.is_logged_in():
                    print("로그인이 확인되었습니다. 세션이 로컬 프로필에 저장됩니다.")
                    time.sleep(3)  # 리다이렉트 완료 대기
                    return True
                if b.page.is_closed():
                    break
            except Exception:  # 사용자가 창을 닫은 경우
                break
            time.sleep(poll_seconds)
    print("로그인이 확인되지 않았습니다.")
    return False


def clear_local_session(settings: Settings) -> bool:
    """로컬 브라우저 프로필(쿠키 포함) 삭제."""
    if settings.profile_dir.exists():
        shutil.rmtree(settings.profile_dir)
        return True
    return False
