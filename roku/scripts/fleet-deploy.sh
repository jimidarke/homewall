#!/usr/bin/env bash
# scripts/fleet-deploy.sh [ip…] — sideload the current build to each Roku that is
# showing HAku right now, and report the version each device runs afterwards.
#
# A sideload relaunches the dev channel over whatever is playing, so a Roku on
# Netflix, Apple TV or the Roku menu is skipped (come back later). An unreachable
# Roku (TV off; the kids' Express is USB-powered by its TV) is reported, not failed.
#
# Passwords: ~/.config/haku/fleet.env (or $HAKU_FLEET_ENV) with ROKU_PW_FLEET for
# living/kids/master/den and ROKU_PW_OFFICE for office .55 and dad .56; see
# fleet.env.example. Uses scripts/deploy.js (ROKU_IP, ROKU_DEV_PASSWORD).
#
# Exit 0 when every reachable, HAku-showing Roku ends up on VERSION.txt's version;
# skips and unreachable devices are not failures. Exit 1 if any deploy failed or a
# device reports a different version afterwards; 2 for a missing env file.
set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${HAKU_FLEET_ENV:-$HOME/.config/haku/fleet.env}"
if [ ! -r "$ENV_FILE" ]; then
    echo "fleet-deploy: cannot read $ENV_FILE (copy fleet.env.example and fill it in)" >&2
    exit 2
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${ROKU_PW_FLEET:?ROKU_PW_FLEET missing in $ENV_FILE}" "${ROKU_PW_OFFICE:?ROKU_PW_OFFICE missing in $ENV_FILE}"

FLEET=(192.0.2.51 192.0.2.52 192.0.2.53 192.0.2.54 192.0.2.55 192.0.2.56)
OFFICE_PW_IPS=" 192.0.2.55 192.0.2.56 "
if [ $# -gt 0 ]; then FLEET=("$@"); fi
WANT=$(tr -d '[:space:]' < VERSION.txt)

device_version() {
    curl -s -m 4 "http://$1:8060/query/apps" | grep -o 'id="dev"[^>]*version="[0-9.]*"' | sed -E 's/.*version="([0-9.]+)".*/\1/'
}

failed=0
for ip in "${FLEET[@]}"; do
    active=$(curl -s -m 4 "http://$ip:8060/query/active-app" 2>/dev/null | tr -d '\n' || true)
    if [ -z "$active" ]; then
        echo "$ip unreachable"
        continue
    fi
    if ! grep -q 'id="dev"' <<<"$active"; then
        app=$(sed -E 's/.*<app[^>]*>([^<]*)<\/app>.*/\1/' <<<"$active")
        echo "$ip skipped: ${app:-unknown app}"
        continue
    fi
    pw=$ROKU_PW_FLEET
    case "$OFFICE_PW_IPS" in *" $ip "*) pw=$ROKU_PW_OFFICE ;; esac
    out=$(ROKU_IP="$ip" ROKU_DEV_PASSWORD="$pw" npm run deploy --silent 2>&1) || {
        echo "$ip deploy FAILED"
        printf '%s\n' "$out" | tail -5 | sed 's/^/    /'
        failed=1
        continue
    }
    sleep 3
    got=$(device_version "$ip" || true)
    if [ "$got" = "$WANT" ]; then
        echo "$ip deployed $got"
    else
        echo "$ip deploy ran but the device reports '${got:-?}' (wanted $WANT)"
        failed=1
    fi
done
exit $failed
