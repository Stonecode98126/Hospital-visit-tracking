# 804 桃園國軍總醫院看診提醒系統｜架構文件 v3

## 系統概覽

讓病患在等候看診期間可以自由離開，快輪到時自動收到提醒通知。

---

## 目前檔案結構

```
hospital-netlify/
├── index.html                  ← 前端主頁面（三步驟流程）
├── netlify.toml                ← Netlify 部署設定
├── netlify/
│   └── functions/
│       └── scrape.js           ← 後端爬蟲 API（供其他醫院使用）
└── architecture.md             ← 本文件
```

---

## 系統架構

### 國軍桃園（目前上線）

```
使用者手機瀏覽器
      ↓ fetch（直接）
Cloudflare Worker
aftygh-proxy.owen163.workers.dev
      ↓ 轉發請求
www.aftygh.gov.tw/opd/opdservice.php
      ↓ 回傳 HTML input 格式資料
前端解析 → 顯示診間清單 → 用戶選擇 → 開始監控 → 推播通知
```

**為什麼要用 Cloudflare Worker？**
- 醫院網站有 Cloudflare 防護，Netlify 伺服器 IP 會被封鎖（403）
- 使用者瀏覽器直接打 API 會被 CORS 擋住
- Cloudflare Worker 跑在 Cloudflare 內部網路，不會被擋，同時幫前端加上 CORS header

### 其他醫院（待新增）

```
使用者手機瀏覽器
      ↓ fetch
Netlify Function /api/scrape
      ↓ 伺服器端抓取
各醫院即時看診進度網頁
      ↓ 解析 HTML table
回傳 JSON 診間清單
```

---

## API 資料格式

### opdservice.php 回傳格式

HTML input 欄位，每個診間索引 i 對應：

| 欄位 | 說明 | 範例 |
|---|---|---|
| `clinname{i}` | 診間名稱 | 家醫科、骨科一診 |
| `drname{i}` | 醫生姓名 | 張永宗 |
| `oncallnum{i}` | 目前叫號號碼 | 56 |
| `nowroomnum{i}` | 診間編號 | 0101 |
| `divnname{i}` | 科別大分類 | 內科、外科、骨科 |
| `timetype{i}` | 類型 | 1=門診, 4=領藥 |
| `totalidx` | 總診間數 | 23 |

---

## 使用者流程

```
STEP 1 選醫院
  └─ 點選「804 桃園國軍總醫院」
  └─ 按「查詢即時診間資訊」
  └─ 系統透過 Cloudflare Worker 抓取即時資料

STEP 2 選診間
  └─ 依科別分組顯示所有診間
  └─ 每張卡片顯示：診間名稱、醫生、目前號碼
  └─ 可搜尋科別或醫生姓名
  └─ 點選診間進入下一步

STEP 3 填號碼
  └─ 輸入自己的掛號號碼
  └─ 設定提前幾號提醒
  └─ 設定輪詢間隔（建議 60 秒）
  └─ 按「開始監控」

監控中
  └─ 每 N 秒自動更新一次號碼
  └─ 顯示進度條、預估等待時間
  └─ 偵測跳號（超過 10 號自動警告）
  └─ 快輪到時：推播通知 + 聲音 + 頁面警報
```

---

## 新增其他醫院步驟

### A. 有 JSON API 的醫院（最穩定）
1. F12 → Network → XHR 找到 API 網址
2. 在 `HOSPITALS` 陣列新增 `directApi` 和對應的 `directParser`
3. 在前端寫對應的解析函式

### B. 需要 Cloudflare Worker 的醫院
1. 在 Cloudflare 新建一個 Worker，修改目標 URL
2. 在 `HOSPITALS` 陣列設定 `directApi` 指向新 Worker

### C. 一般 HTML table 醫院（走後端）
1. 分析網頁 table 欄位順序
2. 在 `scrape.js` 的 `HOSPITAL_PARSERS` 新增規則
3. 在 `HOSPITALS` 陣列新增醫院資訊

---

## 技術堆疊

| 層級 | 技術 | 用途 |
|---|---|---|
| 前端 | 純 HTML/CSS/JS | 使用者介面、三步驟流程 |
| Proxy | Cloudflare Workers（免費） | 轉發國軍桃園 API，解決 CORS |
| 後端 | Netlify Functions（免費） | 其他醫院的伺服器端爬蟲 |
| 部署 | Netlify + GitHub | 自動部署 |
| 通知 | Web Notification API | 瀏覽器推播通知 |

---

## 待辦事項

- [ ] 新增更多醫院支援
- [ ] LINE Bot 推播整合
- [ ] 多人共享等候室（家人同步收到通知）
- [ ] Google Maps 路程時間整合
- [ ] 醫院端 B2B 白標方案
