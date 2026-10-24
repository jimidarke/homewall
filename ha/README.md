# ha/ — Home Assistant packages HAku depends on

Byte-for-byte copies of the packages HAku relies on in Home Assistant on mserver (`192.0.2.10`). The live files are `/root/docker/homeassistantV3/config/ha/packages/<name>.yaml`; HA's `configuration.yaml` includes each one by an explicit `!include` line under `homeassistant: packages:`, so a new package needs a line added there too.

| Repo file | Live file | Owns |
|---|---|---|
| `packages/housewall.yaml` | `packages/housewall.yaml` | HA → Roku push (ECP `rest_command` per Roku, `script.housewall_broadcast`, active-Roku selector, front-steps view, door takeover, after-hours alerts, motion heartbeat, six relaunch automations). Retired in v2 (`haku_event` instead). |
| `packages/haku_water.yaml` | `packages/haku_water.yaml` | Water helpers for the dashboard: hourly/daily/monthly utility meters, `always_available` mirrors, cost today. |
| `packages/water_cost.yaml` | `packages/water_cost.yaml` | Water tariff and cost sensors. |
| `packages/electricity_cost.yaml` | `packages/electricity_cost.yaml` | Electricity tariff and daily/monthly cost sensors (`sensor.electricity_daily_cost` is the one the dashboard reads). |
| `packages/gas_cost.yaml` | `packages/gas_cost.yaml` | Gas tariff constants (updated by hand monthly) and cost sensors. |
| `packages/laundry.yaml` | `packages/laundry.yaml` | The washer/dryer state machine (`sensor.laundry_*_mode`, started/finished datetimes). The sidecar mirrors it and never re-derives it. |
| `packages/cameras_front.yaml` | `packages/cameras_front.yaml` | Genbolt front camera entities (`camera.front_cam_fixed` / `_ptz`, via `!secret` RTSP URLs) and ONVIF PTZ nudge scripts. |
| `packages/recorder_retention.yaml` | `packages/recorder_retention.yaml` | Nightly trim of metering domains to 14 days (global `purge_keep_days` is 90). |
| `packages/water_meter_health.yaml` | `packages/water_meter_health.yaml` | Stalled/offline water-meter alerts to the phone; the pattern v2's `haku_health.yaml` follows. |

Not copied: `arr_pipeline.yaml`, `kids_tv.yaml`, `kids_fan.yaml`, `bathroom.yaml`, `den_tv_ir.yaml`, `espresense.yaml` (not HAku's; `arr_pipeline` embeds API keys).

## Deploy a change

1. Edit the repo copy. Confirm the live file still matches the committed version: `ssh mserver md5sum /root/docker/homeassistantV3/config/ha/packages/<name>.yaml` vs `git show HEAD:ha/packages/<name>.yaml | md5sum`. If they differ, the live side drifted: pull it in first.
2. Back up beside the live file: `ssh mserver 'cp -p …/packages/<name>.yaml …/packages/<name>.yaml.bak-<date>-<topic>'`.
3. Copy: `ssh mserver 'cat > /root/docker/homeassistantV3/config/ha/packages/<name>.yaml' < ha/packages/<name>.yaml`.
4. Validate, then reload only what changed (token stays on mserver):

```bash
ssh mserver 'T=$(grep LONG_LIVE_TOKEN /home/displayuser/ha-calendar/.env | cut -d= -f2-); H="Authorization: Bearer $T"
curl -s -X POST -H "$H" http://127.0.0.1:8123/api/config/core/check_config          # expect "result": "valid"
curl -s -X POST -H "$H" http://127.0.0.1:8123/api/services/automation/reload        # and/or script, rest_command, template
'
```

`check_config` reports `KeyError: 'triggers'` for UI automations written with the plural schema; that is a false positive of the offline script. Template sensors, `utility_meter` and `camera:` platform changes need an HA restart (`docker restart homeassistant`), which also restarts every HAku Roku's push target for a minute.

v2 adds `ha/deploy.sh` (Phase 4) and the packages `haku.yaml` (events) and `haku_health.yaml` (alerting); see `docs/superpowers/specs/2026-10-24-haku-v2-design.md` § 6.5 and § 6.7.
