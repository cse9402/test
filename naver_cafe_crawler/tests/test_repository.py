"""저장소·내보내기 테스트 (시나리오 7·9·10)."""
import pandas as pd

from crawler.types import Board, CafeInfo, Comment
from utils.exporter import export_file, prepare_frame
from utils.logger import mask_sensitive


def _rec(aid, status="ok", **kw):
    base = dict(cafe_name="testcafe", club_id="1", menu_id=5, board_name="자유", article_id=aid,
                url=f"https://cafe.naver.com/testcafe/{aid}", title=f"제목{aid}",
                content_text=f"본문{aid}", author="작성자", written_at="2024-05-01T10:00",
                view_count=1, comment_count=0, image_urls=["https://img/1.jpg"], attachments=[],
                access_status=status)
    base.update(kw)
    return base


def test_cafe_and_boards(repo):
    repo.upsert_cafe(CafeInfo("testcafe", "1", "카페", "https://cafe.naver.com/testcafe"))
    repo.upsert_cafe(CafeInfo("testcafe", None, None, "https://cafe.naver.com/testcafe"))
    assert repo.get_cafe("testcafe")["club_id"] == "1"  # None 으로 덮어쓰지 않음
    repo.upsert_boards("testcafe", [Board(5, "자유"), Board(1, "공지")])
    repo.upsert_boards("testcafe", [Board(5, "자유게시판")])
    assert [(b["menu_id"], b["name"]) for b in repo.list_boards("testcafe")] == [
        (1, "공지"), (5, "자유게시판")]


def test_duplicate_article_upsert(repo):  # 시나리오 7
    assert repo.save_article(_rec(10)) == "inserted"
    assert repo.save_article(_rec(10, title="수정된 제목")) == "updated"
    rows = repo.query_articles("testcafe")
    assert len(rows) == 1 and rows[0]["title"] == "수정된 제목"


def test_ok_article_not_overwritten_by_restricted(repo):
    repo.save_article(_rec(11))
    assert repo.save_article(_rec(11, status="level_restricted", title=None,
                                  content_text=None)) == "kept"
    row = repo.query_articles("testcafe")[0]
    assert row["access_status"] == "ok" and row["content_text"] == "본문11"
    assert "level_restricted" in row["error_message"]


def test_restricted_then_ok_updates(repo):
    repo.save_article(_rec(12, status="members_only", title=None, content_text=None))
    repo.save_article(_rec(12))
    assert repo.get_article_status("testcafe", 12) == "ok"


def test_query_filters_and_max_id(repo):
    repo.save_article(_rec(1, written_at="2024-01-01T10:00", title="텐트 후기"))
    repo.save_article(_rec(2, written_at="2024-03-01", menu_id=6, title="버너"))
    repo.save_article(_rec(3, status="members_only", written_at=None))
    assert repo.max_article_id("testcafe", 5) == 3
    assert repo.max_article_id("testcafe", 6) == 2
    assert [r["article_id"] for r in repo.query_articles("testcafe", keyword="텐트")] == [1]
    assert [r["article_id"] for r in repo.query_articles("testcafe", statuses=["ok"],
                                                         date_from="2024-02-01",
                                                         date_to="2024-03-01")] == [2]
    assert repo.article_stats("testcafe") == {"ok": 2, "members_only": 1}


def test_comments_dedupe(repo):
    cs = [Comment("c-1", "a", "첫 댓글"), Comment("c-2", "b", "둘째", is_reply=True)]
    repo.save_comments("testcafe", 10, cs)
    repo.save_comments("testcafe", 10, [Comment("c-1", "a", "수정 댓글")])
    rows = repo.query_comments("testcafe", 10)
    assert [(r["comment_key"], r["content"]) for r in rows] == [("c-1", "수정 댓글"), ("c-2", "둘째")]


def test_jobs_and_logs(repo):
    jid = repo.create_job("testcafe", {"menu_ids": [5]})
    repo.update_job(jid, status="running", success_count=3, bogus="x")
    repo.request_stop(jid)
    job = repo.get_job(jid)
    assert job["status"] == "running" and job["success_count"] == 3
    assert job["params"] == {"menu_ids": [5]} and repo.is_stop_requested(jid)
    repo.add_log(jid, "INFO", "hello")
    assert repo.list_logs(jid)[0]["message"] == "hello"


def test_export_csv_and_excel(repo, tmp_path):  # 시나리오 10
    repo.save_article(_rec(1, title="=HYPERLINK(\"x\")", content_html="<p>x</p>"))
    rows = repo.query_articles("testcafe")
    csv_path = export_file(rows, tmp_path / "out.csv")
    xlsx_path = export_file(rows, tmp_path / "out.xlsx", include_html=True)
    df_csv = pd.read_csv(csv_path, encoding="utf-8-sig")
    assert df_csv.loc[0, "제목"].startswith("'=")  # 수식 주입 방지
    assert "본문HTML" not in df_csv.columns
    df_x = pd.read_excel(xlsx_path)
    assert df_x.loc[0, "게시글ID"] == 1 and "본문HTML" in df_x.columns


def test_export_frame_has_no_secret_columns():
    df = prepare_frame([{"article_id": 1, "title": "t", "content_html": "<p>"}])
    assert list(df.columns) == ["게시글ID", "제목"]


def test_log_masking():
    s = mask_sensitive("Cookie: NID_AUT=abc123; NID_SES=zzz password=hunter2")
    assert "abc123" not in s and "zzz" not in s and "hunter2" not in s
