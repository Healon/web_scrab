#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

import requests


MAX_MESSAGE_LENGTH = 3900


def chunk_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_message(bot_token: str, chat_id: str, text: str, timeout: int) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )
    response.raise_for_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把價格報告傳送到 Telegram")
    parser.add_argument("report", help="報告檔案路徑")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout 秒數")
    parser.add_argument("--allow-missing-secrets", action="store_true", help="缺少 Telegram secrets 時略過傳送")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        message = "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        if args.allow_missing_secrets:
            print(f"{message}; skip Telegram send.")
            return 0
        print(message, file=sys.stderr)
        return 2

    text = Path(args.report).read_text(encoding="utf-8")
    for index, chunk in enumerate(chunk_text(text), start=1):
        prefix = "" if index == 1 else f"Part {index}\n\n"
        send_message(bot_token, chat_id, prefix + chunk, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
