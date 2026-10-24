# HAku v2 Phase 0: Hygiene, Baseline, Design Doc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land every change the v2 design marks "safe now, independent of the rebuild": stop measured waste, remove secrets and drift from the repo, align clocks, and commit a reproducible baseline to beat.

**Architecture:** No architectural change. v1 keeps running on its current ports and units throughout. Work splits into repo-only tasks (docs, packages, config copies, scripts), small live-system fixes on nserver/mserver (one crash loop, two unit files, one time zone, one memory cap), one v1 Roku release (1.3.2: registry write guard, token bootstrap removal), and three tasks that need the user (HA token rotation, router leases, GitHub repo creation is scripted but visible).

**Tech Stack:** bash, ssh (`nserver`, `mserver` aliases, both root), `gh` CLI (logged in as jimidarke), systemd, go2rtc HTTP API, HA WebSocket API (`websocket-client` in the sidecar venv on nserver), BrightScript + brighterscript (`roku/`), Python pytest (`sidecar/`).

**Spec:** `docs/superpowers/specs/2026-10-24-haku-v2-design.md` (§ 3 decisions, § 3.1 builder-check resolutions, § 9 Phase 0, § 10 row 0, § 11 baseline).

## Global Constraints

- v1 stays live. No task may stop `haku-sidecar`, `go2rtc`, or any `haku-hls@<cam>` other than `backyard` for longer than a restart; the mosaic unit restarts only when nobody is watching it.
- Before sideloading or smoke-testing any Roku, `curl -s http://<ip>:8060/query/active-app` must show `<app id="dev" …>HAku</app>`; otherwise skip that device (spec § 5; memory `feedback-sideload-check-active-app`).
- Deployed files on nserver/mserver: `md5sum` against the repo before touching, back up beside the live file with a `.bak-20261024-<topic>` suffix, copy with `ssh <host> "cat > <path>" < <file>` (keeps owner and mode), then reload/restart (sidecar/CLAUDE.md § Deploy; roku/CLAUDE.md § HA push side).
- Never print or commit a token or password. Tokens travel only inside `ssh` remote subshells or `read -s`. The two Roku dev passwords currently quoted in `roku/CLAUDE.md:58` are typed by the executor into env files, never into this plan or any commit.
- HA package changes: `POST /api/config/core/check_config` must return `"result": "valid"` before `automation.reload` / `rest_command.reload` / `template.reload`.
- Roku version lockstep: `roku/VERSION.txt`, `roku/package.json` `version`, and `roku/manifest` `major_version`/`minor_version`/`build_version` move together (1.3.2 → `build_version=00002`).
- Time zone must be `America/Edmonton` in HA before 2026-11-01 (spec § 3.5).
- `HAKU_POLL_INTERVAL` stays at 1 s in v1 (spec § 6.1 of the session plan: the real fix is the v2 WebSocket feed).

## Review Focus

1. **Deleting `backyard` from go2rtc at runtime must not disturb the five other producers.** Expected: the four Rokus keep `state="play"` and the `front` producer's `bytes_recv` keeps rising. Pinned in Task 5, step 4.
2. **A Roku that has never cached a hub base must still write it once after the guard.** Expected: exactly one `event=reg_write key=hubBaseV2` after a cold launch, none in the following 60 s. Pinned in Task 9, step 8.
3. **The time-zone change must not alter any current reading.** Expected: `/api/config.time_zone` becomes `America/Edmonton` while `{{ now().strftime('%z') }}` stays `-0600` today (both zones are UTC−6 until 2026-11-01). Pinned in Task 7, step 3.
4. **No secret may be committed or pushed.** Expected: `git grep` for both dev passwords and for `Bearer ey` is empty at the commit that precedes `gh repo create`. Pinned in Task 2, step 4 and Task 3, step 1.
5. **The baseline script must leave nothing running on nserver.** Expected: `pgrep -c tcpdump` on nserver is `0` after the script exits, even on Ctrl-C. Pinned in Task 14, step 4.

---

### Task 1: Commit the design doc and this plan

**Files:**
- Create (already written, untracked): `docs/superpowers/specs/2026-10-24-haku-v2-design.md`
- Create (this file): `docs/superpowers/plans/2026-10-24-haku-v2-phase0-hygiene.md`
- Modify: `docs/HAKU_DESIGN.md:1-6` (status note at the top)

- [ ] **Step 1: Add a v2 pointer to the v1 design's status note**

Insert after the existing dated status line at the top of `docs/HAKU_DESIGN.md`: `> **v2 in progress (2026-10-24):** the next generation is designed in [superpowers/specs/2026-10-24-haku-v2-design.md](superpowers/specs/2026-10-24-haku-v2-design.md). This document describes v1, which stays live until the v2 cutover.`

- [ ] **Step 2: Commit**

```bash
git add docs/HAKU_DESIGN.md docs/superpowers/specs/2026-10-24-haku-v2-design.md docs/superpowers/plans/2026-10-24-haku-v2-phase0-hygiene.md
git commit -m "docs: HAku v2 design and Phase 0 plan"
```

---

### Task 2: Move Roku dev passwords out of the repo

**Files:**
- Modify: `roku/CLAUDE.md:29,58`, `docs/HAKU_DESIGN.md:46-47`, `docs/superpowers/plans/2026-10-14-front-steps-view.md:112`, `docs/superpowers/plans/2026-10-07-shared-backgrounds.md:94`, `docs/superpowers/plans/2026-10-07-roku-wall-6x4.md:152,166`
- Create: `roku/fleet.env.example`
- Create on hosts (not committed): `~/.config/haku/fleet.env` (MiniPC, mode 600), `/etc/haku/fleet.env` (nserver, `0640 root:media`)

**Interfaces:**
- Produces: env var names `ROKU_PW_FLEET` (living .51, kids .52, master .53, den .54) and `ROKU_PW_OFFICE` (office .55, dad .56). Task 9 and Task 10 read them from `~/.config/haku/fleet.env`.

- [ ] **Step 1: Write `roku/fleet.env.example`**

