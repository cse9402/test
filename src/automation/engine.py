"""YAML 설정(steps/fields)을 읽어 Playwright 동작으로 실행하는 범용 엔진."""
from playwright.sync_api import Page


def _run_step(page: Page, step: dict) -> None:
    action = step["action"]

    if action == "click":
        page.click(step["selector"])
    elif action == "fill":
        page.fill(step["selector"], str(step.get("value", "")))
    elif action == "select":
        page.select_option(step["selector"], step.get("value"))
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
    else:
        raise ValueError(f"알 수 없는 action: {action}")


def _fill_field(page: Page, field: dict, value: str) -> None:
    field_type = field["type"]
    selector = field["selector"]

    if field_type == "fill":
        page.fill(selector, str(value))
    elif field_type == "select":
        page.select_option(selector, str(value))
    elif field_type == "upload":
        page.set_input_files(selector, str(value))
    elif field_type == "check":
        if str(value).strip().lower() in ("1", "true", "y", "yes"):
            page.check(selector)
        else:
            page.uncheck(selector)
    else:
        raise ValueError(f"알 수 없는 field type: {field_type}")


def run_task_for_row(page: Page, task_config: dict, row: dict) -> None:
    """task_config(예: document_register.yaml)에 정의된 순서대로
    한 건(row)을 화면에 입력하고 제출한다."""

    for step in task_config.get("steps_before_form", []):
        _run_step(page, step)

    for field in task_config.get("fields", []):
        column = field["csv_column"]
        if column not in row:
            raise KeyError(f"CSV에 '{column}' 컬럼이 없습니다.")
        _fill_field(page, field, row[column])

    for step in task_config.get("steps_after_form", []):
        _run_step(page, step)

    success_selector = task_config.get("success_selector")
    if success_selector:
        page.wait_for_selector(success_selector, timeout=15000)
