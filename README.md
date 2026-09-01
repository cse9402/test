# biz.blcm.go.kr 업무 자동화 도구

`https://biz.blcm.go.kr` 에서 반복적으로 수행하는 **문서등록**, **민원처리** 같은
데이터 입력 작업을, 본인의 정상 로그인 계정으로 CSV에 정리한 여러 건을
한 번에 자동으로 처리하기 위한 Playwright 기반 스크립트입니다.

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

자격 증명 설정:

```bash
cp .env.example .env
# .env 파일을 열어 BLCM_USER_ID / BLCM_USER_PW 값을 채웁니다.
```

`.env` 파일은 `.gitignore`에 포함되어 있어 커밋되지 않습니다. 절대 직접 커밋하지 마세요.

## 선택자(selector) 채우는 방법

로그인 화면과 문서등록/민원처리 화면의 실제 버튼·입력란 ID는 로그인해야만
확인할 수 있어 이 저장소에는 `TODO`로 남겨두었습니다. 아래 순서로 채워주세요.

1. Playwright의 녹화 기능을 실행합니다.

   ```bash
   playwright codegen https://biz.blcm.go.kr/biz/cmm/main/mainPage.do
   ```

2. 열린 브라우저 창에서 평소처럼 로그인 → 문서등록(또는 민원처리) 메뉴 이동 →
   입력 → 제출까지 직접 한 번 수행합니다.
3. 옆에 뜨는 "Playwright Inspector" 창에 각 클릭/입력마다 사용된 선택자
   (예: `#userId`, `text=문서등록`, `#submitBtn`)가 자동으로 기록됩니다.
4. 아래 파일들을 복사해서 이름에서 `.example`을 뗀 뒤, 기록된 선택자로
   `TODO` 부분을 교체합니다.

   ```bash
   cp config/login.example.yaml config/login.yaml
   cp config/tasks/document_register.example.yaml config/tasks/document_register.yaml
   cp config/tasks/civil_complaint.example.yaml config/tasks/civil_complaint.yaml
   ```

`config/login.yaml`, `config/tasks/*.yaml` (example이 아닌 파일들)도 로그인
정보나 내부 화면 구조를 담을 수 있으므로 `.gitignore`에 추가해 관리하는 것을
권장합니다(필요하면 팀 내부 저장소에서만 공유).

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
