"""Account management: validation, persistent profile directories, save,
export of non-sensitive metadata."""
from __future__ import annotations

import json
import pickle
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Config
from ..models import Account, SearchConfiguration, SearchStatus, SessionStatus, utcnow

NAME_RE = re.compile(r"^[\w .@()\-]{2,80}$", re.UNICODE)

# Only these fields are ever exported. No passwords, cookies, tokens or
# profile contents exist in the account record, and none are exported.
EXPORT_FIELDS = ("id", "display_name", "profile_dir", "enabled", "session_status", "daily_run_limit",
                 "notes", "last_success_at", "created_at", "updated_at")


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def resolve_profile_dir(cfg: Config, account: Account) -> Path:
    p = Path(account.profile_dir)
    return p if p.is_absolute() else (cfg.BASE_DIR / p)


def _relative_profile_path(cfg: Config, path: Path) -> str:
    try:
        return path.resolve().relative_to(cfg.BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def validate_fields(session: Session, display_name: str, daily_run_limit: Any, notes: str | None,
                    account_id: int | None = None) -> dict:
    errors: list[str] = []
    name = " ".join((display_name or "").split())
    if not NAME_RE.match(name):
        errors.append("Display name must be 2–80 characters (letters, numbers, spaces, . @ ( ) - _).")
    else:
        q = select(Account.id).where(func.lower(Account.display_name) == name.lower())
        if account_id:
            q = q.where(Account.id != account_id)
        if session.scalar(q):
            errors.append(f"An account named '{name}' already exists.")
    try:
        limit = int(daily_run_limit or 0)
        if not 0 <= limit <= 10000:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Daily run limit must be a whole number between 0 and 10000 (0 = unlimited).")
        limit = 0
    notes = (notes or "").strip()
    if len(notes) > 1000:
        errors.append("Notes must be under 1000 characters.")
    if errors:
        raise ValidationError(errors)
    return {"display_name": name, "daily_run_limit": limit, "notes": notes or None}


def create_account(session: Session, cfg: Config, display_name: str, daily_run_limit: Any = 0,
                   notes: str | None = None, enabled: bool = True) -> Account:
    data = validate_fields(session, display_name, daily_run_limit, notes)
    acc = Account(profile_dir=f"pending-{uuid.uuid4().hex}", enabled=enabled,
                  session_status=SessionStatus.NEW, **data)
    session.add(acc)
    session.flush()  # obtain id
    path = cfg.PROFILES_DIR / f"account_{acc.id:03d}"
    n = acc.id
    while path.exists() and any(path.iterdir()) and session.scalar(
            select(Account.id).where(Account.profile_dir == _relative_profile_path(cfg, path))):
        n += 1
        path = cfg.PROFILES_DIR / f"account_{n:03d}"
    path.mkdir(parents=True, exist_ok=True)
    acc.profile_dir = _relative_profile_path(cfg, path)
    acc.status_message = "Profile created. Click 'Open Browser / Login' to sign in manually."
    return acc


def update_account(session: Session, acc: Account, display_name: str, daily_run_limit: Any,
                   notes: str | None, enabled: bool) -> Account:
    data = validate_fields(session, display_name, daily_run_limit, notes, account_id=acc.id)
    for k, v in data.items():
        setattr(acc, k, v)
    set_enabled(session, acc, enabled)
    return acc


def set_enabled(session: Session, acc: Account, enabled: bool) -> None:
    if acc.enabled == enabled:
        return
    acc.enabled = enabled
    if not enabled:
        for s in acc.searches:
            if s.deleted_at is None and s.account_mode == "specific" and s.status == SearchStatus.ACTIVE:
                s.status = SearchStatus.WAITING_ACCOUNT
                s.status_message = f"Assigned account '{acc.display_name}' is disabled."


def save_accounts(session: Session, cfg: Config, rows: list[dict]) -> int:
    """Validate and persist a batch of account edits from the Save Accounts form.

    All rows are validated first; nothing is written if any row is invalid.
    Also verifies each profile directory exists (re-creating empty ones) and
    writes a non-sensitive JSON metadata snapshot to data/exports.
    """
    errors: list[str] = []
    accounts = {a.id: a for a in session.scalars(select(Account)).all()}
    seen_names: set[str] = set()
    cleaned: list[tuple[Account, dict, bool]] = []
    for row in rows:
        acc = accounts.get(int(row.get("id", 0) or 0))
        if acc is None:
            errors.append(f"Account #{row.get('id')} no longer exists.")
            continue
        try:
            data = validate_fields(session, row.get("display_name", ""), row.get("daily_run_limit", 0),
                                   row.get("notes", acc.notes), account_id=acc.id)
        except ValidationError as exc:
            errors.extend(f"{acc.display_name}: {e}" for e in exc.errors)
            continue
        if data["display_name"].lower() in seen_names:
            errors.append(f"Duplicate display name '{data['display_name']}'.")
        seen_names.add(data["display_name"].lower())
        cleaned.append((acc, data, bool(row.get("enabled"))))

    # profile directory integrity
    profile_paths = {}
    for acc in accounts.values():
        p = resolve_profile_dir(cfg, acc)
        key = str(p.resolve()).lower()
        if key in profile_paths:
            errors.append(f"Accounts '{acc.display_name}' and '{profile_paths[key]}' share a profile directory.")
        profile_paths[key] = acc.display_name
        try:
            p.resolve().relative_to(cfg.PROFILES_DIR.resolve())
        except ValueError:
            errors.append(f"Profile for '{acc.display_name}' is outside {cfg.PROFILES_DIR}.")
    if errors:
        raise ValidationError(errors)

    # Two-phase rename avoids transient unique-constraint clashes when swapping names
    for acc, data, _ in cleaned:
        acc.display_name = f"__tmp_{acc.id}_{uuid.uuid4().hex[:6]}"
    session.flush()
    for acc, data, enabled in cleaned:
        for k, v in data.items():
            setattr(acc, k, v)
        set_enabled(session, acc, enabled)
        resolve_profile_dir(cfg, acc).mkdir(parents=True, exist_ok=True)
        acc.updated_at = utcnow()
    session.flush()
    write_metadata_snapshot(session, cfg)
    return len(cleaned)


def delete_account(session: Session, cfg: Config, acc: Account, delete_profile: bool = False) -> None:
    for s in list(acc.searches):
        if s.deleted_at is None:
            s.status = SearchStatus.WAITING_ACCOUNT if s.account_mode == "specific" else s.status
            s.status_message = f"Assigned account '{acc.display_name}' was removed. Choose another account."
        s.account_id = None
    profile = resolve_profile_dir(cfg, acc)
    session.delete(acc)
    session.flush()
    if delete_profile:
        try:
            profile.resolve().relative_to(cfg.PROFILES_DIR.resolve())
            shutil.rmtree(profile, ignore_errors=True)
        except ValueError:
            pass  # never delete outside the profiles root


def assigned_searches(session: Session, acc: Account) -> list[SearchConfiguration]:
    return session.scalars(select(SearchConfiguration).where(
        SearchConfiguration.account_id == acc.id, SearchConfiguration.deleted_at.is_(None))
        .order_by(SearchConfiguration.name)).all()


def metadata(session: Session) -> list[dict]:
    out = []
    for acc in session.scalars(select(Account).order_by(Account.id)).all():
        row = {}
        for f in EXPORT_FIELDS:
            v = getattr(acc, f)
            row[f] = v.isoformat() if hasattr(v, "isoformat") else v
        row["assigned_search_ids"] = [s.id for s in acc.searches if s.deleted_at is None]
        out.append(row)
    return out


def write_metadata_snapshot(session: Session, cfg: Config) -> Path:
    cfg.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = cfg.EXPORT_DIR / "accounts_metadata.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"exported_at": utcnow().isoformat(), "accounts": metadata(session)},
                              indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def export_json_bytes(session: Session) -> bytes:
    return json.dumps({"exported_at": utcnow().isoformat(), "note": "Non-sensitive metadata only",
                       "accounts": metadata(session)}, indent=2).encode("utf-8")


def export_pickle_bytes(session: Session) -> bytes:
    """Explicit-request-only pickle export of plain metadata dicts.

    This application NEVER loads pickle files (pickle can execute code).
    """
    return pickle.dumps({"exported_at": utcnow().isoformat(), "accounts": metadata(session)},
                        protocol=pickle.HIGHEST_PROTOCOL)
