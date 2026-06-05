# Docker VPS Deploy (Hetzner)

## 1. Create VPS
- Provider: Hetzner Cloud
- OS: Ubuntu 24.04
- Size: CPX21 or higher (2 vCPU, 4 GB RAM)
- Add your SSH public key during server creation

## 2. Connect to VPS
```bash
ssh root@YOUR_SERVER_IP
```

## 3. Install Docker + Compose plugin
```bash
apt update
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker
systemctl start docker
```

## 4. Upload project once
Option A: clone from GitHub
```bash
mkdir -p /srv/daily_nexus_update
cd /srv/daily_nexus_update
git clone YOUR_REPO_URL .
```

Option B: upload local project from Windows
```powershell
scp -r C:\local\my_project_attempts\daily_nexus_update\* root@YOUR_SERVER_IP:/srv/daily_nexus_update/
```

## 5. Add runtime secrets/config
On VPS:
```bash
cd /srv/daily_nexus_update
mkdir -p secrets output
nano .env
```

Set at minimum:
```env
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
ENABLE_VOICEOVER=true
YOUTUBE_UPLOAD_ENABLED=true
OUTPUT_DIR=output
YOUTUBE_CLIENT_SECRETS_FILE=secrets/youtube_client_secret.json
YOUTUBE_TOKEN_FILE=secrets/youtube_token.json
```

Upload secret json files from Windows:
```powershell
scp C:\local\my_project_attempts\daily_nexus_update\secrets\youtube_client_secret.json root@YOUR_SERVER_IP:/srv/daily_nexus_update/secrets/
scp C:\local\my_project_attempts\daily_nexus_update\secrets\youtube_token.json root@YOUR_SERVER_IP:/srv/daily_nexus_update/secrets/
```

## 6. Build container image
```bash
cd /srv/daily_nexus_update
docker compose build
```

## 7. Optional: run dashboard/API service
```bash
docker compose up -d web
docker compose logs -f web
```

## 8. Manual pipeline test anytime
```bash
cd /srv/daily_nexus_update
chmod +x scripts/*.sh
./scripts/run_pipeline.sh --topics tech finance crypto geopolitics
```

Publish test:
```bash
./scripts/run_pipeline.sh --topics tech finance crypto geopolitics --publish-to-youtube
```

## 9. Cron automation (Mon/Wed/Fri)
Open cron:
```bash
crontab -e
```

Add schedule run at 08:00 server time:
```cron
0 8 * * 1,3,5 cd /srv/daily_nexus_update && flock -n /tmp/daily_nexus.lock ./scripts/run_pipeline.sh --topics tech finance crypto geopolitics --publish-to-youtube >> /var/log/daily_nexus_update.log 2>&1
```

## 10. Weekly cleanup (delete output older than 7 days)
Add:
```cron
15 3 * * 0 cd /srv/daily_nexus_update && ./scripts/cleanup_output.sh >> /var/log/daily_nexus_cleanup.log 2>&1
```

## 11. Verify
```bash
crontab -l
docker ps
tail -n 100 /var/log/daily_nexus_update.log
```

## Notes
- Keep secrets out of git.
- Container writes outputs into host-mounted `output/`.
- Use local disk for working files; sync old output elsewhere if needed.
