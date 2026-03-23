# 醫院看診追蹤與導航預測：系統架構設計 (Map Integration & Architecture)

本文件概述了將「看診定時監控邏輯 (Polling Engine)」與「路程時間動態判斷 (Traffic-Aware ETA)」整合的技術架構與落地方案。

---

## 1. 架構總覽

整個服務建議拆分為 **前端 UI (Client App)** 與 **後端監控服務 (Worker/Cron Server)** 兩部分，透過 API 溝通。
- **Client App (如 Flutter/React Native/Web):** 負責讓使用者選擇診間、輸入號碼、並請求開啟訂閱通知。
- **後端監控服務 (Node.js/Python 伺服器):** 負責 24 小時執行網頁爬蟲、獲取 Google Maps 即時路況，並判斷何時發送 Push Notification (推播通知) 給使用者。

---

## 2. 背景定時監控 (Polling Engine) 落地方案

行動裝置的作業系統（iOS 尤其是 Android）為了省電，經常會強制中止長駐在背景的應用程序。因此，**「不建議將高頻率掃描的邏輯直接寫在手機 App 的背景執行的機制中」**。

### 推薦方案：Cloud-Based Polling (雲端輪詢 + 推播)
1. **觸發端：** 使用者在 App 端點擊「開始追蹤」，App 將 Device Token (FCM Token)、使用者當前 GPS 座標、目標診間ID、使用者號碼發送給後端資料庫 (如 Firebase/PostgreSQL)。
2. **處理端：** 後端伺服器 (如 Vercel Cron, Render, 或自建 Node.js Worker) 每 2~3 分鐘執行一次任務。
3. **爬取邏輯：** 爬蟲抓取 `https://www.aftygh.gov.tw/opd/` 獲取最新號碼。
4. **過濾警報：**
   - **突然跳號處理：** 若上一次號碼與這次抓到的號碼差距過大 (例如 10 號直接跳 40 號)，後端應在此次輪詢立刻拉取 Google Maps 重新計算時間，不可等待下一輪。
   - **無效狀態防護：** 若爬蟲 Timeout，捕獲例外 (Try-Catch)，後端保留上次資料並不做任何干涉，直到下次輪詢成功。

---

## 3. 路程時間動態判斷 (Traffic-Aware ETA)

核心機制是透過整合 **Google Maps API (Distance Matrix API)** 來實現基於「目前車況」的最精準預測。

### 流程拆解
當 `剩餘人數 <= 一定閥值 (例如 10人)` 時，伺服器啟動 Google Maps API 呼叫，避免過早呼叫浪費 API 額度。

**呼叫範例 (Node.js/Axios 概念):**
```javascript
const origin = `${userLat},${userLng}`; // 來自 App 的 GPS 座標
const destination = "24.8576,121.2185"; // 國軍桃園總醫院座標
const apiKey = "YOUR_GOOGLE_MAPS_API_KEY";

const url = `https://maps.googleapis.com/maps/api/distancematrix/json?origins=${origin}&destinations=${destination}&mode=driving&departure_time=now&key=${apiKey}`;

// 解析回應中的 duration_in_traffic
// example: 1200 seconds (20 mins)
```

### 預測演算法 (ETA Logic)

假設每位病患平均看診時間為 $T_{avg}$ (例如 4 分鐘)。

- **所需總等待時間 ($WaitTime$)** = `剩餘人數 * 4 分鐘`
- **即時交通路程時間 ($CommuteTime$)** = 來自 Google Maps 的分鐘數
- **預留緩衝時間 ($BufferTime$)** = 10 分鐘 (找車位、步行到診間的餘裕)

**觸發條件式：**
```python
if WaitTime <= (CommuteTime + BufferTime):
    trigger_push_notification(user_id, "該出門囉！目前路上依路況約需", CommuteTime, "分鐘，預計抵達時剛好輪到您！")
```

#### 特殊情境處理 (Edge Cases)
1. **醫生跳號/患者過多未到 (醫生提早打卡)：**
   - 解決方法：除了時間條件外，設定一個「絕對底線閾值」。例如「無論家住多近或多遠，只要剩餘人數小於 3 人，無條件發送最強烈等級警報」。
2. **交通產生突發嚴重壅塞 (車禍等)：**
   - 解決方法：在剩餘人數低於 15 人時，提高 API 輪詢頻率（例如每 1 分鐘打一次 Google Maps API），動態更新 $CommuteTime$。若預判所需交通時間激增，提早觸發警報。

---

## 4. 交付與總結
- **維護性考量：** 醫院網站若改版，需快速更新爬蟲規則。可考慮採用無頭瀏覽器 (Headless Browser) 如 Playwright 作為備案，以處理依賴複雜 JavaScript 渲染的頁面。
- **使用者體驗：** 使用 LINE Bot 做為介面也是極佳的替代方案，能免去使用者下載 App，並透過 Webhook 將上述後端架構平滑接軌至 LINE 訊息服務上。
