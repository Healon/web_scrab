#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


@dataclass
class ScrapedItem:
    store: str
    url: str
    name: str | None = None
    price: int | None = None
    error: str | None = None
    diagnosis: str | None = None


class PriceScraper:
    def __init__(self, timeout: int = 20, sleep_seconds: float = 1.0) -> None:
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            }
        )

    def scrape(self, target: dict[str, str]) -> ScrapedItem:
        store = target["store"]
        url = target["url"]
        try:
            if store.lower() == "pchome":
                item = self._scrape_pchome(url)
            elif store.lower() == "momo":
                item = self._scrape_momo(url)
            else:
                item = self._scrape_generic(store, url)
            item.name = target.get("label") or item.name
            return item
        except Exception as exc:
            return ScrapedItem(
                store=store,
                url=url,
                name=target.get("label"),
                error=self._short_error(exc),
                diagnosis=self._diagnose_failure(store, exc=exc),
            )
        finally:
            time.sleep(self.sleep_seconds)

    def _get_html(self, url: str, referer: str | None = None) -> str:
        headers = {"Referer": referer} if referer else None
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    def _get_json(self, url: str, referer: str | None = None) -> Any:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": referer or "https://24h.pchome.com.tw/",
        }
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        text = response.text.strip()
        text = re.sub(r"^[^(]+\((.*)\)\s*;?$", r"\1", text, flags=re.S)
        return json.loads(text)

    def _scrape_pchome(self, url: str) -> ScrapedItem:
        product_id = url.rstrip("/").split("/")[-1]
        api_url = (
            "https://ecapi.pchome.com.tw/ecshop/prodapi/v2/prod/button"
            f"&id={product_id}&fields=Id,Name,Nick,Price,Qty,ButtonType,SaleStatus"
        )
        try:
            data = self._get_json(api_url, referer=url)
            product = data[0] if isinstance(data, list) and data else data
            price = self._pchome_price(product)
            name = self._first_str(product, ("Nick", "Name", "name", "ProdName"))
            if price:
                return ScrapedItem(store="PChome", url=url, name=name, price=price)
        except Exception:
            pass

        html = self._get_html(url)
        name, price = self._parse_html_product(html)
        return ScrapedItem(store="PChome", url=url, name=name, price=price)

    def _scrape_momo(self, url: str) -> ScrapedItem:
        html = self._get_html(url, referer="https://www.momoshop.com.tw/")
        name, price = self._parse_html_product(html)
        if not price:
            price = self._parse_momo_price(html)
        diagnosis = None if price else self._diagnose_failure("Momo", html=html)
        error = None if price else "找不到可解析價格"
        return ScrapedItem(store="Momo", url=url, name=name, price=price, error=error, diagnosis=diagnosis)

    def _scrape_generic(self, store: str, url: str) -> ScrapedItem:
        html = self._get_html(url)
        name, price = self._parse_html_product(html)
        return ScrapedItem(store=store, url=url, name=name, price=price)

    def _parse_html_product(self, html: str) -> tuple[str | None, int | None]:
        soup = BeautifulSoup(html, "html.parser")
        jsonld_items = []
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text()
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                jsonld_items.extend(parsed)
            else:
                jsonld_items.append(parsed)

        for item in jsonld_items:
            product = self._find_product_jsonld(item)
            if not product:
                continue
            name = self._clean_text(product.get("name"))
            offers = product.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = self._first_int(offers, ("price", "lowPrice", "highPrice"))
            if price:
                return name, price

        name = self._meta_content(soup, "property", "og:title") or self._title_text(soup)
        price = self._meta_price(soup) or self._regex_price(html)
        return self._clean_text(name), price

    def _parse_momo_price(self, html: str) -> int | None:
        patterns = [
            r'"goodsPrice"\s*:\s*"?([0-9,]+)"?',
            r'"salePrice"\s*:\s*"?([0-9,]+)"?',
            r'"price"\s*:\s*"?([0-9,]+)"?',
            r"促銷價\s*[$＄]?\s*([0-9,]+)",
            r"折扣價\s*[$＄]?\s*([0-9,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return self._to_int(match.group(1))
        return None

    def _find_product_jsonld(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        item_type = item.get("@type")
        if item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type):
            return item
        graph = item.get("@graph")
        if isinstance(graph, list):
            for child in graph:
                product = self._find_product_jsonld(child)
                if product:
                    return product
        return None

    def _meta_content(self, soup: BeautifulSoup, attr: str, value: str) -> str | None:
        tag = soup.find("meta", attrs={attr: value})
        if not tag:
            return None
        content = tag.get("content")
        return str(content) if content else None

    def _meta_price(self, soup: BeautifulSoup) -> int | None:
        for attr, value in [
            ("property", "product:price:amount"),
            ("property", "og:price:amount"),
            ("name", "price"),
        ]:
            content = self._meta_content(soup, attr, value)
            if content:
                price = self._to_int(content)
                if price:
                    return price
        return None

    def _title_text(self, soup: BeautifulSoup) -> str | None:
        if soup.title and soup.title.string:
            return soup.title.string
        h1 = soup.find("h1")
        return h1.get_text(" ", strip=True) if h1 else None

    def _regex_price(self, html: str) -> int | None:
        text = unescape(html)
        patterns = [
            r"(?:售價|折扣價|促銷價|特價|price|Price)\D{0,20}([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})",
            r"NT\$\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})",
        ]
        prices: list[int] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                price = self._to_int(match.group(1))
                if price and 10 <= price <= 500000:
                    prices.append(price)
        return min(prices) if prices else None

    def _first_int(self, data: Any, keys: tuple[str, ...]) -> int | None:
        if not isinstance(data, dict):
            return None
        for key in keys:
            if key in data:
                price = self._to_int(data[key])
                if price:
                    return price
        return None

    def _pchome_price(self, product: Any) -> int | None:
        if not isinstance(product, dict):
            return None
        price = product.get("Price")
        if isinstance(price, dict):
            # PChome exposes M as list price, P as displayed sale price, and Low as
            # member/coupon-style low price. The requested report uses the sale price.
            parsed = self._first_int(price, ("P", "Low", "M"))
            if parsed:
                return parsed
        return self._first_int(product, ("Price", "price", "SalePrice", "discountPrice"))

    def _first_str(self, data: Any, keys: tuple[str, ...]) -> str | None:
        if not isinstance(data, dict):
            return None
        for key in keys:
            value = data.get(key)
            cleaned = self._clean_text(value)
            if cleaned:
                return cleaned
        return None

    def _to_int(self, value: Any) -> int | None:
        if value is None:
            return None
        match = re.search(r"[0-9][0-9,]*", str(value))
        return int(match.group(0).replace(",", "")) if match else None

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text or None

    def _short_error(self, exc: Exception) -> str:
        if isinstance(exc, requests.exceptions.Timeout) or "timed out" in str(exc).lower():
            return "Read timed out"
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            return f"HTTP {exc.response.status_code}"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "Connection error"
        return str(exc)

    def _diagnose_failure(self, store: str, exc: Exception | None = None, html: str | None = None) -> str | None:
        if store.lower() != "momo":
            return None

        message = str(exc).lower() if exc else ""
        status_code = None
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code

        if isinstance(exc, requests.exceptions.Timeout) or "timed out" in message:
            return "疑似 momo 反爬蟲/限流：連線逾時，GitHub Actions IP 可能被延遲或暫時限制"
        if status_code in {403, 429, 503}:
            return f"疑似 momo 反爬蟲/限流：回傳 HTTP {status_code}"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "可能是 momo 暫時阻擋或網路不穩：連線失敗"

        if html:
            lowered = html.lower()
            block_keywords = (
                "captcha",
                "recaptcha",
                "access denied",
                "forbidden",
                "robot",
                "驗證",
                "安全檢查",
                "系統忙碌",
            )
            if any(keyword in lowered for keyword in block_keywords):
                return "疑似 momo 反爬蟲：回傳驗證、阻擋或安全檢查頁"
            return "可能是 momo 動態載入或版型變更；若同批多筆 momo 失敗，偏向反爬蟲/限流"

        return "可能是 momo 反爬蟲/限流或暫時性網路異常"


def load_products(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("products.json must contain a list")
    return data


def store_icon(store: str) -> str:
    return "🛒" if store.lower() == "pchome" else "🛍️"


def price_label(store: str) -> str:
    return "售價" if store.lower() == "pchome" else "折扣價"


def format_report(products: list[dict[str, Any]], scraped: dict[str, ScrapedItem], report_time: datetime) -> str:
    momo_failures = [
        item for item in scraped.values()
        if item.store.lower() == "momo" and item.price is None
    ]
    lines = [
        f"每日價格報告 {report_time:%Y/%m/%d %H:%M}",
        "",
        "",
    ]
    if momo_failures:
        suspected = sum(1 for item in momo_failures if item.diagnosis and "反爬蟲" in item.diagnosis)
        lines.extend(
            [
                f"⚠️ momo 抓取異常 {len(momo_failures)} 筆，其中 {suspected} 筆疑似反爬蟲/限流或阻擋",
                "",
            ]
        )

    for product in products:
        lines.append(f"📌 {product['title']}")
        grouped: dict[str, list[dict[str, str]]] = {}
        for target in product.get("targets", []):
            grouped.setdefault(target["store"], []).append(target)

        for store, targets in grouped.items():
            lines.append(f"{store_icon(store)} {store}")
            for target in targets:
                item = scraped[target["url"]]
                name = target.get("label") or item.name
                if name and store.lower() == "pchome":
                    lines.append(f"  • {name}")
                elif name and len(targets) > 1:
                    lines.append(f"  • {name}")

                if item.price:
                    lines.append(f"    💰 {price_label(store)} NT${item.price}")
                else:
                    detail = f" ({item.error})" if item.error else ""
                    lines.append(f"    💰 {price_label(store)} 抓取失敗{detail}")
                    if item.diagnosis:
                        lines.append(f"    ⚠️ 判斷：{item.diagnosis}")
                lines.append(f"    🔗 {item.url}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 PChome / momo 商品價格並產生每日價格報告")
    parser.add_argument("--products", default="products.json", help="商品清單 JSON 路徑")
    parser.add_argument("--output", default="", help="輸出報告檔案路徑；不填則印到終端機")
    parser.add_argument("--sleep", type=float, default=1.0, help="每次請求間隔秒數")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout 秒數")
    parser.add_argument("--timezone", default="Asia/Taipei", help="報告時間使用的時區")
    parser.add_argument("--fail-on-missing", action="store_true", help="有商品價格抓取失敗時回傳非 0 exit code")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    products_path = Path(args.products)
    if not products_path.is_absolute():
        products_path = base_dir / products_path

    products = load_products(products_path)
    scraper = PriceScraper(timeout=args.timeout, sleep_seconds=args.sleep)
    scraped: dict[str, ScrapedItem] = {}

    for product in products:
        for target in product.get("targets", []):
            scraped[target["url"]] = scraper.scrape(target)

    report = format_report(products, scraped, datetime.now(ZoneInfo(args.timezone)))
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = base_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    failures = [item for item in scraped.values() if item.price is None]
    return 1 if args.fail_on_missing and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
