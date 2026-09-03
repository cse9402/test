# 건축물 생애이력 업무 자동화 도구

**건축물 생애이력 → 건축물 해체신고처리 → 문서등록 → 민원처리** 를 건(row)
하나당 처음부터 끝까지 반복하는 업무를, 본인의 정상 로그인 계정으로 CSV에
정리한 여러 건에 대해 한 번에 자동으로 처리하기 위한 Playwright 기반 스크립트입니다.

## 전체 흐름

1. 소속 기관 내부 시스템(`intra.eais.go.kr/<기관코드>`)에 **공동인증서**로 로그인
2. "건축물 생애이력" 클릭 → **새 창(팝업)** 이 열림
3. 그 창 안에서 "건축물 해체신고처리" 메뉴로 이동, 안건 검색
4. **문서등록** 입력 → 제출 → **인증서로 전자서명**
5. **민원처리** 입력 → 제출 → **인증서로 전자서명**
6. CSV의 다음 행(다음 건)에 대해 2~5 반복

이 저장소는 이 전체 흐름을 하나의 YAML(`config/tasks/demolition_report_case.yaml`)로
정의하고, 여러 창을 오가며 순서대로 실행하는 엔진(`src/automation/engine.py`)을
갖고 있습니다.

## 로그인/서명 방식: 공동인증서

아이디/비밀번호가 아니라 **공동인증서(하드디스크 저장)** 로 로그인하고,
문서등록·민원처리를 제출할 때마다 **다시 인증서 비밀번호를 입력하는
전자서명**이 필요합니다. 이 저장소는 두 가지를 구분해서 처리합니다.

- **로그인** (`config/login.yaml`, `auth_type: certificate`): 인증서 목록에서
  본인 인증서를 고르고 비밀번호를 입력.
- **서명** (`config/tasks/demolition_report_case.yaml` 의 `certificate_sign`
  단계): 문서등록/민원처리 제출 직후마다 반복 호출. 보통은 인증서를 다시
  고를 필요 없이 비밀번호만 입력하면 되지만, 사이트에 따라 다를 수 있어
  설정으로 켜고 끌 수 있게 해뒀습니다.

주의할 점 두 가지:

- 인증서 비밀번호, 인증서를 구분하는 문구(별칭 등)는 **절대 YAML 파일에
  직접 적지 말고** `.env`의 `BLCM_CERT_LABEL`, `BLCM_CERT_PW`로만 관리하세요.
  `config/login.yaml`, `config/tasks/*.yaml`(example 제외)은 내부 시스템
  주소·화면 구조가 담기므로 `.gitignore`에 이미 등록되어 커밋되지 않습니다.
- 일부 기관 시스템은 자동화 브라우저(Playwright/Selenium)를 탐지해 로그인을
  막는 보안 모듈을 쓰기도 합니다. `--channel msedge`로 실제 설치된 Edge를
  쓰면 탐지를 어느 정도 피할 수 있지만 100% 보장되진 않습니다. 로그인/서명
  단계에서 원인 모를 실패가 반복되면 이 가능성부터 의심해보세요.

**Playwright codegen으로 화면을 녹화해 공유하실 때는 반드시 비밀번호 부분을
가리거나 지우고 보내주세요.** 코드에 비밀번호가 그대로 찍히니,
`fill("실제비밀번호")` 같은 줄은 `fill("****")`로 바꿔서 공유해주시면 됩니다.

## ⚠️ 사용 전 꼭 읽어주세요

- 반드시 **본인(또는 소속 기관)이 정상적으로 이용 권한을 가진 계정**으로만 사용하세요.
- 정부 시스템은 이용약관에 자동화 접근을 제한하는 조항이 있을 수 있습니다.
  운영 부서/소속 기관의 정보보안·전산 담당자에게 자동화 사용 가능 여부를
  먼저 확인하는 것을 권장합니다.
- 서버에 부담을 주지 않도록 `delay_between_rows_seconds` 로 요청 간 간격을
  두었습니다. 과도하게 줄이지 마세요.
- 이 스크립트는 **화면 요소 선택자(selector)가 채워지지 않은 템플릿**입니다.
  실제 사이트는 로그인 후에만 보이므로, 아래 "선택자 채우는 방법"에 따라
  본인이 직접 채워야 동작합니다.

## 준비

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 사내망/관공서 PC에서 `playwright install chromium`이 실패할 때

`cdn.playwright.dev` 접속이 화이트리스트 방식으로 막혀 있어 브라우저 다운로드가
`ECONNRESET` 등으로 계속 실패하는 경우, 브라우저를 새로 받지 않고 **이미 설치된
Edge/Chrome을 그대로 사용**할 수 있습니다. 이 저장소의 `main.py`와
`playwright codegen`은 기본적으로(`--channel msedge`) Windows에 기본 설치된
Edge를 사용하도록 되어 있으므로, `playwright install chromium` 단계를
건너뛰어도 됩니다.

```bash
# 브라우저 다운로드 없이 바로 codegen (설치된 Edge 사용)
playwright codegen --channel msedge https://intra.eais.go.kr/namyangju/index.do

# 실행도 기본값이 msedge이므로 별도 옵션 없이 그대로 실행 가능
python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv
```

Playwright 번들 Chromium을 굳이 쓰고 싶다면 `--channel ""` 옵션으로 끌 수 있습니다
(이 경우 `playwright install chromium` 다운로드가 성공해야 합니다).

자격 증명 설정:

```bash
cp .env.example .env
# BLCM_CERT_LABEL (인증서 목록에서 본인 것 구분하는 문구), BLCM_CERT_PW (인증서 비밀번호) 를 채웁니다.
```

