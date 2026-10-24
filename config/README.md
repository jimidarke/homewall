# config/ — live HAku configuration as deployed

`config/live/dashboard.json` is the sidecar's live configuration, `/etc/haku/dashboard.json` on nserver, as last deployed. It holds entity ids, labels, tile geometry and layouts (`layouts.tablet`, `layouts.roku`); no secrets live in it (those are in `/etc/haku/*.env`, never in the repo). `sidecar/dashboard.json.example` is the template the tests run against; this is the house's real binding.

## Drift check

```bash
ssh nserver sha256sum /etc/haku/dashboard.json        # compare with config/live/SHA256SUMS
(cd config/live && sha256sum -c SHA256SUMS)           # passes only when the committed copy is current
```

If they differ, the live file was edited on nserver without a commit: copy it in (`ssh nserver cat /etc/haku/dashboard.json > config/live/dashboard.json`), refresh `SHA256SUMS`, and commit before changing anything.

## Change the live config

1. Edit `config/live/dashboard.json` (or edit on nserver and pull it in, as above).
2. Back up beside the live file: `ssh nserver 'cp -p /etc/haku/dashboard.json /etc/haku/dashboard.json.bak-<date>-<topic>'`.
3. Copy: `ssh nserver 'cat > /etc/haku/dashboard.json' < config/live/dashboard.json`. The sidecar hot-reloads on mtime (no restart); `curl -s http://192.0.2.20:1986/api/config?layout=roku` shows the result.
4. Refresh the checksum: `ssh nserver sha256sum /etc/haku/dashboard.json | awk '{print $1"  dashboard.json"}' > config/live/SHA256SUMS`, then commit.

The 22 `dashboard.json.bak-*` files that accumulated in `/etc/haku/` before 2026-10-24 are superseded by this history.

## v2

v2 adds `dashboard.v2.json`, `cameras.yaml` and `fleet.yaml` here with JSON Schemas under `contract/`, validated at server start and on change, and a deploy script that refuses on drift (`docs/superpowers/specs/2026-10-24-haku-v2-design.md` § 6.3, § 6.4, § 6.6, § 6.7).
