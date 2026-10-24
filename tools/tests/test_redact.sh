#!/usr/bin/env bash
# tools/tests/test_redact.sh — haku_redact() must strip credentials from anything
# the baseline report could echo: RTSP URLs with user:pass and bearer tokens.
set -uo pipefail
cd "$(dirname "$0")/../.."
fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok    $1"; else echo "  FAIL  $1: got [$2] want [$3]"; fail=1; fi; }

# shellcheck disable=SC1091
source tools/lib/redact.sh || { echo "FAIL: tools/lib/redact.sh missing"; exit 1; }

in1='3045006 ffmpeg -rtsp_transport tcp -i rtsp://admin:s3cret@192.0.2.31:554/11 -vf vpp_qsv'
check "rtsp user:pass redacted" "$(printf '%s\n' "$in1" | haku_redact)" \
      '3045006 ffmpeg -rtsp_transport tcp -i rtsp://***@192.0.2.31:554/11 -vf vpp_qsv'
in2='two: rtsp://u:p@h1/a and rtsp://u2:p2@h2/b'
check "every rtsp on a line" "$(printf '%s\n' "$in2" | haku_redact)" 'two: rtsp://***@h1/a and rtsp://***@h2/b'
in3='-i rtsp://127.0.0.1:8554/front -c copy'
check "credential-free rtsp untouched" "$(printf '%s\n' "$in3" | haku_redact)" "$in3"
in4='curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def" http://x'
check "bearer token redacted" "$(printf '%s\n' "$in4" | haku_redact)" 'curl -H "Authorization: Bearer ***" http://x'
in5='plain line with no secrets 161324'
check "plain line untouched" "$(printf '%s\n' "$in5" | haku_redact)" "$in5"

# The guard the report runs on itself must flag an unredacted leak and accept a redacted one.
check "guard flags leak" "$(printf 'x rtsp://u:p@h/1\n' | haku_leak_check && echo clean || echo leak)" leak
check "guard accepts redacted" "$(printf 'x rtsp://***@h/1 Bearer ***\n' | haku_leak_check && echo clean || echo leak)" clean

echo "RESULT fail=$fail"
exit $fail
