"""
VeriDictum AI — Report Generation Celery Task
PDF contradiction intelligence reports via ReportLab.
"""

import io
import logging
import uuid
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Case, Contradiction, ContradictionSeverity, NLQuery, Report, ReportStatus, Transcript
from app.tasks.celery_app import celery_app
from app.utils.storage import build_report_blob_name, generate_sas_url, upload_blob

logger = logging.getLogger(__name__)

NAVY = colors.HexColor("#1B2B5E")
GOLD = colors.HexColor("#C9A84C")
CRITICAL_RED = colors.HexColor("#DC2626")
HIGH_ORANGE = colors.HexColor("#EA580C")
MEDIUM_YELLOW = colors.HexColor("#D97706")
LOW_BLUE = colors.HexColor("#2563EB")
INFO_GRAY = colors.HexColor("#6B7280")

SEVERITY_COLORS = {
    ContradictionSeverity.CRITICAL: CRITICAL_RED,
    ContradictionSeverity.HIGH: HIGH_ORANGE,
    ContradictionSeverity.MEDIUM: MEDIUM_YELLOW,
    ContradictionSeverity.LOW: LOW_BLUE,
    ContradictionSeverity.INFORMATIONAL: INFO_GRAY,
}


def _get_db_session() -> Session:
    engine = create_engine(settings.SYNC_DATABASE_URL)
    return Session(engine)


