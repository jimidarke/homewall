# tools/lib/redact.sh — strip credentials from operator output before it is shown or saved.
# Source this; both functions are stdin → stdout filters.

# Replace the user:password part of any rtsp:// URL with ***, and any bearer token with ***.
haku_redact() {
    sed -E \
        -e 's#(rtsp://)[^@/[:space:]]+@#\1***@#g' \
        -e 's#(Bearer )[A-Za-z0-9._~+/=-]+#\1***#g'
}

# Exit 0 when the input holds no unredacted rtsp credential or bearer token, 1 otherwise.
haku_leak_check() {
    if grep -qE 'rtsp://[^*@/[:space:]]+@|Bearer [^*[:space:]]' ; then
        return 1
    fi
    return 0
}
