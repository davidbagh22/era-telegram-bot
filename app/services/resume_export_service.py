"""Single assembly path for the participant resume/portfolio PDF with attached documents.

Both HTTP download and bot delivery (Mini App «Получить в боте» and the bot menu)
call :func:`assemble_resume_export`, so the user always gets the same document and
a structured manifest of exactly what is inside. A selected attachment that cannot
be built or merged is never dropped silently: :class:`ResumeAttachmentError` names
every failed document, and the caller may only skip them on an explicit user choice
(``skip_keys`` / ``skip_failed``).
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Awaitable, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.career_models import CareerPortfolioItem
from app.database.certificate_models import CertificateIssue
from app.database.models import User
from app.services import career_service
from app.services.career_pdf_service import RESUME_MODES, build_career_resume
from app.services.certificate_service import DEFAULT_PARTICIPATION_SIGNATORY
from app.services.portfolio_service import build_portfolio_data

FetchFile = Callable[[str], Awaitable[bytes]]

ATTACHMENT_ERROR_CODE = "resume_attachment_failed"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_PAGES = 30
MAX_IMAGE_PIXELS = 40_000_000
MAX_SKIP_KEYS = 50
DOCUMENT_ITEM_TYPES = frozenset({"certificate", "course", "award"})
SUPPORTED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
KEY_PATTERN = re.compile(r"^(cert|doc):\d{1,12}$")


@dataclass
class AttachmentCandidate:
    key: str
    kind: str
    title: str
    number: str | None
    item_id: int | None
    issue_id: int | None
    file_id: str | None
    file_name: str | None
    verified: bool
    visible: bool
    selected: bool
    reason: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "number": self.number,
            "item_id": self.item_id,
            "verified": self.verified,
            "visible": self.visible,
            "selected": self.selected,
            "reason": self.reason,
        }


@dataclass
class ResumeExport:
    pdf: bytes
    manifest: dict[str, Any]


class ResumeAttachmentError(Exception):
    def __init__(self, failures: list[dict[str, Any]]):
        super().__init__(ATTACHMENT_ERROR_CODE)
        self.failures = failures

    def detail(self) -> dict[str, Any]:
        names = ", ".join(_label(item) for item in self.failures)
        return {
            "code": ATTACHMENT_ERROR_CODE,
            "message": f"Не удалось приложить: {names}. Файл не добавлен — повторите или скачайте без него.",
            "failed": self.failures,
        }


def _label(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or "документ")
    number = entry.get("number")
    return f"{title} ({number})" if number else title


def parse_skip_keys(raw: Iterable[str] | str | None) -> frozenset[str]:
    if raw is None:
        return frozenset()
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    keys = {part.strip() for part in parts if part and part.strip()}
    if len(keys) > MAX_SKIP_KEYS or any(not KEY_PATTERN.match(key) for key in keys):
        raise ValueError("invalid_skip_keys")
    return frozenset(keys)


async def list_attachment_candidates(session: AsyncSession, user_id: int) -> list[AttachmentCandidate]:
    candidates: list[AttachmentCandidate] = []
    rows = (
        await session.execute(
            select(CertificateIssue, CareerPortfolioItem)
            .outerjoin(CareerPortfolioItem, CareerPortfolioItem.id == CertificateIssue.portfolio_item_id)
            .where(CertificateIssue.user_id == user_id)
            .order_by(CertificateIssue.id.asc())
        )
    ).all()
    certificate_item_ids: set[int] = set()
    for issue, item in rows:
        if item is not None:
            certificate_item_ids.add(item.id)
        revoked = issue.status != "issued" or (item is not None and item.status == "revoked")
        visible = True if item is None else bool(item.include_in_resume)
        reason = "revoked" if revoked else None if visible else "hidden"
        snapshot = issue.snapshot or {}
        candidates.append(
            AttachmentCandidate(
                key=f"cert:{issue.id}",
                kind="certificate",
                title=str(snapshot.get("event_title") or "Сертификат участника ЭРА"),
                number=issue.document_number,
                item_id=item.id if item is not None else None,
                issue_id=issue.id,
                file_id=None,
                file_name=None,
                verified=True,
                visible=visible,
                selected=not revoked and visible,
                reason=reason,
            )
        )
    doc_rows = (
        await session.scalars(
            select(CareerPortfolioItem)
            .where(
                CareerPortfolioItem.user_id == user_id,
                CareerPortfolioItem.file_id.is_not(None),
                CareerPortfolioItem.item_type.in_(DOCUMENT_ITEM_TYPES),
            )
            .order_by(CareerPortfolioItem.id.asc())
        )
    ).all()
    for item in doc_rows:
        if item.id in certificate_item_ids:
            continue
        name = (item.file_name or "").lower()
        visible = bool(item.include_in_resume)
        if item.status == "revoked":
            reason = "revoked"
        elif item.status == "rejected":
            reason = "rejected"
        elif name and "." in name and not name.endswith(SUPPORTED_EXTENSIONS):
            reason = "unsupported_format"
        elif not visible:
            reason = "hidden"
        else:
            reason = None
        candidates.append(
            AttachmentCandidate(
                key=f"doc:{item.id}",
                kind="document",
                title=item.title,
                number=None,
                item_id=item.id,
                issue_id=None,
                file_id=item.file_id,
                file_name=item.file_name,
                verified=item.status == "verified",
                visible=visible,
                selected=reason is None,
                reason=reason,
            )
        )
    return candidates


async def attachment_preview(session: AsyncSession, user_id: int) -> dict[str, Any]:
    candidates = await list_attachment_candidates(session, user_id)
    selected = [item for item in candidates if item.selected]
    return {
        "items": [item.public() for item in candidates],
        "selected_count": len(selected),
        "default_attach": bool(selected),
    }


def sniff_attachment_kind(blob: bytes) -> str | None:
    if blob[:5] == b"%PDF-":
        return "pdf"
    if blob[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    return None


def _image_to_pdf(blob: bytes) -> bytes:
    from PIL import Image, ImageOps
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    probe = Image.open(BytesIO(blob))
    probe.verify()
    image = Image.open(BytesIO(blob))
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("image_too_large")
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA", "P"}:
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.split()[-1])
        image = flat
    else:
        image = image.convert("RGB")
    page = landscape(A4) if image.width > image.height else A4
    margin = 10 * mm
    box_w, box_h = page[0] - 2 * margin, page[1] - 2 * margin
    scale = min(box_w / image.width, box_h / image.height)
    draw_w, draw_h = image.width * scale, image.height * scale
    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=page)
    pdf.drawImage(
        ImageReader(image),
        (page[0] - draw_w) / 2,
        (page[1] - draw_h) / 2,
        width=draw_w,
        height=draw_h,
    )
    pdf.showPage()
    pdf.save()
    return out.getvalue()


def normalize_attachment_to_pdf(blob: bytes) -> tuple[bytes, int]:
    """Validate an uploaded file by signature and return ``(pdf_bytes, pages)``."""
    from pypdf import PdfReader

    if not blob:
        raise ValueError("empty_file")
    if len(blob) > MAX_ATTACHMENT_BYTES:
        raise ValueError("file_too_large")
    kind = sniff_attachment_kind(blob)
    if kind is None:
        raise ValueError("unsupported_format")
    pdf = blob if kind == "pdf" else _image_to_pdf(blob)
    reader = PdfReader(BytesIO(pdf))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("encrypted_pdf")
    pages = len(reader.pages)
    if pages < 1:
        raise ValueError("empty_pdf")
    if pages > MAX_ATTACHMENT_PAGES:
        raise ValueError("too_many_pages")
    return pdf, pages


def _certificate_pdf(issue: CertificateIssue, owner: User) -> bytes:
    from app.services.certificate_pdf_service import build_certificate_pdf

    snapshot = dict(issue.snapshot or {})
    if not snapshot.get("event_date") or not snapshot.get("event_title"):
        raise ValueError("snapshot_incomplete")
    snapshot.setdefault("signatory", DEFAULT_PARTICIPATION_SIGNATORY)
    snapshot.setdefault(
        "full_name", " ".join(part for part in (owner.first_name, owner.last_name) if part) or "Участник ЭРА"
    )
    return build_certificate_pdf(
        snapshot, number=issue.document_number, issued_at=issue.issued_at, revoked=False
    )


def _failure(candidate: AttachmentCandidate, reason: str) -> dict[str, Any]:
    return {
        "key": candidate.key,
        "kind": candidate.kind,
        "title": candidate.title,
        "number": candidate.number,
        "reason": reason,
    }


def _merge_with_outline(base_pdf: bytes, parts: list[tuple[AttachmentCandidate, bytes, int]]):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(BytesIO(base_pdf)).pages:
        writer.add_page(page)
    base_pages = len(writer.pages)
    failures: list[dict[str, Any]] = []
    attached: list[dict[str, Any]] = []
    for candidate, pdf, pages in parts:
        start = len(writer.pages)
        try:
            for page in PdfReader(BytesIO(pdf)).pages:
                writer.add_page(page)
            label = _label({"title": candidate.title, "number": candidate.number})
            writer.add_outline_item(label, start)
        except Exception:
            failures.append(_failure(candidate, "merge_failed"))
            continue
        attached.append({**_entry(candidate), "pages": pages, "first_page": start + 1})
    out = BytesIO()
    writer.write(out)
    return out.getvalue(), base_pages, attached, failures


def _entry(candidate: AttachmentCandidate) -> dict[str, Any]:
    return {
        "key": candidate.key,
        "kind": candidate.kind,
        "title": candidate.title,
        "number": candidate.number,
        "verified": candidate.verified,
    }


async def assemble_resume_export(
    session: AsyncSession,
    user: User,
    *,
    purpose: str,
    mode: str = "portfolio",
    attach: bool = False,
    fetch_file: FetchFile | None = None,
    skip_keys: Iterable[str] = (),
    skip_failed: bool = False,
) -> ResumeExport:
    """Build the resume PDF and append selected certificate/document pages.

    Raises ``ResumeAttachmentError`` when any selected attachment cannot be built
    and the caller did not explicitly agree to skip it.
    """
    if mode not in RESUME_MODES:
        raise ValueError("invalid_resume_mode")
    attach = attach or mode == "portfolio_with_certificates"
    skip = frozenset(skip_keys)
    profile = await career_service.get_or_create_profile(session, user.id)
    items = await career_service.list_items(session, user.id)
    portfolio = await build_portfolio_data(session, user, preview_limit=None)
    base_pdf = build_career_resume(user, profile, portfolio, items, purpose=purpose, mode=mode)

    skipped: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    parts: list[tuple[AttachmentCandidate, bytes, int]] = []
    failures: list[dict[str, Any]] = []
    if attach:
        candidates = await list_attachment_candidates(session, user.id)
        issues = {
            issue.id: issue
            for issue in (
                await session.scalars(select(CertificateIssue).where(CertificateIssue.user_id == user.id))
            ).all()
        }
        for candidate in candidates:
            if not candidate.selected:
                excluded.append({**_entry(candidate), "reason": candidate.reason})
                continue
            if candidate.key in skip:
                skipped.append({**_entry(candidate), "reason": "user_skipped"})
                continue
            try:
                if candidate.kind == "certificate":
                    pdf = _certificate_pdf(issues[candidate.issue_id], user)
                    pages = normalize_attachment_to_pdf(pdf)[1]
                else:
                    if fetch_file is None or not candidate.file_id:
                        raise ValueError("file_unavailable")
                    pdf, pages = normalize_attachment_to_pdf(await fetch_file(candidate.file_id))
            except Exception as exc:
                reason = str(exc) if isinstance(exc, ValueError) else "build_failed"
                failures.append(_failure(candidate, reason))
                continue
            parts.append((candidate, pdf, pages))

    merged, base_pages, attached, merge_failures = _merge_with_outline(base_pdf, parts)
    failures.extend(merge_failures)
    if failures and not skip_failed:
        raise ResumeAttachmentError(failures)
    for failure in failures:
        skipped.append({**failure, "reason": "build_failed"})
    manifest = {
        "mode": mode,
        "attach_requested": attach,
        "base_pages": base_pages,
        "total_pages": base_pages + sum(item["pages"] for item in attached),
        "attached": attached,
        "skipped": skipped,
        "excluded": excluded,
    }
    return ResumeExport(pdf=merged, manifest=manifest)


def encode_manifest_header(manifest: dict[str, Any]) -> str:
    compact = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(compact).decode("ascii")


def attachments_caption(manifest: dict[str, Any], limit: int = 900) -> str:
    attached = manifest.get("attached") or []
    skipped = manifest.get("skipped") or []
    lines: list[str] = []
    if attached:
        lines.append(f"Приложено документов: {len(attached)}")
        lines.extend(f"• {_label(item)}" for item in attached)
    if skipped:
        lines.append("Без вложений: " + ", ".join(_label(item) for item in skipped))
    text = "\n".join(lines)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def telegram_file_fetcher(bot) -> FetchFile | None:
    if bot is None:
        return None

    async def fetch(file_id: str) -> bytes:
        telegram_file = await bot.get_file(file_id)
        if not telegram_file.file_path:
            raise RuntimeError("missing_file_path")
        buffer = BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buffer)
        return buffer.getvalue()

    return fetch
