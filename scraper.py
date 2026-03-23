"""
醫院叫號爬蟲 - 通用版
支援：requests 靜態抓取 + Playwright 動態渲染 fallback
用法：python scraper.py --url "醫院叫號網址" --my-number 117 --alert-before 5
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
import logging
import argparse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}

# ──────────────────────────────────────────────
# 1. 靜態抓取（requests + BeautifulSoup）
# ──────────────────────────────────────────────
def fetch_static(url: str, timeout: int = 8) -> str | None:
    """用 requests 抓取網頁原始 HTML"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding  # 自動偵測繁中編碼
        return resp.text
    except requests.exceptions.Timeout:
        logging.warning("靜態抓取逾時")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"靜態抓取失敗：{e}")
        return None


# ──────────────────────────────────────────────
# 2. 動態渲染（Playwright）— 當靜態抓不到號碼時自動啟用
# ──────────────────────────────────────────────
def fetch_dynamic(url: str, wait_ms: int = 4000) -> str | None:
    """用 Playwright headless 瀏覽器抓取 JS 渲染後的 HTML"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)  # 等待 JS 渲染
            html = page.content()
            browser.close()
            return html
    except ImportError:
        logging.warning("Playwright 未安裝，跳過動態模式。執行：pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        logging.warning(f"動態抓取失敗：{e}")
        return None


# ──────────────────────────────────────────────
# 3. 通用號碼解析器
# ──────────────────────────────────────────────
# 各醫院常見的叫號 CSS selector（持續補充）
KNOWN_SELECTORS = [
    # 台大醫院系統
    {"hospital": "台大系統", "current": ".current-no, .nowNo, #nowNo, td.now-num", "dept": ".dept-name, .deptName"},
    # 長庚系統
    {"hospital": "長庚系統", "current": ".clinicNowNo, .nowClinicNo, span[id*='NowNo']", "dept": ".deptchinese"},
    # 馬偕系統
    {"hospital": "馬偕系統", "current": "td[id*='curno'], span[id*='curno']", "dept": "td[id*='docname']"},
    # 國軍桃園 / 衛福部部立醫院系統
    {"hospital": "衛福部系統", "current": ".now_num, .call_num, td.callno, .opdNowNo", "dept": ".clinic_name, .deptname"},
    # 聯合醫院系統
    {"hospital": "台北聯合", "current": ".nowno, .now-no, #nowno", "dept": ".deptname, .dept"},
    # 奇美系統
    {"hospital": "奇美系統", "current": "span[class*='now'], td[class*='now']", "dept": "td[class*='dept']"},
]

NUMBER_PATTERNS = [
    r'目前看診[：:]\s*(\d+)',
    r'現在號碼[：:]\s*(\d+)',
    r'目前叫號[：:]\s*(\d+)',
    r'看診中[：:]\s*(\d+)',
    r'Call No[.:\s]+(\d+)',
    r'Now[:\s]+No\.?\s*(\d+)',
    r'現在.*?(\d{1,3})號',
    r'叫到.*?(\d{1,3})號',
]


def extract_current_number(html: str) -> dict:
    """
    從 HTML 中嘗試解析目前看診號碼。
    回傳：{"found": bool, "number": int|None, "method": str, "raw_text": str}
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- 方法 A：嘗試已知 selector ---
    for rule in KNOWN_SELECTORS:
        elements = soup.select(rule["current"])
        if elements:
            for el in elements:
                text = el.get_text(strip=True)
                nums = re.findall(r'\d+', text)
                if nums:
                    num = int(nums[0])
                    if 0 < num < 1000:  # 合理號碼範圍
                        logging.info(f"✅ 用 [{rule['hospital']}] selector 找到號碼：{num}")
                        return {"found": True, "number": num, "method": f"selector:{rule['hospital']}", "raw_text": text}

    # --- 方法 B：用 regex 全文搜尋 ---
    full_text = soup.get_text()
    for pattern in NUMBER_PATTERNS:
        match = re.search(pattern, full_text)
        if match:
            num = int(match.group(1))
            if 0 < num < 1000:
                logging.info(f"✅ 用 regex pattern 找到號碼：{num}")
                return {"found": True, "number": num, "method": "regex", "raw_text": match.group(0)}

    # --- 方法 C：找頁面上最顯眼的大數字（最後手段）---
    # 找字體較大的元素（通常叫號系統會用大字顯示）
    for tag in ["h1", "h2", "h3", "strong", "b", "span", "td", "div"]:
        for el in soup.find_all(tag):
            text = el.get_text(strip=True)
            if re.fullmatch(r'\d{1,3}', text):
                num = int(text)
                if 0 < num < 500:
                    logging.info(f"⚠️ 用大數字推測找到號碼：{num}（請確認是否正確）")
                    return {"found": True, "number": num, "method": "heuristic", "raw_text": text}

    logging.warning("❌ 無法從頁面解析到號碼，請手動檢查 HTML 結構")
    return {"found": False, "number": None, "method": "none", "raw_text": ""}


