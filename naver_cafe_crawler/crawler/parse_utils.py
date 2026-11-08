"""파서 공용 유틸리티."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup, Tag


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("​", "").replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def select_first(root: Tag, selectors: list[str]) -> Tag | None:
    for sel in selectors:
        try:
            found = root.select_one(sel)
        except Exception:  # 잘못된 선택자 방어
            continue
        if found is not None:
            return found
    return None


def select_text(root: Tag, selectors: list[str]) -> str | None:
    el = select_first(root, selectors)
    if el is None:
        return None
    if el.name == "meta":
        return clean_text(el.get("content")) or None
    return clean_text(el.get_text(" ")) or None


def parse_int(text: str | None) -> int | None:
    """'조회 1,234' / '1.2만' / '[3]' -> 정수"""
    if not text:
        return None
    t = text.replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*만", t)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"\d+", t)
    return int(m.group(0)) if m else None


def parse_naver_datetime(text: str | None, now: datetime | None = None) -> str | None:
    """
    네이버 카페 날짜 표기 → ISO 문자열.
    지원: '2024.05.01. 13:45', '2024.05.01.', '24.05.01', '13:45'(오늘), 'N분 전', 'N시간 전', '어제'
    """
    if not text:
        return None
    now = now or datetime.now()
    t = text.strip()
    m = re.search(r"(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?\s*(?:(\d{1,2}):(\d{2}))?", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = (int(m.group(4)), int(m.group(5))) if m.group(4) else (0, 0)
        try:
            dt = datetime(y, mo, d, hh, mm)
        except ValueError:
            return None
        return dt.isoformat(timespec="minutes") if m.group(4) else dt.date().isoformat()
    m = re.search(r"\b(\d{2})\.(\d{1,2})\.(\d{1,2})\.?", t)
    if m:
        try:
            return datetime(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if m:
        return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0,
                           microsecond=0).isoformat(timespec="minutes")
    m = re.search(r"(\d+)\s*분\s*전", t)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).isoformat(timespec="minutes")
    m = re.search(r"(\d+)\s*시간\s*전", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat(timespec="minutes")
    if "어제" in t:
        return (now - timedelta(days=1)).date().isoformat()
    return None


def first_regex(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text or "")
        if m:
            return m.group(1)
    return None
