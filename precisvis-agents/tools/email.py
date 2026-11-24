"""E-mails : envoi du bilan (Resend ou SMTP Gmail) et lecture de la boîte SAV (IMAP)."""
from __future__ import annotations

import base64
import email
import imaplib
import smtplib
import ssl
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .http import request


@dataclass
class InlineImage:
    cid: str
    path: Path


@dataclass
class IncomingEmail:
    uid: str
    message_id: str
    sender: str
    subject: str
    body: str
    references: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


# -- envoi --------------------------------------------------------------------------------
class ResendSender:
    def __init__(self, api_key: str, sender: str):
        self.api_key, self.sender = api_key, sender

    def send(self, to: str, subject: str, html: str, images: list[InlineImage] | None = None,
             reply_to: str | None = None, in_reply_to: str | None = None) -> str:
        body: dict[str, Any] = {"from": self.sender, "to": [to], "subject": subject, "html": html}
        if images:
            body["attachments"] = [{"filename": img.path.name, "content": base64.b64encode(img.path.read_bytes()).decode(),
                                    "content_id": img.cid} for img in images]
        if in_reply_to:
            body["headers"] = {"In-Reply-To": in_reply_to, "References": in_reply_to}
        if reply_to:
            body["reply_to"] = reply_to
        res = request("resend", "POST", "https://api.resend.com/emails", json=body,
                      headers={"Authorization": f"Bearer {self.api_key}"}).json()
        return res.get("id", "")


class SmtpSender:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str | None = None):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender = sender or user

    def send(self, to: str, subject: str, html: str, images: list[InlineImage] | None = None,
             reply_to: str | None = None, in_reply_to: str | None = None) -> str:
        msg = MIMEMultipart("related")
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        if in_reply_to:
            msg["In-Reply-To"] = msg["References"] = in_reply_to
        if reply_to:
            msg["Reply-To"] = reply_to
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)
        for img in images or []:
            part = MIMEImage(img.path.read_bytes())
            part.add_header("Content-ID", f"<{img.cid}>")
            part.add_header("Content-Disposition", "inline", filename=img.path.name)
            msg.attach(part)
        with smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context()) as s:
            s.login(self.user, self.password)
            s.send_message(msg)
        return msg.get("Message-ID", "")


class FileSender:
    """Simulation : écrit l'e-mail en HTML dans output/reports/ au lieu de l'envoyer."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.sent: list[dict[str, Any]] = []

    def send(self, to: str, subject: str, html: str, images: list[InlineImage] | None = None,
             reply_to: str | None = None, in_reply_to: str | None = None) -> str:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        preview = html
        for img in images or []:   # pour l'aperçu local, les images inline deviennent des chemins relatifs
            try:
                rel = img.path.resolve().relative_to(self.out_dir.resolve().parent)
                preview = preview.replace(f"cid:{img.cid}", f"../{rel.as_posix()}")
            except ValueError:
                preview = preview.replace(f"cid:{img.cid}", img.path.resolve().as_uri())
        n = len(self.sent) + 1
        path = self.out_dir / f"email_{n:02d}_{_slug(subject)[:60]}.html"
        path.write_text(f"<!-- À : {to} | Objet : {subject} -->\n" + preview, encoding="utf-8")
        self.sent.append({"to": to, "subject": subject, "path": str(path), "html": html, "images": images or []})
        return str(path)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


# -- réception (SAV) ------------------------------------------------------------------------
class ImapInbox:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host, self.port, self.user, self.password = host, port, user, password

    def _conn(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        conn.login(self.user, self.password)
        conn.select("INBOX")
        return conn

    def unread(self, limit: int = 30) -> list[IncomingEmail]:
        conn = self._conn()
        try:
            _, data = conn.uid("search", None, "UNSEEN")
            uids = data[0].split()[:limit]
            out = []
            for uid in uids:
                _, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")  # PEEK : ne marque pas comme lu
                msg = email.message_from_bytes(msg_data[0][1])
                out.append(IncomingEmail(
                    uid=uid.decode(), message_id=msg.get("Message-ID", ""),
                    sender=parseaddr(msg.get("From", ""))[1], subject=str(make_header(decode_header(msg.get("Subject", "")))),
                    body=_text_body(msg)[:6000], references=msg.get("References", "")))
            return out
        finally:
            conn.logout()

    def mark_handled(self, uid: str, label: str | None = None) -> None:
        conn = self._conn()
        try:
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
            if label:
                conn.uid("store", uid, "+X-GM-LABELS", f'"{label}"')
        except imaplib.IMAP4.error:
            pass
        finally:
            conn.logout()


def _text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                import re
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""
