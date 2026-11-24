"""Participation certificate PDF carries brand assets."""

from datetime import date

from app.services.certificate_pdf_service import SEAL_PATH, build_certificate_pdf


def test_seal_asset_exists():
    assert SEAL_PATH.exists()


def test_build_certificate_pdf_returns_pdf_bytes():
    pdf = build_certificate_pdf(
        {
            "full_name": "Давид Багдасарян",
            "event_title": "Тестовое мероприятие ЭРА",
            "event_date": date.today().isoformat(),
            "signatory": "Багдасарян Д.С.",
            "template_version": "era-event-v2",
        },
        number="ERA-CERT-TEST-1",
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000
