"""CLI 실행기: CSV의 각 행(건)에 대해 지정한 흐름(flow)을 처음부터 끝까지 반복 실행한다.

사용 예:
    python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv
    python main.py --task demolition_report_case --input data/demolition_report_case_sample.csv --headless
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from .browser import start_browser, attach_browser, login, load_yaml
from .engine import run_flow, run_setup


def read_rows(csv_path: str) -> list:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_result_log(results: list, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fieldnames = ["row_index", "status", "error_message", "screenshot_path", "timestamp"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="biz.blcm.go.kr 반복 작업 자동화")
    parser.add_argument("--task", required=True, help="작업 이름 (config/tasks/<task>.yaml)")
    parser.add_argument("--input", required=True, help="처리할 데이터 CSV 경로")
    parser.add_argument("--headless", action="store_true", help="브라우저 창을 띄우지 않음")
    parser.add_argument("--max-retries", type=int, default=1, help="행별 최대 재시도 횟수")
    parser.add_argument(
        "--channel",
        default="msedge",
        help=(
            "이미 설치된 브라우저를 사용 (msedge, chrome 등). "
            "빈 문자열('')로 지정하면 Playwright 번들 Chromium을 사용."
        ),
    )
    parser.add_argument(
        "--login-config", default="config/login.yaml", help="로그인 설정 YAML 경로"
    )
    parser.add_argument(
        "--attach",
        action="store_true",
        help=(
            "새 브라우저를 띄우고 자동 로그인하는 대신, 미리 사람이 로그인해둔 "
            "브라우저(원격 디버깅 포트로 띄운)에 붙어서 그 이후 작업만 실행"
        ),
    )
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        help="--attach 사용 시 붙을 브라우저 주소 (기본값: http://localhost:9222)",
    )
    args = parser.parse_args()

    load_dotenv()

    task_config_path = f"config/tasks/{args.task}.yaml"
    if not os.path.exists(task_config_path):
        print(
            f"[오류] {task_config_path} 가 없습니다. "
            f"config/tasks/{args.task}.example.yaml 을 복사해서 만드세요.",
            file=sys.stderr,
        )
        return 1
    if not args.attach and not os.path.exists(args.login_config):
        print(
            f"[오류] {args.login_config} 가 없습니다. "
            "config/login.example.yaml 을 복사해서 만드세요. "
            "(--attach 로 실행하면 로그인 설정 없이도 됩니다.)",
            file=sys.stderr,
        )
        return 1

    task_config = load_yaml(task_config_path)
    rows = read_rows(args.input)
    print(f"[정보] {len(rows)}건을 처리합니다. (task={args.task})")

    if args.attach:
        playwright, browser, context, page = attach_browser(args.cdp_url)
    else:
        playwright, browser, context, page = start_browser(
            headless=args.headless, channel=args.channel or None
        )
    results = []

    try:
        if args.attach:
            print(f"[정보] 이미 실행 중인 브라우저에 연결했습니다 ({args.cdp_url}). 로그인 단계는 건너뜁니다.")
        else:
            print("[정보] 로그인 중...")
            login(page, args.login_config)
            print("[정보] 로그인 완료")
            page.goto(task_config["start_url"])

        delay = task_config.get("delay_between_rows_seconds", 3)
        pages = {"main": page}

        print("[정보] 준비 작업(setup_steps) 실행 중...")
        run_setup(pages, task_config)
        # setup_steps로 연 탭(예: history)은 매 행마다 다시 만들지 않고 계속 재사용한다.
        persistent_keys = set(pages.keys())
        print("[정보] 준비 작업 완료")

        def close_extra_pages() -> None:
            """setup_steps로 연 탭은 남기고, 건별로 열렸던 팝업만 정리한다."""
            for key in list(pages.keys()):
                if key in persistent_keys:
                    continue
                try:
                    pages[key].close()
                except Exception:  # noqa: BLE001
                    pass
                del pages[key]

        # 건 사이/재시도 사이에 어느 탭을 어느 URL로 되돌릴지.
        # (기본값: setup_steps가 없으면 main+start_url, 있으면 명시적으로 지정)
        reset_cfg = task_config.get("reset", {})
        reset_page_key = reset_cfg.get("page", "main")
        reset_url = reset_cfg.get("url", task_config.get("start_url"))

        def reset_to_start() -> None:
            close_extra_pages()
            try:
                pages[reset_page_key].goto(reset_url)
            except Exception:  # noqa: BLE001
                pass

        for idx, row in enumerate(rows, start=1):
            status = "fail"
            error_message = ""
            screenshot_path = ""

            for attempt in range(1, args.max_retries + 1):
                try:
                    run_flow(pages, task_config, row)
                    status = "success"
                    error_message = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    error_message = f"(시도 {attempt}/{args.max_retries}) {exc}"
                    print(f"[경고] {idx}번째 행 실패: {error_message}")
                    os.makedirs("screenshots", exist_ok=True)
                    screenshot_path = f"screenshots/row_{idx}_attempt_{attempt}.png"
                    try:
                        pages[reset_page_key].screenshot(path=screenshot_path)
                    except Exception:  # noqa: BLE001
                        screenshot_path = ""
                    # 실패 후 다음 시도 전, 열려있던 팝업을 정리하고 시작 화면으로 복귀
                    reset_to_start()

            results.append(
                {
                    "row_index": idx,
                    "status": status,
                    "error_message": error_message,
                    "screenshot_path": screenshot_path,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

            print(f"[{idx}/{len(rows)}] {status}")

            if idx < len(rows):
                time.sleep(delay)
                reset_to_start()

    finally:
        os.makedirs("results", exist_ok=True)
        out_path = f"results/{args.task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        write_result_log(results, out_path)
        print(f"[정보] 결과 로그 저장: {out_path}")
        if args.attach:
            # 사람이 직접 띄운 브라우저이므로 우리가 닫지 않는다.
            # 연결만 끊는다 (탭/창은 그대로 둔다).
            playwright.stop()
        else:
            context.close()
            browser.close()
            playwright.stop()

    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"[완료] 성공 {success_count} / 전체 {len(results)}")
    return 0 if success_count == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
