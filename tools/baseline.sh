#!/usr/bin/env bash
# tools/baseline.sh [seconds] — measure the live HAku system and print a Markdown report.
#
# Read-only. Runs from the MiniPC over the `nserver` and `mserver` ssh aliases (root).
# The HA token is read inside the mserver shell and never leaves it. tcpdump runs on
# nserver for the capture window (default 20 s) and is killed on exit, even on Ctrl-C.
#
# Usage: tools/baseline.sh 20 | tee docs/baseline/$(date +%F).md
# Compare against docs/superpowers/specs/2026-10-24-haku-v2-design.md § 2 and § 11.
set -uo pipefail

SECS="${1:-20}"
ROKUS="192.0.2.51 192.0.2.52 192.0.2.53 192.0.2.54 192.0.2.56 192.0.2.55"
HA_HOST=192.0.2.10
# shellcheck disable=SC1091
source "$(dirname "$0")/lib/redact.sh"
OUT=$(mktemp)
cleanup() { ssh -o ConnectTimeout=8 nserver 'pkill -x tcpdump' >/dev/null 2>&1 || true; rm -f "$OUT"; }
# Ctrl-C: kill the remote captures and stop; do not print the remaining sections.
trap 'cleanup; trap - EXIT; exit 130' INT TERM
trap cleanup EXIT

h() { printf '\n## %s\n\n' "$1"; }
code() { printf '```\n'; cat; printf '```\n'; }

