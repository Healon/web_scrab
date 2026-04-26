#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


WORKFLOW_FILE = "daily-price-report.yml"
LOCAL_TZ = ZoneInfo("Asia/Taipei")


def write_output(name: str, value: str) -> None:
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as file:
            file.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def github_api(path: str) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        raise RuntimeError("Missing GITHUB_TOKEN or GITHUB_REPOSITORY")

    request = Request(
        f"https://api.github.com/repos/{repository}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def has_successful_scheduled_run_today() -> bool:
    current_run_id = os.getenv("GITHUB_RUN_ID")
    today = datetime.now(LOCAL_TZ).date()
    data = github_api(f"/actions/workflows/{WORKFLOW_FILE}/runs?event=schedule&status=success&per_page=20")

    for run in data.get("workflow_runs", []):
        if str(run.get("id")) == str(current_run_id):
            continue
        created_at = run.get("created_at")
        if not created_at:
            continue
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        if created.date() == today and run.get("conclusion") == "success":
            return True
    return False


def main() -> int:
    if os.getenv("GITHUB_EVENT_NAME") != "schedule":
        write_output("should_run", "true")
        return 0

    try:
        should_run = "false" if has_successful_scheduled_run_today() else "true"
    except (HTTPError, RuntimeError, TimeoutError) as exc:
        print(f"Could not check previous scheduled runs; running report anyway: {exc}", file=sys.stderr)
        should_run = "true"

    write_output("should_run", should_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
