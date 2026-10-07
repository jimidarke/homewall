#!/usr/bin/env node
// Sideload haku.zip to a Roku via roku-deploy.
// Required env: ROKU_IP, ROKU_DEV_PASSWORD

const path = require("path");
const rd = require("roku-deploy");

const host = process.env.ROKU_IP;
const password = process.env.ROKU_DEV_PASSWORD;
if (!host) { console.error("ROKU_IP env var required"); process.exit(2); }
if (!password) { console.error("ROKU_DEV_PASSWORD env var required"); process.exit(2); }

const opts = {
  host,
  username: "rokudev",
  password,
  rootDir: path.resolve(__dirname, ".."),
  outDir: path.resolve(__dirname, "..", "dist"),
  outFile: "haku",
  files: ["manifest", "source/**/*", "components/**/*", "images/**/*", "fonts/**/*"],
  retainStagingFolder: false,
};

console.log(`[deploy] sideloading to rokudev@${host}…`);
rd.deploy(opts).then(
  (r) => { console.log("[deploy] ok"); process.exit(0); },
  (e) => { console.error("[deploy] failed:", e.message || e); process.exit(1); }
);
