#!/usr/bin/env node
// Pairs each failure or correction lesson in pi memory with the stream rule that enforces it,
// and lists the lessons that still live only as prose. Rules load through aaaav's own TTSR
// parser, so this sees them exactly as the running extension does.
//
// Usage: node scripts/lesson-audit.mjs [--memory <dir>] [--rules <dir>]

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const LESSON_CATEGORIES = new Set(["failure", "correction"]);

function agentDir() {
  const value = process.env.PI_CODING_AGENT_DIR;
  return value ? value.replace(/^~(?=$|\/)/, homedir()) : join(homedir(), ".pi", "agent");
}

/** aaaav's ttsr.ts: the checkout PI_AAAAV_ROOT names, as the installer uses, else the installed package. */
export function ttsrPath() {
  const override = process.env.PI_AAAAV_ROOT;
  const root = override ? resolve(override.replace(/^~(?=$|\/)/, homedir())) : join(agentDir(), "git/github.com/wayne930242/aaaav");
  const path = join(root, "pi/ttsr.ts");
  if (!existsSync(path)) throw new Error(`aaaav ttsr.ts not found at ${path}; install aaaav or set PI_AAAAV_ROOT to a checkout`);
  return path;
}

/** Every stream rule in `dir`, built by TTSR, with its `blocks` and `allows` fixtures. */
export async function loadStreamRules(dir = join(ROOT, "rules")) {
  const ttsr = await import(pathToFileURL(ttsrPath()).href);
  const rules = [];
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".md")).sort()) {
    const path = join(dir, file);
    const source = readFileSync(path, "utf-8");
    const parsed = ttsr.parseFrontmatter(source);
    if (!parsed || parsed.data.condition === undefined) continue;
    const warnings = [];
    const rule = ttsr.buildRule(path, source, warnings);
    const list = (key) => [parsed.data[key] ?? []].flat();
    rules.push({ name: file.replace(/\.md$/, ""), rule, warnings, blocks: list("blocks"), allows: list("allows"), lessons: list("lesson") });
  }
  return { ttsr, rules };
}

/** True when TTSR would stop `command` as a bash call under this rule. */
export function blocksBash(ttsr, rule, command) {
  return new ttsr.TtsrManager([rule]).check(command, { source: "tool", toolName: "bash", filePaths: [] }).length > 0;
}

/** `- [failure] text` and `- HH:MM [correction] text` entries from MEMORY.md and the daily logs. */
export function readLessons(memoryDir = join(agentDir(), "memory")) {
  const files = [join(memoryDir, "MEMORY.md")];
  const daily = join(memoryDir, "daily");
  if (existsSync(daily)) files.push(...readdirSync(daily).filter((name) => name.endsWith(".md")).sort().map((name) => join(daily, name)));
  const lessons = [];
  for (const file of files.filter(existsSync)) {
    for (const line of readFileSync(file, "utf-8").split("\n")) {
      const entry = /^- (?:\d{1,2}:\d{2} )?\[([a-z-]+)\] (.*)$/.exec(line);
      if (entry && LESSON_CATEGORIES.has(entry[1])) lessons.push({ file, category: entry[1], text: entry[2] });
    }
  }
  return lessons;
}

/**
 * A lesson is enforced only by a rule whose `lesson` key it contains: that key is the rule table entry.
 * A lesson whose text merely matches a rule's condition is a mention to review, because quoting a
 * command does not make the lesson about running it.
 */
export function audit(rules, lessons) {
  const covered = new Map(rules.map(({ name }) => [name, []]));
  const mentions = new Map(rules.map(({ name }) => [name, []]));
  const prose = [];
  for (const lesson of lessons) {
    const owners = rules.filter(({ lessons: keys }) => keys.some((key) => lesson.text.includes(key)));
    for (const { name } of owners) covered.get(name).push(lesson);
    if (owners.length > 0) continue;
    prose.push(lesson);
    for (const { name, rule } of rules) {
      if (rule?.conditions.some((condition) => { condition.lastIndex = 0; return condition.test(lesson.text); })) mentions.get(name).push(lesson);
    }
  }
  return { covered, mentions, prose };
}

function clip(text, width) {
  return text.length > width ? `${text.slice(0, width - 1)}…` : text;
}

async function main(argv) {
  const option = (flag) => { const index = argv.indexOf(flag); return index >= 0 ? argv[index + 1] : undefined; };
  const { rules } = await loadStreamRules(option("--rules"));
  const lessons = readLessons(option("--memory"));
  const { covered, mentions, prose } = audit(rules, lessons);
  console.log("Stream rule | blocks/allows fixtures | lessons it enforces (`lesson` keys) | prose lessons that mention it");
  for (const { name, blocks, allows } of rules) {
    const enforced = covered.get(name);
    const mentioned = mentions.get(name);
    console.log(`${name} | ${blocks.length}/${allows.length} | ${enforced.length} | ${mentioned.length}`);
    for (const lesson of enforced) console.log(`    enforces [${lesson.category}] ${clip(lesson.text, 100)}`);
    for (const lesson of mentioned) console.log(`    mentions [${lesson.category}] ${clip(lesson.text, 100)}`);
  }
  console.log(`\n${prose.length} of ${lessons.length} failure/correction lessons have no enforcer:`);
  for (const lesson of prose) console.log(`- [${lesson.category}] ${clip(lesson.text, 140)}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main(process.argv.slice(2));
