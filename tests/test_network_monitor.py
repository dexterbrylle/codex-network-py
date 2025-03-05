import os
import pytest
import datetime
from unittest.mock import Mock, patch
import psycopg2
from psycopg2.extras import DictCursor

# Import the functions we want to test
from network_monitor import (
    init_db,
    perform_speed_test,
    get_public_ip,
    save_check_results,
    get_report_data,
    perform_network_check
)

@pytest.fixture(scope="session")
def test_db():
    """Create a test database and clean it up after tests."""
    # Parse host and port
    db_host = os.getenv('DB_HOST', 'localhost:5432')
    if ':' in db_host:
        host, port = db_host.split(':')
        port = int(port)
    else:
        host, port = db_host, 5432

    # Connect to postgres database
    conn = psycopg2.connect(
        host=host,
        port=port,
        database='postgres',
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Create test database
    db_name = os.getenv('DB_NAME')
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.execute(f"CREATE DATABASE {db_name}")
    
    cur.close()
    conn.close()

    # Initialize the test database
    init_db()

    yield

    # Cleanup: drop test database
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
    with patch('speedtest.Speedtest') as mock_speedtest:
        instance = mock_speedtest.return_value
        instance.download.return_value = 100_000_000  # 100 Mbps
        instance.upload.return_value = 50_000_000    # 50 Mbps
        instance.results.ping = 20                   # 20 ms
        yield instance

@pytest.fixture
def mock_requests():
    """Mock requests for IP address check."""
    with patch('requests.get') as mock_get:
        mock_get.return_value.text = '1.2.3.4\n'
        yield mock_get

def test_perform_speed_test(mock_speedtest):
    """Test speed test functionality."""
    download, upload, latency = perform_speed_test()
    
    assert download == 100.0  # 100 Mbps
    assert upload == 50.0     # 50 Mbps
    assert latency == 20      # 20 ms
    
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
    # Save test data
    save_check_results(100.0, 50.0, 20.0, '1.2.3.4')
    
    # Get report data for the last hour
    report_data = get_report_data(1)
    
    assert report_data is not None
    assert float(report_data['summary']['Average Download Speed'].split()[0]) == 100.0
    assert float(report_data['summary']['Average Upload Speed'].split()[0]) == 50.0
    assert float(report_data['summary']['Average Latency'].split()[0]) == 20.0
    assert report_data['summary']['IP Changes'] == 'No'

@patch('network_monitor.perform_speed_test')
@patch('network_monitor.get_public_ip')
@patch('network_monitor.save_check_results')
def test_perform_network_check(mock_save, mock_get_ip, mock_speed_test):
    """Test the complete network check process."""
    # Setup mocks
    mock_speed_test.return_value = (100.0, 50.0, 20.0)
    mock_get_ip.return_value = '1.2.3.4'
    
    # Perform check
    perform_network_check()
    
    # Verify all steps were called
    mock_speed_test.assert_called_once()
    mock_get_ip.assert_called_once()
    mock_save.assert_called_once_with(100.0, 50.0, 20.0, '1.2.3.4')

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
    ((100.0, 50.0, 20.0, '1.2.3.4'), True),  # Valid input
    ((None, 50.0, 20.0, '1.2.3.4'), False),  # Missing download speed
    ((100.0, None, 20.0, '1.2.3.4'), False), # Missing upload speed
    ((100.0, 50.0, None, '1.2.3.4'), False), # Missing latency
    ((100.0, 50.0, 20.0, None), False),      # Missing IP
])
def test_network_check_validation(test_input, expected, monkeypatch):
    """Test validation of network check results."""
    # Mock the internal functions
    monkeypatch.setattr('network_monitor.perform_speed_test', lambda: test_input[:3])
    monkeypatch.setattr('network_monitor.get_public_ip', lambda: test_input[3])
    monkeypatch.setattr('network_monitor.save_check_results', lambda *args: None)
    
    # Capture logging output
    with patch('network_monitor.logging.error') as mock_log_error, \
         patch('network_monitor.logging.info') as mock_log_info:
        
        perform_network_check()
        
        if expected:
            mock_log_info.assert_called_once()
            mock_log_error.assert_not_called()
        else:
            mock_log_error.assert_called_once()
            mock_log_info.assert_not_called() 