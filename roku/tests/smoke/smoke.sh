#!/usr/bin/env bash
#
# HAku sideload smoke harness.
#
#   ROKU_IP=192.0.2.52 ROKU_DEV_PASSWORD=$ROKU_PW_FLEET tests/smoke/smoke.sh
#
# Steps:
#   1. lint + unit + contract  (offline gates — fast)
#   2. roku-deploy publish     (sideloads dist/haku.zip)
#   3. cold-relaunch, then drive the HAku flow and tail telnet :8085 for up to
#      ${SMOKE_TIMEOUT:-30}s, asserting the [HAku] event stream:
#        - event=launch                         channel booted
#        - event=route to=home                  boots to the card grid (default route)
#        - event=route ... to=live              ECP takeover routed to a camera
#                                               (via focusModule=, not the cam=+severity= branch)
#        - event=stream_start cam=...           live HLS actually started
#        - >=2 event=cam_switch cam=...         carousel responds to Right
#        - >=3 distinct event=overlay_show kind=...   overlay layer alive
#        - event=home_cam_override cam=front_steps    HA's homeCam= push reached home
#        - event=picker_open + event=picker_select    OK on home lists the cameras,
#                                                    OK on a row plays it, Back returns
#        - no BrightScript runtime error             HA's real payloads (replay=,
#                                                    lastMotion=) don't crash the channel
#
# Requires the HAku server stack (haku-discovery schema 2 + go2rtc/HLS) reachable
# so streams start; the sidecar is optional for this smoke because the camera
# takeover is driven directly via ECP focusModule=/cam= (no /api/config needed).
#
# Exit codes: 0 ok, 1 timeout/missing core event, 2 missing config, 3 gate/deploy
#             failed, 4 discovery_failed without recovery, 5 carousel dead,
#             6 overlay layer dead, 7 takeover routing dead (no route=live),
#             8 channel crashed (runtime error), 9 homeCam= override dead,
#             10 camera picker dead, 11 registry written more than once per launch,
#             12 an haToken value reached the console.

set -uo pipefail

cd "$(dirname "$0")/../.."
CHANNEL_ROOT="$PWD"

: "${ROKU_IP:?ROKU_IP env var required (Roku LAN IP)}"
: "${ROKU_DEV_PASSWORD:?ROKU_DEV_PASSWORD env var required}"
TIMEOUT="${SMOKE_TIMEOUT:-30}"

echo "== smoke gate 1/3: lint =="
npm run -s lint || { echo "!! lint failed"; exit 3; }

echo "== smoke gate 2/3: unit =="
npm run -s test:unit || { echo "!! unit tests failed"; exit 3; }

echo "== smoke gate 3/3: discovery contract =="
HAKU_FIXTURE=1 python3 tests/contract/discovery_contract.py >/dev/null \
    || { echo "!! contract test failed against fixture"; exit 3; }

echo "== sideload to ${ROKU_IP} =="
npm run -s deploy || { echo "!! deploy failed"; exit 3; }

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT
echo "== tailing telnet :8085 + driving the HAku flow =="

# Cold-relaunch (Home then dev) so init() runs fresh and boots to HOME.
curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Home" >/dev/null 2>&1 || true
sleep 2

# Single subshell: telnet as a background job inside so the parent doesn't
# inherit it (avoids SIGHUP cascades).
(
    # `exec cat`, so TELNET_PID is cat itself: killing a plain subshell left cat
    # orphaned, holding the Roku's single console connection.
    ( exec 3<>"/dev/tcp/${ROKU_IP}/8085"; exec cat <&3 ) &
    TELNET_PID=$!
    sleep 1
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/launch/dev" >/dev/null 2>&1 || true
    sleep 6
    # ECP takeover to a camera (drives route=live + cam_switch + stream_start
    # without needing the sidecar/home tiles — moduleById falls back to cam=).
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?focusModule=cameras&cam=front&severity=high&banner=Smoke" >/dev/null 2>&1 || true
    sleep 4
    # Carousel: Right must move to the next cam (regression-catches the
    # focus-on-Group bug class).
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Right" >/dev/null 2>&1 || true
    sleep 1
    # HA's real payload shapes (packages/housewall.yaml): the door-open takeover with
    # replay=, and the motion heartbeat. Until 1.1 both crashed the channel (.toInt()
    # on an integer), unseen because no HA push had ever reached a Roku.
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?cam=front&severity=normal&replay=15&reason=opened&banner=Smoke+door" >/dev/null 2>&1 || true
    sleep 1
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?lastMotion=front&lastMotionAt=$(date +%s)" >/dev/null 2>&1 || true
    sleep 1
    # Overlay layer — 4 kinds that don't need backing infrastructure. PIP skipped
    # (needs the snapshot endpoint; see HAKU_DESIGN.md).
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?overlay=weather&temp=8&hi=14&cond=cloudy" >/dev/null 2>&1 || true
    sleep 0.4
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?overlay=door&label=Smoke&action=opened&severity=normal" >/dev/null 2>&1 || true
    sleep 0.4
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?overlay=sensor&icon=bolt&value=1.0+kW" >/dev/null 2>&1 || true
    sleep 0.4
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?overlay=text&banner=smoke&severity=low" >/dev/null 2>&1 || true
    sleep 0.4
    # Route back to the dashboard.
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?mode=home" >/dev/null 2>&1 || true
    sleep 2
    # Front steps view: HA's homeCam= push, then its revert.
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?homeCam=front_steps" >/dev/null 2>&1 || true
    sleep 3
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/input?homeCam=default" >/dev/null 2>&1 || true
    sleep 1
    # Camera picker: OK on home opens it, Down + OK plays Front Steps, Back goes home.
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Select" >/dev/null 2>&1 || true
    sleep 1
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Down" >/dev/null 2>&1 || true
    sleep 0.5
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Select" >/dev/null 2>&1 || true
    sleep 3
    curl -sf -X POST -d '' "http://${ROKU_IP}:8060/keypress/Back" >/dev/null 2>&1 || true
    REMAINING=$((TIMEOUT > 31 ? TIMEOUT - 28 : 3))
    sleep "$REMAINING"
    kill $TELNET_PID 2>/dev/null
    wait $TELNET_PID 2>/dev/null
) > "$LOG" 2>&1 || true

