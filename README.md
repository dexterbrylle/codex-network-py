# Codex Network Performance Monitor

A Python script that monitors network performance by performing regular speed tests and IP checks, storing results in PostgreSQL, and sending periodic email reports.

## Features

- Speed tests every 30 minutes (download, upload, latency)
- Public IP address monitoring
- PostgreSQL database storage
- Email reports:
  - 6-hour summaries
  - Daily detailed reports (11:59 PM)
- PDF and CSV report attachments
- Comprehensive error logging
- Docker support for easy deployment
- Automated tests with pytest

## Requirements

### Standard Installation
- Python 3.6+
- PostgreSQL database
- SMTP email account (e.g., Gmail)
- Required Python packages (see requirements.txt)

### Docker Installation
- Docker
- Docker Compose

## Setup

### Standard Installation

1. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your configuration values.

3. Run the script:
   ```bash
   python network_monitor.py
   ```

### Docker Installation

1. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your configuration values.

2. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

   This will:
   - Build the application container
   - Start PostgreSQL container
   - Create necessary volumes and networks
   - Mount logs directory

3. View logs:
   ```bash
   docker-compose logs -f app
   ```

## Testing

The project includes a comprehensive test suite using pytest. The tests cover:
- Speed test functionality
- Database operations
- Email reporting
- Error handling
- Input validation

### Running Tests

1. Install test dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure test environment:
   The test configuration is in `pytest.ini`. By default, it uses a separate test database
   to avoid interfering with your production data.

3. Run the tests:
   ```bash
   pytest
   ```

   Or with coverage report:
   ```bash
   pytest --cov=network_monitor tests/
   ```

### Test Categories

- `test_network_monitor.py`: Core functionality tests
  - Speed testing
  - Database operations
  - Network checks
  - Error handling

- `test_email_reports.py`: Email reporting tests
  - Report generation
  - Email sending
  - Attachment handling
  - Error cases

## Environment Variables

Configure the following variables in `.env`:

```ini
# Database Configuration
DB_HOST=localhost      # Use 'db' for Docker
DB_NAME=network_monitor
DB_USER=your_db_user
DB_PASSWORD=your_db_password

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_RECIPIENT=recipient@example.com

# Network Thresholds (Mbps)
DOWNLOAD_THRESHOLD=500
UPLOAD_THRESHOLD=300

# Monitoring Configuration
CHECK_INTERVAL_MINUTES=30
SUMMARY_INTERVAL_HOURS=6
DAILY_REPORT_TIME=23:59
```

Note: For Gmail, you'll need to use an App Password. See [Google Account Help](https://support.google.com/accounts/answer/185833?hl=en) for instructions.

## Logging

All activities and errors are logged to `logs/network_monitor.log` with timestamps and log levels.

## Reports

### 6-Hour Summary
- Sent every 6 hours
- Includes:
  - Average speeds and latency
  - IP address changes
  - Slow speed incidents
  - PDF report
  - CSV data export

### Daily Report
- Sent at 11:59 PM
- Same format as 6-hour summary but covers 24 hours

## Error Handling

The script includes comprehensive error handling for:
- Network connectivity issues
- Database connection problems
- Email sending failures
- Speed test errors

All errors are logged to `network_monitor.log`.

## Docker Volumes

The following Docker volumes are used:
- `postgres_data`: Persists PostgreSQL data
- `./logs`: Mounts the logs directory to the host machine

## Maintenance

### Backup Database
To backup the PostgreSQL database:
```bash
docker-compose exec db pg_dump -U $DB_USER $DB_NAME > backup.sql
```

### Restore Database
To restore from a backup:
```bash
docker-compose exec -T db psql -U $DB_USER $DB_NAME < backup.sql
``` 