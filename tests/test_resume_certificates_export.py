import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401 - registers all metadata tables
from app.api.v1 import career as career_api
from app.database.base import Base
from app.database.certificate_models import CertificateIssue
from app.database.models import PortfolioItem, User
from app.services import resume_export_service as export_service
from app.services.career_pdf_service import build_career_resume, merge_pdf_bytes
from app.services.resume_export_service import (
    ResumeAttachmentError,
    assemble_resume_export,
    attachment_preview,
    normalize_attachment_to_pdf,
)
from app.utils.constants import ApplicationStatus, Role


def _text_pdf(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    out = BytesIO()
    pdf = canvas.Canvas(out)
    pdf.drawString(80, 780, text)
    pdf.showPage()
    pdf.save()
    return out.getvalue()


def _png() -> bytes:
    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (120, 80), (200, 30, 60)).save(out, format="PNG")
    return out.getvalue()


def _pages_text(pdf: bytes, start: int = 0) -> str:
    reader = PdfReader(BytesIO(pdf))
    return "\n".join((page.extract_text() or "") for page in reader.pages[start:])


def _page_count(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages)


class FakeBot:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = files or {}
        self.sent: list[tuple[bytes, str]] = []
        self.send_document = AsyncMock(side_effect=self._send)

    async def _send(self, chat_id, document, caption=None):
        self.sent.append((document.data, caption or ""))
        return SimpleNamespace(document=SimpleNamespace(file_id="sent"))

    async def get_file(self, file_id):
        if file_id not in self.files:
            raise RuntimeError("telegram_file_gone")
        return SimpleNamespace(file_path=file_id)

    async def download_file(self, path, destination):
        destination.write(self.files[path])


async def _seed(session, *, hidden=True, revoked=True, documents=True):
    user = User(
        telegram_id=777001,
        first_name="Анна",
        last_name="Примерова",
        role=Role.PARTICIPANT,
        application_status=ApplicationStatus.APPROVED,
    )
    session.add(user)
    await session.flush()
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    issues: dict[str, CertificateIssue] = {}
    specs = [("one", "Вечер ЭРА", True, "issued"), ("two", "Лекторий ЭРА", True, "issued")]
    if hidden:
        specs.append(("hidden", "Закрытое событие", False, "issued"))
    if revoked:
        specs.append(("revoked", "Отозванное событие", True, "revoked"))
    for name, title, include, status in specs:
        item = PortfolioItem(
            user_id=user.id,
            title=f"Сертификат участника: {title}",
            item_type="certificate",
            status="revoked" if status == "revoked" else "verified",
            include_in_resume=include,
        )
        session.add(item)
        await session.flush()
        issue = CertificateIssue(
            user_id=user.id,
            event_id=1,
            portfolio_item_id=item.id,
            basis_key=f"event:{len(issues) + 1}:user:{user.id}",
            request_key=f"req-{name}",
            status=status,
            snapshot=dict(
                full_name="Анна Примерова",
                event_title=title,
                event_date="2026-10-19",
                signatory="Багдасарян Д.С.",
                template_version="era-event-v2",
            ),
            issued_by=user.id,
            issued_at=now,
        )
        session.add(issue)
        await session.flush()
        issues[name] = issue
    files: dict[str, bytes] = {}
    docs: dict[str, PortfolioItem] = {}
    if documents:
        for name, file_name, blob in (
            ("pdf", "diploma.pdf", _text_pdf("UPLOADED-DIPLOMA-ALPHA")),
            ("png", "scan.png", _png()),
        ):
            doc = PortfolioItem(
                user_id=user.id,
                title=f"Диплом {name}",
                item_type="certificate",
                file_id=f"fid-{name}",
                file_name=file_name,
                status="verified" if name == "pdf" else "self_reported",
                include_in_resume=True,
            )
            session.add(doc)
            await session.flush()
            docs[name] = doc
            files[f"fid-{name}"] = blob
    await session.commit()
    await session.refresh(user, attribute_names=["departments", "directions"])
    return user, issues, docs, files


def _run(scenario):
    async def wrapper():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await scenario(session)
        finally:
            await engine.dispose()

    asyncio.run(wrapper())


