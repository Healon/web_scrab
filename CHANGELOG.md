# Changelog

## 2026-04-25

- 建立 PChome / momo 每日價格爬蟲。
- 加入 GitHub Actions 雲端排程與 Telegram 通知。
- 設定 GitHub repo secrets：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。
- 修正排程報告行為：即使部分商品抓取失敗，仍會送出 Telegram 報告。
- 加入 momo 抓取失敗診斷，若遇到逾時、HTTP 403/429/503、驗證頁或阻擋頁，會在報告標示疑似反爬蟲/限流。
- 將每日自動抓取時間由台北時間 12:45 調整為 12:00。
- 因 GitHub Actions 整點排程可能延遲或被丟棄，將每日自動抓取時間由台北時間 12:00 調整為 12:07。
