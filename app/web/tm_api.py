"""API Blueprint for Tampermonkey Browser Agent Communication.

Provides endpoints for the userscript running on Facebook Marketplace to poll jobs,
report progress/heartbeat, and submit scraped listings back to the dashboard.
"""
from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Optional

from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import login_required
from sqlalchemy import desc, select

from ..db import db
from ..extensions import csrf
from ..models import SearchConfiguration, TmAgent, TmJob, TmJobStatus, utcnow
from ..services import settings_store as st
from ..services import tm_service

bp = Blueprint("tm_api", __name__, url_prefix="/api/tm")

# Exempt the entire Tampermonkey blueprint from CSRF so cross-origin GM_xmlhttpRequest can communicate
csrf.exempt(bp)


def _verify_token() -> bool:
    """Verify bearer token against configured TM_API_TOKEN or DB setting."""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "token" in request.args:
        token = request.args.get("token", "").strip()

    if not token:
        return False

    app_cfg = current_app.config.get("APP_CONFIG")
    expected_token = (app_cfg.TM_API_TOKEN if app_cfg else "") or "fb-marketplace-tm-token-secret"

    # Also check if user customized token in database settings
    db_token = st.get(db, "tm_api_token")
    if db_token:
        expected_token = db_token

    return hmac.compare_digest(token, expected_token)


@bp.before_request
def check_auth():
    """Authenticate API requests except for public script download or internal admin calls."""
    # Allow downloading the script if logged in or with valid token
    if request.endpoint == "tm_api.get_user_script":
        return None

    # Admin endpoints check Flask-Login instead of token
    if request.path.startswith("/api/tm/admin"):
        return None

    if not _verify_token():
        return jsonify({"error": "Unauthorized. Invalid or missing Bearer token."}), 401


# --------------------------------------------------------------------------
# Tampermonkey Agent Endpoints (authenticated via Bearer token)
# --------------------------------------------------------------------------

@bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "default_browser_agent")
    res = tm_service.record_heartbeat(db, agent_id, data)
    return jsonify(res)


@bp.route("/next-job", methods=["GET"])
def next_job():
    agent_id = request.args.get("agent_id", "default_browser_agent")
    job = tm_service.claim_next_job(db, agent_id)
    return jsonify({"job": job})


@bp.route("/jobs/<int:job_id>/progress", methods=["POST"])
def job_progress(job_id: int):
    data = request.get_json(silent=True) or {}
    step = data.get("step", "working")
    success = tm_service.update_progress(db, job_id, step)
    if not success:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"ok": True})


@bp.route("/jobs/<int:job_id>/result", methods=["POST"])
def job_result(job_id: int):
    data = request.get_json(silent=True) or {}
    app_cfg = current_app.config.get("APP_CONFIG")
    try:
        summary = tm_service.ingest_job_results(db, app_cfg, job_id, data)
        return jsonify({"ok": True, "summary": summary})
    except Exception as e:
        current_app.logger.exception("Error ingesting job %s results", job_id)
        tm_service.fail_job(db, job_id, str(e), step="server_ingestion")
        return jsonify({"error": str(e)}), 500


@bp.route("/jobs/<int:job_id>/fail", methods=["POST"])
def job_fail(job_id: int):
    data = request.get_json(silent=True) or {}
    error = data.get("error", "Unknown client error")
    step = data.get("step")
    tm_service.fail_job(db, job_id, error, step=step)
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Dynamic Userscript Distribution
# --------------------------------------------------------------------------

@bp.route("/script.user.js", methods=["GET"])
def get_user_script():
    """Dynamically serve the Tampermonkey Userscript with host, port and token baked in."""
    app_cfg = current_app.config.get("APP_CONFIG")
    token = st.get(db, "tm_api_token") or getattr(app_cfg, "TM_API_TOKEN", "fb-marketplace-tm-token-secret")
    
    # Prefer incoming Host header or config
    host_url = request.host_url.rstrip("/")
    api_base = f"{host_url}/api/tm"

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "fb_marketplace_agent.user.js"
    if not script_path.exists():
        return Response("// Userscript file not found on server", status=404, mimetype="text/javascript")

    content = script_path.read_text(encoding="utf-8")
    content = content.replace("%%API_BASE%%", api_base)
    content = content.replace("%%API_TOKEN%%", token)

    return Response(
        content,
        mimetype="application/javascript",
        headers={
            "Content-Disposition": "inline; filename=fb_marketplace_agent.user.js",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# --------------------------------------------------------------------------
# Dashboard Admin Endpoints (Session login required)
# --------------------------------------------------------------------------

@bp.route("/admin/status", methods=["GET"])
@login_required
def admin_status():
    """Retrieve Tampermonkey agent status and recent jobs for the dashboard."""
    agents = db.scalars(select(TmAgent).order_by(desc(TmAgent.last_heartbeat_at))).all()
    recent_jobs = db.scalars(select(TmJob).order_by(desc(TmJob.created_at)).limit(10)).all()
    is_paused = st.get(db, "tm_agent_paused")
    token = st.get(db, "tm_api_token") or current_app.config["APP_CONFIG"].TM_API_TOKEN

    now = utcnow()
    agent_data = []
    for a in agents:
        online = bool(a.last_heartbeat_at and (now - a.last_heartbeat_at).total_seconds() < 45)
        agent_data.append({
            "id": a.id,
            "agent_id": a.agent_id,
            "display_name": a.display_name,
            "status": a.status if online else "offline",
            "online": online,
            "fb_user": a.fb_user,
            "current_url": a.current_url,
            "last_heartbeat_at": a.last_heartbeat_at.isoformat() if a.last_heartbeat_at else None,
            "current_job_id": a.current_job_id,
        })

    job_data = []
    for j in recent_jobs:
        job_data.append({
            "id": j.id,
            "search_id": j.search_id,
            "search_name": j.search.name if j.search else "Search",
            "status": j.status,
            "agent_id": j.agent_id,
            "progress_step": j.progress_step,
            "created_at": j.created_at.strftime("%H:%M:%S") if j.created_at else None,
            "finished_at": j.finished_at.strftime("%H:%M:%S") if j.finished_at else None,
            "error": j.error,
        })

    return jsonify({
        "is_paused": is_paused,
        "api_token": token,
        "agents": agent_data,
        "recent_jobs": job_data,
        "active_agent_count": sum(1 for a in agent_data if a["online"]),
    })


@bp.route("/admin/enqueue/<int:search_id>", methods=["POST"])
@login_required
def admin_enqueue(search_id: int):
    """Manually enqueue a search job for Tampermonkey from the dashboard."""
    job = tm_service.enqueue_job(db, search_id, trigger="manual", force=True)
    if not job:
        return jsonify({"ok": False, "error": "Search already has an active job or was deleted"}), 400
    return jsonify({"ok": True, "job_id": job.id})


@bp.route("/admin/toggle-pause", methods=["POST"])
@login_required
def admin_toggle_pause():
    """Toggle the global kill-switch for Tampermonkey agents."""
    current = st.get(db, "tm_agent_paused")
    st.set_value(db, "tm_agent_paused", not current)
    db.commit()
    return jsonify({"ok": True, "is_paused": not current})
