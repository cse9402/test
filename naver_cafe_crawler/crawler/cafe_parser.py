"""카페 메인 페이지 파서: 카페 ID, 카페명, 게시판 목록."""
from __future__ import annotations

from crawler import selectors as S
from crawler.parse_utils import clean_text, first_regex, make_soup, select_text
from crawler.types import Board, CafeInfo


def parse_club_id(html: str) -> str | None:
    return first_regex(S.CLUB_ID_PATTERNS, html)


def parse_cafe_info(html: str, cafe_name: str, url: str, extra_html: str = "") -> CafeInfo:
    soup = make_soup(html)
    title = select_text(soup, S.CAFE_TITLE_SELECTORS)
    if title:
        title = title.replace(": 네이버 카페", "").strip()
    club_id = parse_club_id(html) or parse_club_id(extra_html)
    return CafeInfo(cafe_name=cafe_name, club_id=club_id, title=title, url=url)


def parse_board_list(html: str) -> list[Board]:
    """href 에 menuid 가 있는 링크를 게시판으로 간주. menu_id 기준 중복 제거."""
    soup = make_soup(html)
    boards: dict[int, Board] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        menu_id = first_regex(S.MENU_ID_PATTERNS, href)
        if menu_id is None:
            continue
        name = clean_text(a.get_text(" "))
        if name in S.MENU_NAME_EXCLUDE or len(name) > 60:
            continue
        mid = int(menu_id)
        if mid not in boards:
            boards[mid] = Board(menu_id=mid, name=name, url=href)
    return sorted(boards.values(), key=lambda b: b.menu_id)


def is_join_required(html: str) -> bool:
    """페이지에 '카페 가입하기' 버튼이 보이면 비회원으로 추정(가설)."""
    soup = make_soup(html)
    for el in soup.find_all(["a", "button"]):
        if clean_text(el.get_text(" ")) in S.JOIN_BUTTON_MARKERS:
            return True
    return False