def get_current_number(url: str) -> dict:
    """
    主入口：先靜態抓，解析不到號碼就自動切換動態模式。
    """
    # 嘗試靜態
    html = fetch_static(url)
    if html:
        result = extract_current_number(html)
        if result["found"]:
            return result
        logging.info("靜態 HTML 解析不到號碼，改用 Playwright 動態模式...")

    # fallback 到動態
    html = fetch_dynamic(url)
    if html:
        result = extract_current_number(html)
        return result

    return {"found": False, "number": None, "method": "fetch_failed", "raw_text": ""}


# ──────────────────────────────────────────────
# 4. 監控主邏輯
# ──────────────────────────────────────────────
class QueueMonitor:
    def __init__(self, url: str, my_number: int, alert_before: int = 5, interval_sec: int = 60):
        self.url = url
        self.my_number = my_number
        self.alert_before = alert_before
        self.interval_sec = interval_sec
        self.history: list[dict] = []  # 歷史紀錄，用來計算速度

    def avg_time_per_number(self) -> float | None:
        """根據歷史紀錄估算每號平均幾秒"""
        if len(self.history) < 2:
            return None
        first = self.history[0]
        last = self.history[-1]
        num_diff = last["number"] - first["number"]
        time_diff = (last["timestamp"] - first["timestamp"]).total_seconds()
        if num_diff <= 0:
            return None
        return time_diff / num_diff

    def eta_minutes(self, current: int) -> str:
        """預估還需幾分鐘"""
        remaining = self.my_number - current
        avg = self.avg_time_per_number()
        if avg and remaining > 0:
            minutes = (avg * remaining) / 60
            return f"約 {minutes:.0f} 分鐘"
        return "計算中..."

    def run(self):
        logging.info(f"🏥 開始監控 | 我的號碼：{self.my_number} | 提前 {self.alert_before} 號提醒 | 網址：{self.url}")
        alerted = False

        while True:
            result = get_current_number(self.url)

            if not result["found"]:
                logging.warning(f"本次無法取得號碼，{self.interval_sec} 秒後重試...")
            else:
                current = result["number"]
                self.history.append({"number": current, "timestamp": datetime.now()})
                remaining = self.my_number - current
                eta = self.eta_minutes(current)

                # 突然跳號偵測
                if len(self.history) >= 2:
                    prev = self.history[-2]["number"]
                    if current - prev >= 10:
                        logging.warning(f"⚠️  偵測到跳號！{prev} → {current}，立刻重新計算...")
                        self.interval_sec = max(30, self.interval_sec // 2)  # 加快輪詢

                logging.info(f"目前號碼：{current} | 我的號碼：{self.my_number} | 剩餘：{remaining} 號 | ETA：{eta}")

                # 絕對警報（剩3號以內）
                if remaining <= 3 and remaining > 0:
                    self._alert("🚨 緊急！快輪到你了，立刻前往診間！", level="urgent")
                    break
                elif remaining <= 0:
                    self._alert("📣 你的號碼已到！立刻前往診間！", level="urgent")
                    break
                elif remaining <= self.alert_before and not alerted:
                    self._alert(f"⏰ 提醒：目前號碼 {current}，你的號碼 {self.my_number}，還有 {remaining} 號，{eta}，請準備前往！", level="warn")
                    alerted = True

            time.sleep(self.interval_sec)

    def _alert(self, message: str, level: str = "info"):
        """發出警報（目前印出 + 聲音提示，可擴充為 LINE Bot / FCM）"""
        border = "=" * 60
        logging.info(f"\n{border}\n{message}\n{border}")
        # 系統提示音（終端機）
        print("\a\a\a")
        # ── 可在此加入 LINE Bot / Email / FCM 推播 ──


# ──────────────────────────────────────────────
# 5. 命令列介面
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="醫院叫號監控器")
    parser.add_argument("--url", required=True, help="醫院即時看診進度網址")
    parser.add_argument("--my-number", type=int, required=True, help="你的掛號號碼")
    parser.add_argument("--alert-before", type=int, default=5, help="提前幾號發出提醒（預設 5）")
    parser.add_argument("--interval", type=int, default=60, help="輪詢間隔秒數（預設 60 秒）")
    parser.add_argument("--test", action="store_true", help="只測試是否能抓到號碼，不啟動監控")
    args = parser.parse_args()

    if args.test:
        print("\n🔍 測試模式：嘗試抓取號碼...")
        result = get_current_number(args.url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        monitor = QueueMonitor(
            url=args.url,
            my_number=args.my_number,
            alert_before=args.alert_before,
            interval_sec=args.interval
        )
        monitor.run()


if __name__ == "__main__":
    main()