report() {
printf '# HAku baseline — %s\n\nCapture window: %s s. Script: `tools/baseline.sh`.\n' "$(date -u +'%Y-%m-%d %H:%M UTC')" "$SECS"

h "Hosts"
printf '### nserver\n'
ssh nserver 'uptime; free -m' | code
printf '### mserver\n'
ssh mserver 'uptime; free -m; docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" homeassistant' | code

h "Processes (nserver)"
ssh nserver 'SP=$(systemctl show -p MainPID --value haku-sidecar); GP=$(systemctl show -p MainPID --value go2rtc); top -b -n 2 -d 3 -p "$SP,$GP" | grep -E "^ *[0-9]+ " | tail -2 | awk "{printf \"%-8s cpu=%s%% rss=%sKB\n\", \$12, \$9, \$6}"; ps -eo pid,%cpu,rss,etime,args --sort=-%cpu | grep -E "ffmpeg|haku-discovery|haku_sidecar" | grep -v grep' | haku_redact | cut -c1-160 | code

h "Traffic ($SECS s)"
ssh nserver "cd /tmp && timeout $SECS tcpdump -ni any -A -s 400 -l 'dst host $HA_HOST and dst port 8123' 2>/dev/null > /tmp/hk_ha.txt & timeout $SECS tcpdump -ni any -A -s 400 -l 'dst port 1986 and not src host 127.0.0.1' 2>/dev/null > /tmp/hk_sc.txt & timeout $SECS tcpdump -ni any -A -s 400 -l 'dst port 1985 and not src host 127.0.0.1' 2>/dev/null > /tmp/hk_hls.txt & timeout $SECS tcpdump -ni any -nn 'src host $HA_HOST and src port 8123' 2>/dev/null | grep -oE 'length [0-9]+' | awk '{s+=\$2} END{printf \"HA->sidecar bytes/s: %.0f\n\", s/$SECS}' > /tmp/hk_b1.txt & timeout $SECS tcpdump -ni any -nn 'src port 1986 and not dst host 127.0.0.1' 2>/dev/null | grep -oE 'length [0-9]+' | awk '{s+=\$2} END{printf \"sidecar->clients bytes/s: %.0f\n\", s/$SECS}' > /tmp/hk_b2.txt & timeout $SECS tcpdump -ni any -nn 'src port 1985 and not dst host 127.0.0.1' 2>/dev/null | grep -oE 'length [0-9]+' | awk '{s+=\$2} END{printf \"HLS->clients bytes/s: %.0f\n\", s/$SECS}' > /tmp/hk_b3.txt & wait
echo '--- sidecar -> HA requests (count method path)'
grep -aoE '(GET|POST) /api/[a-z_/]*' /tmp/hk_ha.txt | sort | uniq -c | sort -rn | head -10
echo '--- clients -> sidecar :1986 (count src path)'
awk '/ > 192.0.2.20.1986/{for(i=1;i<=NF;i++) if(\$i ~ /^192\.0\.2\.[0-9]+\.[0-9]+\$/){ip=\$i; sub(/\.[0-9]+\$/,\"\",ip); break}} /GET \//{match(\$0,/GET \/[^ ]*/); print ip, substr(\$0,RSTART+4,RLENGTH-4)}' /tmp/hk_sc.txt | sed -E 's/\?.*layout=([a-z]+).*/?layout=\1/' | sort | uniq -c | sort -rn | head -12
echo '--- clients -> HLS :1985 (count src kind)'
awk '/ > 192.0.2.20.1985/{for(i=1;i<=NF;i++) if(\$i ~ /^192\.0\.2\.[0-9]+\.[0-9]+\$/){ip=\$i; sub(/\.[0-9]+\$/,\"\",ip); break}} /GET \//{match(\$0,/GET \/[^ ]*/); p=substr(\$0,RSTART+4,RLENGTH-4); gsub(/_seg_[0-9]+\.ts/,\"_seg_N.ts\",p); gsub(/seg_[0-9]+\.ts/,\"seg_N.ts\",p); print ip, p}' /tmp/hk_hls.txt | sort | uniq -c | sort -rn | head -12
echo '--- bytes'; cat /tmp/hk_b1.txt /tmp/hk_b2.txt /tmp/hk_b3.txt
rm -f /tmp/hk_ha.txt /tmp/hk_sc.txt /tmp/hk_hls.txt /tmp/hk_b1.txt /tmp/hk_b2.txt /tmp/hk_b3.txt" | code

h "Units (nserver)"
ssh nserver 'for u in $(systemctl list-units "haku*" "go2rtc*" --all --no-pager --plain | awk "{print \$1}" | grep -E "^(haku|go2rtc)"); do printf "%-30s %-9s restarts=%s\n" "$u" "$(systemctl show -p ActiveState --value "$u")" "$(systemctl show -p NRestarts --value "$u")"; done' | code

h "Home Assistant"
ssh mserver 'T=$(grep LONG_LIVE_TOKEN /home/displayuser/ha-calendar/.env | cut -d= -f2-); H="Authorization: Bearer $T"
curl -s -H "$H" http://127.0.0.1:8123/api/config | python3 -c "import sys,json; d=json.load(sys.stdin); print(\"version\", d[\"version\"], \"time_zone\", d[\"time_zone\"])"
curl -s -o /tmp/hk_states.json -w "states bytes=%{size_download} t=%{time_total}s\n" -H "$H" http://127.0.0.1:8123/api/states
python3 -c "import json; d=json.load(open(\"/tmp/hk_states.json\")); print(\"entities\", len(d), \"unavailable\", sum(1 for e in d if e[\"state\"]==\"unavailable\"), \"unknown\", sum(1 for e in d if e[\"state\"]==\"unknown\"))"
rm -f /tmp/hk_states.json
ls -la /root/docker/homeassistantV3/config/ha/home-assistant_v2.db | awk "{print \"recorder db bytes\", \$5}"' | code

h "Rokus"
{
for ip in $ROKUS; do
    di=$(curl -s -m 4 "http://$ip:8060/query/device-info" 2>/dev/null)
    if [ -z "$di" ]; then echo "$ip off"; continue; fi
    model=$(grep -oE '<model-name>[^<]*' <<<"$di" | cut -d'>' -f2)
    sw=$(grep -oE '<software-version>[^<]*' <<<"$di" | cut -d'>' -f2)
    app=$(curl -s -m 4 "http://$ip:8060/query/active-app" | tr -d '\n' | sed -E 's/.*<app[^>]*>([^<]*)<\/app>.*/\1/')
    ver=$(curl -s -m 4 "http://$ip:8060/query/apps" | grep -o 'id="dev"[^>]*version="[0-9.]*"' | sed -E 's/.*version="([0-9.]+)".*/\1/')
    perf=$(curl -s -m 4 "http://$ip:8060/query/chanperf" | tr -d '\n')
    cpu=$(grep -oE '<user>[0-9.]+' <<<"$perf" | cut -d'>' -f2)
    mem=$(grep -oE '<used>[0-9]+' <<<"$perf" | cut -d'>' -f2)
    state=$(curl -s -m 4 "http://$ip:8060/query/media-player" | grep -oE 'state="[a-z]*"' | head -1)
    printf '%s %s os=%s app=%s haku=%s cpu=%s%% mem=%sMB player=%s\n' "$ip" "$model" "$sw" "$app" "${ver:-?}" "${cpu:-?}" "$(( ${mem:-0} / 1048576 ))" "${state:-n/a}"
done
} | code

h "Clients connected to the sidecar (:1986)"
ssh nserver 'ss -Htn state established "( sport = :1986 )" | awk "{print \$4}" | sed "s/:[0-9]*\$//" | sort | uniq -c' | code
}

# Everything goes to a buffer first; the report is shown only if it holds no credential.
# The report runs as a background job so that Ctrl-C/TERM interrupt `wait` at once (bash
# defers traps while a foreground command runs), kill it, stop the remote captures and exit 130.
report > "$OUT" &
REPORT_PID=$!
trap 'pkill -TERM -P "$REPORT_PID" 2>/dev/null; kill "$REPORT_PID" 2>/dev/null; wait "$REPORT_PID" 2>/dev/null; cleanup; trap - EXIT; exit 130' INT TERM
wait "$REPORT_PID"
if ! haku_leak_check < "$OUT"; then
    echo "baseline: a credential-like string survived redaction; report withheld (see tools/lib/redact.sh)" >&2
    exit 3
fi
cat "$OUT"
