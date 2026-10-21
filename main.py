"""便利帶會員專網自動化：登入 → 呼叫快遞 → 小件填 30 → 按「呼叫」。

帳號密碼由環境變數 MEMBER_USERNAME / MEMBER_PASSWORD 提供
（在 Cloud Run 上由 Secret Manager 注入，不寫在程式裡）。
國定假日（依行政院人事行政總處辦公日曆）會自動跳過；設 FORCE_RUN=true 可強制執行。
設 DRY_RUN=true 只填欄位、不按「呼叫」，測試時不會真的叫快遞。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://member.25431010.tw/auth/login"
# 政府辦公日曆的 JSON 版本（github.com/ruyut/TaiwanCalendar）
CALENDAR_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"
SMALL_PARCELS = "30"

TAIPEI = timezone(timedelta(hours=8))
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() == "true"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def log(msg):
    print(f"[{datetime.now(TAIPEI):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def is_day_off(today):
    """依政府辦公日曆判斷今天是否放假；讀不到行事曆時改用「週六日放假」判斷。"""
    try:
        with urllib.request.urlopen(CALENDAR_URL.format(year=today.year), timeout=15) as r:
            days = json.load(r)
        key = today.strftime("%Y%m%d")
        for d in days:
            if d["date"] == key:
                if d["isHoliday"]:
                    log(f"今天放假（{d['description'] or '週末'}）")
                return d["isHoliday"]
        log("行事曆裡找不到今天，改用週六日判斷")
    except Exception as e:
        log(f"讀取行事曆失敗（{e}），改用週六日判斷")
    return today.weekday() >= 5


def login(page, username, password):
    page.goto(LOGIN_URL)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda url: "/auth/login" not in url, timeout=20_000)
    except PWTimeout:
        raise RuntimeError("登入失敗：20 秒內沒有離開登入頁（帳密錯誤或網站異常）")
    log(f"登入成功，目前頁面：{page.url}")


def button(page, text):
    """文字完全等於 text 的按鈕（「呼叫」不會誤配到「呼叫快遞」）；
    若不是真正的 <button>，就退而找該文字的元素。"""
    return page.get_by_role("button", name=text, exact=True).or_(page.get_by_text(text, exact=True)).first


def input_for(page, label):
    """依序找：<label> 關聯的欄位、placeholder 為 label 的欄位、label 文字後面的第一個 input。"""
    following = page.locator(f"xpath=//*[contains(normalize-space(text()), '{label}')]/following::input[1]")
    return page.get_by_label(label).or_(page.get_by_placeholder(label)).or_(following).first


def do_task(page):
    button(page, "呼叫快遞").click()
    log("已點選「呼叫快遞」")

    small = input_for(page, "小件")
    small.fill(SMALL_PARCELS)
    log(f"「小件」已填入：{small.input_value()}")

    if DRY_RUN:
        log("DRY_RUN=true，不按「呼叫」")
        return
    # 若網站跳出瀏覽器原生的確認視窗，就按「確定」（Playwright 預設會按取消）
    def accept(dialog):
        log(f"確認視窗：{dialog.message}")
        dialog.accept()

    page.on("dialog", accept)
    button(page, "呼叫").click()
    log("已按下「呼叫」")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeout:
        pass


def main():
    today = datetime.now(TAIPEI).date()
    if FORCE_RUN:
        log("FORCE_RUN=true，略過假日判斷")
    elif is_day_off(today):
        log("今天不執行")
        return 0

    username = os.environ.get("MEMBER_USERNAME")
    password = os.environ.get("MEMBER_PASSWORD")
    if not username or not password:
        log("缺少 MEMBER_USERNAME 或 MEMBER_PASSWORD 環境變數")
        return 2

    with sync_playwright() as p:
        # 有畫面時每個動作放慢 0.5 秒，方便看清楚
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 500)
        context = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei")
        page = context.new_page()
        page.set_default_timeout(30_000)
        try:
            login(page, username, password)
            do_task(page)
            log("任務完成")
            return 0
        except Exception as e:
            log(f"任務失敗：{e}（當下頁面：{page.url}）")
            page.screenshot(path="error.png", full_page=True)
            return 1
        finally:
            if not HEADLESS:
                input("按 Enter 關閉瀏覽器...")
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