def _build_pdf(report: Report, case: Case, contradictions, queries) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1 * inch,
        bottomMargin=0.75 * inch,
        title=report.title,
        author="Sarvam Nyaya",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", fontSize=20, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=8)
    heading_style = ParagraphStyle("Heading", fontSize=14, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=6, spaceBefore=12)
    sub_style = ParagraphStyle("Sub", fontSize=11, fontName="Helvetica-Bold", textColor=GOLD, spaceAfter=4)
    body_style = ParagraphStyle("Body", fontSize=10, fontName="Helvetica", spaceAfter=4, leading=14)
    caption_style = ParagraphStyle("Caption", fontSize=9, fontName="Helvetica-Oblique", textColor=colors.gray)

    elements = []

    # --- Cover ---
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph("SARVAM NYAYA", ParagraphStyle("Brand", fontSize=11, textColor=GOLD, fontName="Helvetica-Bold")))
    elements.append(Paragraph("Contradiction Intelligence Report", title_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=GOLD))
    elements.append(Spacer(1, 0.2 * inch))

    meta = [
        ["Case Number:", case.case_number or "N/A"],
        ["Case Title:", case.title],
        ["Court:", case.court or "N/A"],
        ["Jurisdiction:", case.jurisdiction or "N/A"],
        ["Report Generated:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
        ["Total Contradictions:", str(len(contradictions))],
    ]
    meta_table = Table(meta, colWidths=[2 * inch, 4.5 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8F9FF")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.3 * inch))

    # --- AI Disclaimer ---
    elements.append(Paragraph(
        "⚠ ATTORNEY REVIEW REQUIRED: All contradictions below are AI-suggested and require review by a licensed attorney before use in legal proceedings. Sarvam Nyaya does not provide legal advice.",
        ParagraphStyle("Disclaimer", fontSize=9, textColor=colors.HexColor("#7F1D1D"), backColor=colors.HexColor("#FEF2F2"),
                       borderColor=colors.HexColor("#DC2626"), borderWidth=1, borderPadding=6, spaceAfter=8),
    ))

    # --- Summary Stats ---
    elements.append(PageBreak())
    elements.append(Paragraph("Executive Summary", heading_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=GOLD))

    severity_counts = {}
    for c in contradictions:
        severity_counts[c.severity] = severity_counts.get(c.severity, 0) + 1

    summary_data = [["Severity", "Count", "Action Required"]]
    severity_actions = {
        ContradictionSeverity.CRITICAL: "Immediate attorney review",
        ContradictionSeverity.HIGH: "Priority review recommended",
        ContradictionSeverity.MEDIUM: "Review before trial",
        ContradictionSeverity.LOW: "Review at discretion",
        ContradictionSeverity.INFORMATIONAL: "For reference",
    }
    for sev in ContradictionSeverity:
        count = severity_counts.get(sev, 0)
        summary_data.append([sev.value, str(count), severity_actions.get(sev, "")])

    summary_table = Table(summary_data, colWidths=[2 * inch, 1.5 * inch, 3 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FF")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(summary_table)

    # --- Contradictions Detail ---
    if report.include_contradictions and contradictions:
        elements.append(PageBreak())
        elements.append(Paragraph("Contradiction Detail", heading_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=GOLD))

        for i, c in enumerate(contradictions, 1):
            sev_color = SEVERITY_COLORS.get(c.severity, INFO_GRAY)
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(Paragraph(
                f"Contradiction #{i} — {c.severity.value}",
                ParagraphStyle(f"ContHead{i}", fontSize=12, fontName="Helvetica-Bold", textColor=sev_color),
            ))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=sev_color))

            detail_data = [
                ["Field", "Value"],
                ["Severity", c.severity.value],
                ["Confidence", f"{c.confidence_score:.0%}"],
                ["Type", c.contradiction_type or "N/A"],
                ["Status", c.status.value],
                ["Speaker", c.transcript_speaker or "Unknown"],
                ["Timestamp", f"{c.transcript_timestamp_start:.1f}s" if c.transcript_timestamp_start else "N/A"],
                ["Document Page", str(c.document_page) if c.document_page else "N/A"],
            ]
            detail_table = Table(detail_data, colWidths=[2 * inch, 4.5 * inch])
            detail_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FF")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(detail_table)
            elements.append(Spacer(1, 0.1 * inch))

            elements.append(Paragraph("Transcript Statement:", sub_style))
            elements.append(Paragraph(f'"{c.transcript_text}"', body_style))
            elements.append(Paragraph("Documentary Evidence:", sub_style))
            elements.append(Paragraph(f'"{c.document_text}"', body_style))
            elements.append(Paragraph("AI Analysis:", sub_style))
            elements.append(Paragraph(c.explanation, body_style))

            if c.attorney_notes:
                elements.append(Paragraph("Attorney Notes:", sub_style))
                elements.append(Paragraph(c.attorney_notes, body_style))

    # --- Footer ---
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(width="100%", thickness=1, color=GOLD))
    elements.append(Paragraph(
        f"Generated by Sarvam Nyaya — Confidential — Attorney Work Product — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        caption_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


@celery_app.task(
    name="app.tasks.report.generate_report",
    bind=True,
    # Report generation talks to Azure Blob (for upload) and is otherwise
    # CPU-bound on ReportLab. Auto-retry transient blob failures with
    # exponential backoff + jitter.
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def generate_report(self, report_id: str) -> dict:
    with _get_db_session() as db:
        report = db.get(Report, report_id)
        if not report:
            return {"status": "error"}

        report.status = ReportStatus.GENERATING
        db.commit()

        try:
            case = db.get(Case, report.case_id)

            contradictions = db.execute(
                select(Contradiction).where(Contradiction.case_id == report.case_id)
                .order_by(Contradiction.severity, Contradiction.confidence_score.desc())
            ).scalars().all() if report.include_contradictions else []

            queries = db.execute(
                select(NLQuery).where(NLQuery.case_id == report.case_id)
                .order_by(NLQuery.created_at.desc())
                .limit(50)
            ).scalars().all() if report.include_nl_query_log else []

            pdf_bytes = _build_pdf(report, case, contradictions, queries)

            # Upload to Azure Blob
            blob_name = build_report_blob_name(report.case_id, report.id, "pdf")
            upload_blob(
                settings.AZURE_STORAGE_CONTAINER_REPORTS,
                blob_name,
                pdf_bytes,
                content_type="application/pdf",
            )

            download_url = generate_sas_url(
                settings.AZURE_STORAGE_CONTAINER_REPORTS,
                blob_name,
                expiry_hours=24,
            )

            report.blob_path = f"{settings.AZURE_STORAGE_CONTAINER_REPORTS}/{blob_name}"
            report.download_url = download_url
            report.download_url_expires_at = datetime.now(timezone.utc).replace(hour=0) + \
                                              __import__("datetime").timedelta(days=1)
            report.status = ReportStatus.COMPLETE
            report.completed_at = datetime.now(timezone.utc)
            report.page_count = len(pdf_bytes) // 3000 + 1
            db.commit()

            logger.info(f"Report {report_id} generated successfully")
            return {"status": "complete", "download_url": download_url}

        except Exception as exc:
            logger.exception(f"Report generation failed for {report_id}: {exc}")
            report.status = ReportStatus.FAILED
            report.error_message = str(exc)[:1000]
            db.commit()
            raise self.retry(exc=exc, countdown=60)
