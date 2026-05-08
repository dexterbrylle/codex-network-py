import logging
import time

import schedule

from monitor.config import CHECK_INTERVAL_MINUTES, SUMMARY_INTERVAL_HOURS, DAILY_REPORT_TIME
from monitor.speedtest import perform_speed_test, get_public_ip
from monitor.db import save_check_results, get_recent_checks
from monitor.sla import evaluate_check, check_sla_breach, handle_breach_state
from monitor.reports import send_email_report

logger = logging.getLogger(__name__)


def perform_network_check():
    """Run a speed test, save results, and evaluate SLA."""
    download_speed, upload_speed, latency = perform_speed_test()
    ip_address = get_public_ip()

    if all(v is not None for v in [download_speed, upload_speed, latency, ip_address]):
        below = evaluate_check(download_speed, upload_speed)
        save_check_results(download_speed, upload_speed, latency, ip_address, below_threshold=below)

        logger.info(f"Network check completed - Download: {download_speed:.2f} Mbps, "
                    f"Upload: {upload_speed:.2f} Mbps, Latency: {latency:.2f} ms")

        import monitor.db as db
        result = check_sla_breach(db)
        handle_breach_state(result, db)
    else:
        logger.error("Network check failed — some measurements were not available")


def setup_schedule():
    """Configure scheduled tasks."""
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(perform_network_check)
    schedule.every(SUMMARY_INTERVAL_HOURS).hours.do(lambda: send_email_report(SUMMARY_INTERVAL_HOURS))
    schedule.every().day.at(DAILY_REPORT_TIME).do(lambda: send_email_report(24))


def run_loop():
    """Main scheduling loop."""
    perform_network_check()

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)
