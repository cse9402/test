"""
Streamlit 대시보드.  실행: streamlit run app.py
브라우저 작업(로그인·수집)은 별도 프로세스(main.py)로 실행하여 화면이 멈추지 않도록 합니다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime

import pandas as pd
import streamlit as st

from config import BASE_DIR, cafe_name_from_url, load_settings
from crawler.collector import CrawlOptions
from database.repository import Repository
from utils.exporter import prepare_frame, to_csv_bytes, to_excel_bytes

STATUS_LABELS = {
    "ok": "수집 성공", "members_only": "멤버 전용(제한)", "level_restricted": "등급 제한",
    "login_required": "로그인 필요", "not_found": "삭제/없음", "failed": "실패",
    "unknown_structure": "구조 확인 필요", "captcha": "보안 확인", "blocked": "차단 의심",
}
JOB_LABELS = {"pending": "대기", "running": "수집 중", "completed": "완료", "stopped": "중지됨",
              "failed": "오류", "blocked": "차단 의심(중단)", "captcha": "보안 확인 필요(중단)",
              "session_expired": "세션 만료(재로그인 필요)"}

st.set_page_config(page_title="네이버 카페 게시글 수집기", page_icon="📚", layout="wide")


@st.cache_resource
def get_repo(db_path: str) -> Repository:
    return Repository(db_path)


def run_cli(args: list[str], cafe_url: str, timeout: int = 180) -> tuple[int, str]:
    cmd = [sys.executable, str(BASE_DIR / "main.py"), "--cafe-url", cafe_url, *args]
    proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def spawn_cli(args: list[str], cafe_url: str) -> subprocess.Popen:
    cmd = [sys.executable, str(BASE_DIR / "main.py"), "--cafe-url", cafe_url, *args]
    log_path = load_settings().log_dir / "subprocess.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")
    return subprocess.Popen(cmd, cwd=BASE_DIR, stdout=log_file, stderr=subprocess.STDOUT)


def extract_json(output: str) -> dict | None:
    for line in output.splitlines():
        if line.startswith("JSON:"):
            return json.loads(line[5:])
    return None


settings = load_settings()
settings.ensure_dirs()
repo = get_repo(str(settings.db_path))

st.title("📚 네이버 카페 게시글 수집기")
st.caption("본인 계정에 실제 열람 권한이 있는 게시글만 수집합니다. 접근이 거부된 글은 '접근 제한'으로만 기록됩니다.")

# ---------------- 사이드바 ----------------
with st.sidebar:
    st.header("⚙️ 기본 설정")
    cafe_url = st.text_input("대상 카페 URL", value=settings.cafe_url)
    try:
        cafe_name = cafe_name_from_url(cafe_url)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.write(f"카페 이름: `{cafe_name}`")
    st.write(f"요청 간격: {settings.delay_min:.0f}~{settings.delay_max:.0f}초 (동시 요청 1건)")
    st.write(f"DB: `{settings.db_path.name}`")
    stats = repo.article_stats(cafe_name)
    if stats:
        st.subheader("저장 현황")
        for k, v in stats.items():
            st.write(f"- {STATUS_LABELS.get(k, k)}: {v}건")

tab_login, tab_crawl, tab_result, tab_log = st.tabs(
    ["1️⃣ 로그인", "2️⃣ 수집", "3️⃣ 결과·내보내기", "📝 작업 기록"])

# ---------------- 1. 로그인 ----------------
with tab_login:
    st.subheader("네이버 로그인 상태")
    st.info("① '로그인 창 열기' → 열린 브라우저에서 직접 로그인(2단계 인증 포함) → 로그인 완료 후 창이 자동으로 닫힙니다.\n\n"
            "② '로그인 상태 확인'으로 결과를 확인하세요. 로그인 창이 열려 있는 동안에는 다른 작업을 실행할 수 없습니다.")
    c1, c2 = st.columns(2)
    if c1.button("🔐 로그인 창 열기", width="stretch"):
        spawn_cli(["login", "--timeout", "300"], cafe_url)
        st.success("브라우저 창이 열립니다. 5분 안에 로그인해 주세요.")
    if c2.button("🔎 로그인 상태 확인", width="stretch"):
        with st.spinner("브라우저로 확인 중..."):
            try:
                code, out = run_cli(["status", "--json"], cafe_url, timeout=120)
                data = extract_json(out)
            except subprocess.TimeoutExpired:
                data, out = None, "시간 초과"
        if data:
            st.session_state["login_status"] = data
        else:
            st.error("상태 확인 실패")
            st.code(out[-2000:])
    status = st.session_state.get("login_status")
    if status:
        (st.success if status["logged_in"] else st.warning)(status["message"])

# ---------------- 2. 수집 ----------------
with tab_crawl:
    st.subheader("게시판 선택")
    if st.button("📋 게시판 목록 불러오기"):
        with st.spinner("카페 메인 페이지 확인 중..."):
            try:
                code, out = run_cli(["boards", "--json"], cafe_url, timeout=180)
            except subprocess.TimeoutExpired:
                code, out = 1, "시간 초과"
        if code != 0:
            st.error("게시판 목록을 가져오지 못했습니다. 로그인 창이 열려 있지 않은지 확인하고, "
                     "계속 실패하면 'python main.py diagnose' 를 실행하세요.")
            st.code(out[-2000:])
    boards = repo.list_boards(cafe_name)
    board_options = {f"{b['name']} ({b['menu_id']})": b["menu_id"] for b in boards}
    selected = st.multiselect("수집할 게시판", list(board_options.keys()))
    menu_ids = [board_options[s] for s in selected]

    st.subheader("수집 조건")
    c1, c2, c3 = st.columns(3)
    start_page = c1.number_input("시작 페이지", 1, 1000, 1)
    end_page = c2.number_input("끝 페이지", 1, 1000, 3)
    max_articles = c3.number_input("최대 수집 건수", 1, 5000, settings.default_max_articles)
    c1, c2 = st.columns(2)
    keyword = c1.text_input("키워드 (비우면 전체)")
    scope = c2.selectbox("키워드 위치", ["title", "body", "both"],
                         format_func={"title": "제목", "body": "본문", "both": "제목 또는 본문"}.get)
    use_date = st.checkbox("작성일 범위 지정")
    date_from = date_to = None
    if use_date:
        c1, c2 = st.columns(2)
        date_from = c1.date_input("시작일", value=date.today().replace(day=1))
        date_to = c2.date_input("종료일", value=date.today())
    c1, c2, c3 = st.columns(3)
    only_new = c1.checkbox("신규 글만 (마지막 수집 이후)", value=False)
    include_comments = c2.checkbox("댓글 수집")
    save_html = c3.checkbox("본문 HTML 저장")
    with st.expander("고급 옵션"):
        urls_text = st.text_area("게시글 URL 직접 입력 (한 줄에 하나)")
        recheck = st.checkbox("이전에 접근 제한이었던 글 다시 확인")
        site_search = st.checkbox("카페 내부 검색 페이지 사용 (URL 구조 검증 후 사용)")
        download_media = st.checkbox("이미지 다운로드 (.env 의 MEDIA_DOWNLOAD_POLICY_CONFIRMED=true 필요)")

    active_job_id = st.session_state.get("active_job_id")
    active_job = repo.get_job(active_job_id) if active_job_id else None
    running = bool(active_job and active_job["status"] in ("pending", "running"))

    c1, c2, c3 = st.columns(3)
    if c1.button("▶️ 수집 시작", type="primary", disabled=running, width="stretch"):
        options = CrawlOptions(
            menu_ids=menu_ids,
            article_urls=[u.strip() for u in urls_text.splitlines() if u.strip()],
            start_page=int(start_page), end_page=int(end_page), keyword=keyword.strip(),
            keyword_scope=scope, use_site_search=site_search,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
            max_articles=int(max_articles), only_new=only_new,
            include_comments=include_comments, save_html=save_html,
            download_media=download_media, recheck_restricted=recheck)
        try:
            options.validate()
        except ValueError as exc:
            st.error(f"입력 오류: {exc}")
        else:
            job_id = repo.create_job(cafe_name, options.to_dict())
            spawn_cli(["crawl", "--job-id", str(job_id)], cafe_url)
            st.session_state["active_job_id"] = job_id
            st.rerun()
    if c2.button("⏹️ 중지", disabled=not running, width="stretch"):
        repo.request_stop(active_job_id)
        st.info("현재 게시글 처리 후 중지합니다.")
    resumable = bool(active_job and active_job["status"] in ("stopped", "session_expired",
                                                              "blocked", "captcha", "failed"))
    if c3.button("⏯️ 재개", disabled=not resumable, width="stretch"):
        spawn_cli(["crawl", "--resume", str(active_job_id)], cafe_url)
        time.sleep(1)
        st.rerun()

    if active_job:
        st.subheader(f"진행 상황 (작업 #{active_job['id']})")
        m = st.columns(5)
        m[0].metric("상태", JOB_LABELS.get(active_job["status"], active_job["status"]))
        m[1].metric("성공", active_job["success_count"] or 0)
        m[2].metric("접근 제한", active_job["restricted_count"] or 0)
        m[3].metric("실패", active_job["failed_count"] or 0)
        m[4].metric("건너뜀(중복 등)", active_job["skipped_count"] or 0)
        processed = (active_job["success_count"] or 0) + (active_job["restricted_count"] or 0) \
            + (active_job["failed_count"] or 0)
        st.progress(min(1.0, processed / max(1, active_job["params"].get("max_articles", 1))))
        if active_job.get("current_menu_id"):
            st.caption(f"현재 위치: 게시판 {active_job['current_menu_id']} / {active_job['current_page']}페이지")
        if active_job.get("message"):
            st.write(active_job["message"])
        for log_row in repo.list_logs(active_job["id"], limit=8):
            st.text(f"{log_row['created_at']} [{log_row['level']}] {log_row['message']}")
        if running:
            time.sleep(2)
            st.rerun()

# ---------------- 3. 결과 ----------------
with tab_result:
    st.subheader("수집 결과 검색")
    c1, c2, c3 = st.columns(3)
    q = c1.text_input("검색어 (제목/본문)", key="result_q")
    board_filter = c2.multiselect("게시판", list(board_options.keys()), key="result_boards")
    status_filter = c3.multiselect("접근 상태", list(STATUS_LABELS.keys()), default=["ok"],
                                   format_func=STATUS_LABELS.get)
    c1, c2, c3 = st.columns(3)
    r_from = c1.date_input("작성일 시작", value=None, key="r_from")
    r_to = c2.date_input("작성일 종료", value=None, key="r_to")
    include_html_export = c3.checkbox("내보내기에 본문 HTML 포함")
    rows = repo.query_articles(
        cafe_name=cafe_name, keyword=q.strip(),
        menu_ids=[board_options[b] for b in board_filter] or None,
        statuses=status_filter or None,
        date_from=r_from.isoformat() if r_from else None,
        date_to=r_to.isoformat() if r_to else None)
    st.write(f"검색 결과: **{len(rows)}건**")
    if rows:
        df = pd.DataFrame(rows)
        preview = df[["article_id", "board_name", "title", "author", "written_at", "view_count",
                      "comment_count", "access_status", "url"]].copy()
        preview["access_status"] = preview["access_status"].map(lambda s: STATUS_LABELS.get(s, s))
        st.dataframe(preview, width="stretch", hide_index=True)
        pick = st.selectbox("본문 미리보기", df["article_id"].tolist(),
                            format_func=lambda a: f"{a} - {df.loc[df.article_id == a, 'title'].iloc[0]}")
        row = df[df.article_id == pick].iloc[0]
        st.markdown(f"**{row['title'] or '(제목 없음)'}** · {row['author'] or ''} · {row['written_at'] or ''}")
        st.text_area("본문", row["content_text"] or "(본문 없음 / 접근 제한)", height=250)
        comments = repo.query_comments(cafe_name, int(pick))
        if comments:
            st.write(f"댓글 {len(comments)}건")
            st.dataframe(pd.DataFrame(comments)[["author", "content", "written_at"]],
                         hide_index=True, width="stretch")
        export_df = prepare_frame(df, include_html=include_html_export)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ CSV 내보내기", to_csv_bytes(export_df),
                           file_name=f"{cafe_name}_{stamp}.csv", mime="text/csv",
                           width="stretch")
        c2.download_button("⬇️ Excel 내보내기", to_excel_bytes(export_df),
                           file_name=f"{cafe_name}_{stamp}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

# ---------------- 기록 ----------------
with tab_log:
    jobs = repo.list_jobs(30)
    if jobs:
        jdf = pd.DataFrame(jobs)[["id", "status", "success_count", "restricted_count",
                                  "failed_count", "skipped_count", "started_at", "finished_at",
                                  "message"]]
        jdf["status"] = jdf["status"].map(lambda s: JOB_LABELS.get(s, s))
        st.dataframe(jdf, hide_index=True, width="stretch")
        pick_job = st.selectbox("작업 선택(재개·진행 확인용)", [j["id"] for j in jobs])
        if st.button("이 작업을 진행 화면에 표시"):
            st.session_state["active_job_id"] = pick_job
            st.rerun()
    logs = repo.list_logs(limit=100)
    if logs:
        st.dataframe(pd.DataFrame(logs)[["created_at", "job_id", "level", "message"]],
                     hide_index=True, width="stretch")
