"""YAML로 정의한 한 건(row)당 전체 흐름을 실행하는 범용 엔진.

한 흐름은 여러 창(팝업)을 오갈 수 있고, 중간중간 인증서 재서명이
들어갈 수 있다. pages 딕셔너리가 "이름표 -> 열려 있는 창(Page)"을
들고 다니며, 각 단계(step)는 자신이 어느 창에서 실행될지 page 키로 지정한다.
"""
from .browser import certificate_sign


def _resolve_value(step: dict, row: dict) -> str:
    if "csv_column" in step:
        column = step["csv_column"]
        if column not in row:
            raise KeyError(f"CSV에 '{column}' 컬럼이 없습니다.")
        return row[column]
    return str(step.get("value", ""))


def _run_step(pages: dict, step: dict, row: dict, cert_cfg: dict) -> None:
    action = step["action"]
    page_key = step.get("page", "main")
    if page_key not in pages:
        raise KeyError(
            f"'{page_key}' 창이 아직 열려 있지 않습니다. "
            "이 창을 여는 단계에 opens_page가 먼저 있어야 합니다."
        )
    page = pages[page_key]

    if action == "click":
        opens_page = step.get("opens_page")
        if opens_page:
            with page.expect_popup() as popup_info:
                page.click(step["selector"])
            pages[opens_page] = popup_info.value
        else:
            page.click(step["selector"])
    elif action == "fill":
        page.fill(step["selector"], _resolve_value(step, row))
    elif action == "select":
        page.select_option(step["selector"], _resolve_value(step, row))
    elif action == "upload":
        page.set_input_files(step["selector"], _resolve_value(step, row))
    elif action == "check":
        page.check(step["selector"])
    elif action == "uncheck":
        page.uncheck(step["selector"])
    elif action == "press":
        page.press(step["selector"], step["key"])
    elif action == "wait_for_selector":
        page.wait_for_selector(step["selector"], timeout=step.get("timeout_ms", 15000))
    elif action == "wait_for_timeout":
        page.wait_for_timeout(step.get("ms", 1000))
    elif action == "handle_dialog":
        accept = step.get("accept", True)
        page.once(
            "dialog",
            lambda dialog: dialog.accept() if accept else dialog.dismiss(),
        )
    elif action == "certificate_sign":
        if not cert_cfg:
            raise ValueError(
                "certificate_sign 단계를 쓰려면 flow 설정에 "
                "certificate_signature 블록이 있어야 합니다."
            )
        certificate_sign(page, cert_cfg)
    else:
        raise ValueError(f"알 수 없는 action: {action}")


def run_flow(pages: dict, flow_config: dict, row: dict) -> None:
    """flow_config['steps']에 정의된 순서대로 한 건(row)을 처음부터 끝까지 처리한다."""
    cert_cfg = flow_config.get("certificate_signature", {})

    for step in flow_config.get("steps", []):
        _run_step(pages, step, row, cert_cfg)

    success = flow_config.get("success_selector")
    if success:
        page_key = success.get("page", "main") if isinstance(success, dict) else "main"
        selector = success["selector"] if isinstance(success, dict) else success
        timeout = success.get("timeout_ms", 15000) if isinstance(success, dict) else 15000
        pages[page_key].wait_for_selector(selector, timeout=timeout)