Two commented lines, no values: `ROKU_PW_FLEET=` with the comment `# dev-mode password on living/kids/master/den` and `ROKU_PW_OFFICE=` with `# dev-mode password on office .55 and dad .56`. The repo `.gitignore` already ignores `*.env` and keeps `*.env.example`, so this file is tracked and any real `fleet.env` is not.

- [ ] **Step 2: Create the real env files**

On the MiniPC: `mkdir -p ~/.config/haku && install -m 600 /dev/null ~/.config/haku/fleet.env`, then fill both variables with the values from `roku/CLAUDE.md:58` using an editor (not `echo`). On nserver: `ssh nserver 'install -m 640 -o root -g media /dev/null /etc/haku/fleet.env'` and fill the same two lines via `ssh nserver 'cat > /etc/haku/fleet.env'` fed from the MiniPC file.

- [ ] **Step 3: Replace the password text in the six docs**

In `roku/CLAUDE.md:29` and the three superpowers plans: replace the literal password with `$ROKU_PW_OFFICE` and add once, in `roku/CLAUDE.md` § Deploy, the line `source ~/.config/haku/fleet.env` with the mapping of the two variables to devices. In `roku/CLAUDE.md:58`: "The dev passwords live in `~/.config/haku/fleet.env` (`ROKU_PW_FLEET` for living/kids/master/den, `ROKU_PW_OFFICE` for office .55 and dad .56) and in `/etc/haku/fleet.env` on nserver." In `docs/HAKU_DESIGN.md:46-47`: replace the password mentions with "dev password: `ROKU_PW_OFFICE` / `ROKU_PW_FLEET` in `fleet.env`". The historical plans keep their paths; only the password token changes (docs/CLAUDE.md allows this: secrets override "keep as written").

- [ ] **Step 4: Verify the scrub**

Run: `git grep -n -E "$(cut -d= -f2 ~/.config/haku/fleet.env | paste -sd'|')"` (the pattern is built from the env file, so the values never appear in the shell history as literals)
Expected: no output.

- [ ] **Step 5: Verify the example is value-free**

Run: `grep -E "=.+" roku/fleet.env.example`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add roku/CLAUDE.md roku/fleet.env.example docs/HAKU_DESIGN.md docs/superpowers/plans/2026-10-14-front-steps-view.md docs/superpowers/plans/2026-10-07-shared-backgrounds.md docs/superpowers/plans/2026-10-07-roku-wall-6x4.md
git commit -m "chore: move Roku dev passwords out of the docs into fleet.env"
```

---

### Task 3: Private GitHub remote with a read-only deploy key on nserver

**Files:**
- Create on nserver (not committed): `/root/.ssh/haku_deploy`, `/root/.ssh/haku_deploy.pub`, `/root/.ssh/config` entry, clone at `/opt/haku/homewall`
- Modify: `README.md` (one line under the intro: remote and clone location)

**Interfaces:**
- Produces: remote `origin` = `https://github.com/jimidarke/homewall` (private); nserver clone `/opt/haku/homewall` fetching over `git@github.com-haku:jimidarke/homewall.git`. Later `deploy/nserver/deploy.sh` (Phase 5) runs in that clone.

- [ ] **Step 1: Pre-push secret check**

Run: `git grep -n -i -E "Bearer ey|apikey=|LONG_LIVE_TOKEN=|HAKU_HA_TOKEN=.+" -- ':!*.example'`
Expected: no output (the `.example` files carry empty values). If anything prints, stop and remove it before continuing.

- [ ] **Step 2: Create the repository and push**

Note: commits before Task 2 still carry the two Roku dev-mode passwords in the docs. The repository is private and the passwords only open dev mode on the LAN; changing them on each Roku (dev-mode secret screen) is optional and not part of this phase.

Run: `gh repo create jimidarke/homewall --private --source=. --remote=origin --description "HAku: Home Assistant wall displays (Roku + Fire tablet + sidecar)" --push && git push origin --tags`
Expected: `origin` set; `gh repo view jimidarke/homewall --json visibility -q .visibility` prints `PRIVATE`; `git ls-remote --tags origin | wc -l` ≥ 8.

- [ ] **Step 3: Generate the deploy key on nserver and register it**

Run: `ssh nserver 'ssh-keygen -q -t ed25519 -N "" -C "nserver-haku-deploy" -f /root/.ssh/haku_deploy && printf "Host github.com-haku\n  HostName github.com\n  User git\n  IdentityFile /root/.ssh/haku_deploy\n  IdentitiesOnly yes\n" >> /root/.ssh/config && chmod 600 /root/.ssh/config'` then `ssh nserver cat /root/.ssh/haku_deploy.pub > /tmp/haku_deploy.pub && gh repo deploy-key add /tmp/haku_deploy.pub --repo jimidarke/homewall --title nserver-haku-deploy && rm /tmp/haku_deploy.pub`
Expected: `gh repo deploy-key list --repo jimidarke/homewall` shows `nserver-haku-deploy` with `read-only`.

- [ ] **Step 4: Clone on nserver**

Run: `ssh nserver 'git clone -q git@github.com-haku:jimidarke/homewall.git /opt/haku/homewall && cd /opt/haku/homewall && git log -1 --oneline'`
Expected: the Task 2 commit hash and subject.

- [ ] **Step 5: Document and commit**

Add to `README.md` after the first paragraph: "Remote: private GitHub `jimidarke/homewall`. nserver holds a read-only clone at `/opt/haku/homewall` (deploy key `nserver-haku-deploy`); v2's deploy script will run from it."

```bash
git add README.md
git commit -m "docs: record the GitHub remote and nserver clone"
git push
```

---

### Task 4: Bring every HAku HA package under `ha/packages/`

