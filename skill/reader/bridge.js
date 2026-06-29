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
  global.bridge = { event, get };
})(window);