echo "--- captured [HAku] events ---"
grep "^\[HAku\]" "$LOG" || echo "  (none)"
echo "------------------------------"

SWITCHES=$(grep -c "event=cam_switch cam=" "$LOG" || true)

if grep -q "event=discovery_failed" "$LOG" && ! grep -q "event=discovery_ok" "$LOG"; then
    echo "!! smoke fail: discovery_failed without recovery"
    exit 4
fi

if ! grep -q "event=launch" "$LOG"; then
    echo "!! smoke fail: never saw event=launch in ${TIMEOUT}s"
    exit 1
fi

REG_WRITES=$(grep -c "event=reg_write key=hubBaseV2" "$LOG" || true)
if [ "$REG_WRITES" -gt 1 ]; then
    echo "!! smoke fail: hubBaseV2 written $REG_WRITES times in one launch (expected <=1; regWriteIfChanged guard broken)"
    exit 11
fi

if grep -qiE "hatoken=[^*[:space:]]" "$LOG"; then
    echo "!! smoke fail: an haToken value reached the console (should be ***** or absent)"
    exit 12
fi

if ! grep "event=route" "$LOG" | grep -q "to=home"; then
    echo "!! smoke fail: never booted to the home route"
    exit 1
fi

if ! grep "event=route" "$LOG" | grep -q "to=live"; then
    echo "!! smoke fail: ECP takeover did not route to a live camera"
    echo "   (no 'event=route ... to=live' — dispatchEcp focusModule/cam path broken)"
    exit 7
fi

if ! grep -q "event=stream_start cam=" "$LOG"; then
    echo "!! smoke fail: never saw event=stream_start (HLS backend reachable?)"
    exit 1
fi

if [ "$SWITCHES" -lt 2 ]; then
    echo "!! smoke fail: Right keypress did not trigger a cam_switch"
    echo "   (saw $SWITCHES cam_switch event(s); expected >=2 — takeover + Right)"
    echo "   likely cause: MainScene didn't setFocus(true) on LiveGroup"
    exit 5
fi

OVERLAY_KINDS=$(grep "event=overlay_show" "$LOG" | grep -oE 'kind=[a-z]+' | sort -u | wc -l)
if [ "$OVERLAY_KINDS" -lt 3 ]; then
    echo "!! smoke fail: overlay layer didn't acknowledge enough kinds"
    echo "   (saw $OVERLAY_KINDS distinct overlay_show kinds; expected >=3 of door/weather/sensor/text)"
    exit 6
fi

if grep -qE "runtime error|BrightScript Micro Debugger" "$LOG"; then
    echo "!! smoke fail: the channel crashed into the debugger"
    grep -A12 "runtime error" "$LOG" | head -20
    exit 8
fi

if ! grep -q "event=home_cam_override cam=front_steps" "$LOG"; then
    echo "!! smoke fail: homeCam=front_steps never reached the home camera card"
    exit 9
fi

if ! grep -q "event=picker_open" "$LOG" || ! grep -q "event=picker_select cam=" "$LOG"; then
    echo "!! smoke fail: OK on home didn't open the camera picker, or OK on a row didn't pick"
    exit 10
fi

echo "✓ smoke pass: launch + home + takeover→live + stream_start + carousel (${SWITCHES}) + overlays (${OVERLAY_KINDS} kinds) + HA payloads + homeCam + picker"
exit 0