**Files:**
- Move: `sidecar/ha-gas-cost.yaml` → `ha/packages/gas_cost.yaml`; `sidecar/ha-water-helpers.yaml` → `ha/packages/haku_water.yaml`; `roku/ha-housewall.yaml` → `ha/packages/housewall.yaml`
- Create from mserver `/root/docker/homeassistantV3/config/ha/packages/`: `ha/packages/electricity_cost.yaml`, `water_cost.yaml`, `cameras_front.yaml`, `recorder_retention.yaml`, `water_meter_health.yaml`, `laundry.yaml`
- Create: `ha/README.md`
- Modify: every reference to the three old paths (`git grep -n -E "ha-gas-cost|ha-water-helpers|ha-housewall"` lists them: `CLAUDE.md`, `sidecar/CLAUDE.md`, `sidecar/README.md`, `roku/CLAUDE.md`, `docs/HAKU_DESIGN.md`, memory-free) and the root `CLAUDE.md` folder table (add an `ha/` row)

**Interfaces:**
- Produces: `ha/packages/<name>.yaml` is byte-identical to mserver `packages/<name>.yaml`. Task 6 edits `ha/packages/housewall.yaml`.

- [ ] **Step 1: Move and fetch**

Run the three `git mv` commands, then: `for f in electricity_cost water_cost cameras_front recorder_retention water_meter_health laundry; do ssh mserver "cat /root/docker/homeassistantV3/config/ha/packages/$f.yaml" > ha/packages/$f.yaml; done`

- [ ] **Step 2: Verify byte identity for all nine**

Run: `ssh mserver 'cd /root/docker/homeassistantV3/config/ha/packages && md5sum gas_cost.yaml haku_water.yaml housewall.yaml electricity_cost.yaml water_cost.yaml cameras_front.yaml recorder_retention.yaml water_meter_health.yaml laundry.yaml' > /tmp/live.md5 && (cd ha/packages && md5sum -c /tmp/live.md5)`
Expected: nine lines ending in `: OK`.

- [ ] **Step 3: Confirm no package holds a secret**

