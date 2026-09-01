"""브라우저 실행 및 로그인 처리."""
import os
import yaml
from playwright.sync_api import sync_playwright, Page, BrowserContext


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def start_browser(headless: bool = False):
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()
    return playwright, browser, context, page


def login(page: Page, login_config_path: str = "config/login.yaml") -> None:
    """login.yaml 설정에 따라 아이디/비밀번호 로그인을 수행한다.

    자격 증명은 .env 의 BLCM_USER_ID / BLCM_USER_PW 에서 읽는다.
    """
    cfg = load_yaml(login_config_path)

    user_id = os.environ.get("BLCM_USER_ID")
    user_pw = os.environ.get("BLCM_USER_PW")
    if not user_id or not user_pw:
        raise RuntimeError(
            ".env 파일에 BLCM_USER_ID / BLCM_USER_PW 가 설정되어 있지 않습니다. "
            ".env.example 을 복사해 값을 채워주세요."
        )

    page.goto(cfg["login_url"])

    open_form = cfg.get("open_login_form", {})
    if open_form and open_form.get("selector"):
        page.click(open_form["selector"])

    page.fill(cfg["id_selector"], user_id)
    page.fill(cfg["pw_selector"], user_pw)
    page.click(cfg["submit_selector"])

    page.wait_for_selector(
        cfg["success_selector"],
        timeout=cfg.get("success_timeout_ms", 15000),
    )
