# Network Performance Monitor

Monitors ISP connection quality via scheduled speed tests. Tracks contractual SLA compliance, sends real-time breach alerts (Discord + email), and stores everything in PostgreSQL for Grafana dashboards.

## Features

- Speed tests every 30 minutes (download, upload, latency)
- Public IP address monitoring
- **ISP SLA breach detection** — alerts when speeds drop below contractual minimum (>20% of checks in 24h rolling window)
- **Breach alerts**: Discord webhook (real-time) + HTML email with CSV evidence
- **Episode tracking** — breach start/end recorded in `sla_breach_episodes` table
- PostgreSQL storage (Grafana-ready via direct DB query)
- Periodic email reports (6h summaries + daily)
- PDF and CSV report attachments
- Docker support
- Modular codebase, single container
- Automated tests with pytest

## Architecture

```
main.py              → thin entry point
monitor/
  config.py          → env loading, validation
  db.py              → PostgreSQL: connect, init, save, SLA episode CRUD
  speedtest.py       → Ookla speed test + IP lookup
  sla.py             → threshold evaluation, breach detection, episode state machine
  alerts.py          → Discord webhook + HTML breach email with CSV
  reports.py         → periodic PDF/CSV email reports
  scheduler.py       → schedule setup, main check loop
```

## Setup (Docker)

```bash
cp .env.example .env     # edit with your values
docker-compose up -d
```

## Setup (Standard)

```bash
pip install -r requirements.txt
cp .env.example .env     # edit with your values
python main.py
```

**Requires**: Python 3.9+, running PostgreSQL, SMTP account.

## Environment Variables

```ini
# ISP Plan (contractual SLA)
ISP_PLAN_NAME="Plan 1999"
ISP_PLAN_SPEED=500
ISP_PLAN_UPLOAD_SPEED=500
ISP_PLAN_THRESHOLD=150        # contractual minimum download Mbps
ISP_PLAN_UPLOAD_THRESHOLD=150

# Speed alert thresholds (periodic report "slow incident" counts)
SPEED_ALERT_DOWNLOAD=500
SPEED_ALERT_UPLOAD=300

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Database
DB_HOST=db                    # 'localhost' for non-Docker
DB_NAME=network_monitor
DB_USER=your_db_user
DB_PASSWORD=your_secure_password

# Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_RECIPIENT=recipient@example.com

# Schedule
CHECK_INTERVAL_MINUTES=30
SUMMARY_INTERVAL_HOURS=6
DAILY_REPORT_TIME=23:59
```

## How SLA Breach Detection Works

1. Every speed test is evaluated: download < `ISP_PLAN_THRESHOLD` OR upload < `ISP_PLAN_UPLOAD_THRESHOLD` → flagged `below_threshold`
2. After each test, the last 48 checks (24h rolling window) are counted
3. If >9 checks (20%+) are below threshold → **SLA breach declared**
4. Breach episode starts, Discord alert fires, HTML email with CSV evidence sent
5. Alerts suppressed until breach resolves (all future checks stay under threshold)
6. Episode closed when window clears, `sla_breach_episodes.ended_at` populated

**Edge cases**: failed speed tests (NULL) count in total but not as violating (conservative). Startup (< 48 checks) defers evaluation.

## Grafana Integration

Point Grafana at the same PostgreSQL:

```sql
-- Speed over time
SELECT timestamp, download_speed, upload_speed FROM network_checks ORDER BY timestamp

-- Below-threshold markers
SELECT timestamp FROM network_checks WHERE below_threshold = true

-- SLA breach episodes (duration + severity)
SELECT * FROM sla_breach_episodes ORDER BY started_at

-- Violation % (rolling 24h)
SELECT COUNT(*) FILTER (WHERE below_threshold) * 100.0 / COUNT(*) AS pct
FROM network_checks WHERE timestamp > NOW() - INTERVAL '24 hours'
```

## Testing

```bash
uv sync --group dev
export DB_HOST=localhost     # tests need local PostgreSQL
uv run pytest tests/
```

Tests cover: speed test mocking, SLA breach logic (all state transitions), NULL handling, startup edge cases, Discord/email alert verification, email attachment generation. DB integration test needs a local PostgreSQL instance.

## Maintenance

```bash
# Backup
docker-compose exec db pg_dump -U $DB_USER $DB_NAME > backup.sql

# Restore
docker-compose exec -T db psql -U $DB_USER $DB_NAME < backup.sql

# Logs
docker-compose logs -f app
```
