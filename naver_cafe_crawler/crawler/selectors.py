"""
사이트 구조 의존 요소(선택자·문구) 모음.

※ 아래 값은 네이버 카페의 과거·일반적 구조에 근거한 '구현 가설'입니다.
  실제 사이트에서 검증되지 않았으므로 `python main.py diagnose` 결과를 보고
  이 파일만 수정하면 되도록 분리했습니다. 각 항목은 여러 후보를 순서대로 시도합니다.
"""

# 카페 콘텐츠 iframe 이름/ID (구형 레이아웃)
CONTENT_FRAME_NAMES = ["cafe_main"]

# ---- 카페 메인 ----
CLUB_ID_PATTERNS = [
    r"g_sClubId\s*=\s*['\"]?(\d+)",
    r"search\.clubid=(\d+)",
    r"clubid=(\d+)",
    r"[\"']cafeId[\"']\s*:\s*[\"']?(\d+)",
    r"/cafes/(\d+)",
]
CAFE_TITLE_SELECTORS = ["meta[property='og:title']", "h1.d-none", "title"]
# 게시판 링크 href 에서 menu id 추출
MENU_ID_PATTERNS = [r"search\.menuid=(\d+)", r"menuid=(\d+)", r"/menus/(\d+)"]
# 게시판 링크로 간주하지 않을 텍스트
MENU_NAME_EXCLUDE = {"", "더보기", "전체보기 더보기"}

# ---- 게시글 목록 ----
ARTICLE_ID_PATTERNS = [r"articleid=(\d+)", r"/articles/(\d+)"]
# 목록의 행(row) 후보
LIST_ROW_TAGS = ["tr", "li"]
ROW_TITLE_SELECTORS = ["a.article", "a.board-list .inner_list a", ".article_title", "a.title"]
ROW_AUTHOR_SELECTORS = [".p-nick a", ".p-nick", ".nickname", ".nick", "td.td_name", ".td_name"]
ROW_DATE_SELECTORS = ["td.td_date", ".td_date", ".date", "span.date"]
ROW_VIEW_SELECTORS = ["td.td_view", ".td_view", ".view_count", ".count"]
ROW_COMMENT_SELECTORS = ["a.cmt", ".cmt", ".comment_count", ".num_reply"]
ROW_NOTICE_HINTS = ["board-notice", "type_notice", "notice", "td_notice"]

# ---- 게시글 상세 ----
DETAIL_TITLE_SELECTORS = [".title_text", "h3.title_text", ".ArticleTitle .title_text",
                          ".tit-box .b", "h3.title"]
DETAIL_CONTENT_SELECTORS = [".se-main-container", ".ContentRenderer", "#tbody",
                            ".article_viewer", ".ArticleContentBox .article_container"]
DETAIL_AUTHOR_SELECTORS = [".nickname", ".nick_box .nickname", ".profile_info .nick", ".p-nick"]
DETAIL_DATE_SELECTORS = [".article_info .date", ".date", ".m-tcol-c.date"]
DETAIL_VIEW_SELECTORS = [".article_info .count", ".count"]
DETAIL_COMMENT_COUNT_SELECTORS = [".button_comment .num", ".comment_info .num", ".CommentBox .num"]
DETAIL_BOARD_NAME_SELECTORS = [".link_board", ".ArticleTitle .link_board"]
DETAIL_IMAGE_SELECTORS = [".se-main-container img", ".ContentRenderer img", "#tbody img",
                          ".article_viewer img"]
DETAIL_ATTACHMENT_SELECTORS = [".AttachFileListItem", ".attach_file li", ".file_list li",
                               "a[href*='download']"]
# 상세 페이지 로딩 대기 선택자
DETAIL_WAIT_SELECTORS = DETAIL_TITLE_SELECTORS[:2] + DETAIL_CONTENT_SELECTORS[:2]
LIST_WAIT_SELECTORS = ["a.article", "a[href*='articleid=']", "a[href*='/articles/']"]

# ---- 댓글 ----
COMMENT_ITEM_SELECTORS = ["ul.comment_list li.CommentItem", ".comment_list > li", "li.CommentItem"]
COMMENT_AUTHOR_SELECTORS = [".comment_nickname", ".comment_nick_info .nickname", ".nickname"]
COMMENT_TEXT_SELECTORS = [".text_comment", ".comment_text_view", ".comment_text"]
COMMENT_DATE_SELECTORS = [".comment_info_date", ".date"]
COMMENT_REPLY_HINTS = ["CommentItem--reply", "reply"]

# ---- 접근 상태 판정 문구 (본문 요소가 없을 때만 검사) ----
CAPTCHA_MARKERS = ["자동입력 방지", "자동 입력 방지", "captcha", "보안 절차", "보안문자",
                   "비정상적인 접근", "비정상적인 활동"]
CAPTCHA_SELECTORS = ["#captcha", "img#captchaimg", "iframe[src*='captcha']", "div.captcha"]
LEVEL_MARKERS = ["등급이 되시면", "등급 이상", "등급부터", "회원등급", "멤버등급"]
MEMBERS_ONLY_MARKERS = ["멤버만", "카페 멤버", "카페에 가입", "가입 후", "회원만"]
LOGIN_MARKERS = ["로그인이 필요", "로그인 후", "로그인해 주세요", "로그인 하시면"]
NOT_FOUND_MARKERS = ["삭제되었거나", "존재하지 않는 게시글", "삭제된 게시글", "없는 게시글"]
LOGIN_URL_HINTS = ["nid.naver.com/nidlogin", "nid.naver.com/login"]

# ---- 카페 가입 여부 ----
JOIN_BUTTON_MARKERS = ["카페 가입하기", "가입하기"]

# 네이버 로그인 쿠키 이름 (로그인 여부 판단용, 값은 절대 기록하지 않음)
LOGIN_COOKIE_NAMES = ("NID_AUT", "NID_SES")
