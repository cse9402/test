# biz.blcm.go.kr 업무 자동화 도구

`https://biz.blcm.go.kr` 에서 반복적으로 수행하는 **문서등록**, **민원처리** 같은
데이터 입력 작업을, 본인의 정상 로그인 계정으로 CSV에 정리한 여러 건을
한 번에 자동으로 처리하기 위한 Playwright 기반 스크립트입니다.

## 로그인 방식: 공동인증서

실제 업무 화면은 `biz.blcm.go.kr`이 아니라 소속 기관 내부 시스템
(예: `intra.eais.go.kr/<기관코드>`)에 있고, 아이디/비밀번호가 아니라
**공동인증서(하드디스크 저장) 로그인**을 사용합니다. 이 저장소는
`config/login.yaml`에 `auth_type: certificate`로 설정하면 인증서 로그인을
자동으로 처리합니다.

인증서 자동 로그인에는 두 가지를 알아두세요.

- 인증서 비밀번호와, 인증서 목록에서 본인 인증서를 구분하는 문구(별칭 등)는
  **절대 YAML 파일에 직접 적지 말고** `.env`의 `BLCM_CERT_LABEL`,
  `BLCM_CERT_PW`로만 관리하세요. `config/login.yaml`,
  `config/tasks/*.yaml`(example 제외)은 `.gitignore`에 이미 포함되어 있어
  실수로 커밋되지 않습니다.
- 일부 기관 시스템은 자동화 브라우저(Playwright/Selenium)를 탐지해 로그인
  자체를 막는 보안 모듈을 쓰기도 합니다. `--channel msedge`로 실제 설치된
  Edge를 사용하면 이런 탐지를 어느 정도 피할 수 있지만, 100% 보장되지는
  않습니다. 로그인 단계에서 원인 모를 실패가 반복되면 이 가능성부터
  의심해보세요.

**Playwright codegen으로 로그인 과정을 녹화해 저한테 보여주실 때는 반드시
인증서 비밀번호 부분을 가리거나 지우고 보내주세요.** 코드에 비밀번호가
그대로 찍히니, `fill("실제비밀번호")` 같은 줄은 `fill("****")`로 바꿔서
공유해주시면 됩니다.

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
python main.py --task document_register --input data/document_register_sample.csv
```

Playwright 번들 Chromium을 굳이 쓰고 싶다면 `--channel ""` 옵션으로 끌 수 있습니다
(이 경우 `playwright install chromium` 다운로드가 성공해야 합니다).

자격 증명 설정:

```bash
cp .env.example .env
# 인증서 로그인이면 BLCM_CERT_LABEL / BLCM_CERT_PW,
# 아이디/비밀번호 로그인이면 BLCM_USER_ID / BLCM_USER_PW 값을 채웁니다.
```

`.env` 파일은 `.gitignore`에 포함되어 있어 커밋되지 않습니다. 절대 직접 커밋하지 마세요.

## 선택자(selector) 채우는 방법

로그인 화면과 문서등록/민원처리 화면의 실제 버튼·입력란 ID는 로그인해야만
확인할 수 있어 이 저장소에는 `TODO`로 남겨두었습니다. 아래 순서로 채워주세요.

1. Playwright의 녹화 기능을 실행합니다 (설치된 Edge 사용).

   ```bash
   playwright codegen --channel msedge https://intra.eais.go.kr/namyangju/index.do
   ```

2. 열린 브라우저 창에서 평소처럼 로그인 → 문서등록(또는 민원처리) 메뉴 이동 →
   입력 → 제출까지 직접 한 번 수행합니다.
3. 옆에 뜨는 "Playwright Inspector" 창에 각 클릭/입력마다 사용된 선택자
   (예: `text=인증서 로그인`, `text=문서등록`, `#submitBtn`)가 자동으로 기록됩니다.
4. 아래 파일들을 복사해서 이름에서 `.example`을 뗀 뒤, 기록된 선택자로
   `TODO` 부분을 교체합니다.

   ```bash
   cp config/login.example.yaml config/login.yaml
   cp config/tasks/document_register.example.yaml config/tasks/document_register.yaml
   cp config/tasks/civil_complaint.example.yaml config/tasks/civil_complaint.yaml
   ```

   비밀번호나 인증서 비밀번호는 이 파일들에 적지 말고 `.env`에만 넣으세요.
   `config/login.yaml`, `config/tasks/*.yaml`(example 제외)은 내부 시스템
   주소와 화면 구조가 담기므로 `.gitignore`에 이미 등록되어 있어 커밋되지
   않습니다.

## 입력 데이터(CSV) 준비

- `data/document_register_sample.csv`, `data/civil_complaint_sample.csv` 를
  참고해 실제 처리할 건들을 CSV로 정리하세요.
- CSV의 헤더(컬럼명)는 해당 task YAML의 `fields[].csv_column` 값과 일치해야 합니다.
- 파일 첨부가 필요하면 `attachment_path` 컬럼에 로컬 파일 경로를 적습니다.

## 실행

```bash
# 처음에는 headless 없이 실행해서 실제로 잘 동작하는지 눈으로 확인하세요.
python main.py --task document_register --input data/document_register_sample.csv

python main.py --task civil_complaint --input data/civil_complaint_sample.csv

# 잘 되는 걸 확인한 뒤에는 창 없이 실행 가능
python main.py --task document_register --input data/document_register_sample.csv --headless

# 일시적 오류(네트워크 지연 등)에 대비해 행마다 재시도 횟수 지정
python main.py --task document_register --input data/document_register_sample.csv --max-retries 3
```

## 결과 확인

- 각 실행이 끝나면 `results/<task>_<시각>.csv` 에 행별 성공/실패, 오류 메시지,
  실패 시 스크린샷 경로가 기록됩니다.
- 실패한 행은 스크린샷(`screenshots/`)으로 원인을 확인한 뒤, 선택자나 데이터를
  고쳐서 실패한 행만 다시 CSV로 만들어 재실행하면 됩니다.

## 구조

```
config/
  login.example.yaml              # 로그인 화면 선택자 (복사해서 login.yaml로 사용)
  tasks/
    document_register.example.yaml  # 문서등록 화면 선택자/순서
    civil_complaint.example.yaml    # 민원처리 화면 선택자/순서
data/
  document_register_sample.csv    # 문서등록 입력 데이터 예시
  civil_complaint_sample.csv      # 민원처리 입력 데이터 예시
src/automation/
  browser.py   # 브라우저 실행, 로그인
  engine.py    # YAML에 정의된 단계를 실제 클릭/입력으로 실행하는 범용 엔진
  runner.py    # CLI: CSV를 순회하며 각 행에 대해 task 실행, 로그 기록
main.py        # 진입점
```

## 다른 반복 업무 추가하기

문서등록/민원처리 외에 다른 반복 화면이 있다면, 기존 예시 YAML을 복사해
`config/tasks/새작업이름.yaml` 을 만들고, CSV도 하나 준비한 뒤 다음처럼
실행하면 됩니다.

```bash
python main.py --task 새작업이름 --input data/새작업이름.csv
```

코드를 수정할 필요 없이 YAML 설정과 CSV만으로 새 반복 작업을 추가할 수 있게
설계했습니다.
