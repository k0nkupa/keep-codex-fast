#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(packageRoot, "package.json"), "utf8"));
const skillName = "keep-codex-fast";

function usage() {
  return `keep-codex-fast ${packageJson.version}

Usage:
  keep-codex-fast setup [--codex-home <path>] [--no-automation] [--dry-run]
  keep-codex-fast audit [script options]
  keep-codex-fast apply [script options]
  keep-codex-fast doctor [--codex-home <path>]

Examples:
  keep-codex-fast setup
  keep-codex-fast audit --days 10
  keep-codex-fast apply --days 10 --worktree-days 14 --log-max-mb 250
`;
}

function parseOptions(args) {
  const options = {
    codexHome: process.env.CODEX_HOME || path.join(os.homedir(), ".codex"),
    dryRun: false,
    noAutomation: false,
  };
  const rest = [];
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--codex-home") {
      const value = args[i + 1];
      if (!value) throw new Error("--codex-home requires a value");
      options.codexHome = value;
      i += 1;
    } else if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "--no-automation") {
      options.noAutomation = true;
    } else {
      rest.push(arg);
    }
  }
  options.codexHome = path.resolve(options.codexHome.replace(/^~(?=$|\/|\\)/, os.homedir()));
  return { options, rest };
}

function sourceSkillDir() {
  return path.join(packageRoot, "skills", skillName);
}

function installedSkillDir(codexHome) {
  return path.join(codexHome, "skills", skillName);
}

function maintenanceScript(codexHome) {
  const installed = path.join(installedSkillDir(codexHome), "scripts", "codex_fast_maintenance.py");
  if (fs.existsSync(installed)) return installed;
  return path.join(sourceSkillDir(), "scripts", "codex_fast_maintenance.py");
}

function timestamp() {
  return new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
}

async function pathExists(target) {
  try {
    await fsp.access(target);
    return true;
  } catch {
    return false;
  }
}

async function copyDirAtomic(source, destination, dryRun) {
  const parent = path.dirname(destination);
  const tmp = path.join(parent, `.${path.basename(destination)}.tmp-${process.pid}-${Date.now()}`);
  const backup = `${destination}.backup-${timestamp()}`;

  if (dryRun) {
    console.log(`[dry-run] install skill ${source} -> ${destination}`);
    return { backup: null };
  }

  await fsp.mkdir(parent, { recursive: true });
  await fsp.rm(tmp, { recursive: true, force: true });
  await fsp.cp(source, tmp, {
    recursive: true,
    dereference: false,
    filter: (src) => !src.split(path.sep).includes("__pycache__") && !src.endsWith(".pyc"),
  });

  let backupPath = null;
  if (await pathExists(destination)) {
    backupPath = backup;
    await fsp.rename(destination, backupPath);
  }
  await fsp.rename(tmp, destination);
  return { backup: backupPath };
}

function tomlSafePath(target) {
  return target.split(path.sep).join("/");
}

async function installAutomation(codexHome, scriptPath, dryRun) {
  const templatePath = path.join(packageRoot, "templates", "automations", "keep-codex-fast-weekly.toml");
  const destination = path.join(codexHome, "automations", "keep-codex-fast-weekly", "automation.toml");
  const rendered = (await fsp.readFile(templatePath, "utf8"))
    .replaceAll("{{SCRIPT_PATH}}", tomlSafePath(scriptPath))
    .replaceAll("{{TIMESTAMP_MS}}", String(Date.now()));

  if (dryRun) {
    console.log(`[dry-run] install automation ${destination}`);
    return { backup: null };
  }

  await fsp.mkdir(path.dirname(destination), { recursive: true });
  let backupPath = null;
  if (await pathExists(destination)) {
    backupPath = `${destination}.backup-${timestamp()}`;
    await fsp.copyFile(destination, backupPath);
  }
  await fsp.writeFile(destination, rendered);
  return { destination, backup: backupPath };
}

function checkPython() {
  const result = spawnSync("python3", ["--version"], { encoding: "utf8" });
  if (result.error) {
    return { ok: false, version: "python3 not found" };
  }
  return { ok: result.status === 0, version: (result.stdout || result.stderr).trim() };
}

async function setup(rawArgs) {
  const { options } = parseOptions(rawArgs);
  const python = checkPython();
  if (!python.ok) {
    throw new Error("python3 is required. Install Python 3.11+ before running setup.");
  }

  const source = sourceSkillDir();
  const destination = installedSkillDir(options.codexHome);
  const install = await copyDirAtomic(source, destination, options.dryRun);
  const scriptPath = path.join(destination, "scripts", "codex_fast_maintenance.py");

  if (!options.dryRun) {
    await fsp.chmod(scriptPath, 0o755);
  }

  let automation = null;
  if (!options.noAutomation) {
    automation = await installAutomation(options.codexHome, scriptPath, options.dryRun);
  }

  console.log(`Codex home: ${options.codexHome}`);
  console.log(`Skill: ${destination}`);
  if (install.backup) console.log(`Previous skill backup: ${install.backup}`);
  if (automation?.destination) console.log(`Automation: ${automation.destination}`);
  if (automation?.backup) console.log(`Previous automation backup: ${automation.backup}`);
  console.log(`Python: ${python.version}`);
}

function runPython(command, rawArgs) {
  const { options, rest } = parseOptions(rawArgs);
  const script = maintenanceScript(options.codexHome);
  if (!fs.existsSync(script)) {
    throw new Error(`Maintenance script not found: ${script}`);
  }
  const pythonArgs = [script];
  if (command === "apply") pythonArgs.push("--apply");
  pythonArgs.push(...rest);

  const result = spawnSync("python3", pythonArgs, { stdio: "inherit" });
  if (result.error) {
    throw result.error;
  }
  process.exitCode = result.status ?? 1;
}

function doctor(rawArgs) {
  const { options } = parseOptions(rawArgs);
  const python = checkPython();
  const skillDir = installedSkillDir(options.codexHome);
  const automationPath = path.join(options.codexHome, "automations", "keep-codex-fast-weekly", "automation.toml");
  const script = maintenanceScript(options.codexHome);

  console.log(`Package: ${packageRoot}`);
  console.log(`Version: ${packageJson.version}`);
  console.log(`Codex home: ${options.codexHome}`);
  console.log(`Skill installed: ${fs.existsSync(path.join(skillDir, "SKILL.md")) ? "yes" : "no"} (${skillDir})`);
  console.log(`Automation installed: ${fs.existsSync(automationPath) ? "yes" : "no"} (${automationPath})`);
  console.log(`Maintenance script: ${script}`);
  console.log(`Python: ${python.version}`);
}

async function main() {
  const [command = "help", ...args] = process.argv.slice(2);
  if (command === "--version" || command === "-v") {
    console.log(packageJson.version);
    return;
  }
  if (command === "help" || command === "--help" || command === "-h") {
    console.log(usage());
    return;
  }
  if (command === "setup") {
    await setup(args);
    return;
  }
  if (command === "audit" || command === "apply") {
    runPython(command, args);
    return;
  }
  if (command === "doctor") {
    doctor(args);
    return;
  }
  throw new Error(`Unknown command: ${command}\n\n${usage()}`);
}

main().catch((error) => {
  console.error(`keep-codex-fast: ${error.message}`);
  process.exit(1);
});
