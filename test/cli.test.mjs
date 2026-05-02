import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const cli = path.join(repoRoot, "bin", "keep-codex-fast.js");

function run(args, env = {}) {
  return spawnSync(process.execPath, [cli, ...args], {
    cwd: repoRoot,
    env: { ...process.env, ...env },
    encoding: "utf8",
  });
}

test("prints version", () => {
  const result = run(["--version"]);
  assert.equal(result.status, 0);
  assert.match(result.stdout.trim(), /^\d+\.\d+\.\d+$/);
});

test("setup installs skill and automation into a custom Codex home", () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "keep-codex-fast-test-"));
  const result = run(["setup", "--codex-home", temp]);

  assert.equal(result.status, 0, result.stderr);
  assert.ok(fs.existsSync(path.join(temp, "skills", "keep-codex-fast", "SKILL.md")));
  assert.ok(fs.existsSync(path.join(temp, "skills", "keep-codex-fast", "scripts", "codex_fast_maintenance.py")));

  const automationPath = path.join(temp, "automations", "keep-codex-fast-weekly", "automation.toml");
  assert.ok(fs.existsSync(automationPath));
  assert.match(fs.readFileSync(automationPath, "utf8"), /keep-codex-fast apply --days 10/);
});

test("doctor reports installation state", () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "keep-codex-fast-doctor-"));
  run(["setup", "--codex-home", temp, "--no-automation"]);

  const result = run(["doctor", "--codex-home", temp]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Skill installed: yes/);
  assert.match(result.stdout, /Automation installed: no/);
});
