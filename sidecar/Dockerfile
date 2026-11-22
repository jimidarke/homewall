# HAku sidecar — portable container (the easy path for non-systemd installs).
#   docker build -t haku-sidecar sidecar
#   docker run --rm --network host --env-file /etc/haku/haku.env \
#     -v /etc/haku/dashboard.json:/etc/haku/dashboard.json:ro haku-sidecar
# --network host lets it reach HA on the LAN and share the port space with the
# existing stream stack; drop it and set HAKU_HA_URL to the LAN IP for bridge mode.
FROM python:3.12-slim

WORKDIR /opt/haku/sidecar
ENV PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    HAKU_CONFIG=/etc/haku/dashboard.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY haku_sidecar ./haku_sidecar

EXPOSE 1986
CMD ["python", "-m", "haku_sidecar.app"]