def test_two_selected_certificates_appended_hidden_and_revoked_excluded():
    async def scenario(session):
        user, issues, _docs, _files = await _seed(session, documents=False)
        base = await assemble_resume_export(session, user, purpose="universal", mode="portfolio")
        merged = await assemble_resume_export(
            session, user, purpose="universal", mode="portfolio", attach=True
        )
        manifest = merged.manifest
        assert [item["number"] for item in manifest["attached"]] == [
            issues["one"].document_number,
            issues["two"].document_number,
        ]
        assert _page_count(merged.pdf) == _page_count(base.pdf) + 2 == manifest["total_pages"]
        attached_text = _pages_text(merged.pdf, start=manifest["base_pages"])
        assert issues["one"].document_number in attached_text
        assert issues["two"].document_number in attached_text
        full_text = _pages_text(merged.pdf)
        assert issues["hidden"].document_number not in full_text
        assert issues["revoked"].document_number not in full_text
        assert "ОТОЗВАН" not in full_text
        assert {(item["number"], item["reason"]) for item in manifest["excluded"]} == {
            (issues["hidden"].document_number, "hidden"),
            (issues["revoked"].document_number, "revoked"),
        }
        assert _page_count(base.pdf) == manifest["base_pages"]
        assert base.manifest["attached"] == []

    _run(scenario)


def test_download_and_bot_send_share_one_assembly_and_manifest():
    async def scenario(session):
        user, issues, _docs, files = await _seed(session)
        bot = FakeBot(files)
        response = await career_api.download_resume(
            purpose="universal",
            mode="portfolio",
            attach_certificates=True,
            skip=None,
            user=user,
            session=session,
            bot=bot,
        )
        sent = await career_api.send_resume_to_bot_chat(
            career_api.PurposeIn(purpose="universal", mode="portfolio", attach_certificates=True),
            user=user,
            session=session,
            bot=bot,
        )
        delivered, caption = bot.sent[0]
        assert sent["sent"] is True
        assert _page_count(response.body) == _page_count(delivered)
        assert _pages_text(response.body, start=sent["manifest"]["base_pages"]) == _pages_text(
            delivered, start=sent["manifest"]["base_pages"]
        )
        header = response.headers["X-ERA-Resume-Manifest"]
        import base64
        import json

        header_manifest = json.loads(base64.urlsafe_b64decode(header.encode()).decode())
        assert header_manifest["attached"] == sent["manifest"]["attached"]
        assert response.headers["X-ERA-Attached-Count"] == str(len(sent["manifest"]["attached"]))
        titles = [item["title"] for item in sent["manifest"]["attached"]]
        assert titles == ["Вечер ЭРА", "Лекторий ЭРА", "Диплом pdf", "Диплом png"]
        assert issues["one"].document_number in caption
        assert issues["hidden"].document_number not in caption

    _run(scenario)


def test_uploaded_pdf_and_image_are_included_by_signature():
    async def scenario(session):
        user, _issues, docs, files = await _seed(session, hidden=False, revoked=False)
        base = await assemble_resume_export(session, user, purpose="universal")
        merged = await assemble_resume_export(
            session, user, purpose="universal", attach=True,
            fetch_file=export_service.telegram_file_fetcher(FakeBot(files)),
        )
        assert _page_count(merged.pdf) == _page_count(base.pdf) + 2 + 2
        assert "UPLOADED-DIPLOMA-ALPHA" in _pages_text(merged.pdf, start=merged.manifest["base_pages"])
        by_title = {item["title"]: item for item in merged.manifest["attached"]}
        assert by_title["Диплом pdf"]["verified"] is True
        assert by_title["Диплом png"]["verified"] is False
        assert docs["png"].id and by_title["Диплом png"]["pages"] == 1

    _run(scenario)


def test_signature_validation_rejects_disguised_files():
    with pytest.raises(ValueError, match="unsupported_format"):
        normalize_attachment_to_pdf(b"<html><script>alert(1)</script></html>")
    with pytest.raises(ValueError, match="empty_file"):
        normalize_attachment_to_pdf(b"")
    pdf, pages = normalize_attachment_to_pdf(_png())
    assert pdf.startswith(b"%PDF") and pages == 1
    with pytest.raises(Exception):
        normalize_attachment_to_pdf(b"%PDF-1.4 truncated garbage")


