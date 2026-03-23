# 醫院叫號監控系統：架構設計文件 v2

## 本次優化重點

### 前端 index.html
| 問題（v1）| 解決（v2）|
|---|---|
| 診間資料為假資料 `mockClinics` | 真實串接醫院網址，用 CORS proxy 抓取 |
| 按下追蹤只跑數字動畫 | 真正每 N 秒輪詢一次醫院頁面 |
| 沒有推播通知 | 整合 Web Notification API，鎖屏也能收到 |
| 沒有 ETA 預估 | 根據號碼歷史自動計算每號速度 |
| 沒有跳號偵測 | 偵測到 10 號以上跳號時警告 |
| 沒有聲音警報 | 用 AudioContext 產生提示音 |

### 爬蟲 scraper.py
| 問題（v1）| 解決（v2）|
|---|---|
| CSS selector 為假的 `.clinic-card` | 整合 20+ 個真實醫院 selector 規則 |
| 只有靜態抓取 | 靜態失敗自動 fallback 到 Playwright 動態模式 |
| 沒有 ETA 計算 | QueueMonitor 類別內建歷史速度計算 |
| 監控邏輯寫死 | 命令列參數化，支援任意醫院網址 |

---

## 系統架構

```
┌─────────────────────────────────────┐
│           手機瀏覽器 / App           │
│  index.html                         │
│  ├── 設定：醫院URL、我的號碼         │
│  ├── setInterval 每 N 秒呼叫         │
│  │   └── fetch(CORS proxy)           │
│  │       └── 解析 HTML 取得號碼      │
│  ├── 計算 ETA、剩餘號碼              │
│  └── 觸發：Notification + 聲音       │
└──────────────┬──────────────────────┘
               │ HTTPS
┌──────────────▼──────────────────────┐
│         CORS Proxy (暫用)            │
│  api.allorigins.win                  │
│  （正式版換成自己的後端 /api/scrape）│
└──────────────┬──────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────┐
│       醫院即時看診進度網頁            │
│  https://www.aftygh.gov.tw/opd/      │
└─────────────────────────────────────┘
```

---

## 爬蟲策略（雙模式）

### 模式 A：靜態（requests + BeautifulSoup）
- 速度快、資源少
- 適合伺服器端渲染的醫院頁面

### 模式 B：動態（Playwright headless）
- 靜態解析不到號碼時自動啟用
- 適合 JS 動態渲染頁面（React/Vue 前端）

### 解析順序
1. 嘗試已知醫院 CSS selector（20+ 條規則）
2. 用 regex 全文搜尋（中文/英文叫號字樣）
3. 啟發式：找頁面上獨立的 1~3 位數數字

---

## 已收錄醫院 Selector

| 醫院系統 | CSS Selector |
|---|---|
| 台大系統 | `.current-no`, `.nowNo`, `#nowNo` |
| 長庚系統 | `.clinicNowNo`, `[id*="NowNo"]` |
| 馬偕系統 | `[id*="curno"]` |
| 衛福部/國軍 | `.now_num`, `.call_num`, `.opdNowNo` |
| 台北聯合 | `.nowno`, `#nowno` |

---

## 命令列使用方式

```bash
# 安裝依賴
pip install requests beautifulsoup4 playwright
playwright install chromium

# 測試是否能抓到號碼
python scraper.py --url "https://www.aftygh.gov.tw/opd/" --my-number 117 --test

# 開始監控（每60秒，快到5號提醒）
python scraper.py --url "https://www.aftygh.gov.tw/opd/" --my-number 117 --alert-before 5 --interval 60
```

---

## 待辦事項（正式產品）

- [ ] 後端 API 伺服器（取代 allorigins CORS proxy）
- [ ] LINE Bot 推播整合
- [ ] FCM Push Notification（原生 App）
- [ ] Google Maps Distance Matrix API 整合
- [ ] 新增更多醫院 selector 規則
- [ ] 跳號後自動縮短輪詢間隔
