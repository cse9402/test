"""브라우저 실행 및 로그인 처리."""
import os
import yaml
from playwright.sync_api import sync_playwright, Page, BrowserContext


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def start_browser(headless: bool = False, channel: str | None = "msedge"):
    """브라우저를 실행한다.

    channel 을 지정하면(기본값 "msedge") Playwright 전용 Chromium을
    새로 내려받지 않고, 이미 컴퓨터에 설치된 Edge/Chrome을 그대로 사용한다.
    사내망 등에서 cdn.playwright.dev 접속이 막혀 브라우저 다운로드가
    실패하는 경우에 유용하다. channel=None 이면 Playwright 번들 Chromium을 쓴다.
    """
    playwright = sync_playwright().start()
    launch_kwargs = {"headless": headless}
    if channel:
        launch_kwargs["channel"] = channel
    browser = playwright.chromium.launch(**launch_kwargs)
    context = browser.new_context()
    page = context.new_page()
    return playwright, browser, context, page


def login(page: Page, login_config_path: str = "config/login.yaml") -> None:
    """login.yaml 설정에 따라 로그인을 수행한다.

    auth_type: id_pw       -> BLCM_USER_ID / BLCM_USER_PW (.env)
    auth_type: certificate -> BLCM_CERT_LABEL / BLCM_CERT_PW (.env)
    """
    cfg = load_yaml(login_config_path)
    auth_type = cfg.get("auth_type", "id_pw")

    page.goto(cfg["login_url"])

    if auth_type == "certificate":
        _login_with_certificate(page, cfg)
    elif auth_type == "id_pw":
        _login_with_id_pw(page, cfg)
    else:
        raise ValueError(f"알 수 없는 auth_type: {auth_type}")

    page.wait_for_selector(
        cfg["success_selector"],
        timeout=cfg.get("success_timeout_ms", 15000),
    )


def _login_with_id_pw(page: Page, cfg: dict) -> None:
    user_id = os.environ.get("BLCM_USER_ID")
    user_pw = os.environ.get("BLCM_USER_PW")
    if not user_id or not user_pw:
        raise RuntimeError(
            ".env 파일에 BLCM_USER_ID / BLCM_USER_PW 가 설정되어 있지 않습니다. "
            ".env.example 을 복사해 값을 채워주세요."
        )

    open_form = cfg.get("open_login_form", {})
    if open_form and open_form.get("selector"):
        page.click(open_form["selector"])

    page.fill(cfg["id_selector"], user_id)
    page.fill(cfg["pw_selector"], user_pw)
    page.click(cfg["submit_selector"])


def _login_with_certificate(page: Page, cfg: dict) -> None:
    """공동인증서(하드디스크 저장) 로그인. 인증서 선택부터 새로 한다."""
    certificate_sign(
        page,
        {
            "cert_login_button_selector": cfg["cert_login_button_selector"],
            "cert_storage_button_selector": cfg["cert_storage_button_selector"],
            "cert_select_by_label": True,
            "password_selector": cfg["cert_password_selector"],
            "confirm_button_selector": cfg["cert_confirm_button_selector"],
        },
    )


def certificate_sign(page: Page, cfg: dict) -> None:
    """인증서 비밀번호 입력이 필요한 모든 순간(로그인, 문서 제출 시 전자서명 등)에
    공통으로 쓰는 함수.

    cfg 의 cert_login_button_selector / cert_storage_button_selector 는
    선택 사항이다. 값이 있으면 그 버튼을 먼저 누르고, 없으면 바로 비밀번호
    입력칸부터 채운다 (제출 시 전자서명 창은 인증서를 다시 고를 필요 없이
    비밀번호만 물어보는 경우가 많기 때문).

    cert_select_by_label 이 true 이면 .env 의 BLCM_CERT_LABEL 텍스트로
    인증서 목록에서 본인 인증서를 클릭한다.
    """
    cert_pw = os.environ.get("BLCM_CERT_PW")
    if not cert_pw:
        raise RuntimeError(
            ".env 파일에 BLCM_CERT_PW 가 설정되어 있지 않습니다. "
            ".env.example 을 복사해 값을 채워주세요."
        )

    if cfg.get("cert_login_button_selector"):
        page.click(cfg["cert_login_button_selector"])
    if cfg.get("cert_storage_button_selector"):
        page.click(cfg["cert_storage_button_selector"])
    if cfg.get("cert_select_by_label"):
        cert_label = os.environ.get("BLCM_CERT_LABEL")
        if not cert_label:
            raise RuntimeError(".env 파일에 BLCM_CERT_LABEL 이 설정되어 있지 않습니다.")
        page.get_by_text(cert_label).click()

    page.fill(cfg["password_selector"], cert_pw)
    page.click(cfg["confirm_button_selector"])
