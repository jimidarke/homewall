# config/ — the live HAku configuration

The sidecar's live configuration is `/etc/haku/dashboard.json` on nserver. Its working copy is `config/live/dashboard.json` (+ `config/live/SHA256SUMS`), which is **gitignored**: it is the house's real binding (entity ids, people, labels) and stays on the workstation. `dashboard.live.example.json` is a sanitized copy of it (fictional people), kept so the real layouts (`layouts.tablet`, `layouts.roku`) are readable in the repo. `sidecar/dashboard.json.example` is the smaller template the tests run against. No secrets live in either (those are in `/etc/haku/*.env`).

If `config/live/` is missing (a fresh clone), seed it from the server: `mkdir -p config/live && ssh nserver cat /etc/haku/dashboard.json > config/live/dashboard.json`, then refresh the checksum as in step 4 below.

## Drift check

```bash
ssh nserver sha256sum /etc/haku/dashboard.json        # compare with config/live/SHA256SUMS
(cd config/live && sha256sum -c SHA256SUMS)           # passes only when the local copy is current
```

If they differ, the live file was edited on nserver without updating the local copy: copy it in (`ssh nserver cat /etc/haku/dashboard.json > config/live/dashboard.json`) and refresh `SHA256SUMS` before changing anything.

## Change the live config

1. Edit `config/live/dashboard.json` (or edit on nserver and pull it in, as above).
2. Back up beside the live file: `ssh nserver 'cp -p /etc/haku/dashboard.json /etc/haku/dashboard.json.bak-<date>-<topic>'`.
3. Copy: `ssh nserver 'cat > /etc/haku/dashboard.json' < config/live/dashboard.json`. The sidecar hot-reloads on mtime (no restart); `curl -s http://<nserver>:1986/api/config?layout=roku` shows the result.
4. Refresh the checksum: `ssh nserver sha256sum /etc/haku/dashboard.json | awk '{print $1"  dashboard.json"}' > config/live/SHA256SUMS`.
5. If the change is structural (a new module or layout), mirror it in `dashboard.live.example.json` with placeholder names and commit that.

The live config's history is no longer in git: keep the `dashboard.json.bak-*` copies on nserver (or a private backup) if you need to go back.

## v2

v2 adds `dashboard.v2.json`, `cameras.yaml` and `fleet.yaml` here with JSON Schemas under `contract/`, validated at server start and on change, and a deploy script that refuses on drift (`docs/superpowers/specs/2026-10-24-haku-v2-design.md` § 6.3, § 6.4, § 6.6, § 6.7). Their house-specific instances follow the same split: gitignored live copies, committed sanitized examples.
