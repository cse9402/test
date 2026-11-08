"""크롤러 공용 데이터 구조와 예외."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AccessStatus(str, Enum):
    OK = "ok"                          # 본문 열람 성공
    MEMBERS_ONLY = "members_only"      # 카페 멤버 전용
    LEVEL_RESTRICTED = "level_restricted"  # 등급 미달
    LOGIN_REQUIRED = "login_required"  # 로그인 필요
    NOT_FOUND = "not_found"            # 삭제/없음
    CAPTCHA = "captcha"                # 보안 확인 화면
    BLOCKED = "blocked"                # 차단/과다요청
    UNKNOWN_STRUCTURE = "unknown_structure"  # 구조 변경 의심
    FAILED = "failed"                  # 네트워크 등 실패

    @property
    def is_restricted(self) -> bool:
        return self in {AccessStatus.MEMBERS_ONLY, AccessStatus.LEVEL_RESTRICTED,
                        AccessStatus.LOGIN_REQUIRED}


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int | None
    html: str                # 콘텐츠 프레임(cafe_main 있으면 그 프레임) HTML
    top_html: str = ""       # 최상위 문서 HTML
    dialogs: list[str] = field(default_factory=list)  # alert/confirm 메시지
    frame_url: str = ""


@dataclass
class CafeInfo:
    cafe_name: str
    club_id: str | None
    title: str | None
    url: str


@dataclass
class Board:
    menu_id: int
    name: str
    url: str = ""


@dataclass
class ArticleSummary:
    article_id: int
    title: str
    url: str = ""
    author: str | None = None
    written_at: str | None = None   # ISO 형식
    view_count: int | None = None
    comment_count: int | None = None
    is_notice: bool = False


@dataclass
class Comment:
    comment_key: str
    author: str | None
    content: str
    written_at: str | None = None
    is_reply: bool = False


@dataclass
class ArticleDetail:
    title: str | None = None
    content_text: str | None = None
    content_html: str | None = None
    author: str | None = None
    written_at: str | None = None
    view_count: int | None = None
    comment_count: int | None = None
    board_name: str | None = None
    image_urls: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)


class CrawlerError(Exception):
    """크롤러 기본 예외."""


class TransientError(CrawlerError):
    """재시도 가능한 일시 오류(타임아웃, 네트워크)."""


class BlockedError(CrawlerError):
    """429/403 등 차단 의심 → 즉시 중단."""


class CaptchaDetectedError(CrawlerError):
    """보안 확인(CAPTCHA) 화면 → 사용자 개입 필요, 중단."""


class SessionExpiredError(CrawlerError):
    """로그인 세션 만료 → 재로그인 필요."""


class ProfileInUseError(CrawlerError):
    """브라우저 프로필을 다른 프로세스가 사용 중."""
