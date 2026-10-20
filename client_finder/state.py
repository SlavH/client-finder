"""SQLite state store for leads, outreach, opt-outs, and dedup."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from client_finder.models import Lead, OutreachRecord


class StateStore:
    def __init__(self, db_path: str | Path = ".client_finder_state.db"):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                company TEXT NOT NULL,
                name TEXT,
                role TEXT,
                email TEXT,
                phone TEXT,
                website TEXT,
                url TEXT,
                contact_hint TEXT,
                fit_score INTEGER,
                fit_reason TEXT,
                hook TEXT,
                pain_point TEXT,
                suggested_role TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS outreach (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                subject TEXT,
                message TEXT,
                mode TEXT DEFAULT 'email_only',
                deliverable_path TEXT,
                sent_at TEXT,
                status TEXT DEFAULT 'queued',
                response TEXT,
                dry_run INTEGER DEFAULT 1,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );
            CREATE TABLE IF NOT EXISTS opt_outs (
                id TEXT PRIMARY KEY,
                email TEXT,
                domain TEXT,
                reason TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sent_hashes (
                hash TEXT PRIMARY KEY,
                lead_id TEXT,
                channel TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                direction TEXT NOT NULL,  -- inbound | outbound
                message TEXT,
                created_at TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );
        """
        )
        self._conn.commit()

    # ----- leads -----

    def upsert_lead(self, lead: Lead) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO leads
            (id, source, company, name, role, email, phone, website, url,
             contact_hint, fit_score, fit_reason, hook, pain_point,
             suggested_role, status, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead.id,
                lead.source,
                lead.company,
                lead.name,
                lead.role,
                lead.email,
                lead.phone,
                lead.website,
                lead.url,
                lead.contact_hint,
                lead.fit_score,
                lead.fit_reason,
                lead.hook,
                lead.pain_point,
                lead.suggested_role,
                lead.status,
                lead.created_at,
                __import__("json").dumps(lead.metadata),
            ),
        )
        self._conn.commit()

    def get_lead(self, lead_id: str) -> Lead | None:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return Lead(
            id=row["id"],
            source=row["source"],
            company=row["company"],
            name=row["name"],
            role=row["role"],
            email=row["email"],
            phone=row["phone"],
            website=row["website"],
            url=row["url"],
            contact_hint=row["contact_hint"],
            fit_score=row["fit_score"],
            fit_reason=row["fit_reason"],
            hook=row["hook"],
            pain_point=row["pain_point"],
            suggested_role=row["suggested_role"],
            status=row["status"],
            created_at=row["created_at"],
            metadata=__import__("json").loads(row["metadata"] or "{}"),
        )

    def list_leads(self, status: str | None = None, limit: int = 100) -> list[Lead]:
        cur = self._conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [self._row_to_lead(r) for r in cur.fetchall()]

    def update_lead_status(self, lead_id: str, status: str) -> None:
        cur = self._conn.cursor()
        cur.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        self._conn.commit()

    def _row_to_lead(self, row: sqlite3.Row) -> Lead:
        return Lead(
            id=row["id"],
            source=row["source"],
            company=row["company"],
            name=row["name"],
            role=row["role"],
            email=row["email"],
            phone=row["phone"],
            website=row["website"],
            url=row["url"],
            contact_hint=row["contact_hint"],
            fit_score=row["fit_score"],
            fit_reason=row["fit_reason"],
            hook=row["hook"],
            pain_point=row["pain_point"],
            suggested_role=row["suggested_role"],
            status=row["status"],
            created_at=row["created_at"],
            metadata=__import__("json").loads(row["metadata"] or "{}"),
        )

    # ----- outreach -----

    def record_outreach(self, record: OutreachRecord) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO outreach
            (id, lead_id, channel, subject, message, mode, deliverable_path,
             sent_at, status, response, dry_run)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.lead_id,
                record.channel,
                record.subject,
                record.message,
                record.mode,
                record.deliverable_path,
                record.sent_at,
                record.status,
                record.response,
                1 if record.dry_run else 0,
            ),
        )
        self._conn.commit()

    def list_outreach(self, lead_id: str | None = None, limit: int = 100) -> list[OutreachRecord]:
        cur = self._conn.cursor()
        if lead_id:
            cur.execute(
                "SELECT * FROM outreach WHERE lead_id = ? ORDER BY sent_at DESC LIMIT ?",
                (lead_id, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM outreach ORDER BY sent_at DESC LIMIT ?", (limit,)
            )
        return [self._row_to_outreach(r) for r in cur.fetchall()]

    def _row_to_outreach(self, row: sqlite3.Row) -> OutreachRecord:
        return OutreachRecord(
            id=row["id"],
            lead_id=row["lead_id"],
            channel=row["channel"],
            subject=row["subject"],
            message=row["message"],
            mode=row["mode"],
            deliverable_path=row["deliverable_path"],
            sent_at=row["sent_at"],
            status=row["status"],
            response=row["response"],
            dry_run=bool(row["dry_run"]),
        )

    def outreach_count_today(self, channel: str, dry_run: bool = False) -> int:
        cur = self._conn.cursor()
        today = datetime.utcnow().date().isoformat()
        cur.execute(
            """
            SELECT COUNT(*) FROM outreach
            WHERE channel = ? AND sent_at LIKE ? AND dry_run = ?
            """,
            (channel, f"{today}%", 1 if dry_run else 0),
        )
        return cur.fetchone()[0]

    # ----- opt-outs -----

    def is_opted_out(self, email: str | None, domain: str | None) -> bool:
        if not email and not domain:
            return False
        cur = self._conn.cursor()
        if email:
            cur.execute("SELECT 1 FROM opt_outs WHERE email = ?", (email,))
            if cur.fetchone():
                return True
        if domain:
            cur.execute("SELECT 1 FROM opt_outs WHERE domain = ?", (domain,))
            if cur.fetchone():
                return True
        return False

    def add_opt_out(self, email: str | None, domain: str | None, reason: str = "") -> None:
        cur = self._conn.cursor()
        oid = hashlib.sha256(f"{email}:{domain}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
        cur.execute(
            """
            INSERT OR IGNORE INTO opt_outs (id, email, domain, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (oid, email, domain, reason, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    # ----- dedup hashes -----

    def is_sent(self, lead_id: str, channel: str, message: str) -> bool:
        h = hashlib.sha256(f"{lead_id}:{channel}:{message}".encode()).hexdigest()
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM sent_hashes WHERE hash = ?", (h,))
        return cur.fetchone() is not None

    def record_sent_hash(self, lead_id: str, channel: str, message: str) -> None:
        h = hashlib.sha256(f"{lead_id}:{channel}:{message}".encode()).hexdigest()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO sent_hashes (hash, lead_id, channel, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (h, lead_id, channel, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    # ----- conversations -----

    def record_conversation(
        self, lead_id: str, direction: str, message: str
    ) -> None:
        cur = self._conn.cursor()
        cid = hashlib.sha256(
            f"{lead_id}:{direction}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        cur.execute(
            """
            INSERT INTO conversations (id, lead_id, direction, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cid, lead_id, direction, message, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ----- cookie persistence -----

    def save_cookies(self, domain: str, cookies: list[dict]) -> None:
        """Save cookies for a domain to state/cookies/<domain>.json."""
        cookies_dir = Path(self.db_path).parent / "cookies"
        cookies_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(cookies_dir, 0o700)
        safe_name = domain.replace(".", "_").replace(":", "_")
        path = cookies_dir / f"{safe_name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        os.chmod(path, 0o600)

    def load_cookies(self, domain: str) -> list[dict] | None:
        """Load saved cookies for a domain. Returns None if not found."""
        cookies_dir = Path(self.db_path).parent / "cookies"
        safe_name = domain.replace(".", "_").replace(":", "_")
        path = cookies_dir / f"{safe_name}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            os.chmod(path, 0o600)
            return data if isinstance(data, list) else None
        except Exception:
            return None

    def clear_cookies(self, domain: str) -> None:
        """Delete saved cookies for a domain (forces re-login)."""
        cookies_dir = Path(self.db_path).parent / "cookies"
        safe_name = domain.replace(".", "_").replace(":", "_")
        path = cookies_dir / f"{safe_name}.json"
        if path.exists():
            path.unlink()