import logging
import psycopg2
from psycopg2.extras import DictCursor
from monitor.config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

def get_connection(database=None):
    """Get a psycopg2 connection. If database is None, uses DB_NAME."""
    if ':' in DB_HOST:
        host, port = DB_HOST.split(':')
        port = int(port)
    else:
        host = DB_HOST
        port = 5432

    conn = psycopg2.connect(
        host=host,
        port=port,
        database=database or DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn


def init_db():
    """Initialize the database and create tables if they don't exist."""
    try:
        conn = get_connection(database='postgres')
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE {DB_NAME}')
            logging.info(f"Database {DB_NAME} created successfully")

        cur.close()
        conn.close()

        conn = get_connection()
        cur = conn.cursor()

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

        cur.execute("""
            ALTER TABLE network_checks
            ADD COLUMN IF NOT EXISTS below_threshold BOOLEAN DEFAULT FALSE;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sla_breach_episodes (
                id SERIAL PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                worst_download_speed FLOAT,
                worst_upload_speed FLOAT,
                violating_check_count INT NOT NULL,
                total_check_count INT NOT NULL,
                violation_pct FLOAT NOT NULL
            );
        """)

        conn.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Database initialization error: {e}")
        raise
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def save_check_results(download_speed, upload_speed, latency, ip_address, below_threshold=False):
    """Save a network check result to the database."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO network_checks (timestamp, download_speed, upload_speed, latency, ip_address, below_threshold)
            VALUES (NOW(), %s, %s, %s, %s, %s)
        """, (download_speed, upload_speed, latency, ip_address, below_threshold))

        conn.commit()
        logging.info("Results saved to database successfully")
    except Exception as e:
        logging.error(f"Database save error: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def get_recent_checks(hours=24):
    """Get checks from the last N hours for SLA computation."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute("""
            SELECT *
            FROM network_checks
            WHERE timestamp >= NOW() - interval %s hour
            ORDER BY timestamp ASC
        """, (hours,))

        results = cur.fetchall()
        return [dict(r) for r in results]
    except Exception as e:
        logging.error(f"Error getting recent checks: {e}")
        return []
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def get_check_count(hours=24):
    """Get the number of checks in the specified window."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*)
            FROM network_checks
            WHERE timestamp >= NOW() - interval %s hour
        """, (hours,))

        count = cur.fetchone()[0]
        return count
    except Exception as e:
        logging.error(f"Error getting check count: {e}")
        return 0
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def get_report_data(hours):
    """Get report data for the specified number of hours."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute("""
            SELECT *
            FROM network_checks
            WHERE timestamp >= NOW() - interval %s hour
            ORDER BY timestamp DESC
        """, (hours,))

        results = cur.fetchall()

        if not results:
            return None

        return [dict(r) for r in results]
    except Exception as e:
        logging.error(f"Error getting report data: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def start_breach_episode(violating_count, total_count, violation_pct, worst_down, worst_up):
    """Start a new breach episode. Returns the episode id."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO sla_breach_episodes
                (started_at, worst_download_speed, worst_upload_speed,
                 violating_check_count, total_check_count, violation_pct)
            VALUES (NOW(), %s, %s, %s, %s, %s)
            RETURNING id
        """, (worst_down, worst_up, violating_count, total_count, violation_pct))

        episode_id = cur.fetchone()[0]
        conn.commit()
        logging.info(f"Breach episode {episode_id} started")
        return episode_id
    except Exception as e:
        logging.error(f"Error starting breach episode: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def update_breach_episode(episode_id, worst_down, worst_up, violating_count, total_count, violation_pct):
    """Update an active breach episode with running stats."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE sla_breach_episodes
            SET worst_download_speed = LEAST(worst_download_speed, %s),
                worst_upload_speed = LEAST(worst_upload_speed, %s),
                violating_check_count = %s,
                total_check_count = %s,
                violation_pct = %s
            WHERE id = %s AND ended_at IS NULL
        """, (worst_down, worst_up, violating_count, total_count, violation_pct, episode_id))

        conn.commit()
    except Exception as e:
        logging.error(f"Error updating breach episode: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def end_breach_episode(episode_id):
    """Close an active breach episode."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE sla_breach_episodes
            SET ended_at = NOW()
            WHERE id = %s AND ended_at IS NULL
        """, (episode_id,))

        conn.commit()
        logging.info(f"Breach episode {episode_id} ended")
    except Exception as e:
        logging.error(f"Error ending breach episode: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def get_active_breach_episode():
    """Get the currently active breach episode, or None."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute("""
            SELECT *
            FROM sla_breach_episodes
            WHERE ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """)

        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"Error getting active breach episode: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
