import logging
from monitor.config import (
    ISP_PLAN_THRESHOLD, ISP_PLAN_UPLOAD_THRESHOLD,
    SLA_WINDOW_HOURS, SLA_VIOLATION_MAX,
    ISP_PLAN_NAME
)

logger = logging.getLogger(__name__)


def evaluate_check(download, upload):
    """Returns True if this single check is below the ISP contractual minimum.
    Returns False if either value is None (failed test = conservative, not a violation).
    """
    if download is None or upload is None:
        return False

    return download < ISP_PLAN_THRESHOLD or upload < ISP_PLAN_UPLOAD_THRESHOLD


def check_sla_breach(db):
    """Evaluate SLA breach status from recent checks.
    Returns dict with status, stats, and breached check data.
    """
    recent = db.get_recent_checks(hours=SLA_WINDOW_HOURS)
    total_count = len(recent)

    if total_count < 48:
        logger.info(f"SLA evaluation deferred — insufficient data ({total_count}/48 checks)")
        return {"status": "insufficient_data", "check_count": total_count}

    violating_count = 0
    worst_download = float('inf')
    worst_upload = float('inf')
    breached_checks = []

    for check in recent:
        dl = check['download_speed']
        ul = check['upload_speed']

        if evaluate_check(dl, ul):
            violating_count += 1
            if dl is not None and dl < worst_download:
                worst_download = dl
            if ul is not None and ul < worst_upload:
                worst_upload = ul
            breached_checks.append(check)

    if worst_download == float('inf'):
        worst_download = None
    if worst_upload == float('inf'):
        worst_upload = None

    violation_pct = (violating_count / total_count) * 100
    is_breach = violating_count > SLA_VIOLATION_MAX

    logger.info(f"SLA eval: {violating_count}/{total_count} below threshold ({violation_pct:.1f}%) — "
                f"{'BREACH' if is_breach else 'OK'}")

    return {
        "status": "breach" if is_breach else "ok",
        "violating_count": violating_count,
        "total_count": total_count,
        "violation_pct": round(violation_pct, 1),
        "worst_download": worst_download,
        "worst_upload": worst_upload,
        "breached_checks": breached_checks
    }


def handle_breach_state(result, db):
    """State machine for breach episodes. Calls alert functions when appropriate."""
    if result["status"] == "insufficient_data":
        return

    active = db.get_active_breach_episode()

    if result["status"] == "breach" and not active:
        episode_id = db.start_breach_episode(
            violating_count=result["violating_count"],
            total_count=result["total_count"],
            violation_pct=result["violation_pct"],
            worst_down=result["worst_download"],
            worst_up=result["worst_upload"]
        )

        if episode_id:
            from monitor.alerts import send_discord_alert, send_breach_email
            send_discord_alert(result)
            send_breach_email(result)

            logger.info(f"Breach alert fired — episode {episode_id}")

    elif result["status"] == "breach" and active:
        db.update_breach_episode(
            episode_id=active["id"],
            worst_down=result["worst_download"],
            worst_up=result["worst_upload"],
            violating_count=result["violating_count"],
            total_count=result["total_count"],
            violation_pct=result["violation_pct"]
        )

    elif result["status"] == "ok" and active:
        db.end_breach_episode(active["id"])
        logger.info(f"Breach resolved — episode {active['id']} closed")
