#!/usr/bin/env node
"use strict";

const { execFileSync, spawnSync } = require("child_process");

try {
  execFileSync("python3", ["--version"], { stdio: "pipe" });
} catch {
  console.error("selfblog requires Python 3.12+. Install from https://python.org/");
  process.exit(1);
}

// Capture stderr so a missing Python module can be distinguished from a
// real selfblog failure. stdout stays inherited for normal interactivity.
const result = spawnSync("python3", ["-m", "selfblog", ...process.argv.slice(2)], {
  stdio: ["inherit", "inherit", "pipe"],
  encoding: "utf-8",
});

const stderr = result.stderr || "";
if (
  result.status !== 0 &&
  /No module named ['"]?selfblog['"]?/.test(stderr)
) {
  console.error("The selfblog Python package is not installed.");
  console.error("Install it with: pip install selfblog");
  process.exit(1);
}

// Real failure or success: forward the captured stderr untouched.
if (stderr) {
  process.stderr.write(stderr);
}
process.exit(result.status ?? 1);
