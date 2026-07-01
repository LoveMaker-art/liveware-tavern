// actor.js — 演员卡 reader。取 /api/actor_card 聚合数据 → 渲染墨的生涯/亲密度/口味/年表。
// 展示 surface，无渐进披露、无原生手势（liveware-frontend §1）。词汇：戏路≠搭档，口味≠年表。
'use strict';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// 累计字：≥1万显「X.X万」，否则整数（actor-card §6 数值格式）。
function fmtWords(n) {
  n = Math.round(n || 0);
  return n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n);
}

function stat(v, label) {
  return `<div class="acStat"><div class="acStatV">${v}</div><div class="acStatL">${esc(label)}</div></div>`;
}

function render(d) {
  const c = d.career || {}, it = d.intimacy || {};
  const knows = (d.knows || []).filter(Boolean);
  const tl = d.timeline || [];

  const stats = [
    stat(c.debut_days, '出道天'),
    stat(c.turns, '轮演出'),
    stat(fmtWords(c.words), '累计字'),
    stat(c.productions, '个剧组'),
    stat(c.roles, '戏路'),                       // 戏路 = 演过的角色数（不是搭档）
    stat(`<span class="acStatBrand">${esc(it.level || '初见')}</span>`, '亲密度'),
  ].join('');

  const pct = Math.round((it.progress || 0) * 100);
  const sub = `一起 ${c.turns || 0} 轮 · 记下你 ${it.log || 0} 笔`;  // 笔 = 年表条数（非口味）
  const foot = it.next
    ? `<span>${esc(it.blurb || '')}</span><span>距「${esc(it.next)}」还差 ${Math.max(0, it.to_next || 0)}</span>`
    : `<span>${esc(it.blurb || '')}</span><span>已是知己</span>`;
  const intimacy = `
    <div class="acIntimacy">
      <div class="acIntHead"><span class="acIntLevel">${esc(it.level || '初见')}</span><span class="acIntSub">${esc(sub)}</span></div>
      <div class="acProg"><div class="acProgBar" style="width:${pct}%"></div></div>
      <div class="acIntFoot">${foot}</div>
    </div>`;

  const knowsBlock = `
    <div class="acSec">
      <div class="pHead">我对你的了解</div>
      ${knows.length
        ? `<ul class="acKnows">${knows.map((k) => `<li class="acKnow">${esc(k)}</li>`).join('')}</ul>`
        : `<div class="acEmpty2">还在读你的口味——演几场我就懂了。</div>`}
    </div>`;

  const timelineBlock = `
    <div class="acSec">
      <div class="acSecHead"><span class="pHead">生涯年表</span>${tl.length ? `<span class="acCount">${tl.length} 笔</span>` : ''}</div>
      ${tl.length
        ? `<div class="acTimeline">${tl.map((e) => `
            <div class="acEntry">
              <div class="acEntryMeta">${esc([e.date, e.reason].filter(Boolean).join(' · '))}</div>
              <div class="acEntryText">${esc(e.change)}</div>
            </div>`).join('')}</div>`
        : `<div class="acEmpty2">还没有生涯记录。演几场、复个盘，我就开始长了。</div>`}
    </div>`;

  document.getElementById('acRoot').innerHTML = `
    <div class="acHero">
      <div class="acAvatar">✦</div>
      <div class="acName">${esc(d.name || '墨')}</div>
      <div class="acTagline">${esc(d.tagline || '')}</div>
    </div>
    <div class="acStats">${stats}</div>
    ${intimacy}
    ${knowsBlock}
    ${timelineBlock}
    <div class="acFoot"><span class="mark">✦</span> 活件 · 酒馆 ${esc(d.version || '')}</div>`;
}

async function load() {
  try {
    const r = await fetch('/api/actor_card');
    render(await r.json());
  } catch (e) {
    document.getElementById('acRoot').innerHTML =
      `<div class="acEmpty">读不到演员卡：${esc(e.message || e)}</div>`;
  }
}
load();
