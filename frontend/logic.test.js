/* Unit tests for the pure logic helpers in logic.js (run under Vitest/Node). */

import { describe, it, expect } from "vitest";
import {
  stripVnAccents,
  normalizeTopicOrder,
  parseStoredEntries,
  pickRelated,
  distinctSources,
} from "./logic.js";

describe("stripVnAccents", () => {
  it("folds Vietnamese diacritics and lowercases", () => {
    expect(stripVnAccents("Tiếng Việt")).toBe("tieng viet");
    expect(stripVnAccents("ĐÀ NẴNG")).toBe("da nang");
    expect(stripVnAccents("Đỗ")).toBe("do");
  });

  it("handles empty / null input", () => {
    expect(stripVnAccents("")).toBe("");
    expect(stripVnAccents(null)).toBe("");
    expect(stripVnAccents(undefined)).toBe("");
  });

  it("leaves plain ascii untouched (but lowercased)", () => {
    expect(stripVnAccents("Hello WORLD")).toBe("hello world");
  });
});

describe("normalizeTopicOrder", () => {
  const defaults = ["all", "thoi_su", "kinh_te", "cong_nghe"];

  it("returns defaults when stored value is not an array", () => {
    expect(normalizeTopicOrder(null, defaults)).toEqual(defaults);
    expect(normalizeTopicOrder("oops", defaults)).toEqual(defaults);
    expect(normalizeTopicOrder({}, defaults)).toEqual(defaults);
  });

  it("keeps a valid saved order as-is", () => {
    const saved = ["kinh_te", "all", "thoi_su", "cong_nghe"];
    expect(normalizeTopicOrder(saved, defaults)).toEqual(saved);
  });

  it("drops unknown keys", () => {
    const saved = ["kinh_te", "banana", "all", "thoi_su", "cong_nghe"];
    expect(normalizeTopicOrder(saved, defaults)).toEqual([
      "kinh_te",
      "all",
      "thoi_su",
      "cong_nghe",
    ]);
  });

  it("appends defaults missing from the saved order (newer app version)", () => {
    const saved = ["all", "thoi_su"];
    expect(normalizeTopicOrder(saved, defaults)).toEqual([
      "all",
      "thoi_su",
      "kinh_te",
      "cong_nghe",
    ]);
  });

  it("falls back to defaults when nothing valid remains", () => {
    expect(normalizeTopicOrder(["banana", "xyz"], defaults)).toEqual(defaults);
    expect(normalizeTopicOrder([], defaults)).toEqual(defaults);
  });
});

describe("parseStoredEntries", () => {
  it("parses a JSON string into a Map keyed by url", () => {
    const raw = JSON.stringify([
      { url: "a", title: "A" },
      { url: "b", title: "B" },
    ]);
    const map = parseStoredEntries(raw, 200);
    expect(map.size).toBe(2);
    expect(map.get("a").title).toBe("A");
  });

  it("accepts an already-parsed array too", () => {
    const map = parseStoredEntries([{ url: "x" }], 200);
    expect(map.has("x")).toBe(true);
  });

  it("returns an empty Map on junk / empty input", () => {
    expect(parseStoredEntries("", 10).size).toBe(0);
    expect(parseStoredEntries(null, 10).size).toBe(0);
    expect(parseStoredEntries("not json{", 10).size).toBe(0);
    expect(parseStoredEntries(JSON.stringify({ not: "array" }), 10).size).toBe(0);
  });

  it("skips entries without a url", () => {
    const map = parseStoredEntries([{ title: "no url" }, { url: "ok" }], 10);
    expect(map.size).toBe(1);
    expect(map.has("ok")).toBe(true);
  });

  it("caps the number of entries at the limit", () => {
    const many = Array.from({ length: 50 }, (_, i) => ({ url: `u${i}` }));
    expect(parseStoredEntries(many, 10).size).toBe(10);
  });

  it("de-duplicates by url (last wins, like a Map)", () => {
    const map = parseStoredEntries([{ url: "a", v: 1 }, { url: "a", v: 2 }], 10);
    expect(map.size).toBe(1);
    expect(map.get("a").v).toBe(2);
  });
});

describe("pickRelated", () => {
  const sources = {
    topicMap: {
      kinh_te: { items: [{ url: "k1" }, { url: "k2" }, { url: "cur" }] },
      cong_nghe: { items: [{ url: "c1" }, { url: "c2" }] },
    },
    allItems: [{ url: "a1" }, { url: "k1" }, { url: "a2" }],
  };

  it("prefers the same topic and excludes the current article", () => {
    const out = pickRelated("cur", "kinh_te", sources, 5);
    const urls = out.map((x) => x.url);
    expect(urls).not.toContain("cur");
    // same-topic items come first
    expect(urls.slice(0, 2)).toEqual(["k1", "k2"]);
  });

  it("de-duplicates across topic + all feed", () => {
    const out = pickRelated("cur", "kinh_te", sources, 10);
    const urls = out.map((x) => x.url);
    expect(new Set(urls).size).toBe(urls.length); // no dupes
    expect(urls.filter((u) => u === "k1").length).toBe(1);
  });

  it("respects the limit", () => {
    expect(pickRelated("cur", "kinh_te", sources, 3).length).toBe(3);
  });

  it("falls back to all-feed when topic is 'all' or unknown", () => {
    const out = pickRelated("x", "all", sources, 5);
    expect(out.map((x) => x.url)).toContain("a1");
  });

  it("handles empty sources without throwing", () => {
    expect(pickRelated("x", "kinh_te", {}, 5)).toEqual([]);
    expect(pickRelated("x", "kinh_te", null, 5)).toEqual([]);
  });
});

describe("distinctSources", () => {
  it("returns sources in first-seen order, de-duplicated", () => {
    const items = [
      { source: "VnExpress" },
      { source: "Tuổi Trẻ" },
      { source: "VnExpress" },
      { source: "" },
      { source: "Dân Trí" },
    ];
    expect(distinctSources(items)).toEqual(["VnExpress", "Tuổi Trẻ", "Dân Trí"]);
  });

  it("handles empty / missing input", () => {
    expect(distinctSources([])).toEqual([]);
    expect(distinctSources(null)).toEqual([]);
    expect(distinctSources([{}, { source: "" }])).toEqual([]);
  });
});
