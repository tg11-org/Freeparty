# Live Logs Viewing Guide

## Quick Start

To view live logs from all running Docker containers:

**PowerShell:**
```powershell
./scripts/logs.ps1
```

**Command Prompt:**
```cmd
scripts\logs.cmd
```

## View Logs from Specific Service

View logs from a single service (web, db, redis, celery_worker, celery_beat, or mailhog):

**PowerShell:**
```powershell
./scripts/logs.ps1 web
./scripts/logs.ps1 db
./scripts/logs.ps1 redis
./scripts/logs.ps1 celery_worker
./scripts/logs.ps1 celery_beat
./scripts/logs.ps1 mailhog
```

**Command Prompt:**
```cmd
scripts\logs.cmd web
scripts\logs.cmd db
scripts\logs.cmd redis
scripts\logs.cmd celery_worker
scripts\logs.cmd celery_beat
scripts\logs.cmd mailhog
```

## How It Works

- The log scripts use `docker compose logs -f` to follow live output
- Output displays real-time container logs with service names and timestamps
- Press **Ctrl+C** to stop following logs
- Logs are sent to stdout - you can redirect to a file if needed

## Advanced Usage

### Follow logs with timestamps:
```powershell
docker compose logs -f --timestamps
```

### View last 100 lines:
```powershell
docker compose logs --tail 100
```

### View logs since a specific time:
```powershell
docker compose logs -f --since 5m  # Last 5 minutes
```

### Save logs to a file:
```powershell
./scripts/logs.ps1 > logs.txt
```

## Troubleshooting

If containers aren't running, start them first:
```powershell
./scripts/start.ps1
```

If you see "no such service" errors, verify the service name matches the compose.yaml exactly (case-sensitive on Linux).

For containers that have restarted, logs only show output since the most recent start.
