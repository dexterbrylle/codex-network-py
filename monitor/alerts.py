import csv
import datetime
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

import requests

from monitor.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_RECIPIENT, DISCORD_WEBHOOK_URL, ISP_PLAN_NAME
)

logger = logging.getLogger(__name__)


def send_discord_alert(result):
    """Send a compact breach card to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.info("Discord webhook URL not configured — skipping")
        return

    try:
        worst_down = f"{result['worst_download']:.1f}" if result['worst_download'] else "N/A"
        worst_upload = f"{result['worst_upload']:.1f}" if result['worst_upload'] else "N/A"

        embed = {
            "title": f"⚠️ ISP SLA Breach — {ISP_PLAN_NAME}",
            "color": 0xFF0000,
            "fields": [
                {"name": "Below Threshold", "value": f"{result['violating_count']}/{result['total_count']} checks", "inline": True},
                {"name": "Violation %", "value": f"{result['violation_pct']}%", "inline": True},
                {"name": "Worst Download", "value": f"{worst_down} Mbps", "inline": True},
                {"name": "Worst Upload", "value": f"{worst_upload} Mbps", "inline": True},
            ],
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        }

        payload = {"embeds": [embed]}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord alert sent")
    except Exception as e:
        logger.error(f"Discord alert failed: {e}")


def send_breach_email(result):
    """Send HTML email with breach summary, CSV and PDF evidence."""
    try:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=24)

        # Build CSV
        csv_filename = f'sla_breach_{end_time.strftime("%Y%m%d_%H%M%S")}.csv'
        breached = [dict(r) for r in result.get("breached_checks", [])]

        with open(csv_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'download_speed', 'upload_speed', 'latency', 'ip_address', 'below_threshold'])
            for check in breached:
                writer.writerow([
                    check['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if check.get('timestamp') else '',
                    check.get('download_speed', ''),
                    check.get('upload_speed', ''),
                    check.get('latency', ''),
                    check.get('ip_address', ''),
                    check.get('below_threshold', '')
                ])

        worst_down = f"{result['worst_download']:.1f}" if result['worst_download'] else "N/A"
        worst_upload = f"{result['worst_upload']:.1f}" if result['worst_upload'] else "N/A"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #cc0000;">ISP SLA Breach — {ISP_PLAN_NAME}</h2>
            <p><strong>Period:</strong> {start_time.strftime('%m/%d/%Y, %I:%M:%S %p')} — {end_time.strftime('%m/%d/%Y, %I:%M:%S %p')}</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background: #f5f5f5;">
                    <td><strong>Threshold</strong></td><td>Below {result.get('threshold', '150')} Mbps</td>
                </tr>
                <tr>
                    <td><strong>Below Threshold</strong></td><td>{result['violating_count']}/{result['total_count']} checks</td>
                </tr>
                <tr>
                    <td><strong>Violation %</strong></td><td>{result['violation_pct']}%</td>
                </tr>
                <tr>
                    <td><strong>Worst Download</strong></td><td>{worst_down} Mbps</td>
                </tr>
                <tr>
                    <td><strong>Worst Upload</strong></td><td>{worst_upload} Mbps</td>
                </tr>
            </table>
            <p>Full evidence CSV attached.</p>
        </body>
        </html>
        """

        msg = MIMEMultipart()
        msg['Subject'] = f'ISP SLA Breach — {ISP_PLAN_NAME}'
        msg['From'] = SMTP_USER
        msg['To'] = EMAIL_RECIPIENT

        msg.attach(MIMEText(html_body, 'html'))

        with open(csv_filename, 'rb') as f:
            csv_attachment = MIMEApplication(f.read(), _subtype='csv')
            csv_attachment.add_header('Content-Disposition', 'attachment', filename=csv_filename)
            msg.attach(csv_attachment)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("Breach email sent")

        os.remove(csv_filename)
    except Exception as e:
        logger.error(f"Breach email failed: {e}")
