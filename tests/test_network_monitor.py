import os
import pytest
import datetime
from unittest.mock import Mock, patch
import psycopg2
from psycopg2.extras import DictCursor

from monitor.speedtest import perform_speed_test, get_public_ip
from monitor.db import save_check_results, get_report_data, init_db
from monitor.sla import evaluate_check, check_sla_breach

@pytest.fixture(scope="session")
def test_db():
    """Create a test database and clean it up after tests."""
    db_host = os.getenv('DB_HOST', 'localhost:5432')
    if ':' in db_host:
        host, port = db_host.split(':')
        port = int(port)
    else:
        host, port = db_host, 5432

    conn = psycopg2.connect(
        host=host,
        port=port,
        database='postgres',
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    conn.autocommit = True
    cur = conn.cursor()

    db_name = os.getenv('DB_NAME', 'network_monitor')
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.execute(f"CREATE DATABASE {db_name}")

    cur.close()
    conn.close()

    init_db()

    yield

    conn = psycopg2.connect(
        host=host,
        port=port,
        database='postgres',
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.close()
    conn.close()


@pytest.fixture
def mock_speedtest():
    """Mock speedtest results."""
    with patch('monitor.speedtest.speedtest.Speedtest') as mock_st:
        instance = mock_st.return_value
        instance.download.return_value = 100_000_000
        instance.upload.return_value = 50_000_000
        instance.results.ping = 20
        yield instance


@pytest.fixture
def mock_requests():
    """Mock requests for IP address check."""
    with patch('monitor.speedtest.requests.get') as mock_get:
        mock_get.return_value.text = '1.2.3.4\n'
        yield mock_get


def test_perform_speed_test(mock_speedtest):
    """Test speed test functionality."""
    download, upload, latency = perform_speed_test()

    assert download == 100.0
    assert upload == 50.0
    assert latency == 20

    mock_speedtest.get_best_server.assert_called_once()
    mock_speedtest.download.assert_called_once()
    mock_speedtest.upload.assert_called_once()


def test_get_public_ip(mock_requests):
    """Test IP address retrieval."""
    ip = get_public_ip()
    assert ip == '1.2.3.4'
    mock_requests.assert_called_once_with('http://ipinfo.io/ip')


def test_save_and_get_results(test_db):
    """Test saving and retrieving results from database."""
    save_check_results(100.0, 50.0, 20.0, '1.2.3.4')

    report_data = get_report_data(1)

    assert report_data is not None, "Should return data"
    assert len(report_data) > 0, "Should have at least one row"

    row = report_data[0]
    assert row['download_speed'] == 100.0
    assert row['upload_speed'] == 50.0
    assert row['latency'] == 20.0
    assert row['ip_address'] == '1.2.3.4'


@patch('monitor.scheduler.perform_speed_test')
@patch('monitor.scheduler.get_public_ip')
@patch('monitor.scheduler.save_check_results')
def test_perform_network_check(mock_save, mock_get_ip, mock_speed_test_fn):
    """Test the complete network check process."""
    from monitor.scheduler import perform_network_check

    mock_speed_test_fn.return_value = (100.0, 50.0, 20.0)
    mock_get_ip.return_value = '1.2.3.4'

    # Also patch SLA functions so we don't hit DB during this unit test
    with patch('monitor.scheduler.check_sla_breach'), \
         patch('monitor.scheduler.handle_breach_state'):
        perform_network_check()

    mock_speed_test_fn.assert_called_once()
    mock_get_ip.assert_called_once()
    mock_save.assert_called_once_with(100.0, 50.0, 20.0, '1.2.3.4', below_threshold=True)


def test_failed_speed_test(mock_speedtest):
    """Test handling of failed speed test."""
    mock_speedtest.download.side_effect = Exception("Network error")

    download, upload, latency = perform_speed_test()
    assert all(v is None for v in [download, upload, latency])


def test_failed_ip_check(mock_requests):
    """Test handling of failed IP address check."""
    mock_requests.side_effect = Exception("Connection error")

    ip = get_public_ip()
    assert ip is None


@pytest.mark.parametrize("test_input,expected", [
    ((100.0, 50.0, 20.0, '1.2.3.4'), True),
    ((None, 50.0, 20.0, '1.2.3.4'), False),
    ((100.0, None, 20.0, '1.2.3.4'), False),
    ((100.0, 50.0, None, '1.2.3.4'), False),
    ((100.0, 50.0, 20.0, None), False),
])
def test_network_check_validation(test_input, expected, monkeypatch):
    """Test validation of network check results."""
    from monitor.scheduler import perform_network_check

    monkeypatch.setattr('monitor.scheduler.perform_speed_test', lambda: test_input[:3])
    monkeypatch.setattr('monitor.scheduler.get_public_ip', lambda: test_input[3])
    monkeypatch.setattr('monitor.scheduler.save_check_results', lambda *a, **kw: None)
    monkeypatch.setattr('monitor.scheduler.check_sla_breach', lambda db: {"status": "ok", "violating_count": 0, "total_count": 48, "violation_pct": 0, "worst_download": 100, "worst_upload": 50, "breached_checks": []})
    monkeypatch.setattr('monitor.scheduler.handle_breach_state', lambda *a: None)

    with patch('monitor.scheduler.logger.error') as mock_log_error, \
         patch('monitor.scheduler.logger.info') as mock_log_info:

        perform_network_check()

        if expected:
            mock_log_info.assert_called()
            mock_log_error.assert_not_called()
        else:
            mock_log_error.assert_called_once()
            mock_log_info.assert_not_called()


# --- SLA-specific tests ---

def test_evaluate_check_normal():
    """Normal speeds should not be below threshold."""
    assert evaluate_check(500.0, 500.0) is False
    assert evaluate_check(151.0, 151.0) is False


def test_evaluate_check_below_threshold():
    """Speeds below 150 Mbps should evaluate True."""
    assert evaluate_check(149.0, 500.0) is True
    assert evaluate_check(500.0, 149.0) is True
    assert evaluate_check(100.0, 100.0) is True


def test_evaluate_check_none_values():
    """None values (failed tests) should return False — conservative."""
    assert evaluate_check(None, 500.0) is False
    assert evaluate_check(500.0, None) is False
    assert evaluate_check(None, None) is False


class FakeDB:
    """Minimal fake DB for testing SLA logic."""
    def __init__(self, checks=None, episode=None):
        self.checks = checks or []
        self.episode = episode
        self.started_episode_id = None
        self.last_update = None
        self.ended = False

    def get_recent_checks(self, hours=24):
        return self.checks

    def get_check_count(self, hours=24):
        return len(self.checks)

    def get_active_breach_episode(self):
        return self.episode

    def start_breach_episode(self, violating_count, total_count, violation_pct, worst_down, worst_up):
        self.started_episode_id = 1
        self.episode = {"id": 1}
        return 1

    def update_breach_episode(self, episode_id, worst_down, worst_up, violating_count, total_count, violation_pct):
        self.last_update = (episode_id, worst_down, worst_up, violating_count, total_count, violation_pct)

    def end_breach_episode(self, episode_id):
        self.ended = True
        self.episode = None


def test_sla_insufficient_data():
    """Fewer than 48 checks should return insufficient_data."""
    fake_db = FakeDB(checks=[{"download_speed": 100, "upload_speed": 100}] * 10)
    result = check_sla_breach(fake_db)
    assert result["status"] == "insufficient_data"
    assert result["check_count"] == 10


def test_sla_no_breach():
    """All speeds above threshold should return ok."""
    checks = [{"download_speed": 500.0, "upload_speed": 500.0}] * 48
    fake_db = FakeDB(checks=checks)
    result = check_sla_breach(fake_db)
    assert result["status"] == "ok"
    assert result["violating_count"] == 0


def test_sla_breach_detected():
    """More than 9 checks below 150 should trigger breach."""
    checks = [{"download_speed": 500.0, "upload_speed": 500.0}] * 38
    checks += [{"download_speed": 100.0, "upload_speed": 100.0}] * 10
    fake_db = FakeDB(checks=checks)
    result = check_sla_breach(fake_db)
    assert result["status"] == "breach"
    assert result["violating_count"] == 10
    assert result["total_count"] == 48
    assert result["violation_pct"] == round((10/48)*100, 1)


def test_sla_breach_exactly_boundary():
    """9 checks below threshold: no breach. 10 checks: breach."""
    checks = [{"download_speed": 500.0, "upload_speed": 500.0}] * 39
    checks += [{"download_speed": 100.0, "upload_speed": 100.0}] * 9
    result = check_sla_breach(FakeDB(checks=checks))
    assert result["status"] == "ok"

    checks = [{"download_speed": 500.0, "upload_speed": 500.0}] * 38
    checks += [{"download_speed": 100.0, "upload_speed": 100.0}] * 10
    result = check_sla_breach(FakeDB(checks=checks))
    assert result["status"] == "breach"


def test_sla_null_in_total():
    """NULL speed checks count in total but not as violating."""
    checks = [{"download_speed": 500.0, "upload_speed": 500.0}] * 38
    checks += [{"download_speed": None, "upload_speed": None}] * 5
    checks += [{"download_speed": 100.0, "upload_speed": 100.0}] * 5
    fake_db = FakeDB(checks=checks)
    result = check_sla_breach(fake_db)
    assert result["total_count"] == 48
    assert result["violating_count"] == 5
    assert result["status"] == "ok"


@patch('monitor.alerts.send_discord_alert')
@patch('monitor.alerts.send_breach_email')
def test_handle_breach_state_new_breach(mock_email, mock_discord):
    """New breach with no active episode: start episode + fire alerts."""
    from monitor.sla import handle_breach_state

    fake_db = FakeDB(episode=None)
    result = {
        "status": "breach",
        "violating_count": 12,
        "total_count": 48,
        "violation_pct": 25.0,
        "worst_download": 50.0,
        "worst_upload": 40.0,
        "breached_checks": []
    }

    handle_breach_state(result, fake_db)
    assert fake_db.started_episode_id is not None
    mock_discord.assert_called_once()
    mock_email.assert_called_once()


@patch('monitor.alerts.send_discord_alert')
@patch('monitor.alerts.send_breach_email')
def test_handle_breach_state_active_episode(mock_email, mock_discord):
    """Breach with active episode: update, no new alerts."""
    from monitor.sla import handle_breach_state

    fake_db = FakeDB(episode={"id": 1})
    result = {
        "status": "breach",
        "violating_count": 15,
        "total_count": 48,
        "violation_pct": 31.2,
        "worst_download": 30.0,
        "worst_upload": 25.0,
        "breached_checks": []
    }

    handle_breach_state(result, fake_db)
    assert fake_db.last_update is not None
    mock_discord.assert_not_called()
    mock_email.assert_not_called()


@patch('monitor.alerts.send_discord_alert')
@patch('monitor.alerts.send_breach_email')
def test_handle_breach_state_resolved(mock_email, mock_discord):
    """Breach resolved: end episode, no alerts."""
    from monitor.sla import handle_breach_state

    fake_db = FakeDB(episode={"id": 1})
    result = {
        "status": "ok",
        "violating_count": 5,
        "total_count": 48,
        "violation_pct": 10.4,
        "worst_download": 200.0,
        "worst_upload": 200.0,
        "breached_checks": []
    }

    handle_breach_state(result, fake_db)
    assert fake_db.ended is True
    mock_discord.assert_not_called()
    mock_email.assert_not_called()
