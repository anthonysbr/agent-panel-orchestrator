"use strict";

const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const npmRoot = path.resolve(__dirname, "..");
const target = path.join(npmRoot, "python");

function rmrf(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

function copyDir(src, dst) {
  fs.cpSync(src, dst, { recursive: true });
}

function cleanPycache(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__pycache__") {
        rmrf(full);
      } else {
        cleanPycache(full);
      }
    }
  }
}

rmrf(target);
fs.mkdirSync(target, { recursive: true });

copyDir(path.join(repoRoot, "panel_core"), path.join(target, "panel_core"));
for (const name of ["config", "skills", "third_party"]) {
  copyDir(path.join(repoRoot, name), path.join(target, name));
}

cleanPycache(target);
console.log(`Bundled ${target} for npm publish.`);
