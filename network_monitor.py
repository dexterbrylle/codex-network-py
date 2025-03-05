#!/usr/bin/env python3

import datetime
import logging
import os
import schedule
import speedtest
import time
import requests
import psycopg2
from psycopg2.extras import DictCursor
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import csv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('network_monitor.log'),
        logging.StreamHandler()
    ]
)

# Load configuration from environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'network_monitor')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

# Network thresholds (in Mbps)
DOWNLOAD_THRESHOLD = float(os.getenv('DOWNLOAD_THRESHOLD', '500'))
UPLOAD_THRESHOLD = float(os.getenv('UPLOAD_THRESHOLD', '300'))

# Monitoring configuration
CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '30'))
SUMMARY_INTERVAL_HOURS = int(os.getenv('SUMMARY_INTERVAL_HOURS', '6'))
DAILY_REPORT_TIME = os.getenv('DAILY_REPORT_TIME', '23:59')

# Validate required environment variables
required_vars = [
    'DB_USER', 'DB_PASSWORD', 'SMTP_USER', 
    'SMTP_PASSWORD', 'EMAIL_RECIPIENT'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def init_db():
    """Initialize the database and create the network_checks table if it doesn't exist."""
    try:
        # Parse host and port from DB_HOST
        if ':' in DB_HOST:
            host, port = DB_HOST.split(':')
            port = int(port)
        else:
            host = DB_HOST
            port = 5432  # Default PostgreSQL port

        # First connect to 'postgres' database to create our database if it doesn't exist
        conn = psycopg2.connect(
            host=host,
            port=port,
            database='postgres',
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True  # Required for database creation
        cur = conn.cursor()
        
        # Check if our database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            # Create database if it doesn't exist
            cur.execute(f'CREATE DATABASE {DB_NAME}')
            logging.info(f"Database {DB_NAME} created successfully")
        
        # Close connection to postgres database
        cur.close()
        conn.close()

        # Now connect to our database and create the table
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        
        # Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS network_checks (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                download_speed FLOAT,
                upload_speed FLOAT,
                latency FLOAT,
                ip_address TEXT
            );
        """)
        
        conn.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Database initialization error: {e}")
        raise  # Re-raise the exception to stop the program if database init fails
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def perform_speed_test():
    """Perform a speed test and return the results."""
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        
        download_speed = st.download() / 1_000_000  # Convert to Mbps
        upload_speed = st.upload(pre_allocate=False) / 1_000_000  # Convert to Mbps
        latency = st.results.ping
        
        return download_speed, upload_speed, latency
    except Exception as e:
        logging.error(f"Speed test error: {e}")
        return None, None, None

def get_public_ip():
    """Get the public IP address."""
    try:
        return requests.get('http://ipinfo.io/ip').text.strip()
    except Exception as e:
        logging.error(f"IP address check error: {e}")
        return None

def save_check_results(download_speed, upload_speed, latency, ip_address):
    """Save the network check results to the database."""
    try:
        # Parse host and port from DB_HOST
        if ':' in DB_HOST:
            host, port = DB_HOST.split(':')
            port = int(port)
        else:
            host = DB_HOST
            port = 5432  # Default PostgreSQL port
            
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO network_checks (timestamp, download_speed, upload_speed, latency, ip_address)
            VALUES (NOW(), %s, %s, %s, %s)
        """, (download_speed, upload_speed, latency, ip_address))
        
        conn.commit()
        logging.info("Results saved to database successfully")
    except Exception as e:
        logging.error(f"Database save error: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def generate_pdf_report(data, start_time, end_time, filename):
    """Generate a PDF report with the network monitoring data."""
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title
    elements.append(Paragraph(f"Network Monitoring Report", styles['Title']))
    elements.append(Spacer(1, 12))
    
    # Period
    period_text = f"Report Period: {start_time.strftime('%m/%d/%Y, %I:%M:%S %p')} - {end_time.strftime('%m/%d/%Y, %I:%M:%S %p')}"
    elements.append(Paragraph(period_text, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Summary
    elements.append(Paragraph("Summary:", styles['Heading2']))
    for key, value in data['summary'].items():
        elements.append(Paragraph(f"• {key}: {value}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Incidents Table
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
    """Generate a CSV report with the network monitoring data."""
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Download Speed (Mbps)', 'Upload Speed (Mbps)', 'Latency (ms)', 'IP Address'])
        for row in data:
            writer.writerow(row)

def get_report_data(hours):
    """Get report data for the specified number of hours."""
    try:
        # Parse host and port from DB_HOST
        if ':' in DB_HOST:
            host, port = DB_HOST.split(':')
            port = int(port)
        else:
            host = DB_HOST
            port = 5432  # Default PostgreSQL port
            
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get data for the specified period
        cur.execute("""
            SELECT *
            FROM network_checks
            WHERE timestamp >= NOW() - interval %s hour
            ORDER BY timestamp DESC
        """, (hours,))
        
        results = cur.fetchall()
        
        if not results:
            return None
        
        # Calculate summary statistics
        download_speeds = [r['download_speed'] for r in results]
        upload_speeds = [r['upload_speed'] for r in results]
        latencies = [r['latency'] for r in results]
        ip_addresses = set(r['ip_address'] for r in results)
        
        summary = {
            'Average Download Speed': f"{sum(download_speeds)/len(download_speeds):.2f} Mbps",
            'Average Upload Speed': f"{sum(upload_speeds)/len(upload_speeds):.2f} Mbps",
            'Average Latency': f"{sum(latencies)/len(latencies):.2f} ms",
            'IP Changes': 'Yes' if len(ip_addresses) > 1 else 'No',
            'Slow Download Incidents': sum(1 for speed in download_speeds if speed < DOWNLOAD_THRESHOLD),
            'Slow Upload Incidents': sum(1 for speed in upload_speeds if speed < UPLOAD_THRESHOLD)
        }
        
        # Get incidents
        incidents = []
        for r in results:
            if r['download_speed'] < DOWNLOAD_THRESHOLD or r['upload_speed'] < UPLOAD_THRESHOLD:
                incidents.append([
                    r['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    f"{r['download_speed']:.2f} Mbps" if r['download_speed'] < DOWNLOAD_THRESHOLD else "OK",
                    f"{r['upload_speed']:.2f} Mbps" if r['upload_speed'] < UPLOAD_THRESHOLD else "OK"
                ])
        
        return {
            'summary': summary,
            'incidents': incidents,
            'raw_data': [
                [r['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                 r['download_speed'],
                 r['upload_speed'],
                 r['latency'],
                 r['ip_address']] for r in results
            ]
        }
    except Exception as e:
        logging.error(f"Error getting report data: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def send_email_report(hours):
    """Send an email report with the network monitoring data."""
    try:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=hours)
        
        data = get_report_data(hours)
        if not data:
            logging.warning(f"No data available for the past {hours} hours")
            return
        
        # Generate PDF and CSV reports
        pdf_filename = f'network_report_{hours}h.pdf'
        csv_filename = f'network_data_{hours}h.csv'
        
        generate_pdf_report(data, start_time, end_time, pdf_filename)
        generate_csv_report(data['raw_data'], csv_filename)
        
        # Create email
        msg = MIMEMultipart()
        msg['Subject'] = 'Network Monitoring Report'
        msg['From'] = SMTP_USER
        msg['To'] = EMAIL_RECIPIENT
        
        # Email body
        body = f"""Network Monitoring Report
Report Period: {start_time.strftime('%m/%d/%Y, %I:%M:%S %p')} - {end_time.strftime('%m/%d/%Y, %I:%M:%S %p')}

Summary:
"""
        for key, value in data['summary'].items():
            body += f"• {key}: {value}\n"
        
        msg.attach(MIMEText(body))
        
        # Attach PDF
        with open(pdf_filename, 'rb') as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
            msg.attach(pdf_attachment)
        
        # Attach CSV
        with open(csv_filename, 'rb') as f:
            csv_attachment = MIMEApplication(f.read(), _subtype='csv')
            csv_attachment.add_header('Content-Disposition', 'attachment', filename=csv_filename)
            msg.attach(csv_attachment)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logging.info(f"Email report sent successfully for past {hours} hours")
        
        # Clean up temporary files
        os.remove(pdf_filename)
        os.remove(csv_filename)
        
    except Exception as e:
        logging.error(f"Error sending email report: {e}")

def perform_network_check():
    """Perform a network check and save the results."""
    download_speed, upload_speed, latency = perform_speed_test()
    ip_address = get_public_ip()
    
    if all(v is not None for v in [download_speed, upload_speed, latency, ip_address]):
        save_check_results(download_speed, upload_speed, latency, ip_address)
        logging.info(f"Network check completed - Download: {download_speed:.2f} Mbps, Upload: {upload_speed:.2f} Mbps, Latency: {latency:.2f} ms")
    else:
        logging.error("Network check failed - some measurements were not available")

def main():
    """Main function to run the network monitoring script."""
    # Initialize database
    init_db()
    
    # Schedule tasks
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(perform_network_check)
    schedule.every(SUMMARY_INTERVAL_HOURS).hours.do(lambda: send_email_report(SUMMARY_INTERVAL_HOURS))
    schedule.every().day.at(DAILY_REPORT_TIME).do(lambda: send_email_report(24))
    
    # Perform initial check
    perform_network_check()
    
    # Main loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)  # Wait a minute before retrying

if __name__ == "__main__":
    main() 