def test_failed_certificate_is_explicit_error_not_silent_base_only():
    async def scenario(session):
        user, issues, _docs, files = await _seed(session, documents=False)
        bot = FakeBot(files)
        real = export_service._certificate_pdf

        def flaky(issue, owner):
            if issue.id == issues["two"].id:
                raise RuntimeError("boom")
            return real(issue, owner)

        with patch.object(export_service, "_certificate_pdf", flaky):
            with pytest.raises(ResumeAttachmentError) as caught:
                await assemble_resume_export(
                    session, user, purpose="universal", mode="portfolio", attach=True
                )
            failed = caught.value.failures
            assert [(item["title"], item["number"]) for item in failed] == [
                ("Лекторий ЭРА", issues["two"].document_number)
            ]
            assert "Лекторий ЭРА" in caught.value.detail()["message"]

            with pytest.raises(HTTPException) as http_error:
                await career_api.download_resume(
                    purpose="universal", mode="portfolio", attach_certificates=True,
                    skip=None, user=user, session=session, bot=bot,
                )
            assert http_error.value.status_code == 409
            assert http_error.value.detail["code"] == "resume_attachment_failed"
            assert http_error.value.detail["failed"][0]["key"] == f"cert:{issues['two'].id}"

            with pytest.raises(HTTPException) as send_error:
                await career_api.send_resume_to_bot_chat(
                    career_api.PurposeIn(attach_certificates=True), user=user, session=session, bot=bot
                )
            assert send_error.value.status_code == 409
            bot.send_document.assert_not_awaited()

            skipped = await assemble_resume_export(
                session, user, purpose="universal", attach=True,
                skip_keys={f"cert:{issues['two'].id}"},
            )
            assert [item["title"] for item in skipped.manifest["attached"]] == ["Вечер ЭРА"]
            assert skipped.manifest["skipped"][0]["reason"] == "user_skipped"

            retried_ok = await assemble_resume_export(
                session, user, purpose="universal", attach=True, skip_failed=True
            )
            assert retried_ok.manifest["skipped"][0]["reason"] == "build_failed"

        recovered = await assemble_resume_export(session, user, purpose="universal", attach=True)
        assert len(recovered.manifest["attached"]) == 2

    _run(scenario)


def test_unreadable_uploaded_document_is_named_in_error():
    async def scenario(session):
        user, _issues, docs, files = await _seed(session, hidden=False, revoked=False)
        files["fid-pdf"] = b"not a pdf at all"
        with pytest.raises(ResumeAttachmentError) as caught:
            await assemble_resume_export(
                session, user, purpose="universal", attach=True,
                fetch_file=export_service.telegram_file_fetcher(FakeBot(files)),
            )
        assert [item["title"] for item in caught.value.failures] == ["Диплом pdf"]
        assert caught.value.failures[0]["reason"] == "unsupported_format"

        del files["fid-png"]
        with pytest.raises(ResumeAttachmentError) as gone:
            await assemble_resume_export(
                session, user, purpose="universal", attach=True,
                fetch_file=export_service.telegram_file_fetcher(FakeBot(files)),
            )
        assert {item["title"] for item in gone.value.failures} == {"Диплом pdf", "Диплом png"}
        assert docs["pdf"].id

    _run(scenario)


def test_legacy_certificate_without_template_fields_or_portfolio_row_is_included():
    async def scenario(session):
        user, issues, _docs, _files = await _seed(session, hidden=False, revoked=False, documents=False)
        legacy = issues["one"]
        legacy.snapshot = dict(event_title="Старый сертификат", event_date="2025-05-01")
        legacy.portfolio_item_id = 999999
        await session.commit()
        merged = await assemble_resume_export(session, user, purpose="universal", attach=True)
        assert [item["title"] for item in merged.manifest["attached"]] == ["Старый сертификат", "Лекторий ЭРА"]
        assert legacy.document_number in _pages_text(merged.pdf, start=merged.manifest["base_pages"])

        legacy.snapshot = {"event_title": "Битый"}
        await session.commit()
        with pytest.raises(ResumeAttachmentError) as caught:
            await assemble_resume_export(session, user, purpose="universal", attach=True)
        assert caught.value.failures[0]["reason"] == "snapshot_incomplete"

    _run(scenario)


def test_preview_lists_selected_hidden_revoked_and_default_toggle():
    async def scenario(session):
        user, issues, docs, _files = await _seed(session)
        preview = await attachment_preview(session, user.id)
        by_key = {item["key"]: item for item in preview["items"]}
        assert preview["selected_count"] == 4 and preview["default_attach"] is True
        assert by_key[f"cert:{issues['one'].id}"]["number"] == issues["one"].document_number
        assert by_key[f"cert:{issues['hidden'].id}"] | {"selected": False, "visible": False, "reason": "hidden"} == by_key[
            f"cert:{issues['hidden'].id}"
        ]
        assert by_key[f"cert:{issues['revoked'].id}"]["reason"] == "revoked"
        assert by_key[f"doc:{docs['png'].id}"]["verified"] is False

        for key, item in by_key.items():
            if item["selected"] and item["item_id"]:
                row = await session.get(PortfolioItem, item["item_id"])
                row.include_in_resume = False
        await session.commit()
        empty = await attachment_preview(session, user.id)
        assert empty["selected_count"] == 0 and empty["default_attach"] is False

        endpoint = await career_api.resume_attachments_preview(user=user, session=session)
        assert endpoint["selected_count"] == 0

    _run(scenario)


