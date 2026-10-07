#!/usr/bin/env node
// Wraps `brs` so we can return a non-zero exit code when test_pure.brs reports
// any FAILs. brs by itself always exits 0 regardless of test outcome.

const { spawnSync } = require("child_process");
const path = require("path");

const channelRoot = path.resolve(__dirname, "..", "..");
const brsCli = path.join(channelRoot, "node_modules", "@rokucommunity", "brs", "bin", "cli.js");

const args = [
  brsCli,
  path.join(channelRoot, "source", "Config.brs"),
  path.join(channelRoot, "source", "Glyphs.brs"),
  path.join(channelRoot, "tests", "unit", "test_pure.brs"),
];

const result = spawnSync("node", args, { cwd: channelRoot, encoding: "utf8" });
process.stdout.write(result.stdout);
process.stderr.write(result.stderr);

const m = /RESULT pass=(\d+) fail=(\d+)/.exec(result.stdout);
if (!m) {
  console.error("\n!! Could not find RESULT line in brs output — test runner failed.");
  process.exit(2);
}
const fail = parseInt(m[2], 10);
if (fail > 0) {
  console.error(`\n!! ${fail} unit test(s) failed.`);
  process.exit(1);
}
console.log(`\n✓ ${m[1]} unit assertions passed.`);
process.exit(0);
