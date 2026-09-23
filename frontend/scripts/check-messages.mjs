/**
 * Every t("…") in the tree must resolve in every locale.
 *
 * A missing key is the quiet failure mode of this setup: next-intl renders
 * the key's own path, so "app.library.title" appears on the page, the
 * build succeeds, lint is clean and nothing anywhere says a word. With
 * four locales and 500+ keys that is a typo away at all times, and it
 * reaches production looking like a styling bug.
 *
 * Two things are checked: that the four files hold exactly the same set
 * of keys, and that every key a component asks for exists in all of them.
 * Dynamic keys — t(`status.${x}`) — are checked as far as their static
 * prefix, which catches a renamed group without pretending to know x.
 *
 *   node scripts/check-messages.mjs
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const LOCALES = ["en", "tr", "pl", "de"];
const BASE = "en";

const messages = Object.fromEntries(
  LOCALES.map((l) => [l, JSON.parse(readFileSync(join(ROOT, "messages", `${l}.json`), "utf8"))])
);

function flatten(object, prefix = "") {
  const out = {};
  for (const [key, value] of Object.entries(object)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(out, flatten(value, `${prefix}${key}.`));
    } else {
      out[`${prefix}${key}`] = value;
    }
  }
  return out;
}

function lookup(object, dotted) {
  return dotted.split(".").reduce((node, part) => {
    if (!node || typeof node !== "object" || !(part in node)) return undefined;
    return node[part];
  }, object);
}

const problems = [];

// --- 1. the locales agree on what keys exist ---------------------------
const flat = Object.fromEntries(LOCALES.map((l) => [l, flatten(messages[l])]));
const baseKeys = new Set(Object.keys(flat[BASE]));
for (const locale of LOCALES) {
  if (locale === BASE) continue;
  const keys = new Set(Object.keys(flat[locale]));
  for (const key of baseKeys) if (!keys.has(key)) problems.push(`${locale}: missing ${key}`);
  for (const key of keys) if (!baseKeys.has(key)) problems.push(`${locale}: extra ${key}`);
}

// --- 2. every key a component asks for exists --------------------------
function* sources(dir) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* sources(full);
    else if (full.endsWith(".tsx") || full.endsWith(".ts")) yield full;
  }
}

let checked = 0;
for (const file of sources(ROOT)) {
  const src = readFileSync(file, "utf8");
  // Which local name holds which namespace: `const t = useTranslations("a.b")`.
  const namespaces = new Map();
  for (const m of src.matchAll(/const\s+(\w+)\s*=\s*useTranslations\(\s*"([^"]+)"\s*\)/g)) {
    namespaces.set(m[1], m[2]);
  }
  if (namespaces.size === 0) continue;

  const where = relative(ROOT, file);
  for (const m of src.matchAll(/\b(\w+)(?:\.rich)?\(\s*"([^"]+)"/g)) {
    const namespace = namespaces.get(m[1]);
    if (!namespace) continue;
    checked += 1;
    const full = `${namespace}.${m[2]}`;
    for (const locale of LOCALES) {
      if (lookup(messages[locale], full) === undefined) {
        problems.push(`${where}: ${locale} has no ${full}`);
      }
    }
  }
  // Dynamic keys: check the static prefix names a group that exists.
  for (const m of src.matchAll(/\b(\w+)(?:\.rich)?\(\s*`([^`]+)`/g)) {
    const namespace = namespaces.get(m[1]);
    if (!namespace) continue;
    const prefix = m[2].split("${")[0].replace(/\.$/, "");
    if (!prefix) continue;
    checked += 1;
    const full = `${namespace}.${prefix}`;
    for (const locale of LOCALES) {
      if (lookup(messages[locale], full) === undefined) {
        problems.push(`${where}: ${locale} has no group ${full}`);
      }
    }
  }
}

const unique = [...new Set(problems)].sort();
if (unique.length > 0) {
  console.error(`${unique.length} problem(s):`);
  for (const problem of unique) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(`messages ok — ${baseKeys.size} keys × ${LOCALES.length} locales, ${checked} references`);
