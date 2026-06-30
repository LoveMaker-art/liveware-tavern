/* bridge.js — 控制台 ↔ 演员运行时的同源桥（占位，复刻 digest reader/bridge.js）。
 *
 * 页面只跟自己的 agent server 同源说话：所有写回都过 bridge.event(ev) → POST /api/event。
 * 模型 creds 在 server 端，页面永不见。真 ClawChat 容器桥到位时只换这一处：
 *   event() → window.clawchat.sendFragment(event)。其余 UI 不知道反馈怎么走。
 */
(function (global) {
  "use strict";
  async function event(ev) {
    try {
      const r = await fetch("/api/event", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(ev),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data.ok === false) throw new Error(data.error || ("HTTP " + r.status));
      return data;
    } catch (err) {
      console.error("[bridge] event failed:", ev.type, err);
      throw err;
    }
  }
  async function get(path) {
    const r = await fetch(path);
    return r.json();
  }
  // 流式 send_message:逐 token 调 onDelta,返回最终 message。传输层不支持/出错则 throw,
  // 由调用方回退到阻塞式 event()。SSE 行：`data: {json}\n\n`。
  async function eventStream(ev, onDelta, signal) {
    const r = await fetch("/api/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(ev),
      signal,  // 早停:AbortController 取消时 fetch/读流抛 AbortError
    });
    if (!r.ok || !r.body) throw new Error("stream unavailable: HTTP " + r.status);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "", result = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).split("\n").find((l) => l.startsWith("data:"));
        buf = buf.slice(i + 2);
        if (!line) continue;
        let obj;
        try { obj = JSON.parse(line.slice(5).trim()); } catch (_) { continue; }
        if (obj.error) throw new Error(obj.error);
        if (obj.delta && onDelta) onDelta(obj.delta);
        if (obj.done) result = obj.message;
      }
    }
    if (!result) throw new Error("stream ended without result");
    return result;
  }
  global.bridge = { event, get, eventStream };
})(window);
