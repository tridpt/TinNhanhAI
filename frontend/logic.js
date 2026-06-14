/* Pure, DOM-free logic helpers for TinNhanh AI.
 *
 * These functions hold the trickier client-side logic (accent folding, topic
 * order repair, read-later parsing, related-article picking). They take all
 * their inputs as explicit arguments — no globals, no localStorage, no DOM —
 * so they can be unit-tested under Node (Vitest) and reused by ``app.js`` in
 * the browser.
 *
 * Loaded as a classic script before ``app.js`` (exposes ``window.TNLogic``)
 * and also importable via CommonJS in tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api; // Node / Vitest
  }
  root.TNLogic = api; // browser global
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Fold Vietnamese accents and lowercase, for accent-insensitive matching.
  function stripVnAccents(text) {
    return (text || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase();
  }

  // Repair a stored topic order against the known defaults: drop unknown keys,
  // keep the saved sequence, then append any defaults that are missing (e.g.
  // topics introduced in a newer app version). Always returns a non-empty list.
  function normalizeTopicOrder(raw, defaultOrder) {
    const defaults = Array.isArray(defaultOrder) ? defaultOrder : [];
    if (!Array.isArray(raw)) return [...defaults];
    const valid = raw.filter((k) => defaults.includes(k));
    for (const k of defaults) {
      if (!valid.includes(k)) valid.push(k);
    }
    return valid.length ? valid : [...defaults];
  }

  // Parse the stored read-later / bookmark array into a Map keyed by url,
  // tolerating junk input and capping the size. Returns an empty Map on error.
  function parseStoredEntries(raw, limit) {
    const map = new Map();
    if (!raw) return map;
    let parsed;
    try {
      parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch (e) {
      return map;
    }
    if (!Array.isArray(parsed)) return map;
    const cap = Number.isFinite(limit) ? limit : parsed.length;
    for (const entry of parsed.slice(0, cap)) {
      if (entry && entry.url) map.set(entry.url, entry);
    }
    return map;
  }

  // Pick up to ``limit`` related articles for the reader, preferring the same
  // topic, then the unified "all" feed, then any other topic — de-duplicating
  // by url and never including the article currently being read.
  function pickRelated(currentUrl, topicKey, sources, limit) {
    const { topicMap = {}, allItems = [] } = sources || {};
    const max = Number.isFinite(limit) ? limit : 5;
    const seen = new Set([currentUrl]);
    const pool = [];

    const addFrom = (items) => {
      for (const item of items || []) {
        if (!item || !item.url || seen.has(item.url)) continue;
        seen.add(item.url);
        pool.push(item);
      }
    };

    if (topicKey && topicKey !== "all" && topicMap[topicKey]) {
      addFrom(topicMap[topicKey].items || []);
    }
    addFrom(allItems);
    for (const topic of Object.values(topicMap)) addFrom(topic.items || []);

    return pool.slice(0, max);
  }

  // Distinct sources present in a list of articles, in first-seen order.
  function distinctSources(items) {
    const seen = new Set();
    const out = [];
    for (const item of items || []) {
      const src = (item && item.source) || "";
      if (!src || seen.has(src)) continue;
      seen.add(src);
      out.push(src);
    }
    return out;
  }

  return {
    stripVnAccents,
    normalizeTopicOrder,
    parseStoredEntries,
    pickRelated,
    distinctSources,
  };
});
