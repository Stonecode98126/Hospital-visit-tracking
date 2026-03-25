/**
 * Netlify Function: /api/subscribe
 * 儲存或刪除用戶的 Web Push 訂閱
 * POST { subscription, task } → 儲存訂閱 + 監控任務
 * DELETE { endpoint } → 取消訂閱
 */

const { getStore } = require('@netlify/blobs');

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json; charset=utf-8',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    const store = getStore('subscriptions');

    if (event.httpMethod === 'DELETE') {
      const { endpoint } = JSON.parse(event.body);
      const key = encodeKey(endpoint);
      await store.delete(key);
      return { statusCode: 200, headers, body: JSON.stringify({ ok: true }) };
    }

    if (event.httpMethod === 'POST') {
      const { subscription, task } = JSON.parse(event.body);
      // task = { url, clinicName, doctor, myNumber, alertBefore }

      const key = encodeKey(subscription.endpoint);
      const record = {
        subscription,
        task,
        createdAt: new Date().toISOString(),
        lastNumber: null,
        alerted: false,
      };

      await store.setJSON(key, record);
      return { statusCode: 200, headers, body: JSON.stringify({ ok: true }) };
    }

    return { statusCode: 405, headers, body: JSON.stringify({ ok: false, error: 'Method not allowed' }) };

  } catch (err) {
    console.error('subscribe error:', err);
    return { statusCode: 500, headers, body: JSON.stringify({ ok: false, error: err.message }) };
  }
};

function encodeKey(endpoint) {
  // 把 endpoint URL 轉成安全的 key
  return Buffer.from(endpoint).toString('base64').replace(/[/+=]/g, '_').substring(0, 100);
}