Run: `grep -n -i -E "password|token|apikey|secret" ha/packages/*.yaml | grep -v "!secret"`
Expected: no output. (`cameras_front.yaml` uses `!secret` references only. `arr_pipeline.yaml` is deliberately not imported: it embeds API keys and is not HAku's.)

- [ ] **Step 4: Write `ha/README.md`**

Contents: a table `repo file → live path → what it owns` for the nine packages; the note that `configuration.yaml` includes each package by an explicit `!include` line (a new file needs a line added); the deploy procedure (md5 compare, backup `.bak-<date>-<topic>` beside the live file, `cat >` copy, `check_config`, then the matching reloads); the pointer that `ha/deploy.sh` arrives in v2 Phase 4.

- [ ] **Step 5: Fix references and the folder table**

Replace the three old paths everywhere `git grep` found them with the new ones. In root `CLAUDE.md` add a row `| ha/ | Home Assistant packages HAku depends on (byte-for-byte copies of mserver's packages/) | mserver (192.0.2.10) |`.

- [ ] **Step 6: Run the suites that could reference the moved files**

Run: `cd sidecar && .venv/bin/python -m pytest tests -q && cd ../roku && HAKU_FIXTURE=1 npm test`
Expected: both green (nothing imports the yaml; this guards against a path string in a test).

- [ ] **Step 7: Commit**

```bash
git add -A ha sidecar roku CLAUDE.md docs/HAKU_DESIGN.md
git commit -m "chore: collect every HAku Home Assistant package under ha/packages"
```

---

### Task 5: Stop the `backyard` crash loop

**Files:**
- Modify (nserver live): `haku-hls@backyard` unit state; go2rtc runtime; `/etc/go2rtc/go2rtc.yaml`; `/etc/haku/dashboard.json`
- Modify (repo): `stream/go2rtc.yaml` (comment out `backyard:`), `sidecar/dashboard.json.example:64` (drop `"backyard"` from `streams`), `sidecar/tests/golden/roku_config.json` (regenerated), `roku/tests/contract/discovery_contract.py:31` (`EXPECTED_STREAMS` without `backyard`), `roku/tests/fixtures/discovery.json` (remove the `backyard` object), `roku/tests/fixtures/config_roku.json:313` (drop `"backyard"`), `ha/packages/housewall.yaml` (`cam=backyard` → `cam=yard` in the two after-hours automations), `docs/HAKU_DESIGN.md` § Open items (mark done, with the re-enable steps)
- Modify (mserver live): `packages/housewall.yaml`

- [ ] **Step 1: Disable the unit and clear its files**

Run: `ssh nserver 'systemctl disable --now haku-hls@backyard && rm -f /run/haku-hls/backyard.m3u8 /run/haku-hls/backyard_seg_*.ts && systemctl is-enabled haku-hls@backyard; systemctl is-active haku-hls@backyard'`
Expected: `disabled` then `inactive`.

- [ ] **Step 2: Record the restart counter, wait, confirm it froze**

Run: `ssh nserver 'systemctl show -p NRestarts --value haku-hls@backyard; sleep 60; systemctl show -p NRestarts --value haku-hls@backyard; journalctl -u haku-hls@backyard --since -60s --no-pager | wc -l'`
Expected: the same number twice, then `0` (one `Stopped` line is acceptable in the first minute).

- [ ] **Step 3: Remove the stream from go2rtc at runtime (no restart)**

Run: `ssh nserver 'curl -s -X DELETE "http://127.0.0.1:1984/api/streams?src=backyard"; curl -s http://127.0.0.1:1984/api/streams | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)))"'`
Expected: `['front', 'front_steps', 'mosaic', 'side', 'yard']`.

- [ ] **Step 4: Verify the other producers were not disturbed (Review Focus 1)**

Run: `ssh nserver 'a=$(curl -s http://127.0.0.1:1984/api/streams | python3 -c "import sys,json; print(json.load(sys.stdin)[\"front\"][\"producers\"][0][\"bytes_recv\"])"); sleep 5; b=$(curl -s http://127.0.0.1:1984/api/streams | python3 -c "import sys,json; print(json.load(sys.stdin)[\"front\"][\"producers\"][0][\"bytes_recv\"])"); echo "front bytes_recv delta=$((b-a))"'; for ip in 192.0.2.51 192.0.2.53 192.0.2.54 192.0.2.55; do curl -s -m 4 http://$ip:8060/query/media-player | grep -o 'state="[a-z]*"'; done`
Expected: a positive delta; each reachable Roku prints `state="play"`.

- [ ] **Step 5: Persist the removal in `go2rtc.yaml` and the discovery fallback (repo, then nserver)**

In `stream/go2rtc.yaml`, comment out the `backyard:` stream and its URL line with the note `# disabled 2026-10-24: camera .34 offline (RTSP closed, NVR can't reach it). Re-enable here and 'systemctl enable --now haku-hls@backyard' when it returns.` In `stream/haku-discovery.py`, comment out the `"backyard"` entry of `STREAM_METADATA` with the same note (it is only the fallback roster used when go2rtc is unreachable, but it would re-advertise a dead stream). Then for each of the two files: `ssh nserver md5sum <live path>` must equal `git show HEAD:<repo path> | md5sum` (the pre-edit file; on 2026-10-24 `71b94c2a…` and `1316bc44…`); back up beside the live file as `.bak-20261024-backyard`; copy with `ssh nserver 'cat > <live path>' < <repo path>`. Do **not** restart go2rtc (the runtime already matches; a restart would interrupt every wall). Do not restart `haku-discovery` here either: Task 8 step 4 restarts it (and, through `PartOf=`, the sidecar) in one quiet moment.

- [ ] **Step 6: Confirm discovery dropped it**

Run: `sleep 65; curl -s http://192.0.2.20:1985/discovery.json | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)['streams']))"`
Expected: no `backyard` (discovery refreshes from go2rtc every 60 s).

- [ ] **Step 7: Drop it from the live and example dashboard configs**

Live: `ssh nserver 'cp -p /etc/haku/dashboard.json /etc/haku/dashboard.json.bak-20261024-backyard'`; fetch it (`ssh nserver cat /etc/haku/dashboard.json > "$SCRATCH/dashboard.json"`), remove the `"backyard"` string from `modules[id=cameras].streams` with `python3 -c` (`json.load`, filter the list, `json.dump(indent=2)`; keep `entities.motion.backyard`, the HA sensor still exists), and copy it back with `ssh nserver 'cat > /etc/haku/dashboard.json' < "$SCRATCH/dashboard.json"`. The sidecar hot-reloads on mtime: `curl -s http://192.0.2.20:1986/api/config | python3 -c "import sys,json; m=[x for x in json.load(sys.stdin)['modules'] if x['id']=='cameras'][0]; print(m['streams'])"` prints `['front', 'yard', 'side', 'mosaic']`. Repo: the same removal in `sidecar/dashboard.json.example`.

- [ ] **Step 8: Regenerate the sidecar golden and run the suite**

Run: `cd sidecar && HAKU_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_roku_golden.py -q && .venv/bin/python -m pytest tests -q`
Expected: green; `git diff --stat sidecar/tests/golden/` shows only the `streams` array change.

- [ ] **Step 9: Update the Roku contract and fixtures**

`EXPECTED_STREAMS = ("mosaic", "front", "front_steps", "yard", "side")`; remove the `backyard` object from `roku/tests/fixtures/discovery.json` and the `"backyard"` string from `roku/tests/fixtures/config_roku.json`. Run: `cd roku && HAKU_FIXTURE=1 npm run test:contract && npm run test:contract`
Expected: both green (the second is against the live sidecar and discovery).

- [ ] **Step 10: Point the after-hours automations at `yard`**

In `ha/packages/housewall.yaml`, change `cam=backyard` to `cam=yard` in `housewall_after_hours_back_motion` and `housewall_after_hours_back_door` payloads, and update their descriptions. Deploy: `ssh mserver md5sum /root/docker/homeassistantV3/config/ha/packages/housewall.yaml` equals `git show HEAD:ha/packages/housewall.yaml | md5sum` (`0b3c2e29…` on 2026-10-24); back up as `housewall.yaml.bak-20261024-yard`; `cat >` copy; then validate and reload with the token kept on mserver:

```bash
ssh mserver 'T=$(grep LONG_LIVE_TOKEN /home/displayuser/ha-calendar/.env | cut -d= -f2-); H="Authorization: Bearer $T"
curl -s -X POST -H "$H" http://127.0.0.1:8123/api/config/core/check_config
curl -s -X POST -H "$H" http://127.0.0.1:8123/api/services/automation/reload >/dev/null
curl -s -H "$H" http://127.0.0.1:8123/api/states/automation.housewall_after_hours_back_door | python3 -c "import sys,json; print(json.load(sys.stdin)[\"state\"])"'
```

Expected: `"result": "valid"` then `on`.

- [ ] **Step 11: Tick the open item and commit**

In `docs/HAKU_DESIGN.md` § Open items, mark the backyard item done: "2026-10-24: unit disabled, stream removed from go2rtc/discovery/config, after-hours automations use `yard`; re-enable = uncomment in `stream/go2rtc.yaml`, deploy, `systemctl enable --now haku-hls@backyard`, add back to `streams`, revert the automations."

```bash
git add stream/go2rtc.yaml sidecar/dashboard.json.example sidecar/tests/golden roku/tests ha/packages/housewall.yaml docs/HAKU_DESIGN.md
git commit -m "fix(stream): retire the offline backyard camera instead of crash-looping"
```

---

### Task 6: Commit the live `dashboard.json` under `config/live/`

**Files:**
- Create: `config/live/dashboard.json` (copy of `/etc/haku/dashboard.json` after Task 5), `config/README.md`
- Modify: root `CLAUDE.md` folder table (add `config/` row), `.gitignore` is already fine (`*.env` only)

- [ ] **Step 1: Copy and record the checksum**

Run: `mkdir -p config/live && ssh nserver cat /etc/haku/dashboard.json > config/live/dashboard.json && ssh nserver 'sha256sum /etc/haku/dashboard.json' | awk '{print $1"  dashboard.json"}' > config/live/SHA256SUMS && (cd config/live && sha256sum -c SHA256SUMS)`
Expected: `dashboard.json: OK`.

- [ ] **Step 2: Write `config/README.md`**

Contents: `config/live/` holds the live `/etc/haku/dashboard.json` as last deployed (no secrets live in it: entity ids, labels, geometry); the drift check `ssh nserver sha256sum /etc/haku/dashboard.json` vs `SHA256SUMS`; the rule "edit here, copy to nserver (`cat >`), the sidecar hot-reloads on mtime, then refresh `SHA256SUMS`"; v2 will add `dashboard.v2.json`, `cameras.yaml`, `fleet.yaml` and a schema (spec § 6.3, § 6.4, § 6.6). Add a `| config/ | live sidecar config as deployed (config/live/) | nserver /etc/haku |` row to root `CLAUDE.md`.

- [ ] **Step 3: Commit**

```bash
git add config CLAUDE.md
git commit -m "chore: track the live dashboard.json under config/live"
```

---

### Task 7: Set Home Assistant's time zone to Edmonton

**Files:**
- Modify (mserver live, via the WebSocket API): HA core config `time_zone`

- [ ] **Step 1: Record the current value and the current offset**

Run (token stays on mserver): `ssh mserver 'T=$(grep LONG_LIVE_TOKEN /home/displayuser/ha-calendar/.env | cut -d= -f2-); curl -s -H "Authorization: Bearer $T" http://127.0.0.1:8123/api/config | python3 -c "import sys,json; print(json.load(sys.stdin)[\"time_zone\"])"; curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d "{\"template\":\"{{ now().strftime(\\\"%z %Z\\\") }}\"}" http://127.0.0.1:8123/api/template'`
Expected: `America/Regina` and `-0600 CST`.

- [ ] **Step 2: Change it over the admin WebSocket (the sidecar's token is the owner's, see spec § 3.1)**

Run on nserver with the sidecar venv: `ssh nserver 'set -a; . /etc/haku/haku.env; set +a; /opt/haku/sidecar/venv/bin/python -c "
import json, os, websocket
ws = websocket.create_connection(os.environ[\"HAKU_HA_URL\"].replace(\"http\",\"ws\",1)+\"/api/websocket\", timeout=8); ws.recv()
ws.send(json.dumps({\"type\":\"auth\",\"access_token\":os.environ[\"HAKU_HA_TOKEN\"]})); print(json.loads(ws.recv())[\"type\"])
ws.send(json.dumps({\"id\":1,\"type\":\"config/core/update\",\"time_zone\":\"America/Edmonton\"})); print(json.loads(ws.recv()).get(\"success\"))"'`
Expected: `auth_ok` then `True`.

- [ ] **Step 3: Verify the zone changed and the offset did not (Review Focus 3)**

Re-run Step 1.
Expected: `America/Edmonton` and `-0600 MDT`.

- [ ] **Step 4: Note it in the design doc and commit**

Append to spec § 3.5: "Done 2026-10-24 via `config/core/update`; HA now reports `America/Edmonton`."

```bash
git add docs/superpowers/specs/2026-10-24-haku-v2-design.md
git commit -m "docs: HA time zone aligned to Edmonton"
```

---

### Task 8: Fix the two unit files

**Files:**
- Modify: `sidecar/haku-sidecar.service:3` (`Documentation=`), add `Environment=MPLCONFIGDIR=/tmp/haku-matplotlib` under `[Service]`
- Modify: `stream/haku-hls.service` (the mosaic unit): add `ExecStartPre=/bin/sh -c 'rm -f /run/haku-hls/mosaic.m3u8 /run/haku-hls/seg_*.ts'` before `ExecStart`
- Deploy both to `/etc/systemd/system/` on nserver

- [ ] **Step 1: Edit the units**

`Documentation=https://github.com/jimidarke/homewall/blob/main/sidecar/README.md` (one valid URI; systemd rejected the current free text at every daemon-reload). The `MPLCONFIGDIR` line removes the matplotlib cache warning the journal shows at every start. The mosaic `ExecStartPre` mirrors the template unit's cleanup for the un-prefixed mosaic segment names (`seg_%05d.ts`), which is why `seg_1841xx.ts` from 10-22 still sit in `/run/haku-hls`.

- [ ] **Step 2: Lint the units**

Run: `systemd-analyze verify sidecar/haku-sidecar.service stream/haku-hls.service 2>&1 | grep -v "Unit .* not found"`
Expected: no `Invalid URL` or syntax warnings (dependency "not found" lines are expected off-host).

- [ ] **Step 3: Deploy with drift check and backup**

Run: `ssh nserver 'cd /etc/systemd/system && md5sum haku-sidecar.service haku-hls.service'` and compare with `git show HEAD:sidecar/haku-sidecar.service | md5sum; git show HEAD:stream/haku-hls.service | md5sum` — the live files must equal the committed pre-edit files (`433e73c6…` and `8a167309…` on 2026-10-24). Then: `ssh nserver 'cp -p /etc/systemd/system/haku-sidecar.service /etc/systemd/system/haku-sidecar.service.bak-20261024-nits; cp -p /etc/systemd/system/haku-hls.service /etc/systemd/system/haku-hls.service.bak-20261024-nits'`; copy both with `cat >`; `ssh nserver systemctl daemon-reload`.

- [ ] **Step 4: Restart discovery and the sidecar; restart the mosaic unit only if idle**

Run: `ssh nserver 'systemctl restart haku-discovery && sleep 5 && systemctl is-active haku-discovery haku-sidecar && journalctl -u haku-sidecar --since -30s --no-pager | grep -ci "matplotlib\|Invalid URL"; curl -s http://127.0.0.1:1986/api/health | python3 -c "import sys,json; print(json.load(sys.stdin)[\"ha_connected\"])"; curl -s http://192.0.2.20:1985/discovery.json | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)[\"streams\"]))"'` (restarting `haku-discovery` restarts the sidecar through `PartOf=`, which also loads Task 5's discovery file)
Expected: `active` twice, `0`, `True`, and a stream list without `backyard`. Then: `ssh nserver 'journalctl -u haku-discovery --since -90s --no-pager | grep -c "/hls/mosaic"'`; if `0` (nobody watching the mosaic), `ssh nserver 'systemctl restart haku-hls && sleep 5 && ls /run/haku-hls/ | grep -c "^seg_1841"'` → `0`. If someone is watching, skip the mosaic restart and note it; the cleanup applies at its next restart.

- [ ] **Step 5: Commit**

```bash
git add sidecar/haku-sidecar.service stream/haku-hls.service
git commit -m "fix(units): valid Documentation URI, matplotlib cache dir, mosaic segment cleanup"
```

---

### Task 9: Roku 1.3.2: registry write only on change, drop the HA token bootstrap

**Files:**
- Modify: `roku/source/Config.brs:198-203` (`regWrite`), `roku/source/Api.brs:12-14` (`hkSetHubBase`), `roku/components/MainScene.brs:134-143` (token bootstrap), `roku/components/InputPumpTask.brs:21` (raw param print), `roku/VERSION.txt`, `roku/package.json`, `roku/manifest`
- Test: `roku/tests/unit/test_pure.brs` (new cases for `hkRegChanged`), `roku/tests/smoke/smoke.sh` (two new assertions)

**Interfaces:**
- Produces: `function hkRegChanged(current as dynamic, value as string) as boolean` in `Config.brs` (true when `current` is invalid or differs from `value`); `sub regWriteIfChanged(key as string, value as string)` in `Config.brs`, which reads, calls `hkRegChanged`, and only then writes, flushes and logs `hkEvent("reg_write", { key: key })`. Task 10 sideloads the resulting 1.3.2.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/unit/test_pure.brs`, in the existing `assertEq` style:

```brightscript
assertEq(hkRegChanged(invalid, "http://a:1986"), true, "regChanged: nothing cached writes")
assertEq(hkRegChanged("http://a:1986", "http://a:1986"), false, "regChanged: same value skips")
assertEq(hkRegChanged("http://a:1986", "http://b:1986"), true, "regChanged: new value writes")
assertEq(hkRegChanged("", "x"), true, "regChanged: empty cached writes")
```

- [ ] **Step 2: Run the unit suite to see them fail**

Run: `cd roku && npm run test:unit`
Expected: FAIL (runtime error `hkRegChanged` undefined, or 4 `FAIL` lines).

- [ ] **Step 3: Implement**

In `Config.brs`: `hkRegChanged` next to the other pure helpers; `regWriteIfChanged(key, value)` beside `regWrite`, using `regRead(key)` then `regWrite` only when `hkRegChanged` is true, followed by `hkEvent("reg_write", { key: key })`. In `Api.brs`, `hkSetHubBase` calls `regWriteIfChanged`. (`brs` has no `roRegistrySection`, so the registry path itself is checked on the device in Step 8.)

- [ ] **Step 4: Remove the token bootstrap**

In `MainScene.brs:134-143` delete the `haToken`/`haUrl` registry writes and add, in `init()`, `regDelete("haToken")` and `regDelete("haUrl")` with the comment "one-time cleanup of the unused 2026-05 bootstrap; harmless when absent". In `InputPumpTask.brs:21` pass the params through `hkScrub` before printing, or drop the print.

- [ ] **Step 5: Bump the version**

`roku/VERSION.txt` → `1.3.2`; `roku/package.json` `"version": "1.3.2"`; `roku/manifest` `build_version=00002`.

- [ ] **Step 6: Lint, unit, fixture contract**

Run: `cd roku && npm run lint && npm run test:unit && HAKU_FIXTURE=1 npm run test:contract`
Expected: lint clean; `RESULT pass=N fail=0` with N four higher than before; contract green.

- [ ] **Step 7: Extend the smoke assertions**

In `tests/smoke/smoke.sh`, after the existing `event=launch` assertion, add: count of `event=reg_write key=hubBaseV2` lines in the capture must be ≤ 1, and the capture must not contain `haToken` (case-insensitive). Reuse the script's existing grep/assert helpers and exit-code table.

- [ ] **Step 8: Smoke on the office Roku (Review Focus 2)**

Run: `curl -s http://192.0.2.55:8060/query/active-app | grep -q 'id="dev"' && (source ~/.config/haku/fleet.env && ROKU_IP=192.0.2.55 ROKU_DEV_PASSWORD=$ROKU_PW_OFFICE SMOKE_TIMEOUT=90 tests/smoke/smoke.sh)`
Expected: smoke exit 0; its console capture shows `event=launch … version=1.3.2`, exactly one `reg_write key=hubBaseV2` in the first seconds, none later, and no `haToken`. If the office Roku is not on HAku, wait and retry; never sideload over another app.

- [ ] **Step 9: Commit**

```bash
git add roku/source roku/components roku/tests roku/VERSION.txt roku/package.json roku/manifest
git commit -m "fix(roku): write the registry only on change, drop the HA token bootstrap (1.3.2)"
```

---

### Task 10: Roll 1.3.2 to the fleet, gated on active-app

**Files:**
- Create: `roku/scripts/fleet-deploy.sh`
- Modify: `roku/CLAUDE.md` § Deploy (document the script)

**Interfaces:**
- Consumes: `~/.config/haku/fleet.env` (Task 2 variable names), `scripts/deploy.js` (`ROKU_IP`, `ROKU_DEV_PASSWORD`).
- Produces: `scripts/fleet-deploy.sh [ip…]`: for each Roku (default: the six in `roku/CLAUDE.md`'s table), GET `/query/active-app`; sideload only when it is HAku; print a one-line result per device (`deployed 1.3.2` / `skipped: <active app>` / `unreachable`); exit 0 if nothing failed (skips are not failures). Password choice: `.55` and `.56` use `ROKU_PW_OFFICE`, the rest `ROKU_PW_FLEET`.

- [ ] **Step 1: Write the script**

bash, `set -euo pipefail`, sources `~/.config/haku/fleet.env`, 4 s curl timeouts, calls `npm run deploy --silent` with the env set, then re-queries `/query/apps` and prints the `dev` app's `version=` attribute as the deployed version.

- [ ] **Step 2: Dry run on the office only**

Run: `cd roku && scripts/fleet-deploy.sh 192.0.2.55`
Expected: `192.0.2.55 deployed 1.3.2` (already on 1.3.2 from Task 9; this proves the gate and the version readback).

- [ ] **Step 3: Fleet run**

Run: `cd roku && scripts/fleet-deploy.sh`
Expected: one line per device; any `skipped:` line names the app someone is watching (come back later); `unreachable` for a TV that is off (kids `.52` and dad `.56` were off on 2026-10-24). Record the lines in the commit message body.

- [ ] **Step 4: Verify the fleet versions**

Run: `for ip in 192.0.2.51 192.0.2.52 192.0.2.53 192.0.2.54 192.0.2.56 192.0.2.55; do printf "%s " $ip; curl -s -m 4 http://$ip:8060/query/apps | grep -o 'id="dev"[^>]*version="[0-9.]*"' || echo off; done`
Expected: `version="1.3.2"` on every reachable device.

- [ ] **Step 5: Document and commit**

In `roku/CLAUDE.md` § Deploy add: "Fleet: `scripts/fleet-deploy.sh [ip…]` sideloads only to Rokus currently showing HAku and prints the deployed version per device." Then:

```bash
git add roku/scripts/fleet-deploy.sh roku/CLAUDE.md
git commit -m "feat(roku): gated fleet deploy script; 1.3.2 rolled to the walls that were on HAku"
```

---

### Task 11: Cap qBittorrent's memory on nserver

**Files:**
- Modify (nserver live): `/root/docker/qbittorrent/docker-compose.yml` (add `mem_limit: 1536m` to the `qbittorrent` service)

- [ ] **Step 1: Back up and edit**

Run: `ssh nserver 'cp -p /root/docker/qbittorrent/docker-compose.yml /root/docker/qbittorrent/docker-compose.yml.bak-20261024-memlimit && grep -n "qbittorrent:\|image:\|mem_limit" /root/docker/qbittorrent/docker-compose.yml'`, then insert `    mem_limit: 1536m` under the `qbittorrent:` service at the same indentation as `image:` (use `ssh nserver 'cat > …'` with the edited file, or `sed -i` after the `image:` line).

- [ ] **Step 2: Apply**

Run: `ssh nserver 'cd /root/docker/qbittorrent && docker compose config --quiet && docker compose up -d && sleep 10 && docker inspect qbittorrent --format "mem={{.HostConfig.Memory}} status={{.State.Status}}" && curl -s -o /dev/null -w "webui=%{http_code}\n" http://127.0.0.1:808/'`
Expected: `mem=1610612736 status=running` and `webui=200` (or `401`/`403`, which also proves the UI answers).

- [ ] **Step 3: Record the before/after in the baseline notes**

Add to `docs/baseline/2026-10-24.md` (created in Task 14; if Task 11 runs first, keep the two numbers in the commit message and copy them in Task 14): nserver `free -m` swap used and qBittorrent RSS before and after. No repo file changes otherwise; nothing to commit here.

---

### Task 12: Rotate the sidecar's HA token to a dedicated administrator user (needs the user)

**Files:**
- Modify (nserver live): `/etc/haku/haku.env` (`HAKU_HA_TOKEN=`)

The user performs the HA UI steps; the executor does the nserver side and the checks.

- [ ] **Step 1 (user): Create the user and token**

In HA: Settings → People → Users → Add user: name `haku`, username `haku`, **Administrator** on, "Can only log in from the local network" on. Then sign in as `haku` in a private browser window, Profile → Security → Long-lived access tokens → Create → name `haku-server`. Keep the token on the clipboard only.

- [ ] **Step 2: Install the token on nserver without echoing it**

Run: `ssh -t nserver 'read -rs -p "paste haku-server token: " T; echo; cp -p /etc/haku/haku.env /etc/haku/haku.env.bak-20261024-token; sed -i "s|^HAKU_HA_TOKEN=.*|HAKU_HA_TOKEN=$T|" /etc/haku/haku.env; unset T; systemctl restart haku-sidecar; sleep 3; curl -s http://127.0.0.1:1986/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[\"ha_connected\"], d[\"ha\"][\"entity_count\"])"'`
Expected: `True 7xx`.

- [ ] **Step 3: Verify the token's identity and rights**

Run the WebSocket probe from Task 7 Step 2 with `{"id":1,"type":"auth/current_user"}` instead of the config update, printing only `name` and `is_admin`.
Expected: `haku True`.

- [ ] **Step 4 (user): Revoke the old token**

In HA as Jimi: Profile → Security → Long-lived access tokens → delete the token the sidecar used until today (the one created in May 2026 for the Rokus / "rokuapp"). Then re-run Step 2's health check.
Expected: still `True`.

- [ ] **Step 5: Record**

Append to spec § 3.1 first bullet: "Done 2026-10-24: user `haku` (administrator, local-only), token `haku-server`; the May 2026 owner token is revoked." Commit:

```bash
git add docs/superpowers/specs/2026-10-24-haku-v2-design.md
git commit -m "docs: sidecar now authenticates as the dedicated haku admin user"
```

---

### Task 13: Static DHCP leases and DNS names for the Rokus (needs router access)

**Files:**
- Create: `docs/fleet-leases.md` (the lease table: id, IP, MAC, model; no secrets)

- [ ] **Step 1: Collect MACs**

Known from 2026-10-24 `/query/device-info`: living `.51` `xx:xx:xx:xx:xx:xx`, master `.53` `xx:xx:xx:xx:xx:xx`, den `.54` `xx:xx:xx:xx:xx:xx`, office `.55` `xx:xx:xx:xx:xx:xx`. For kids `.52` and dad `.56` run `curl -s http://<ip>:8060/query/device-info | grep -oE "<wifi-mac>[^<]*"` when the TV is on. The tablet `.60` is already static (`xx:xx:xx:xx:xx:xx`, NETWORK.md).

- [ ] **Step 2 (user or executor with router access): Add the leases and names on the MikroTik**

For each Roku: `/ip dhcp-server lease add address=192.0.2.<n> mac-address=<MAC> server=<dhcp server name from '/ip dhcp-server print'> comment="roku-<id> (HAku)"` and `/ip dns static add name=roku-<id>.home.lan address=192.0.2.<n> comment="HAku"`. (The DHCP domain is `home.lan` per `home-arr/docs/NETWORK.md`.)

- [ ] **Step 3: Verify**

Run on the MiniPC: `for n in living master den office; do getent hosts roku-$n.home.lan || echo "roku-$n unresolved"; done`
Expected: four lines with the right IPs (kids and dad once their MACs are in).

- [ ] **Step 4: Commit the table**

```bash
git add docs/fleet-leases.md
git commit -m "docs: Roku fleet static leases and DNS names"
```

---

### Task 14: `tools/baseline.sh` and the committed baseline

**Files:**
- Create: `tools/baseline.sh`, `docs/baseline/2026-10-24.md`
- Modify: root `CLAUDE.md` folder table (add `tools/` row), `README.md` (one line)

**Interfaces:**
- Produces: `tools/baseline.sh [seconds]` prints a Markdown report to stdout with sections `Hosts`, `Processes (nserver)`, `Traffic (<seconds> s)`, `Units`, `Home Assistant`, `Rokus`, `Clients connected to the sidecar`. It is re-run after v2's Phase 10 (spec § 11).

- [ ] **Step 1: Write the script**

bash, `set -uo pipefail`, default capture 20 s, `trap` that runs `ssh nserver 'pkill -x tcpdump' || true` on EXIT. Sections and commands (all read-only):
- Hosts: `ssh nserver 'uptime; free -m'`, `ssh mserver 'uptime; free -m; docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" homeassistant'`.
- Processes: `ssh nserver 'top -b -n 2 -d 3 -p "$(systemctl show -p MainPID --value haku-sidecar),$(systemctl show -p MainPID --value go2rtc)"'` last two process lines; `ps -eo pid,%cpu,rss,etime,args | grep -E "ffmpeg|haku-discovery" | grep -v grep`.
- Traffic: the three concurrent `timeout <s> tcpdump -ni any -A -s 400 -l` captures (dst 192.0.2.10:8123; dst port 1986 from non-local; dst port 1985 from non-local) summarised as `count method path` and `count src-ip path`, plus the byte counters with plain `tcpdump -ni any -nn <filter> | grep -oE "length [0-9]+"` summed (`-q` output has no length field). Exactly the commands used on 2026-10-24 (memory `reference-sidecar-deploy-and-ha-access`).
- Units: `ssh nserver 'for u in $(systemctl list-units "haku*" --all --no-pager --plain | awk "{print \$1}" | grep haku); do printf "%s %s %s\n" $u $(systemctl show -p ActiveState --value $u) $(systemctl show -p NRestarts --value $u); done'`.
- Home Assistant: the token is read **inside** the mserver ssh subshell (`T=$(grep LONG_LIVE_TOKEN /home/displayuser/ha-calendar/.env | cut -d= -f2-)`), never returned: `/api/config` version + time_zone; `/api/states` byte size, entity count, unavailable/unknown counts.
- Rokus: for the six IPs, `device-info` model + software, `active-app`, `apps` dev version, `chanperf` cpu-percent user and memory used, `media-player` state; `off` when unreachable within 4 s.
- Clients: `ssh nserver 'ss -Htn state established "( sport = :1986 )"'` grouped by peer.

- [ ] **Step 2: Run it and save the report**

Run: `mkdir -p docs/baseline && tools/baseline.sh 20 | tee docs/baseline/2026-10-24.md`
Expected: all seven sections present; HA→sidecar request mix shows `GET /api/states` ≈ 20 per 20 s; the backyard unit line reads `inactive` with its frozen restart count.

- [ ] **Step 3: Compare with the numbers in the spec**

Open `docs/superpowers/specs/2026-10-24-haku-v2-design.md` § 2 next to the report. Expected: the same order of magnitude on every line; note any line that differs by more than 2× at the top of the report with a one-line reason (time of day, TVs off).

- [ ] **Step 4: Verify nothing is left running (Review Focus 5)**

Run: `ssh nserver 'pgrep -c tcpdump || echo 0'` and, once, `tools/baseline.sh 20 & sleep 5; kill -INT $!; sleep 2; ssh nserver 'pgrep -c tcpdump || echo 0'`
Expected: `0` both times.

- [ ] **Step 5: Document and commit**

Root `CLAUDE.md` table: `| tools/ | operator scripts: baseline.sh (the measurements v2 must beat) | MiniPC |`. `README.md`: "Baseline: `tools/baseline.sh` → `docs/baseline/`." Then:

```bash
git add tools/baseline.sh docs/baseline/2026-10-24.md CLAUDE.md README.md
git commit -m "feat(tools): reproducible HAku baseline measurement and the 2026-10-24 report"
git push
```

---

### Task 15: Close Phase 0

**Files:**
- Modify: `docs/superpowers/specs/2026-10-24-haku-v2-design.md` § 10 row 0 (status), `docs/HAKU_DESIGN.md` § Open items (token rotation item ticked)

- [ ] **Step 1: Check every Phase 0 exit criterion**

Run: `ssh nserver 'systemctl show -p NRestarts --value haku-hls@backyard; systemctl is-active haku-hls@backyard'` (frozen count, `inactive`); the Task 7 Step 1 command (`America/Edmonton`); `git remote -v` (origin on GitHub) and `ssh nserver 'cd /opt/haku/homewall && git fetch -q && git status -sb | head -1'` (`## main...origin/main`); the Task 2 Step 4 grep (empty); `ls docs/baseline/2026-10-24.md`.
Expected: all as stated.

- [ ] **Step 2: Mark the phase done and commit**

In the spec's § 10 row 0 append "**Done 2026-10-xx**" with the date; in `docs/HAKU_DESIGN.md` § Open items tick "HA token rotation". Anything skipped (a Roku that stayed on 1.3.1 because someone was watching, a lease missing a MAC) is listed under a new "Phase 0 leftovers" line in the spec's § 9.

```bash
git add docs
git commit -m "docs: Phase 0 complete"
git push
```
