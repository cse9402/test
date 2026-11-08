"""CSV / Excel 내보내기. 인증 정보는 DB에 저장하지 않으므로 포함될 수 없음."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

EXCEL_CELL_LIMIT = 32_000
DEFAULT_EXCLUDE = {"content_html"}

COLUMN_LABELS = {
    "cafe_name": "카페", "club_id": "카페ID", "menu_id": "게시판ID", "board_name": "게시판명",
    "article_id": "게시글ID", "url": "URL", "title": "제목", "content_text": "본문",
    "content_html": "본문HTML", "author": "작성자", "written_at": "작성일", "view_count": "조회수",
    "comment_count": "댓글수", "image_urls": "이미지URL", "attachments": "첨부파일",
    "access_status": "접근상태", "error_message": "오류", "collected_at": "수집시각",
    "updated_at": "갱신시각", "job_id": "작업ID",
}


def _neutralize_formula(value):
    """CSV/Excel 수식 주입 방지: = + - @ 로 시작하는 문자열 앞에 ' 추가."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def prepare_frame(rows: list[dict] | pd.DataFrame, include_html: bool = False,
                  korean_headers: bool = True) -> pd.DataFrame:
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    drop = [c for c in df.columns if c in DEFAULT_EXCLUDE and not include_html]
    drop += [c for c in df.columns if c == "id"]
    df = df.drop(columns=drop)
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].map(_neutralize_formula)
    if korean_headers:
        df = df.rename(columns=COLUMN_LABELS)
    return df


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")  # Excel 한글 깨짐 방지


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].map(
                lambda v: v[:EXCEL_CELL_LIMIT] if isinstance(v, str) else v)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="articles")
    return buf.getvalue()


def export_file(rows: list[dict] | pd.DataFrame, path: Path, include_html: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = prepare_frame(rows, include_html=include_html)
    if path.suffix.lower() == ".xlsx":
        path.write_bytes(to_excel_bytes(df))
    elif path.suffix.lower() == ".csv":
        path.write_bytes(to_csv_bytes(df))
    else:
        raise ValueError("지원 형식: .csv, .xlsx")
    return path
