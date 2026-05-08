import os
import pytest
from unittest.mock import patch, Mock, MagicMock
import datetime
from monitor.reports import send_email_report


@pytest.fixture
def mock_get_report_data():
    """Mock report data."""
    return {
        'summary': {
            'Average Download Speed': '100.00 Mbps',
            'Average Upload Speed': '50.00 Mbps',
            'Average Latency': '20.00 ms',
            'IP Changes': 'No',
            'Slow Download Incidents': 0,
            'Slow Upload Incidents': 0
        },
        'incidents': [],
        'raw_data': [
            ['2024-03-05 15:00:00', 100.0, 50.0, 20.0, '1.2.3.4']
        ]
    }


@pytest.fixture
def mock_smtp():
    """Mock SMTP connection."""
    with patch('monitor.reports.smtplib.SMTP') as mock_smtp:
        instance = mock_smtp.return_value
        instance.__enter__.return_value = instance
        yield instance


@patch('monitor.reports.get_report_data')
def test_send_email_report_success(mock_get_data, mock_smtp, mock_get_report_data):
    """Test successful email report sending."""
    mock_get_data.return_value = mock_get_report_data

    send_email_report(6)

    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once()
    mock_smtp.send_message.assert_called_once()

    sent_email = mock_smtp.send_message.call_args[0][0]
    assert 'Network Monitoring Report' in sent_email['Subject']
    assert os.getenv('SMTP_USER') == sent_email['From']
    assert os.getenv('EMAIL_RECIPIENT') == sent_email['To']


@patch('monitor.reports.get_report_data')
def test_send_email_report_no_data(mock_get_data, mock_smtp):
    """Test email report handling when no data is available."""
    mock_get_data.return_value = None

    with patch('monitor.reports.logger.warning') as mock_log_warning:
        send_email_report(6)
        mock_log_warning.assert_called_once()
        mock_smtp.assert_not_called()


@patch('monitor.reports.get_report_data')
def test_send_email_report_smtp_error(mock_get_data, mock_smtp, mock_get_report_data):
    """Test email report handling when SMTP fails."""
    mock_get_data.return_value = mock_get_report_data
    mock_smtp.send_message.side_effect = Exception("SMTP error")

    with patch('monitor.reports.logger.error') as mock_log_error:
        send_email_report(6)
        mock_log_error.assert_called_once()


@patch('monitor.reports.get_report_data')
def test_email_attachments(mock_get_data, mock_smtp, mock_get_report_data):
    """Test that email attachments are properly generated and attached."""
    mock_get_data.return_value = mock_get_report_data

    send_email_report(6)

    sent_email = mock_smtp.send_message.call_args[0][0]

    attachment_names = [part.get_filename() for part in sent_email.get_payload() if part.get_filename()]
    assert any(name.endswith('.pdf') for name in attachment_names)
    assert any(name.endswith('.csv') for name in attachment_names)
