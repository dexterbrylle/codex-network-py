import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('network_monitor.log'),
        logging.StreamHandler()
    ]
)

# Database
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'network_monitor')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Email
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

# Speed alert thresholds (periodic report "slow incident" counts)
SPEED_ALERT_DOWNLOAD = float(os.getenv('SPEED_ALERT_DOWNLOAD', '500'))
SPEED_ALERT_UPLOAD = float(os.getenv('SPEED_ALERT_UPLOAD', '300'))

# ISP Plan (contractual SLA)
ISP_PLAN_NAME = os.getenv('ISP_PLAN_NAME', 'Plan 1999')
ISP_PLAN_SPEED = int(os.getenv('ISP_PLAN_SPEED', '500'))
ISP_PLAN_UPLOAD_SPEED = int(os.getenv('ISP_PLAN_UPLOAD_SPEED', '500'))
ISP_PLAN_THRESHOLD = float(os.getenv('ISP_PLAN_THRESHOLD', '150'))
ISP_PLAN_UPLOAD_THRESHOLD = float(os.getenv('ISP_PLAN_UPLOAD_THRESHOLD', '150'))

# Discord
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')

# Monitoring schedule
CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '30'))
SUMMARY_INTERVAL_HOURS = int(os.getenv('SUMMARY_INTERVAL_HOURS', '6'))
DAILY_REPORT_TIME = os.getenv('DAILY_REPORT_TIME', '23:59')

# SLA constants
SLA_WINDOW_HOURS = 24
SLA_VIOLATION_MAX = 9

# Validation
required_vars = [
    'DB_USER', 'DB_PASSWORD', 'SMTP_USER',
    'SMTP_PASSWORD', 'EMAIL_RECIPIENT'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

if not DISCORD_WEBHOOK_URL:
    logging.info("Discord alerts disabled (no webhook URL configured)")
