#!/usr/bin/env bash
set -euo pipefail
# Run on the Oracle Ubuntu 24.04 VM from the cloned repository.
if [[ $EUID -ne 0 ]]; then echo 'Run: sudo bash server/deploy/install.sh'; exit 1; fi
source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ ! -f "$source_root/vendor/geo-sleuth/SKILL.md" ]]; then echo 'Missing complete vendor skill'; exit 1; fi
if [[ -f /etc/geo-lens/server.env ]]; then echo 'Already configured. See server/README.md for updates; existing secrets were preserved.'; exit 1; fi
apt-get update
apt-get install -y docker.io python3-venv python3-pip curl ca-certificates iptables rsync
systemctl enable --now docker
id geolens >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/geo-lens --shell /usr/sbin/nologin geolens
usermod -aG docker geolens
install -d -m 755 /opt/geo-lens
rsync -a --exclude=.git --exclude=node_modules --exclude=dist --exclude=public --exclude=.env --exclude=.dev.vars "$source_root/" /opt/geo-lens/
python3 -m venv /opt/geo-lens/.venv
/opt/geo-lens/.venv/bin/pip install -r /opt/geo-lens/server/requirements.txt
cd /opt/geo-lens
docker build -f server/tool.Dockerfile -t geo-lens-tools:local .
docker network inspect geo-tools >/dev/null 2>&1 || docker network create --subnet 172.30.80.0/24 geo-tools
docker volume create geo-tool-cache >/dev/null
runner_uid=$(id -u geolens);runner_gid=$(id -g geolens)
docker run --rm --user 0:0 --network none -v geo-tool-cache:/cache geo-lens-tools:local sh -c "mkdir -p /cache/home /cache/huggingface /cache/uv && chown -R $runner_uid:$runner_gid /cache"
install -d -o geolens -g geolens -m 700 /var/lib/geo-lens/jobs
install -d -m 700 /etc/geo-lens
read -rp 'Full API base URL (including /v1, from provider docs): ' api_base
read -rsp 'Provider API key (hidden): ' provider_key; echo
backend_token=$(/opt/geo-lens/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(36))')
# JSON quotes are valid systemd EnvironmentFile quotes; refuse newlines.
[[ "$api_base" == https://* && "$api_base" != *$'\n'* && "$provider_key" != *$'\n'* ]] || { echo 'Invalid configuration'; exit 1; }
GEO_API_BASE="$api_base" GEO_API_KEY="$provider_key" GEO_BACKEND_TOKEN="$backend_token" /opt/geo-lens/.venv/bin/python - <<'PY'
import json,os
from pathlib import Path
p=Path('/etc/geo-lens/server.env')
with p.open('x') as f:
 for key,value in {'PHOTO_API_BASE':os.environ['GEO_API_BASE'],'PHOTO_API_KEY':os.environ['GEO_API_KEY'],'BACKEND_TOKEN':os.environ['GEO_BACKEND_TOKEN'],'JOB_ROOT':'/var/lib/geo-lens/jobs','MAX_AGENT_STEPS':'32','JOB_TIMEOUT_SECONDS':'1800','RETENTION_HOURS':'24'}.items(): f.write(key+'='+json.dumps(value)+'\n')
p.chmod(0o600)
PY
unset provider_key backend_token
install -m 755 server/deploy/egress.sh /usr/local/sbin/geo-lens-egress
install -m 644 server/deploy/geo-lens-egress.service /etc/systemd/system/
install -m 644 server/deploy/geo-lens.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now geo-lens-egress geo-lens
# Verify the API before starting a public tunnel.
curl --fail --retry 10 --retry-delay 2 --retry-connrefused http://127.0.0.1:8080/health
printf '\nInstalled. Next: server/README.md → HTTPS tunnel and Worker secrets.\n'
