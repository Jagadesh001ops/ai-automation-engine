"""PDF and Anki export utilities (Days 16-17)."""
from __future__ import annotations

import contextlib
import io
import json

# ─── PDF export (Day 16) ──────────────────────────────────────────────────────

def generate_pdf(run) -> bytes:
    """Return PDF bytes for a workflow run using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:
        raise RuntimeError(
            "reportlab not installed — run: pip install reportlab"
        ) from exc

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter,
                            leftMargin=1*inch, rightMargin=1*inch,
                            topMargin=1*inch, bottomMargin=1*inch)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18, spaceAfter=12)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceAfter=6)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    q_style = ParagraphStyle("q", parent=styles["Normal"], fontSize=11,
                              fontName="Helvetica-Bold", spaceAfter=4)

    story = []
    story.append(Paragraph(f"Study Kit: Run #{run.id}", title_style))
    story.append(Paragraph(f"Goal: {run.goal or ''}", body_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 0.15*inch))

    output_data = {}
    if run.output_json:
        with contextlib.suppress(Exception):
            output_data = json.loads(run.output_json)

    # Summary section
    summary = output_data.get("summary") or run.summary
    if summary:
        story.append(Paragraph("Summary", h2_style))
        story.append(Paragraph(str(summary), body_style))
        story.append(Spacer(1, 0.15*inch))

    # Concepts section
    concepts = output_data.get("concepts")
    if concepts:
        story.append(Paragraph("Key Concepts", h2_style))
        if isinstance(concepts, list):
            for c in concepts:
                story.append(Paragraph(f"• {c}", body_style))
        else:
            story.append(Paragraph(str(concepts), body_style))
        story.append(Spacer(1, 0.15*inch))

    # Quiz section
    quiz_items = output_data.get("quiz_items") or output_data.get("verified_quiz_items")
    if quiz_items:
        if isinstance(quiz_items, str):
            try:
                quiz_items = json.loads(quiz_items)
            except Exception:
                quiz_items = []
        story.append(Paragraph("Quiz Questions", h2_style))
        for i, item in enumerate(quiz_items, 1):
            story.append(Paragraph(f"Q{i}. {item.get('question', '')}", q_style))
            opts = item.get("options", {})
            for letter, text in opts.items():
                marker = " *" if letter == item.get("answer") else ""
                story.append(Paragraph(f"   {letter}. {text}{marker}", body_style))
            expl = item.get("explanation", "")
            if expl:
                story.append(Paragraph(f"   Explanation: {expl}", body_style))
            story.append(Spacer(1, 0.08*inch))

    doc.build(story)
    return output.getvalue()


# ─── Anki export (Day 17) ─────────────────────────────────────────────────────

def generate_anki(run) -> bytes:
    """Return .apkg bytes for a workflow run using genanki."""
    try:
        import genanki
    except ImportError as exc:
        raise RuntimeError(
            "genanki not installed — run: pip install genanki"
        ) from exc

    output_data = {}
    if run.output_json:
        with contextlib.suppress(Exception):
            output_data = json.loads(run.output_json)

    quiz_items = output_data.get("quiz_items") or output_data.get("verified_quiz_items") or []
    if isinstance(quiz_items, str):
        try:
            quiz_items = json.loads(quiz_items)
        except Exception:
            quiz_items = []

    deck_id = abs(hash(f"workflow-{run.id}")) % (10**10)
    model_id = abs(hash("ai-workflow-engine-quiz-model")) % (10**10)

    model = genanki.Model(
        model_id,
        "AI Workflow Quiz",
        fields=[
            {"name": "Question"},
            {"name": "Options"},
            {"name": "Answer"},
            {"name": "Explanation"},
        ],
        templates=[{
            "name": "Card 1",
            "qfmt": "{{Question}}<br><br>{{Options}}",
            "afmt": '{{FrontSide}}<hr id="answer"><b>Answer: {{Answer}}</b><br>{{Explanation}}',
        }],
    )

    deck = genanki.Deck(deck_id, f"AI Workflow Engine — Run #{run.id}")

    for item in quiz_items:
        opts = item.get("options", {})
        opts_html = "<br>".join(f"{k}. {v}" for k, v in opts.items())
        note = genanki.Note(
            model=model,
            fields=[
                item.get("question", ""),
                opts_html,
                item.get("answer", ""),
                item.get("explanation", ""),
            ],
        )
        deck.add_note(note)

    pkg = genanki.Package(deck)
    buf = io.BytesIO()
    pkg.write_to_file(buf)
    return buf.getvalue()
