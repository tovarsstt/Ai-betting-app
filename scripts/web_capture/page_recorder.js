// page_recorder.js — in-page network recorder (our adaptation of REA's browser-observation / captures idea, https://github.com/morluto/rea).
// REA drives Chrome over CDP; we cannot (the user's Chrome is reached through an extension that only evaluates JS in the tab), so we hook the page's own
// fetch / XMLHttpRequest / WebSocket instead. It records METADATA ONLY: method, URL (query values redacted), status, GraphQL operationName + variable
// keys, and the SHAPE of JSON responses (key paths, array lengths, a few non-sensitive numeric samples). Never headers, cookies, tokens, request bodies'
// values or response text. Runs on the user's own logged-in tab, reads what the page already loads, places and changes nothing.
//
//   paste -> window.__rea.start(); navigate inside the SPA (clicks); window.__rea.dump() -> JSON for scripts/web_capture/analyze_capture.py
(() => {
  if (window.__rea && window.__rea.installed) return;
  const MAX_EVENTS = 400, MAX_DEPTH = 6, MAX_KEYS = 40;
  const log = [];
  const SECRET_KEY = /token|auth|session|cookie|password|secret|key|bearer|signature|jwt|email|phone|address|balance|iban|wallet/i;
  const redactUrl = (u) => {
    try {
      const x = new URL(u, location.href);
      const q = [...x.searchParams.keys()].map((k) => k + "=").join("&");
      return x.origin + x.pathname + (q ? "?" + q : "");
    } catch (e) { return String(u).slice(0, 120); }
  };
  const shape = (v, d = 0) => {
    if (v === null) return "null";
    if (Array.isArray(v)) return { _arr: v.length, _item: v.length && d < MAX_DEPTH ? shape(v[0], d + 1) : null };
    if (typeof v === "object") {
      if (d >= MAX_DEPTH) return "obj";
      const o = {};
      Object.keys(v).slice(0, MAX_KEYS).forEach((k) => { o[k] = SECRET_KEY.test(k) ? "<redacted>" : shape(v[k], d + 1); });
      return o;
    }
    return typeof v;
  };
  // does this payload carry betting odds? decimal price-like numbers next to market-ish keys
  const oddsHint = (v, hits = { n: 0 }, d = 0) => {
    if (hits.n > 50 || d > 8 || v === null || typeof v !== "object") return hits.n;
    for (const k of Object.keys(v).slice(0, 60)) {
      const x = v[k];
      if (/^(odds|price|coefficient|decimal|factor)$/i.test(k) && typeof x !== "object" && +x > 1 && +x < 1000) hits.n++;
      else if (typeof x === "object") oddsHint(x, hits, d + 1);
    }
    return hits.n;
  };
  const push = (e) => { if (log.length < MAX_EVENTS) log.push(Object.assign({ t: Math.round(performance.now()) }, e)); };
  const gqlInfo = (body) => {
    try {
      const j = typeof body === "string" ? JSON.parse(body) : null;
      const one = Array.isArray(j) ? j[0] : j;
      return one ? { op: one.operationName || null, vars: Object.keys(one.variables || {}).filter((k) => !SECRET_KEY.test(k)) } : {};
    } catch (e) { return {}; }
  };
  const origFetch = window.fetch;
  const origSend = XMLHttpRequest.prototype.send, origOpen = XMLHttpRequest.prototype.open;
  const OrigWS = window.WebSocket;
  const api = {
    installed: true,
    start() {
      window.fetch = async function (input, init) {
        const url = typeof input === "string" ? input : input.url;
        const meta = Object.assign({ kind: "fetch", method: (init && init.method) || (input && input.method) || "GET", url: redactUrl(url) }, gqlInfo(init && init.body));
        const res = await origFetch.apply(this, arguments);
        try {
          const c = res.clone();
          const txt = await c.text();
          meta.status = res.status; meta.bytes = txt.length;
          if (/json/.test(res.headers.get("content-type") || "")) { const j = JSON.parse(txt); meta.shape = shape(j); meta.odds_hits = oddsHint(j); }
        } catch (e) { meta.note = "unreadable"; }
        push(meta);
        return res;
      };
      XMLHttpRequest.prototype.open = function (m, u) { this.__rea = { kind: "xhr", method: m, url: redactUrl(u) }; return origOpen.apply(this, arguments); };
      XMLHttpRequest.prototype.send = function (body) {
        const meta = this.__rea || { kind: "xhr" };
        Object.assign(meta, gqlInfo(body));
        this.addEventListener("loadend", () => {
          meta.status = this.status;
          try { const j = JSON.parse(this.responseText); meta.shape = shape(j); meta.odds_hits = oddsHint(j); meta.bytes = this.responseText.length; } catch (e) {}
          push(meta);
        });
        return origSend.apply(this, arguments);
      };
      window.WebSocket = function (url, protocols) {
        const ws = protocols ? new OrigWS(url, protocols) : new OrigWS(url);
        const meta = { kind: "ws", url: redactUrl(url), frames: 0, odds_hits: 0, sample_shape: null, bytes: 0 };
        push(meta);
        ws.addEventListener("message", (ev) => {
          meta.frames++;
          try {
            const s = typeof ev.data === "string" ? ev.data : "";
            meta.bytes += s.length;
            if (!meta.sample_shape && s) { const j = JSON.parse(s); meta.sample_shape = shape(j); }
            if (s) meta.odds_hits += oddsHint(JSON.parse(s));
          } catch (e) { /* non-JSON frame: counted only */ }
        });
        return ws;
      };
      window.WebSocket.prototype = OrigWS.prototype;
      ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach((k) => { window.WebSocket[k] = OrigWS[k]; });
      return "recording";
    },
    stop() { window.fetch = origFetch; XMLHttpRequest.prototype.send = origSend; XMLHttpRequest.prototype.open = origOpen; window.WebSocket = OrigWS; return "stopped"; },
    dump() { return JSON.stringify({ page: location.origin + location.pathname, events: log }); },
    clear() { log.length = 0; return "cleared"; },
  };
  window.__rea = api;
})();