`.env` 파일은 `.gitignore`에 포함되어 있어 커밋되지 않습니다. 절대 직접 커밋하지 마세요.

## 선택자(selector) 채우는 방법

로그인/생애이력/해체신고처리/문서등록/민원처리 화면의 실제 버튼·입력란은
로그인해야만 확인할 수 있어 이 저장소에는 `TODO`로 남겨두었습니다. 아래
순서로 채워주세요.

1. Playwright의 녹화 기능을 실행합니다 (설치된 Edge 사용).

   ```bash
   playwright codegen --channel msedge https://intra.eais.go.kr/namyangju/index.do
   ```

2. 열린 브라우저 창에서 **처음부터 끝까지 한 번에** 수행합니다: 인증서
   로그인 → 건축물 생애이력 클릭(새 창 뜸) → 건축물 해체신고처리 → 안건
   검색 → 문서등록 입력·제출·전자서명 → 민원처리 입력·제출·전자서명.
   중간에 새 창이 뜨면 Playwright Inspector가 자동으로 `page1` 같은 새
   변수를 만들어 기록합니다 — 이후 그 창에서 하는 조작은 그 변수로 기록돼요.
3. 옆에 뜨는 "Playwright Inspector" 창에 각 클릭/입력마다 사용된 선택자가
   자동으로 기록됩니다. **비밀번호를 입력하는 줄은 복사하기 전에 지우거나
   `****`로 바꾸세요.**
4. 아래 파일들을 복사해서 이름에서 `.example`을 뗀 뒤, 기록된 선택자로
   `TODO` 부분을 교체합니다.

   ```bash
   cp config/login.example.yaml config/login.yaml
   cp config/tasks/demolition_report_case.example.yaml config/tasks/demolition_report_case.yaml
   ```

   비밀번호나 인증서 비밀번호는 이 파일들에 적지 말고 `.env`에만 넣으세요.

## 입력 데이터(CSV) 준비

- `data/demolition_report_case_sample.csv` 를 참고해 실제 처리할 건들을
  CSV로 정리하세요. 한 행 = 안건(건축물 해체신고 건) 하나입니다.
- CSV의 헤더(컬럼명)는 task YAML의 각 단계에 적힌 `csv_column` 값과
  일치해야 합니다.
- 파일 첨부가 필요하면 별도 컬럼(예: `attachment_path`)에 로컬 파일 경로를
  적고, 해당 단계를 `type: upload`로 추가하세요.

## 실행

```bash
# 처음에는 headless 없이, 데이터 1~2건으로 실제로 잘 동작하는지 눈으로 확인하세요.
python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv

# 잘 되는 걸 확인한 뒤에는 창 없이 실행 가능
python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv --headless

# 일시적 오류(네트워크 지연 등)에 대비해 건마다 재시도 횟수 지정
python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv --max-retries 3
```

## 결과 확인

- 각 실행이 끝나면 `results/<task>_<시각>.csv` 에 건별 성공/실패, 오류 메시지,
  실패 시 스크린샷 경로가 기록됩니다.
- 실패한 건은 스크린샷(`screenshots/`)으로 원인을 확인한 뒤, 선택자나 데이터를
  고쳐서 실패한 행만 다시 CSV로 만들어 재실행하면 됩니다.
- 실패했다가 다음 건으로 넘어갈 때, 중간에 열렸던 팝업 창들은 자동으로
  정리(닫힘)되고 시작 화면으로 돌아갑니다.

## 구조

```
config/
  login.example.yaml                       # 로그인 화면 선택자 (복사해서 login.yaml로 사용)
  tasks/
    demolition_report_case.example.yaml    # 전체 흐름(생애이력→해체신고처리→문서등록→민원처리) 선택자/순서
data/
  demolition_report_case_sample.csv        # 입력 데이터 예시 (한 행 = 안건 하나)
src/automation/
  browser.py   # 브라우저 실행, 로그인, 인증서 서명(certificate_sign)
  engine.py    # 여러 창을 오가며 YAML의 steps를 실제 클릭/입력으로 실행하는 범용 엔진
  runner.py    # CLI: CSV를 순회하며 각 건에 대해 흐름 전체 실행, 팝업 정리, 로그 기록
main.py        # 진입점
```

### task YAML의 step 문법

```yaml
steps:
  - action: click            # click / fill / select / upload / check / uncheck /
                              # press / wait_for_selector / wait_for_timeout /
                              # handle_dialog / certificate_sign
    page: main                # 어느 창에서 실행할지 (기본값 "main")
    selector: "text=건축물 생애이력"
    opens_page: history       # 이 클릭이 새 창을 띄우면, 그 창에 붙일 이름표.
                               # 이후 단계에서 page: history 로 그 창을 지정
  - action: fill
    page: history
    selector: "#docTitle"
    csv_column: doc_title     # CSV의 doc_title 컬럼 값을 입력 (고정값은 value: 사용)
  - action: certificate_sign  # 인증서 비밀번호 재입력(전자서명)
    page: history
```

## 다른 반복 업무 추가하기

다른 반복 흐름이 필요하면, 기존 예시 YAML을 복사해
`config/tasks/새작업이름.yaml` 을 만들고, CSV도 하나 준비한 뒤 다음처럼
실행하면 됩니다.

```bash
python main.py --task 새작업이름 --input data/새작업이름.csv
```

코드를 수정할 필요 없이 YAML 설정과 CSV만으로 새 반복 업무를 추가할 수 있게
설계했습니다.
