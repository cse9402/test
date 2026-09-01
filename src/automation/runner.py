"""CLI 실행기: CSV의 각 행에 대해 지정한 작업(task)을 반복 실행한다.

사용 예:
    python main.py --task document_register --input data/document_register_sample.csv
    python main.py --task civil_complaint --input data/civil_complaint_sample.csv --headless
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from .browser import start_browser, login, load_yaml
from .engine import run_task_for_row


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
        "--login-config", default="config/login.yaml", help="로그인 설정 YAML 경로"
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
    if not os.path.exists(args.login_config):
        print(
            f"[오류] {args.login_config} 가 없습니다. "
            "config/login.example.yaml 을 복사해서 만드세요.",
            file=sys.stderr,
        )
        return 1

    task_config = load_yaml(task_config_path)
    rows = read_rows(args.input)
    print(f"[정보] {len(rows)}건을 처리합니다. (task={args.task})")

    playwright, browser, context, page = start_browser(headless=args.headless)
    results = []

    try:
        print("[정보] 로그인 중...")
        login(page, args.login_config)
        print("[정보] 로그인 완료")

        page.goto(task_config["start_url"])

        delay = task_config.get("delay_between_rows_seconds", 3)

        for idx, row in enumerate(rows, start=1):
            status = "fail"
            error_message = ""
            screenshot_path = ""

            for attempt in range(1, args.max_retries + 1):
                try:
                    run_task_for_row(page, task_config, row)
                    status = "success"
                    error_message = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    error_message = f"(시도 {attempt}/{args.max_retries}) {exc}"
                    print(f"[경고] {idx}번째 행 실패: {error_message}")
                    os.makedirs("screenshots", exist_ok=True)
                    screenshot_path = f"screenshots/row_{idx}_attempt_{attempt}.png"
                    try:
                        page.screenshot(path=screenshot_path)
                    except Exception:  # noqa: BLE001
                        screenshot_path = ""
                    # 실패 후 다음 시도 전 시작 화면으로 복귀
                    try:
                        page.goto(task_config["start_url"])
                    except Exception:  # noqa: BLE001
                        pass

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
                page.goto(task_config["start_url"])

    finally:
        os.makedirs("results", exist_ok=True)
        out_path = f"results/{args.task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        write_result_log(results, out_path)
        print(f"[정보] 결과 로그 저장: {out_path}")
        context.close()
        browser.close()
        playwright.stop()

    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"[완료] 성공 {success_count} / 전체 {len(results)}")
    return 0 if success_count == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
