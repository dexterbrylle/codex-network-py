import logging
import speedtest
import requests


def perform_speed_test():
    """Perform a speed test and return the results."""
    try:
        st = speedtest.Speedtest()
        st.get_best_server()

        download_speed = st.download() / 1_000_000
        upload_speed = st.upload(pre_allocate=False) / 1_000_000
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
