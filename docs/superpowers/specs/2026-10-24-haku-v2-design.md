# HAku v2 design

Date: 2026-10-24. Status: approved by the user for planning (decisions in § 3). Companion: the audit and measured baseline in `~/.claude/plans/we-ve-built-a-successful-shimmying-tower.md` (session plan; the numbers that matter are repeated in § 2).

## 1. Intent and why

HAku v1 works and the household likes it: six Rokus and the kitchen Fire 7 show the same glass dashboard, the front camera plays live, the door opens and every wall shows the steps. It got there feature by feature, and each step left a seam. The same decision now lives in several places, every hop polls, the contract is three hand-captured snapshots, health is dishonest, deploys are manual file copies, and nothing watches the fleet.

v2 is a ground-up rebuild of all three parts (server, Roku channel, tablet app) with the same look and the same behaviour as seen from the couch, built beside v1 and cut over once. The point is long-term success: one owner per decision, change-driven data flow, a schema'd contract, honest health with alerting, one-command deploys, and a fleet you can see.

## 2. Where v1 stands (measured 2026-10-24)

| Fact | Value |
|---|---|
| Sidecar → HA | `GET /api/states` once a second (310 KB, 701 entities) plus `GET /api/logbook` 0.6/s: 297 KB/s, about 25 GB/day, whether or not any display is on |
| Clients → sidecar | each Roku 1 req/s (Express 3930: 2 s), tablet ~1 req/s, 10–12 KB each; each Roku also flushes its registry on every poll |
| Rokus → HLS | one playlist and one 2 s segment every ~4 s each; ~2 Mbps per Roku on the front camera |
| nserver | i5-1035G1, 7.5 GB; swap 1.85 GB used; sidecar 114 MB RSS + 304 MB swapped; mosaic capture ffmpeg 63% of a core 24/7 with no viewer; `haku-hls@backyard` 25,580 restarts (camera offline) |
| mserver / HA | HA 2026.9.4 in Docker, 4.6% CPU, 889 MB; recorder 494 MB; HA time zone `America/Regina` while everything else is `America/Edmonton` |
| Drift | deployed sidecar, stream files and HA packages equal the repo byte for byte; seven HA packages exist only on mserver; the live `dashboard.json` is not in the repo; the repo has no remote |
| Clients | all six Rokus on 1.3.1 (kids and dad's TVs off at capture time); tablet 1.1.1; HAku channel 62–65 MB, 11–18% CPU on Sticks |

Debt themes the design answers: polling at every hop (T1); the same decision in several places (T2: door event ×5, camera roster ×7, ~15 display helpers hand-ported Kotlin→BrightScript); contract pinned by snapshots of a view no client reads (T3); dishonest health and no alerting (T4); lifecycle coupling and always-on transcodes (T5); manual deploys and an invisible fleet (T6).

## 3. Decisions (the user's, 2026-10-24)

1. **Parallel greenfield.** New repo layout and contract v2; server, Roku channel and tablet app rewritten together; v1 keeps running on its current ports and units until one planned cutover. The walls never go dark.
2. **The server owns the view-model.** It decides every display token: text, severity, accent, stale/hold, door order, day labels, LED frame parameters, overlay timing. Clients lay out, animate and play video. Both displays keep their current glass look.
3. **HA decides, the server delivers.** HA automations stay the rule engine and emit `haku_event` on HA's event bus; the server subscribes and delivers takeovers, overlays and toasts to every client over the same change stream. `rest_command`s, `script.housewall_broadcast`, ECP pushes and the six hard-coded Roku IPs are retired.
4. **Compose stack on nserver.** Server, stream packager/discovery and fleet watcher in docker-compose with memory limits and healthchecks; go2rtc stays bare-metal (it needs the GPU and the USB capture stick); git-pull deploy with drift detection; behind the existing nginx-proxy for humans.
5. **Time zone: Edmonton.** HA core `time_zone` becomes `America/Edmonton` in Phase 0, before 2026-11-01. Done 2026-10-24 via `config/core/update`; HA now reports `America/Edmonton`.
6. **Dad's Roku is a wall like the others:** it receives takeovers (`targets: all`) and the fleet watcher relaunches it over ECP.
7. **Tablet door camera: Media3 ExoPlayer RTSP** from go2rtc (sub-second), HLS `VideoView` kept behind a flag as fallback, gated at 95 MB PSS.
8. **After cutover the v1 directories are deleted** in one commit after tagging `v1-final`.
9. **Git remote: a private GitHub repository** with a read-only deploy key on nserver; `deploy.sh` can redeploy an already-fetched ref when GitHub is unreachable.
10. **After-hours alerts go to every wall and the kitchen tablet** (`targets: all`), the same as the door takeover.
11. **qBittorrent gets a memory cap in Phase 0** (a `mem_limit` on its compose service on nserver, about 1.5 GB) so the soak measures HAku and not the torrent client.

### 3.1 Builder-check resolutions (my calls, for the user to check)

A fresh reviewer read this document as a builder would. Facts verified and calls made:

- **HA token must be admin.** HA refuses `subscribe_events` for a custom event type unless the WebSocket user is an administrator (only built-in types are allow-listed). Verified live: the v1 sidecar's token already belongs to the owner account (`is_admin: true`), and `subscribe_events haku_event` succeeds with it. Call: at the Phase 0 rotation, create a dedicated HA user `haku` with administrator rights and mint the server's long-lived token from it, so the token is revocable on its own and named in HA's logs. HA has no finer scopes. **Done 2026-10-24:** user `haku` (administrator, local-only) exists, its `haku-server` token is in `/etc/haku/haku.env`, the sidecar authenticates as `haku`, and the owner's `rokuapp` token is revoked. The `haku-server` token was pasted into the working chat during installation, so it should be re-minted from the UI and installed with the `ssh -t nserver 'read -rs …'` command in `ha/README.md` § Rotate, then the pasted one deleted. HA refuses `auth/long_lived_access_token` over a connection that itself uses a long-lived token, so the re-mint has to go through the UI (or a password login).
- **go2rtc API stays reachable on the LAN, with credentials.** HA's generic camera entry for `192.0.2.20` (`camera.camerafeed`) reads go2rtc's MJPEG and snapshot endpoints on `:1984`, and the optional `go2rtc: url:` follow-up needs the API from mserver too. Call: `api.listen: 192.0.2.20:1984` with `api.username`/`api.password` from `cam-creds.env` (go2rtc substitutes env vars); HA's generic camera gets the same credentials; the v1 Roku PIP (the only unauthenticated consumer) is deleted in v2. `origin: "*"` goes.
- **The tablet's firewall quarantine does not affect LAN traffic.** `iot` only drops WAN-bound packets and redirects NTP; LAN is switched. So `:1987`, `:1988`/`:1985` and RTSP `:8554` are reachable from the tablet, and no Roku is in that list.
- **After-hours camera is `yard` while `backyard` is disabled.** The playground camera (`backyard`, .34) is offline; the Reolink PTZ (`yard`) covers the back yard. Re-enabling `backyard` in `cameras.yaml` and changing one word in the HA automation restores the original when the camera returns.
- **Tablet kiosk fallback is a watchdog, not a factory reset.** If Fire OS 8 refuses the HOME takeover (`cmd package set-home-activity`), Phase 7 falls back to a foreground service plus `BOOT_COMPLETED` and the crash handler. Device-owner mode (factory reset, no Amazon account) is not in scope unless the user asks for it.
- **Phase 5's "mosaic encoder idle" gate moves to Phase 11.** v1's `haku-hls.service` is a permanent consumer of the mosaic until decommission. Phase 5 proves the lease logic with a transient test (stop the v1 mosaic unit for five minutes in a quiet hour, observe the encoder stop, restart it); the steady-state gate is checked after v1 is gone.

## 4. Goals, non-goals, anti-goals

**Goals.** Change-driven data flow end to end (HA WebSocket in, long-poll out). One owner per decision (house rules in HA; display tokens in the server; layout in clients; cameras in one file). A versioned, schema'd contract with generated fixtures shared by every test suite. Honest health that reaches the phone. One-command, drift-checked, rollback-able deploys. A fleet tool that knows each device's version and state. Lower resource use than v1 on every measured line (§ 2, targets in § 11).

**Non-goals.** No visual redesign. No new cameras or grid shapes. No HA custom integration or MQTT bridge. No WebSocket on the Roku. No second video decoder or PIP. No authentication or TLS beyond LAN plus nginx-proxy. No two-way controls from a wall. No per-device configuration stored on the device. No Kubernetes or image registry. No reliance on adb-over-network for the tablet.

**Anti-goals (failure even if it works).** A cutover that darkens a wall for more than a sideload. A v2 that still needs a human to notice an outage. A contract bump that strands a Roku that was not re-sideloaded. Two systems maintained for longer than the soak.

## 5. Constraints

- **Roku:** BrightScript/SceneGraph; `roUrlTransfer` async GET only (no WebSocket); `ParseJson` chokes on `null`; registry slots about 16 KB; most models have one hardware video decoder; Roku OS stops a stream 4 h 00 m 31 s after its last start with no input; sideload is the only install path; Dad's `.56` runs ECP in Limited mode (`/input`, `/launch`, `/query/active-app` only); the kids' Express 3930 is the weakest device and is powered by the TV's USB.
- **Tablet:** Fire 7 on Fire OS 8; Kotlin/Compose with OkHttp and kotlinx.serialization already pinned; adb-over-network resets on reboot.
- **Streams:** go2rtc 1.9.14 is current; its built-in HLS is ~1 s deep and underflows the Roku (go2rtc #1699, open), so an external `ffmpeg -c copy` HLS packager stays; the Genbolt lenses are HEVC and must be transcoded with QSV for the Rokus; the mosaic comes from a USB capture stick that re-enumerates; `libmfx1` was installed by hand on nserver.
- **HA:** 2026.9.4 in Docker on mserver; WebSocket API with `subscribe_entities`, `subscribe_events`, `supported_features {coalesce_messages: 1}`; `go2rtc:` integration accepts `url:`.
- **Hosts:** nserver is shared with the *arr stack and qBittorrent (2.3 GB RSS) and is under memory pressure; mserver has free RAM but no HEVC hardware decode and no capture stick.
- **Secrets** stay on the hosts: `/etc/haku/haku.env`, `/etc/haku/cam-creds.env`, and a new `/etc/haku/fleet.env`.

## 6. Architecture

```
            mserver (HA 2026.9)                                nserver (compose + bare-metal go2rtc)
 ┌─────────────────────────────────────┐          ┌──────────────────────────────────────────────────────┐
 │ HA core + automations (rule engine) │          │ haku-server (aiohttp, :1987; bridge net, mem 256m)   │
 │   fire haku_event on the HA bus ────┼── WS ──▶ │   feed/ha_ws: subscribe_entities + subscribe_events  │
 │ subscribe_entities snapshot + diffs │ ◀─────── │   viewmodel: per-layout view, rev, overlays(until)   │
 │ REST binary_sensor ◀── /v2/health   │          │   api: /v2/config /v2/view(long-poll) /v2/detail     │
 │ notify.phone when haku_ok is off    │          │        /v2/event /v2/health /metrics /v2/background  │
 └─────────────────────────────────────┘          │ haku-stream (host net, mem 192m; :1988 → :1985 later)│
                                                  │   gen: cameras.yaml → go2rtc.yaml + packager list    │
   long-poll GET /v2/view/<layout>?rev=…&wait=25  │   packager: N× ffmpeg -c copy → tmpfs /run/haku-hls  │
 ┌─────────────┐ ┌─────────────┐  ◀───────────────│   discovery v3: SSDP + /discovery.json + /hls/*      │
 │ Roku v2 ×6  │ │ Tablet v2   │                  │ haku-fleet (watcher: active-app → /launch/dev)       │
 │ one Video   │ │ Media3 RTSP │ ◀── rtsp :8554 ──│ go2rtc (systemd, QSV, USB capture; API basic-auth)   │
 └─────────────┘ └─────────────┘                  └──────────────────────────────────────────────────────┘
        ▲ ECP /query/active-app + /launch/dev from haku-fleet only. No HA→Roku pushes.
```

### 6.1 Components and ownership

| Component | Path | Decides | Never decides |
|---|---|---|---|
| haku-server | `server/` (Python 3.12, aiohttp) | every display token; overlay timing; stream online/lastMotion; which clients a takeover targets | whether a house event matters (HA); pixels and fonts (clients) |
| haku-stream | `stream/` (container) + `stream/systemd/go2rtc.service` | video plumbing: generated `go2rtc.yaml`, one HLS packager per enabled camera, SSDP + `discovery.json` + `/hls` | events, layout |
| Roku channel v2 | `clients/roku/` | layout, animation, the single Video node | severity, staleness, ages, door order, LED phase; receives no ECP pushes |
| Tablet v2 | `clients/tablet/` | layout, animation, door video playback | when the door camera shows (it plays `overlays[type=takeover]` until `until`) |
| HA package | `ha/packages/haku.yaml`, `ha/packages/haku_health.yaml` | house rules → `haku_event`; health notification | device addressing, IPs, camera URLs |
| Fleet tooling | `fleet/` (CLI `haku-fleet` + watcher service) | relaunch, gated sideload, inventory, check-in records | what the wall shows |
| Contract | `contract/v2/*.schema.json`, `contract/tools/`, `contract/v2/fixtures/` | the shapes; generated fixtures for all three test suites | — |
| Config | `config/` examples; live `/etc/haku/{dashboard.v2.json,cameras.yaml,fleet.yaml}` | entity bindings and tile placement | — |
| Deploy | `deploy/nserver/{docker-compose.yml,deploy.sh}`, `ha/deploy.sh` | | |

Repo layout after v2 lands: `server/`, `stream/`, `clients/roku/`, `clients/tablet/`, `ha/`, `fleet/`, `contract/`, `config/`, `deploy/`, `docs/`. The v1 directories (`sidecar/`, `roku/`, `fire-tablet/`, v1 files in `stream/`) remain until Phase 11.

Technology calls made for the builder: **aiohttp** (one library for the HTTP server, the long-poll hold via `asyncio.Condition` per layout, the WebSocket client to HA with `heartbeat=20`, and the few REST calls); **no matplotlib** (the one Roku chart is drawn with Pillow `ImageDraw` using the tick/scale helpers from v1's `history.py`, carried over with its tests); `backgrounds.py` carried over; **go2rtc bare-metal**, with `PartOf=` and the capture-device `ExecStartPre` gate removed, and its API kept on the LAN address but behind `api.username`/`api.password` (today 0.0.0.0 with `origin: "*"` and no auth; HA's generic camera for the mosaic needs it, see § 3.1). Containerising go2rtc is a follow-up spike, not a dependency.

### 6.2 Data flow

**HA → server** (`server/haku/feed/ha_ws.py`). One persistent `/api/websocket` session authenticated with the long-lived token of the dedicated administrator user `haku` (administrator rights are required for `subscribe_events` on a custom event type): `auth` → `supported_features {coalesce_messages: 1}` → `subscribe_entities` (full `a` snapshot, then `c`/`r` diffs applied to an in-memory snapshot) → `subscribe_events event_type=haku_event` → `weather/subscribe_forecast`. Reconnect with backoff 1/2/5/10/30 s; a reconnect's fresh snapshot replaces the store and bumps `rev` once. `snapshotAgeS` = now minus the last WS message; `ha.link ∈ ok | stale (>10 s) | down`. Logbook (`logbook/get_events`), history and statistics go over the same socket, fetched on a relevant entity change plus hourly, never per client request. Calendars: one REST GET per 5 min. The 1 Hz `/api/states` poll and the logbook polling disappear.

**View-model** (`server/haku/viewmodel/build.py`, pure). `build_view(layout_cfg, snapshot, overlays, streams_status, now) -> dict`. Rebuilt on snapshot, overlay, stream-status or config change, debounced 250 ms per layout. A tile whose JSON is unchanged keeps its previous `tile.rev`; everything else gets the new view `rev`. `rev` is an opaque string `"<bootId>.<n>"`; clients only echo it. `view.ts` is server epoch seconds; `view.configRev` is the sha of the loaded config.

**Transport: long-poll for both clients.** `GET /v2/view/<layout>?rev=<r>&wait=25&client=<id>&model=&version=&uptime=&min=<ms>&watching=<cam>`. The server answers at once with `200` and the full view when the client's `rev` is from another `bootId` or is older; otherwise it holds up to `wait` seconds and answers `200` on change or `204` on timeout. `min` is a per-client floor between answers (the Express 3930 sends 2000). On a LAN the round-trip after a change is milliseconds, so SSE or WebSocket would not make the tablet faster; one path means one server implementation, one fixture set, and no WebSocket upgrade through nginx-proxy. The same request is the **health check-in** (`client`, `model`, `version`, `uptime`) and the **stream lease** (`watching`).

**Timed fields.** `view.overlays[]` entries carry `since` and `until` on the server clock; `view.homeCam {cam, until}`. Clients compute remaining time as `until − view.ts`. There is no second push path.

**Scenarios.** A quick open-and-close: HA fires `takeover` on `to: on`; the close is irrelevant; no edge detection anywhere. HA restart: `ha.link = down` appears in the view within a second, tiles render at hold opacity with "No data since …", overlays keep their `until`, the reconnect snapshot restores values. Server restart: a new `bootId` forces a full view on every client's next poll; active overlays are persisted to `/var/lib/haku/overlays.json` (atomic write) and reloaded if `until > now`. A Roku asleep for an hour: its poll carries a stale `rev` and gets a full view; if `configRev` differs it refetches `/v2/config`; after 4 poll failures it re-runs discovery.

### 6.3 Contract v2

- Files: `contract/v2/{config,view,detail,discovery,health,event}.schema.json` (JSON Schema 2020-12); `contract/v2/input/` (a scrubbed HA snapshot and an event list); `contract/v2/fixtures/` generated by `contract/tools/make_fixtures.py` from the real `build_view` at a frozen `now`; `contract/tools/validate.py`.
- Every payload has `v: 2`. Clients refuse `v ≠ 2` (show the cached view plus an "update needed" badge on the diag screen). Within a major: additive only, unknown keys ignored, every optional key has a documented default. A major bump is path-versioned: `/v2/` and `/v3/` are served concurrently, discovery lists `api: [{v, base}]`, clients pick the highest they support, and the old path is removed only when `haku-fleet versions` shows no check-ins on it for 7 days. Discovery compatibility is "minimum version plus lenient parse", never equality.
- Null policy: one encoder boundary `dumps(prune(obj))`; schemas never allow `null`; `validate.py` asserts no `null` in any fixture.
- Size budget: `view` and `config` for `layout=roku` ≤ 12 KB (a contract test); only config and discovery are cached in the Roku registry.
- One golden per layout is the generated fixture, read byte-exact by server pytest, by the Roku tests with `HAKU_FIXTURE=1`, and by Gradle through `resources.srcDirs`. No hand-captured snapshots.
- **Config v2 shape:** `modules{}` are shared definitions keyed by id (kind, title, entities, tunables); `layouts.<name>.{grid, background, nightDim, tiles[]}` where each tile is `{module, col, row, w, h, style?, cam?, card?}`. This replaces the default view and the shallow-merge `ref:` / `tablet:` indirection that makes every v1 layout entry repeat `entities` in full. `dashboard.v2.json` is validated against `config.schema.json` at startup and on change.

### 6.4 Cameras: one source of truth

`config/cameras.yaml` (live copy `/etc/haku/cameras.yaml`): per camera `name`, `source` (RTSP URL with `${HAKU_*}` credential placeholders, or `capture` for the mosaic), `transcode` (`qsv_h264_720p | qsv_mosaic | none`), `order`, `quadrant`, `motion` (HA entity), `warm`, `picker`, `enabled`.

`stream/gen.py` renders `go2rtc.yaml` (credentials stay `${…}` for go2rtc's env substitution) and the packager list. `stream/packager.py` supervises one `ffmpeg -c copy` per enabled camera with the flags of today's `haku-hls@.service`, per-camera restart backoff, and a `segmentAgeS` report; it also restarts a packager whose playlist has not advanced for 30 s or whose current segment exceeds 16 MB, because on 2026-10-24 a timestamp discontinuity from the `front_steps` transcode left v1's ffmpeg unable to cut a segment, and one 639 MB `.ts` filled `/run` (tmpfs) and took the door camera and `systemctl daemon-reload` down with it. `stream/discovery.py` builds the discovery metadata from the same file. The server reads it for `config.streams` (name, order, hls, rtsp, picker) and `view.streams[cam].{online, lastMotion}`.

`enabled: false` means no go2rtc stream, no packager, greyed "offline" in pickers and an "Offline" grid quadrant: no crash loops. `warm: false` cameras run their packager only while some client sends `watching=<cam>` (lease 60 s after the last poll), which is what stops the mosaic encoder burning 0.6 core for nobody; takeover cameras are `warm: true`. The Roku's `HK_CAMS`/`GridGroup.xml` roster and the contract test's `EXPECTED_STREAMS` disappear; HA names cameras only inside `haku_event`.

### 6.5 Events

`haku_event` data (`contract/v2/event.schema.json`): `type: takeover | overlay | toast | home_cam` (required); `cam`; `severity: low | normal | high` (default `normal`; a `low` takeover is a toast only); `duration_s` (defaults: takeover 60, overlay 8, toast 4, home_cam 900); `banner`; `targets: all | layout:<name> | room:<id>` (default `all`); `key` (dedupe key, default `<type>:<cam>:<targets>`); `replay_s`.

`server/haku/feed/events.py` validates (bad events are logged and counted, never fatal), resolves `room:` through `fleet.yaml`, and stores `Overlay{id, key, …, until}`. A repeat with the same `key` while active extends `until` and keeps `id` so clients do not re-animate; `home_cam default` removes the match; an expiry timer removes the overlay and bumps `rev` (clients also self-expire on `until`). `POST /v2/event` accepts the same body for curl, smoke tests and the fleet tool.

`ha/packages/haku.yaml` v2: front steps view → `home_cam front_steps` / `home_cam default`; **front door opened → `takeover front_steps normal 60 all`** (this one event is the Roku takeover and the tablet door camera: v1's `doors.py` edge detection, `camera.sec`, the Roku 60 s constant and the ECP broadcast collapse into it); after-hours back door and backyard motion → `takeover yard high replay_s=15` with `targets: all` (the user's decision 10: every wall and the kitchen tablet; `yard` stands in for the offline `backyard` camera per § 3.1; the follow-me sensor has not updated since 2026-10-17, so `room:` targeting waits for ESPresense to be repaired); motion timestamps are not pushed because the server has the motion entities and sets `view.streams[cam].lastMotion`. Deleted: all `rest_command`s, `script.housewall_broadcast`, the active-service template sensor, the six relaunch automations.

### 6.6 Fleet management

`config/fleet.yaml`: `rokus: [{id, host, serial, model, ecp: full | limited, devPasswordEnv}]` and `tablets: [{id, host}]`; hosts are MikroTik static-lease names; passwords live in `/etc/haku/fleet.env`.

`haku-fleet watch` (a compose service, 64 MB): every 60 s `GET /query/active-app` on each Roku; the Roku home screen (app `562859`) → `POST /launch/dev`. Works in Dad's Limited mode. Logs transitions only. `haku-fleet deploy --roku <id> | --all` refuses unless the active app is HAku (`--force` overrides), uses roku-deploy, and waits for the new version to check in. Also `status`, `versions`, `screenshot`, `console` (single-reader lock on `:8085`). Check-in data from the view poll is exposed in `/v2/health.clients`; `GET /v2/hello` at boot returns `{v, serverTime, minClient, configRev}`. The tablet is not managed over adb: the app checks in through the same poll and posts its last 200 log lines to `POST /v2/clientlog` on a crash restart.

### 6.7 Operations

**Compose** (`deploy/nserver/docker-compose.yml`): `haku-server` (bridge network, `1987:8080`, `VIRTUAL_HOST`/`VIRTUAL_PORT` for nginx-proxy, 256 MB, `/etc/haku:ro`, `haku-state:/var/lib/haku`, healthcheck `/v2/health`); `haku-stream` (host network for SSDP, HLS and go2rtc on 127.0.0.1, 192 MB, `tmpfs /run/haku-hls size=256m`, healthcheck `/discovery.json`); `haku-fleet` (the server image with `command: haku-fleet watch`, 64 MB). All `restart: unless-stopped`, json-file logs 10 MB × 3, `env_file: /etc/haku/haku.env`. Devices talk to `IP:1987` and `IP:1985` as given by discovery; the nginx vhost is for humans and HA.

**Deploy** (`deploy/nserver/deploy.sh <ref>`): on nserver `git fetch` from the private GitHub remote over a read-only deploy key (when GitHub is unreachable, `--offline` redeploys a ref that is already fetched) and `git checkout <ref>`; refuse on a dirty tree; `sha256sum -c` of `/etc/haku/{dashboard.v2.json,cameras.yaml,fleet.yaml}` against the committed manifest (drift → refuse; `--accept-drift` copies the live files into `config/live/` for a commit); `contract/tools/validate.py` on the live config; `GIT_SHA=$(git rev-parse --short HEAD) docker compose build && docker compose up -d --wait`; gate on `/v2/health.ok && ha_link.ok` within 60 s, else roll back to `deploy/.last_good`. HA packages deploy through `ha/deploy.sh` (md5 compare, backup, copy, `check_config`, targeted reloads).

**Config** is schema-validated at startup (fail fast) and on mtime change (a bad edit keeps the last good config and sets `health.config.ok = false`); a good reload bumps `configRev`, which clients see in their next view.

**Observability:** stdlib JSON logging (`event, layout, client, rev, dur_ms`); `/metrics` in Prometheus text (HA messages/s, rebuilds, long-poll waiters, event counts, per-camera segment age, client last-seen); `/v2/health.checks.{ha_link, config, cameras.<id>, clients.<id>}`. `ha/packages/haku_health.yaml` follows the existing `water_meter_health.yaml` pattern: a REST `binary_sensor.haku_ok` polling `/v2/health` every 60 s with attributes, and one automation that notifies the phone when it is off or unavailable for 5 min and again on recovery. That covers server down, HA link down, a stale camera, and a Roku that should be on HAku but has not polled for 5 min.

**Hygiene:** `haku.env` (the new `haku` administrator user's token), `cam-creds.env` (now also the go2rtc API credentials) and `fleet.env` stay on the host; dev passwords and tokens leave the docs; the private GitHub remote is added with a deploy key on nserver; all HA packages come under `ha/packages/`; the 22 `dashboard.json.bak-*` files and the 12 `/opt/haku/sidecar*backup*` directories on nserver go (one live copy committed under `config/live/`).

**Estate notes outside HAku, for the user:** nserver's swap pressure is mostly qBittorrent (2.3 GB RSS); a memory limit on that container would do more for HAku than any HAku change. Optional follow-up: point HA's `go2rtc: url:` at nserver's go2rtc so HA's own `camera.front_cam_*` entities reuse the QSV transcodes instead of HA's `ffmpeg` camera platform decoding the Genbolt a third time.

### 6.8 Roku channel v2 (`clients/roku/`)

brighterscript tooling and the `brs` unit runner are kept. Components: `MainScene` (routes home · picker · live · grid · diag); `FeedTask` (the long-poll loop: one `roUrlTransfer`, `wait=25`, client timeout 35 s, backoff 2–30 s on failure, re-issued immediately on a `watching` change, handles `204`); `DiscoveryTask` (SSDP ST `urn:haku:service:dashboard:2`, lenient `v ≥ 3`); `ConfigTask` (on boot and when `view.configRev` changes, 8 s timeout); `BackgroundGallery` and `BackgroundListTask` (kept); `Wall` (header plus tiles from `config.tiles` and `view.tiles`); tile bodies (Value, Doors, Laundry, Agenda, Forecast, CameraSlot); **`Player`**; `LiveGroup` and `GridGroup` as chrome only (HUD, chevrons, focus ring, no Video of their own); `CameraPicker`; `OverlayLayer` fed from `view.overlays`; `Toast`; `DiagScreen` rendering `view.status` and `/v2/health`.

**Single decoder owner.** `Player` holds the only Video node; `mode ∈ off | keepawake | home | live | grid | takeover` plus `cam`. The node is moved and resized between the home tile rect and full screen rather than instantiated per screen, so two decoders cannot exist. Every transition is `stop → set url → play`; the 3 h refresh timer, the "Camera offline" rest and the backoff live here once. A takeover is driven by `view.overlays`: a new overlay id remembers `(route, cam, manualLive)` and goes live; when `until` passes (local timer from `until − ts`) or the overlay disappears, it returns. Keys cancel a takeover as today.

Registry keys `v2.config`, `v2.discovery`, `v2.base`, `v2.audio_<cam>` are written only when the serialized string differs; v1 keys are deleted on first boot. Every fetch has a timeout through one `hkGet(url, timeoutMs)`. Discovery re-runs at boot, after 4 consecutive poll failures, after an HLS failure past 4 retries, and every 24 h. `hkView(json)` fills defaults for every missing optional key and rejects only `v ≠ 2` or a missing `tiles`. Express 3930: it sends `min=2000`, the payload is ≤ 12 KB, it repaints only tiles whose `tile.rev` changed (string compare), and it uses the 1280×720 background size from config.

Deleted from v1: `ModuleScreen` and its row components; `JpegPipTask` and PIP; `InputPumpTask`, `dispatchEcp` and the `supports_input_launch` handling; the HA token/URL registry writes and launch args; `HK_CAMS`/`HK_CAM_DISPLAY_NAME`; `DiagHealthTask`; the default-view fallback; `hkStatePollMsFor`; `HK_RETURN_HOME_MS`/`HK_HOME_CAM_MAX_MS` (the server's `until` replaces them); the ~15 ported formatting helpers; the watchdog log spam.

Verified in `brs` unit tests: `hkTileRect`, `hkView` defaults, remaining-time maths, backoff, picker ordering from `config.streams`, registry change detection, the `v` check. Verified on a device (smoke v2): `POST /v2/event` takeover → `route to=live`, `stream_start`, return home at `until`; picker → grid → home with exactly one `player_start` between stops; a server restart mid-poll → `feed_resync`; a config edit on nserver → `config_reload` without relaunch; a 4 h soak with no `EXIT_USER_NAV`; Express payload and repaint timing.

### 6.9 Tablet v2 (`clients/tablet/`)

Same pinned Compose stack; theme, fonts, glyph data, cards and detail panels carried over. Data layer: `FeedClient` long-poll (OkHttp `callTimeout` 35 s, backoff 2–30 s, resumes with `rev`); `ConfigClient` on `configRev` change; kotlinx.serialization with `ignoreUnknownKeys`, `coerceInputValues` and explicit defaults (no all-or-nothing config parse); a disk cache of the last `config.json` and `view.json` for an instant first frame and an honest "No data since …" from `view.ts`. Discovery: one compiled seed `http://192.0.2.20:1988/discovery.json` (debug-overridable) from which it reads the `api[]` base and `streams`; `network_security_config` allows cleartext to the LAN host. Door camera: Media3 ExoPlayer with `media3-exoplayer-rtsp` playing `rtsp://<nserver>:8554/front_steps` (about +4 MB APK, +10–15 MB PSS, gated at 95 MB PSS; HLS `VideoView` behind a flag as fallback). Kiosk: HOME + DEFAULT intent filter (Android relaunches the HOME app after a crash and at boot), a `BOOT_COMPLETED` receiver, an uncaught-exception handler that posts the log tail to `/v2/clientlog` then exits (HOME brings it back), immersive sticky, `FLAG_KEEP_SCREEN_ON`; the device-side `locksettings set-disabled true` stays. If Fire OS 8 refuses the HOME takeover, the fallback is a foreground service that restarts the activity, not device-owner mode (§ 3.1). The tablet's `iot` membership only blocks its internet access; every nserver port it needs is plain LAN. The demo source replays `contract/v2/fixtures`.

## 7. What is left to the builder

- Exact aiohttp module layout under `server/haku/`, logging formatter, and the metrics text implementation (hand-rolled counters are fine).
- The debounce, lease and backoff constants beyond those named here, provided they are config-tunable with the defaults above.
- Pillow chart styling, matching the current `weather_chart.png` closely enough that the wall does not visibly change.
- How `make_fixtures.py` scrubs the captured HA snapshot (entity ids kept, personal names and calendar titles replaced).
- Whether `haku-fleet` is a Python entry point in the server image (preferred) or a separate image.
- Whether the Roku `Player` keeps a 2 px keep-awake clip or an off-screen position for the resting state, as long as one decoder rule holds.
- Media3 buffering parameters for the Fire 7, within the 95 MB PSS gate.
- Test layout per directory, provided each exit criterion in § 10 has an automated check where one is possible.

## 8. Risks

- **Long-poll on the Express 3930.** Mitigation: `min=2000`, payload ≤ 12 KB, one-evening trial gated on active-app before the fleet cutover.
- **HA WebSocket reconnect edge cases** (HA restarts mid-snapshot, token expiry). Mitigation: fake-HA WebSocket tests in Phase 1, `ha.link` honesty in the view, the health notification.
- **go2rtc API credentials** break any unauthenticated reader. Known readers: HA's generic camera `192_168_1_45` (gets the credentials) and the v1 Roku PIP (deleted in v2; until cutover the v1 Rokus lose PIP snapshots, which no live automation sends). Mitigation: a 15 s `tcpdump` for new connections to `:1984` showed none from the LAN at idle; re-check before the change.
- **Two SSDP responders during the parallel run.** Mitigation: v2 uses a different ST (`…:2`) and port (`:1988`) until decommission.
- **Media3 memory on the Fire 7.** Mitigation: PSS gate and the HLS fallback flag.
- **Time zone change** shifts HA's day labels and `after 22:00` windows by an hour in winter (the intended fix, but visible). Mitigation: change before 2026-11-01 and watch the first utility_meter reset.

## 9. Phase 0: safe now, independent of the rebuild

Disable `haku-hls@backyard` and comment the stream out of `go2rtc.yaml`, `STREAM_METADATA` and `dashboard.json` until the camera returns. Set HA's time zone to Edmonton. Guard the Roku `hkSetHubBase` registry write so it only writes on change. Fix the `Documentation=` line and set `MPLCONFIGDIR` in `haku-sidecar.service`; give the mosaic `haku-hls.service` the template's cleanup. Add a git remote; bring the untracked HA packages (`electricity_cost`, `water_cost`, `laundry`, `cameras_front`, `recorder_retention`, `water_meter_health`) and the live `dashboard.json` into the repo; move Roku dev passwords out of `docs/HAKU_DESIGN.md`, `roku/CLAUDE.md` and the four `docs/superpowers/plans/*.md` files that quote them (`roku/dist/haku.zip` is already ignored and untracked, nothing to do there). Create the HA administrator user `haku`, mint its long-lived token into `/etc/haku/haku.env`, revoke the owner-account token the sidecar uses today, and delete the unused `haToken`/`haUrl` registry write on the Roku. Reserve static DHCP leases for the six Rokus and the tablet. Cap qBittorrent's memory on nserver. Commit `tools/baseline.sh` and its output as the number to beat.

**Phase 0 leftovers (2026-10-24):** living `.51` (Plex was playing), kids `.52` and dad `.56` (TVs off) are still on Roku 1.3.1: re-run `roku/scripts/fleet-deploy.sh` when they show HAku. Router leases and DNS names: paste the commands in `docs/fleet-leases.md` (since moved to the gitignored `PRIVATE.md`) (router is WinBox-only) and add the kids/dad MACs. The `haku-server` token was pasted into the working chat: re-mint it per `ha/README.md` § Rotate and delete the pasted one; the owner account also still holds an unused `claude2` token from 2026-04. The mosaic `haku-hls.service` was not restarted (someone was fetching it), so its new pre-start cleanup applies at the next restart. Found during the final review: v1's `haku-hls@front_steps` had been stuck since ~03:05 UTC on a non-monotonic DTS, growing one segment to 639 MB until `/run` was full (playlist stale 20 min, `daemon-reload` refused); restarting the unit fixed it. v1 has no guard against this; v2's packager supervisor gets one (§ 6.4). Until then, `df /run` and `ls -laS /run/haku-hls | head` are the checks when a camera goes stale.

## 10. Roadmap

v1 stays live throughout. Phases 1–5 and 8 (shadow) are invisible to the walls; 6 touches only the office Roku; 7 only the tablet when installed. Each phase gets its own implementation plan.

| # | Phase | Size | Exit criteria | Rollback |
|---|---|---|---|---|
| 0 | Hygiene, baseline, this document | S | backyard 0 restarts/24 h; tz aligned; remote pushed; secrets out of docs; `docs/baseline/2026-10-24.md` committed. **Done 2026-10-24** (leftovers in § 9) | tz revert |
| 1 | Server skeleton + HA WS feed on :1987 | M | `/v2/health` shows `ha_link.ok`, `snapshotAgeS < 2` for 24 h; HA shows one extra WS session, zero extra REST; RSS < 100 MB | `compose down` |
| 2 | Contract v2 + fixtures | M | `validate.py` green; no `null`; `view_roku.json` < 12 KB | none |
| 3 | View-model, layouts, `/v2/config`, `/v2/view`, `/v2/detail`, backgrounds, Pillow chart, parity tool vs v1 | L | goldens byte-exact; parity shows only intended differences for 3 days; long-poll releases within 500 ms of a door toggle | none |
| 4 | Events + HA package v2 firing alongside v1 pushes | M | door open → overlay in both layouts within 1 s, extends on repeat, expires; `check_config` clean; v1 pushes still arrive | HA package reload |
| 5 | `cameras.yaml`, packager, discovery v3 on :1988, `haku-stream` container, go2rtc decoupled + API credentials, `deploy.sh` | M/L | v2 HLS plays in VLC for every enabled camera; v1 `/hls` unaffected; generated `go2rtc.yaml` equals the live one modulo comments; lease logic proven by a five-minute transient test (steady-state "idle when unwatched" is checked in Phase 11); HA's mosaic camera still works with credentials; rollback exercised once on purpose | `compose down haku-stream` |
| 6 | Roku v2 on the office .55 | L | `npm test` green; smoke green; 72 h soak with 0 relaunches, 0 `EXIT_USER_NAV`, stable `/query/chanperf`; one-evening Express 3930 trial | re-sideload v1 zip |
| 7 | Tablet v2 | L | unit tests green; release PSS ≤ 95 MB; door event → video < 1.5 s; killed process back < 5 s; reboot → app up | `adb install -r` v1 apk |
| 8 | Fleet tool: shadow, then live; `haku_health.yaml` | M | shadow log matches the HA relaunch automations for 3 days, then relaunch enabled and the six automations disabled; a deliberate HA stop produces one phone notification within 6 min and one recovery | re-enable HA automations |
| 9 | Two-week soak with both stacks | S | § 11 targets met; alerts only true positives | — |
| 10 | Cutover: tablet, then the four fleet Rokus in one evening gated on active-app, Dad's last; HA automations to events-only | M | every client checks in on v2 within 10 min; a hall door test shows on all walls and the tablet; `haku-fleet status` green | per device v1 zip/apk; HA re-adds the v1 action lines |
| 11 | Decommission v1: units, `housewall.yaml`, `haku-stream` to :1985, tag `v1-final`, delete v1 dirs, docs rewritten, final baseline | S | no :1986 listener; `check_config` clean; `HAKU_DESIGN.md` describes only v2; mosaic encoder at 0% CPU with no `watching` lease | `git checkout v1-final -- <dir>` + re-enable units |

## 11. Numbers to beat (re-measured after Phase 10 with `tools/baseline.sh`)

| Metric | v1 | v2 target |
|---|---|---|
| HA → server bytes | 297 KB/s (25 GB/day) | < 5 KB/s idle |
| HA requests from server | 1.6 req/s | 0 polling; 1 WS session; on-demand history/logbook on change or hourly |
| Client → server requests | ~5 req/s for 5 clients | ≤ 0.2 req/s per client |
| Roku registry writes | 1/s per device | only on change |
| Door → tablet camera visible | ~1.5 s | < 1 s |
| Door → Roku takeover visible | ECP push (sub-second when it works) | ≤ 2 s via long-poll wake |
| Mosaic encode CPU | 63% of a core, 24/7 | 0 when unwatched |
| Crash-looping units | 1 | 0 |
| Server RSS / swap | 114 MB + 304 MB swapped | < 150 MB RSS, 0 swapped |
| Health honesty | always ok | `ok` false on HA link loss; snapshot age; per-client last-seen |
| Alerting | none | phone notification within 5 min of server, HA-link, camera or Roku check-in failure |
| Deploy | manual per-file scp | one command, drift-checked, rollback-able |
| Fleet visibility | none | `haku-fleet status` lists version and active app per device |