def test_unsupported_document_format_is_listed_but_not_selected():
    async def scenario(session):
        user, _issues, docs, _files = await _seed(session, hidden=False, revoked=False)
        docs["png"].file_name = "scan.docx"
        await session.commit()
        preview = await attachment_preview(session, user.id)
        entry = next(item for item in preview["items"] if item["key"] == f"doc:{docs['png'].id}")
        assert entry["selected"] is False and entry["reason"] == "unsupported_format"

    _run(scenario)


def test_skip_keys_are_validated():
    assert export_service.parse_skip_keys("cert:1,doc:2") == {"cert:1", "doc:2"}
    with pytest.raises(ValueError):
        export_service.parse_skip_keys("cert:1;drop")
    with pytest.raises(HTTPException) as caught:
        career_api._skip_keys_or_400("../etc/passwd")
    assert caught.value.status_code == 400


def test_strict_merge_never_drops_a_part():
    base = _text_pdf("base")
    assert _page_count(merge_pdf_bytes([base, b"junk"])) == 1
    with pytest.raises(ValueError, match="invalid_pdf_part"):
        merge_pdf_bytes([base, b"junk"], strict=True)
    with pytest.raises(ValueError, match="empty_pdf_part"):
        merge_pdf_bytes([base, b""], strict=True)
    assert _page_count(merge_pdf_bytes([base, base], strict=True)) == 2


def test_build_career_resume_raises_when_certificate_merge_fails():
    from app.services.portfolio_service import PortfolioData

    portfolio = PortfolioData(
        full_name="Анна Примерова", role="Участник", participation_status="Активный",
        departments=[], directions=[], period="", skills=[], stats={},
    )
    user = User(telegram_id=1, first_name="Анна", last_name="Примерова")
    profile = SimpleNamespace(headline="", about="", languages=[])
    with pytest.raises(ValueError):
        build_career_resume(
            user, profile, portfolio, [], purpose="universal",
            mode="portfolio_with_certificates", certificate_pdfs=[b"junk"],
        )


def test_bot_menu_path_uses_shared_assembly_and_offers_retry_on_failure():
    from app.handlers.participant import cabinet

    async def scenario(session):
        user, issues, _docs, _files = await _seed(session, hidden=False, revoked=False, documents=False)
        message = SimpleNamespace(answer=AsyncMock())
        call = SimpleNamespace(message=message, bot=FakeBot(), answer=AsyncMock(), data="portfolio:resume")
        real = export_service._certificate_pdf

        def flaky(issue, owner):
            if issue.id == issues["one"].id:
                raise RuntimeError("boom")
            return real(issue, owner)

        sender = AsyncMock(return_value=True)
        with patch.object(cabinet, "_guard", new=AsyncMock(return_value=True)), patch.object(
            cabinet, "safe_answer_document", new=sender
        ), patch.object(export_service, "_certificate_pdf", flaky):
            await cabinet.resume(call, user, session)
            sender.assert_not_awaited()
            text = message.answer.await_args.args[0]
            assert "Вечер ЭРА" in text and issues["one"].document_number in text
            buttons = [
                button.text
                for row in message.answer.await_args.kwargs["reply_markup"].inline_keyboard
                for button in row
            ]
            assert "Повторить" in buttons and "Отправить без них" in buttons

            await cabinet.resume_without_failed_attachments(call, user, session)
            sender.assert_awaited_once()
            delivered = sender.await_args.args[1].data
            assert "Без вложений" in sender.await_args.kwargs["caption"]
            assert issues["two"].document_number in _pages_text(delivered)

        sender.reset_mock()
        with patch.object(cabinet, "_guard", new=AsyncMock(return_value=True)), patch.object(
            cabinet, "safe_answer_document", new=sender
        ):
            await cabinet.resume(call, user, session)
            delivered = sender.await_args.args[1].data
            reader_text = _pages_text(delivered)
            assert issues["one"].document_number in reader_text and issues["two"].document_number in reader_text
            assert "Приложено документов: 2" in sender.await_args.kwargs["caption"]

    _run(scenario)
