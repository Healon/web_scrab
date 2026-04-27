# web_scrab

PChome / momo 商品價格爬蟲，會依照 `products.json` 的商品清單產生每日價格報告。

## 安裝

```bash
cd /Users/si-chinglin/Documents/codex/web_scrab
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 執行

直接印出報告：

```bash
python price_report.py
```

輸出到檔案：

```bash
python price_report.py --output reports/price_report_$(date +%Y%m%d_%H%M).md
```

傳送到 Telegram：

```bash
export TELEGRAM_BOT_TOKEN="你的 bot token"
export TELEGRAM_CHAT_ID="你的 chat id"
python price_report.py --output reports/latest.md
python send_telegram.py reports/latest.md
```

## GitHub Actions 雲端定時跑

這個資料夾已包含 `.github/workflows/daily-price-report.yml`，推到 GitHub 後會每天台北時間 12:07 自動執行，也可以在 Actions 頁面手動按 `Run workflow`。

目前排程時間：每天台北時間 12:07。

GitHub repo 需要設定兩個 secrets：

- `TELEGRAM_BOT_TOKEN`: Telegram BotFather 給你的 bot token
- `TELEGRAM_CHAT_ID`: 要接收報告的個人、群組或頻道 chat id

設定位置：

`GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret`

如果還沒設定 Telegram secrets，workflow 仍會產生報告 artifact，但會略過 Telegram 傳送。

每日排程預設會在部分商品抓取失敗時繼續送出報告，讓 Telegram 也能收到失敗明細。若要在本機用嚴格模式檢查，可加上 `--fail-on-missing`。

GitHub Actions 的 scheduled workflow 不是精準排程服務，偶爾可能延遲或漏觸發；目前依使用需求維持單一 12:07 排程。

如果你的 GitHub repo 根目錄不是 `web_scrab`，要把 `.github/workflows/daily-price-report.yml` 放到 repo 根目錄，並把 workflow 裡的路徑改成 `web_scrab/requirements.txt`、`web_scrab/price_report.py` 等。

## 修改商品

編輯 `products.json`。每個商品可放多個 `targets`，目前支援：

- `store`: `PChome` 或 `Momo`
- `label`: 報告中顯示的商品名稱，可省略
- `url`: 商品頁網址

## 注意

momo 與 PChome 頁面可能會調整版型或加強防爬；如果價格抓取失敗，程式會在報告中標示「抓取失敗」，方便後續調整解析規則。

PChome API 目前會回傳 `M`、`P`、`Low` 等價格欄位；本程式用 `P` 當報告中的「售價」。
