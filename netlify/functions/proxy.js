// Netlify Function: proxy.js
// Forwards requests to BACKEND_URL and attaches AGENT_TOKEN from Netlify env.
// Expects POST body: { method: 'GET'|'POST', path: '/settings'|'/queue'|..., body: {...} }

exports.handler = async function(event) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers };
  }

  let payload = {};
  try {
    payload = event.body ? JSON.parse(event.body) : {};
  } catch (e) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'invalid JSON' }) };
  }

  const BACKEND_URL = process.env.BACKEND_URL || '';
  const AGENT_TOKEN = process.env.AGENT_TOKEN || '';
  if (!BACKEND_URL) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: 'BACKEND_URL not configured' }) };
  }

  const method = (payload.method || 'GET').toUpperCase();
  const path = payload.path || '/';
  const url = BACKEND_URL.replace(/\/$/, '') + path;

  const fetchOpts = { method, headers: { 'Content-Type': 'application/json' } };
  if (AGENT_TOKEN) fetchOpts.headers['Authorization'] = `Bearer ${AGENT_TOKEN}`;
  if (payload.body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    fetchOpts.body = JSON.stringify(payload.body);
  }

  try {
    const resp = await fetch(url, fetchOpts);
    const text = await resp.text();
    let json = null;
    try { json = JSON.parse(text); } catch (e) { json = text; }
    return { statusCode: resp.status, headers, body: JSON.stringify({ status: resp.status, data: json }) };
  } catch (e) {
    return { statusCode: 502, headers, body: JSON.stringify({ error: String(e) }) };
  }
};
