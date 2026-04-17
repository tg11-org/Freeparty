# Logs and Telemetry Setup Guide

This guide covers both container log streaming and structured telemetry triage for Freeparty.

## 1. Quick Start (Container Logs)

View live logs from all running services:

**PowerShell:**
```powershell
./scripts/logs.ps1
```

**Command Prompt:**
```cmd
scripts\logs.cmd
```

View one service only (`web`, `db`, `redis`, `celery_worker`, `celery_beat`, `mailhog`):

**PowerShell:**
```powershell
./scripts/logs.ps1 web
```

**Command Prompt:**
```cmd
scripts\logs.cmd web
```

## 2. Structured Signals You Should See

The application emits key structured log patterns:

- Request lifecycle:
	- `request_complete`
	- `request_error`
	- `slow_request`
- Celery lifecycle:
	- `task_start`
	- `task_success`
	- `task_failure`
- Moderation escalation:
	- `incident_escalation severity=critical report_id=<uuid> assigned_to=<user_id>`
- SMTP delivery telemetry:
	- `smtp_delivery event=attempt|success|failure|retry_scheduled`
- Async interaction telemetry:
	- `interaction_metric name=<flow> success=<bool> duration_ms=<value>`

## 3. High-Value Log Filters

Follow worker logs and isolate SMTP issues:

```powershell
docker compose logs -f celery_worker | Select-String -Pattern "smtp_delivery"
```

Follow web logs and isolate async UX failures:

```powershell
docker compose logs -f web | Select-String -Pattern "interaction_metric|request_error|slow_request"
```

Correlate a single incident by request id/correlation id:

```powershell
$id = "replace-with-request-or-correlation-id"
docker compose logs --since 30m web celery_worker | Select-String -Pattern $id
```

Inspect critical moderation escalations:

```powershell
docker compose logs --since 60m web | Select-String -Pattern "incident_escalation|High-severity reports require evidence"
```

Inspect federation and dead-letter behavior:

```powershell
docker compose logs --since 60m celery_worker | Select-String -Pattern "federation_delivery|task_failure|manual_replay|max_retries_exceeded"
```

## 4. Operational Triage Workflow

1. Capture `X-Request-ID` from client/API response.
2. Find matching `request_complete` or `request_error` in `web` logs.
3. Follow `correlation_id` into Celery `task_*` log entries.
4. If SMTP errors are present, run:

```powershell
u:/Projects/Freeparty/.venv/Scripts/python.exe manage.py check_smtp
```

5. If retries surge, inspect async terminal failures:

```powershell
u:/Projects/Freeparty/.venv/Scripts/python.exe manage.py async_failures --terminal-only
```

6. If terminal failures need recovery triage, inspect and replay from the dead-letter queue:

```powershell
u:/Projects/Freeparty/.venv/Scripts/python.exe manage.py dead_letter_inspect --limit 25
u:/Projects/Freeparty/.venv/Scripts/python.exe manage.py dead_letter_inspect --replay <failure-id>
```

## 5. Compose Log Usage Tips

Timestamps:

```powershell
docker compose logs -f --timestamps
```

Recent lines only:

```powershell
docker compose logs --tail 200 web
```

Since duration:

```powershell
docker compose logs -f --since 10m web celery_worker
```

Save logs to file:

```powershell
./scripts/logs.ps1 > logs.txt
```

## 6. Troubleshooting

- If containers are not running, start them first:

```powershell
./scripts/start.ps1
```

- If `no such service` appears, verify service names from `compose.yaml`.
- If logs look incomplete after restarts, use `docker compose logs --since` with a wider window.
- If moderation/federation triage requires sqlite-only local validation, run commands with `DATABASE_URL=sqlite:///test.sqlite3` to avoid the default compose-only Postgres hostname.
