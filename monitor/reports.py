import csv
import datetime
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from monitor.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_RECIPIENT, SPEED_ALERT_DOWNLOAD, SPEED_ALERT_UPLOAD
)
from monitor.db import get_report_data as db_get_report_data

logger = logging.getLogger(__name__)


def generate_pdf_report(data, start_time, end_time, filename):
    """Generate a PDF report with network monitoring data."""
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Network Monitoring Report", styles['Title']))
    elements.append(Spacer(1, 12))

    period_text = f"Report Period: {start_time.strftime('%m/%d/%Y, %I:%M:%S %p')} - {end_time.strftime('%m/%d/%Y, %I:%M:%S %p')}"
    elements.append(Paragraph(period_text, styles['Normal']))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("Summary:", styles['Heading2']))
    for key, value in data['summary'].items():
        elements.append(Paragraph(f"• {key}: {value}", styles['Normal']))
    elements.append(Spacer(1, 12))

    if data['incidents']:
        elements.append(Paragraph("Speed Incidents:", styles['Heading2']))
        table_data = [['Timestamp', 'Download Speed', 'Upload Speed']]
        table_data.extend(data['incidents'])

        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(t)

    doc.build(elements)


def generate_csv_report(data, filename):
    """Generate a CSV report with network monitoring data."""
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Download Speed (Mbps)', 'Upload Speed (Mbps)', 'Latency (ms)', 'IP Address'])
        for row in data:
            writer.writerow(row)


def get_report_data(hours):
    """Get report data for the specified number of hours."""
    results = db_get_report_data(hours)

    if not results:
        return None

    download_speeds = [r['download_speed'] for r in results if r.get('download_speed') is not None]
    upload_speeds = [r['upload_speed'] for r in results if r.get('upload_speed') is not None]
    latencies = [r['latency'] for r in results if r.get('latency') is not None]
    ip_addresses = set(r['ip_address'] for r in results if r.get('ip_address'))

    summary = {
        'Average Download Speed': f"{sum(download_speeds)/len(download_speeds):.2f} Mbps" if download_speeds else "N/A",
        'Average Upload Speed': f"{sum(upload_speeds)/len(upload_speeds):.2f} Mbps" if upload_speeds else "N/A",
        'Average Latency': f"{sum(latencies)/len(latencies):.2f} ms" if latencies else "N/A",
        'IP Changes': 'Yes' if len(ip_addresses) > 1 else 'No',
        'Slow Download Incidents': sum(1 for speed in download_speeds if speed < SPEED_ALERT_DOWNLOAD),
        'Slow Upload Incidents': sum(1 for speed in upload_speeds if speed < SPEED_ALERT_UPLOAD)
    }

    incidents = []
    for r in results:
        dl = r.get('download_speed')
        ul = r.get('upload_speed')
        if dl is not None and ul is not None:
            if dl < SPEED_ALERT_DOWNLOAD or ul < SPEED_ALERT_UPLOAD:
                incidents.append([
                    r['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if r.get('timestamp') else '',
                    f"{dl:.2f} Mbps" if dl < SPEED_ALERT_DOWNLOAD else "OK",
                    f"{ul:.2f} Mbps" if ul < SPEED_ALERT_UPLOAD else "OK"
                ])

    return {
        'summary': summary,
        'incidents': incidents,
        'raw_data': [
            [r['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if r.get('timestamp') else '',
             r.get('download_speed'),
             r.get('upload_speed'),
             r.get('latency'),
             r.get('ip_address')] for r in results
        ]
    }


def send_email_report(hours):
    """Send an email report with network monitoring data."""
    try:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=hours)

        data = get_report_data(hours)
        if not data:
            logger.warning(f"No data available for the past {hours} hours")
            return

        pdf_filename = f'network_report_{hours}h.pdf'
        csv_filename = f'network_data_{hours}h.csv'

        generate_pdf_report(data, start_time, end_time, pdf_filename)
        generate_csv_report(data['raw_data'], csv_filename)

        msg = MIMEMultipart()
        msg['Subject'] = 'Network Monitoring Report'
        msg['From'] = SMTP_USER
        msg['To'] = EMAIL_RECIPIENT

        body = f"""Network Monitoring Report
Report Period: {start_time.strftime('%m/%d/%Y, %I:%M:%S %p')} - {end_time.strftime('%m/%d/%Y, %I:%M:%S %p')}

Summary:
"""
        for key, value in data['summary'].items():
            body += f"• {key}: {value}\n"

        msg.attach(MIMEText(body))

        with open(pdf_filename, 'rb') as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
            msg.attach(pdf_attachment)

        with open(csv_filename, 'rb') as f:
            csv_attachment = MIMEApplication(f.read(), _subtype='csv')
            csv_attachment.add_header('Content-Disposition', 'attachment', filename=csv_filename)
            msg.attach(csv_attachment)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email report sent successfully for past {hours} hours")

        os.remove(pdf_filename)
        os.remove(csv_filename)

    except Exception as e:
        logger.error(f"Error sending email report: {e}")
