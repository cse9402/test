# 네이버 카페 게시글 수집기 (MVP)

본인 네이버 계정에 **실제로 부여된 열람 권한 범위 안에서** 카페 게시글을 수집·저장·검색·내보내기하는 로컬 도구입니다.

> ⚠️ **검증 상태**: 이 코드는 네이버에 접속할 수 없는 개발 환경에서 작성되었습니다.
> 사이트 구조(선택자·URL·제한 안내 문구)는 **검증되지 않은 구현 가설**이며, 가상 HTML과 로컬 모의 서버로만 테스트했습니다.
> 처음 사용할 때 반드시 `python main.py diagnose`로 현장 진단을 실행하세요.

## 1. 사용 전 확인 사항 (중요)

| 항목 | 내용 |
|---|---|
| 서비스 약관 | 네이버 이용약관·카페 운영정책의 자동화 수집 관련 조항을 직접 확인하세요. (개발 환경에서 원문 확인 불가 → **확인이 필요합니다**) |
| robots.txt | `https://cafe.naver.com/robots.txt` 내용을 직접 확인하세요. (**확인이 필요합니다**) |
| 카페 운영진 동의 | 회원 전용 게시글 수집은 카페 매니저의 사전 동의를 받는 것을 권장합니다. |
| 개인정보 | 작성자 닉네임·본문 속 개인정보는 「개인정보 보호법」 적용 대상일 수 있습니다. 수집 목적 범위 안에서만 이용하고 외부 공유를 삼가세요. |
| 저작권 | 게시글·이미지 저작권은 작성자에게 있습니다. 이미지 다운로드는 기본 비활성화되어 있습니다. |

**이 프로그램이 하지 않는 일**: 비밀번호 자동 입력, CAPTCHA 자동 해결, 회원 등급 위조, 권한 우회, 비공개 내부 API 호출, 프록시/IP 회전, 브라우저 지문 위조.

## 2. 설치

Python 3.11 이상 필요.

**Windows (간편)**: `start_windows.bat` 더블클릭 → 설치 후 화면이 자동으로 열립니다.

**직접 설치**
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    / macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env      # Windows: copy .env.example .env
```

## 3. 네이버 로그인

1. 화면(Streamlit)의 **[1️⃣ 로그인] → [로그인 창 열기]** 또는 `python main.py login`
2. 열린 브라우저 창에서 **직접** 아이디·비밀번호 입력, 2단계 인증·보안문자 완료
3. 로그인 쿠키가 확인되면 창이 자동으로 닫힙니다.
4. 세션은 `browser_profile/` 폴더(소유자 전용 권한)에만 저장됩니다. 로그·DB·내보내기 파일에는 포함되지 않습니다.
5. 세션 만료 시 수집이 `세션 만료` 상태로 멈추며, 재로그인 후 **[재개]** 하면 됩니다.
6. 로컬 세션 삭제: `python main.py logout`

> 로그인 창이 열려 있는 동안에는 다른 작업(상태 확인·수집)을 실행할 수 없습니다(브라우저 프로필 잠금).

## 4. 실행

### 화면(권장)
```bash
streamlit run app.py
```
로그인 → 게시판 목록 불러오기 → 게시판·조건 선택 → 수집 시작 → 결과 탭에서 검색·CSV/Excel 다운로드

### 명령줄
```bash
python main.py status                                   # 로그인 상태
python main.py boards                                   # 게시판 목록(ID 확인)
python main.py crawl --menu 5 --pages 1-3 --max 50      # 5번 게시판 1~3페이지
python main.py crawl --menu 5 7 --keyword 텐트 --scope both --from 2024-01-01 --comments
python main.py crawl --menu 5 --only-new                # 마지막 수집 이후 신규 글만
python main.py crawl --resume 3                         # 중단된 작업 3번 재개
python main.py article https://cafe.naver.com/adoutdoor/12345
python main.py export --format xlsx                     # exports/ 폴더에 저장
python main.py jobs                                     # 작업 이력
python main.py diagnose                                 # 사이트 구조 진단
```

## 5. 현장 진단 및 수정 방법

```bash
python main.py diagnose                       # 첫 게시판 기준
python main.py diagnose --menu 5 --article-url https://cafe.naver.com/adoutdoor/12345
```
`diagnostics/날짜시각/` 폴더에 HTML·스크린샷·`report.json`이 저장됩니다.

| report.json 항목 | 정상 기준 | 0 또는 null 이면 수정할 곳 |
|---|---|---|
| `main.club_id` | 숫자 | `crawler/selectors.py` → `CLUB_ID_PATTERNS` |
| `main.boards_found` | 1 이상 | `MENU_ID_PATTERNS` |
| `list.articles_found` | 1 이상 | `.env` → `LIST_URL_TEMPLATE`, `ARTICLE_ID_PATTERNS`, `ROW_*` |
| `article.access_status` | `ok` | `DETAIL_CONTENT_SELECTORS` |
| `article.selector_hits` | 1 이상인 항목 존재 | `DETAIL_*` 선택자 |

※ 진단 HTML에는 닉네임 등이 포함될 수 있으니 외부에 공유하지 마세요. (쿠키·헤더는 저장하지 않음)

## 6. 동작 원칙

- 요청 간격 기본 3~6초(무작위), 동시 요청 1건, 1초 미만 설정 불가
- 타임아웃·5xx: 최대 2회 재시도(지수 백오프)
- HTTP 429/403 → 즉시 중단(`차단 의심`), CAPTCHA 화면 → 즉시 중단(`보안 확인 필요`)
- 접근 거부 글: 본문을 저장하지 않고 `members_only` / `level_restricted` / `login_required`로만 기록
- 중복 방지: `(카페, 게시글ID)` 고유키. 이미 `ok`인 글은 다시 요청하지 않음
- 이전에 `ok`였던 글을 재확인 시 제한되어도 기존 본문 보존

## 7. 테스트

```bash
pytest -q
```
가상 HTML Fixture·Mock Fetcher·로컬 HTTP 서버를 사용합니다. **실제 네이버 사이트 검증이 아닙니다.**

## 8. 폴더 구조

```
app.py / main.py / config.py      화면 / 명령줄 / 설정
crawler/  browser.py auth.py cafe_parser.py board_parser.py article_parser.py
          collector.py selectors.py urls.py parse_utils.py types.py diagnostics.py
database/ models.py repository.py
utils/    logger.py exporter.py rate_limiter.py
tests/    test_parser.py test_repository.py test_collector.py test_rate_limiter.py
          test_browser_local.py fixtures/
```
