"use strict";

const assert = require("node:assert/strict");

global.window = { location: new URL("https://tavern.example/actor?from=console") };
global.document = {
  createElement(tag) { return { tagName: tag.toUpperCase(), className: "" }; },
};

require("../skill/reader/security.js");
const { TavernUI } = window;

assert.equal(TavernUI.escapeHtml('<img src=x onerror="x">'), "&lt;img src=x onerror=&quot;x&quot;&gt;");
assert.equal(TavernUI.safeSameOriginTarget("/world?id=1#story"), "/world?id=1#story");
assert.equal(TavernUI.safeSameOriginTarget("https://evil.example/steal"), "");
assert.equal(TavernUI.safeSameOriginTarget("javascript:alert(1)"), "");
assert.equal(TavernUI.element("div", "card").className, "card");
