/**
 * Netlify Scheduled Function: /api/notify
 * 每分鐘自動執行，檢查所有訂閱用戶的號碼，快輪到時推播通知
 */

const https = require('https');
const http  = require('http');
const webpush = require('web-push');
const { getStore } = require('@netlify/blobs');

// VAPID 金鑰設定
webpush.setVapidDetails(
  'mailto:admin@visit-tracking.netlify.app',
  process.env.VAPID_PUBLIC_KEY,
  process.env.VAPID_PRIVATE_KEY
);

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json; charset=utf-8',
  };

  try {
    const store = getStore('subscriptions');
    const { keys } = await store.list();

    if (!keys || keys.length === 0) {
      return { statusCode: 200, headers, body: JSON.stringify({ ok: true, checked: 0 }) };
    }

    let checked = 0, notified = 0, errors = 0;

    // 依醫院 URL 分組，同一家醫院只抓一次
    const tasksByUrl = {};
    const records = {};

    for (const { name: key } of keys) {
      try {
        const record = await store.get(key, { type: 'json' });
        if (!record || !record.task) continue;
        records[key] = record;
        const url = record.task.url;
        if (!tasksByUrl[url]) tasksByUrl[url] = [];
        tasksByUrl[url].push(key);
      } catch {}
    }

    // 每個醫院只抓一次資料
    const clinicsCache = {};
    for (const url of Object.keys(tasksByUrl)) {
      try {
        clinicsCache[url] = await fetchClinics(url);
      } catch (err) {
        console.error(`fetch failed for ${url}:`, err.message);
        clinicsCache[url] = null;
      }
    }

    // 逐一檢查每個用戶
    for (const key of Object.keys(records)) {
      const record = records[key];
      const { subscription, task } = record;

      try {
        const clinics = clinicsCache[task.url];
        if (!clinics) continue;

        // 找到用戶選的那個診間
        const match = clinics.find(c =>
          c.clinic === task.clinicName && c.doctor === task.doctor
        ) || clinics.find(c => c.clinic === task.clinicName);

        if (!match || match.current === null) continue;

        const current = match.current;
        const remaining = task.myNumber - current;
        checked++;

        // 更新 lastNumber
        record.lastNumber = current;

        // 判斷是否要推播
        let shouldNotify = false;
        let urgent = false;
        let title = '';
        let body = '';

        if (remaining <= 0 && !record.alerted) {
          shouldNotify = true; urgent = true;
          title = '🚨 快輪到你了！';
          body = `${task.clinicName} 目前 ${current} 號，你的號碼 ${task.myNumber}，請立刻前往診間！`;
          record.alerted = true;
        } else if (remaining <= 3 && !record.urgentAlerted) {
          shouldNotify = true; urgent = true;
          title = '🚨 緊急！還有 3 號！';
          body = `${task.clinicName} 目前 ${current} 號，還有 ${remaining} 號，請立刻出發！`;
          record.urgentAlerted = true;
        } else if (remaining <= task.alertBefore && !record.warnAlerted) {
          shouldNotify = true; urgent = false;
          title = '⏰ 請準備出發';
          body = `${task.clinicName} 目前 ${current} 號，還有 ${remaining} 號輪到你，請開始移動！`;
          record.warnAlerted = true;
        }

        if (shouldNotify) {
          const payload = JSON.stringify({ title, body, urgent, url: '/' });
          try {
            await webpush.sendNotification(subscription, payload);
            notified++;
          } catch (pushErr) {
            // 410 = 訂閱已失效，刪除
            if (pushErr.statusCode === 410) {
              await store.delete(key);
            } else {
              errors++;
            }
          }
        }

        // 更新記錄
        await store.setJSON(key, record);

      } catch (err) {
        console.error(`process error for key ${key}:`, err.message);
        errors++;
      }
    }

    return {
      statusCode: 200, headers,
      body: JSON.stringify({ ok: true, checked, notified, errors, timestamp: new Date().toISOString() })
    };

  } catch (err) {
    console.error('notify handler error:', err);
    return { statusCode: 500, headers, body: JSON.stringify({ ok: false, error: err.message }) };
  }
};

// ── 抓取國軍桃園診間資料 ──
async function fetchClinics(url) {
  // 國軍桃園用 Cloudflare Worker
  if (url.includes('aftygh.gov.tw')) {
    const text = await fetchText('https://aftygh-proxy.owen163.workers.dev/');
    return parseAftygh(text);
  }
  // 其他醫院走原本的 scrape 邏輯
  return [];
}

function fetchText(url) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; HospitalBot/1.0)',
      },
      timeout: 10000,
    }, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.on('error', reject);
  });
}

function parseAftygh(text) {
  const clinics = [];
  const totalMatch = text.match(/id="totalidx"[^>]*value="(\d+)"/);
  const total = totalMatch ? parseInt(totalMatch[1]) : 30;

  for (let i = 0; i < total; i++) {
    const get = (field) => {
      const m = text.match(new RegExp(`id="${field}${i}"[^>]*value="([^"]*)"`));
      return m ? m[1].trim() : '';
    };
    const clinname  = get('clinname');
    const drname    = get('drname');
    const oncallnum = get('oncallnum');
    const roomnum   = get('nowroomnum');
    const divnname  = get('divnname');
    if (!clinname) continue;
    const current = parseInt(oncallnum);
    clinics.push({
      dept:    divnname || clinname,
      clinic:  roomnum ? `${clinname}（${roomnum}）` : clinname,
      doctor:  drname || '—',
      current: (!isNaN(current) && current > 0) ? current : null,
    });
  }
  return clinics;
}
