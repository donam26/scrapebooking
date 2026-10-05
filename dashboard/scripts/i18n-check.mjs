#!/usr/bin/env node
/**
 * Kiểm tra bản dịch (chạy: `npm run i18n:check`, CI nên chạy cùng typecheck).
 *
 * 1. Mọi ngôn ngữ có cùng bộ namespace và cùng khoá với `vi` (nguồn gốc).
 * 2. Mỗi chuỗi là ICU hợp lệ và có cùng tham số ({name}, {count, plural…}) giữa các ngôn ngữ.
 * 3. Không còn chữ tiếng Việt viết cứng trong code (string literal, JSX text, template) ngoài
 *    comment. Dòng cố ý giữ nguyên (tên riêng, dữ liệu minh hoạ địa phương) ghi `i18n-ignore`.
 * 4. Cảnh báo (không lỗi) khi bản không phải tiếng Việt còn chứa dấu tiếng Việt.
 *
 * `--files a.tsx b.tsx`: chỉ quét bước 3 trên các tệp này (dùng khi chuyển đổi từng phần).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse, TYPE } from "@formatjs/icu-messageformat-parser";
import ts from "typescript";

const ROOT = new URL("..", import.meta.url).pathname;
const MESSAGES = join(ROOT, "src/messages");
const SOURCE = "vi";
const VI_CHARS = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i;
// Không quét: bản dịch, kiểu sinh từ OpenAPI.
const SKIP = [/^src\/messages\//, /^src\/lib\/api-types\.ts$/];

const errors = [];
const warnings = [];

// ---- 1 + 2: bản dịch ----

function flatten(obj, prefix = "", out = new Map()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") flatten(v, key, out);
    else out.set(key, String(v));
  }
  return out;
}

function argNames(elements, out = new Set()) {
  for (const el of elements) {
    if (el.type === TYPE.argument || el.type === TYPE.number || el.type === TYPE.date || el.type === TYPE.time) out.add(el.value);
    if (el.type === TYPE.plural || el.type === TYPE.select) {
      out.add(el.value);
      for (const opt of Object.values(el.options)) argNames(opt.value, out);
    }
    if (el.type === TYPE.tag) {
      out.add(`<${el.value}>`);
      argNames(el.children, out);
    }
  }
  return out;
}

function icuArgs(text, where) {
  try {
    return [...argNames(parse(text))].sort().join(",");
  } catch (e) {
    errors.push(`${where}: ICU không hợp lệ (${e.message}): ${JSON.stringify(text)}`);
    return null;
  }
}

function loadLocale(locale) {
  const dir = join(MESSAGES, locale);
  const out = new Map();
  for (const f of readdirSync(dir).filter((f) => f.endsWith(".json"))) {
    const ns = f.replace(/\.json$/, "");
    out.set(ns, flatten(JSON.parse(readFileSync(join(dir, f), "utf8"))));
  }
  return out;
}

const locales = readdirSync(MESSAGES).filter((d) => statSync(join(MESSAGES, d)).isDirectory());
const source = loadLocale(SOURCE);
for (const [ns, keys] of source) for (const [k, v] of keys) icuArgs(v, `${SOURCE}/${ns}.json ${k}`);

for (const locale of locales.filter((l) => l !== SOURCE)) {
  const target = loadLocale(locale);
  for (const ns of source.keys()) if (!target.has(ns)) errors.push(`${locale}: thiếu namespace ${ns}.json`);
  for (const ns of target.keys()) if (!source.has(ns)) errors.push(`${locale}: thừa namespace ${ns}.json (không có trong ${SOURCE})`);
  for (const [ns, keys] of source) {
    const other = target.get(ns);
    if (!other) continue;
    for (const [k, v] of keys) {
      const where = `${locale}/${ns}.json ${k}`;
      if (!other.has(k)) {
        errors.push(`${where}: thiếu khoá`);
        continue;
      }
      const a = icuArgs(v, `${SOURCE}/${ns}.json ${k}`);
      const b = icuArgs(other.get(k), where);
      if (a !== null && b !== null && a !== b) errors.push(`${where}: tham số {${b}} khác ${SOURCE} {${a}}`);
      if (VI_CHARS.test(other.get(k))) warnings.push(`${where}: còn dấu tiếng Việt: ${JSON.stringify(other.get(k))}`);
    }
    for (const k of other.keys()) if (!keys.has(k)) errors.push(`${locale}/${ns}.json ${k}: thừa khoá (không có trong ${SOURCE})`);
  }
}

// ---- 3: chữ tiếng Việt viết cứng trong code ----

function walk(dir, out = []) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(f) && !f.endsWith(".d.ts")) out.push(p);
  }
  return out;
}

const fileArgs = process.argv.indexOf("--files");
const files = fileArgs >= 0 ? process.argv.slice(fileArgs + 1).map((f) => join(process.cwd(), f)) : walk(join(ROOT, "src"));
let hardcoded = 0;
for (const file of files) {
  const rel = relative(ROOT, file);
  if (SKIP.some((re) => re.test(rel))) continue;
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const visit = (node) => {
    let value = null;
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) value = node.text;
    else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) value = node.text;
    if (value !== null && VI_CHARS.test(value)) {
      const line = sf.getLineAndCharacterOfPosition(node.getStart()).line;
      if (!lines[line].includes("i18n-ignore") && !(line > 0 && lines[line - 1].includes("i18n-ignore-next-line"))) {
        hardcoded++;
        errors.push(`${rel}:${line + 1}: chữ viết cứng: ${JSON.stringify(value.trim().slice(0, 80))}`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
}

for (const w of warnings) console.warn(`cảnh báo  ${w}`);
for (const e of errors) console.error(`lỗi      ${e}`);
console.log(
  `\ni18n: ${locales.length} ngôn ngữ, ${source.size} namespace, ${[...source.values()].reduce((n, m) => n + m.size, 0)} khoá; ` +
    `${errors.length} lỗi (${hardcoded} chữ viết cứng), ${warnings.length} cảnh báo`,
);
process.exit(errors.length ? 1 : 0);
