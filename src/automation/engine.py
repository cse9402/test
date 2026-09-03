"""YAML로 정의한 한 건(row)당 전체 흐름을 실행하는 범용 엔진.

한 흐름은 여러 창(팝업)을 오갈 수 있고, 중간중간 인증서 재서명이
들어갈 수 있다. pages 딕셔너리가 "이름표 -> 열려 있는 창(Page)"을
들고 다니며, 각 단계(step)는 자신이 어느 창에서 실행될지 page 키로 지정한다.

captured 딕셔너리는 화면에 표시된 값(예: 시스템이 새로 부여한 문서번호)을
읽어서 저장해뒀다가, 뒤의 단계에서 다시 입력값으로 쓸 때 사용한다.
"""
from .browser import certificate_sign


def _resolve_value(step: dict, row: dict, captured: dict) -> str:
    if "from_capture" in step:
        key = step["from_capture"]
        if key not in captured:
            raise KeyError(
                f"'{key}' 값이 아직 capture_text 단계로 읽히지 않았습니다. "
                "이 단계보다 앞에 save_as가 같은 capture_text 단계가 있어야 합니다."
            )
        return captured[key]
    if "csv_column" in step:
        column = step["csv_column"]
        if column not in row:
            raise KeyError(f"CSV에 '{column}' 컬럼이 없습니다.")
        return row[column]
    return str(step.get("value", ""))


def _resolve_selector(step: dict, row: dict, captured: dict) -> str:
    """selector 안에 {value} 가 있으면, csv_column/from_capture/value로 채운다.

    목록에서 매번 다른 행(안건번호 등)을 클릭해야 할 때 사용:
      selector: "text={value}"
      csv_column: case_no
    """
    selector = step["selector"]
    if "{value}" in selector:
        selector = selector.replace("{value}", _resolve_value(step, row, captured))
    return selector


def _run_step(pages: dict, step: dict, row: dict, captured: dict, cert_cfg: dict) -> None:
    action = step["action"]
    page_key = step.get("page", "main")

    if action == "close_page":
        if page_key not in pages:
            raise KeyError(f"'{page_key}' 창이 열려있지 않아 닫을 수 없습니다.")
        if page_key == "main":
            raise ValueError("main 창은 닫을 수 없습니다.")
        pages[page_key].close()
        del pages[page_key]
        return

    if page_key not in pages:
        raise KeyError(
            f"'{page_key}' 창이 아직 열려 있지 않습니다. "
            "이 창을 여는 단계에 opens_page가 먼저 있어야 합니다."
        )
    page = pages[page_key]

    if action == "click":
        selector = _resolve_selector(step, row, captured)
        opens_page = step.get("opens_page")
        if opens_page:
            with page.expect_popup() as popup_info:
                page.click(selector)
            pages[opens_page] = popup_info.value
        else:
            page.click(selector)
    elif action == "dblclick":
        selector = _resolve_selector(step, row, captured)
        opens_page = step.get("opens_page")
        if opens_page:
            with page.expect_popup() as popup_info:
                page.dblclick(selector)
            pages[opens_page] = popup_info.value
        else:
            page.dblclick(selector)
    elif action == "fill":
        page.fill(step["selector"], _resolve_value(step, row, captured))
    elif action == "select":
        page.select_option(step["selector"], _resolve_value(step, row, captured))
    elif action == "upload":
        page.set_input_files(step["selector"], _resolve_value(step, row, captured))
    elif action == "check":
        page.check(step["selector"])
    elif action == "uncheck":
        page.uncheck(step["selector"])
    elif action == "press":
        page.press(step["selector"], step["key"])
    elif action == "capture_text":
        if step.get("from") == "value":
            text = page.input_value(step["selector"])
        else:
            text = page.inner_text(step["selector"])
        captured[step["save_as"]] = text.strip()
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
    captured: dict = {}

    for step in flow_config.get("steps", []):
        _run_step(pages, step, row, captured, cert_cfg)

    success = flow_config.get("success_selector")
    if success:
        page_key = success.get("page", "main") if isinstance(success, dict) else "main"
        selector = success["selector"] if isinstance(success, dict) else success
        timeout = success.get("timeout_ms", 15000) if isinstance(success, dict) else 15000
        pages[page_key].wait_for_selector(selector, timeout=timeout)
