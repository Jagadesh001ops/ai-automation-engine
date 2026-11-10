"""Tests for engine/export.py — PDF and Anki export."""
import io
import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_run(
    id_=1,
    goal="Summarise Chapter 5",
    summary="Print culture transformed society.",
    concepts=None,
    quiz_items=None,
    output_json=None,
):
    run = MagicMock()
    run.id = id_
    run.goal = goal
    run.summary = summary
    data = {}
    if concepts is not None:
        data["concepts"] = concepts
    if quiz_items is not None:
        data["quiz_items"] = quiz_items
    run.output_json = output_json if output_json is not None else (
        json.dumps(data) if data else None
    )
    return run


# ── PDF — missing reportlab ───────────────────────────────────────────────────

def test_generate_pdf_raises_if_no_reportlab():
    with patch.dict(sys.modules, {"reportlab": None,
                                   "reportlab.lib": None,
                                   "reportlab.lib.pagesizes": None,
                                   "reportlab.lib.styles": None,
                                   "reportlab.lib.units": None,
                                   "reportlab.lib.colors": None,
                                   "reportlab.platypus": None}):
        # Force re-import attempt inside function
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        with pytest.raises((RuntimeError, ImportError)):
            exp.generate_pdf(_make_run())


# ── PDF — happy path with mocked reportlab ───────────────────────────────────

def _mock_reportlab():
    """Return a sys.modules patch dict that stubs out reportlab."""
    rl = ModuleType("reportlab")
    rl_lib = ModuleType("reportlab.lib")
    rl_pages = ModuleType("reportlab.lib.pagesizes")
    rl_pages.letter = (612, 792)
    rl_styles = ModuleType("reportlab.lib.styles")
    rl_styles.getSampleStyleSheet = MagicMock(return_value=MagicMock())
    rl_styles.ParagraphStyle = MagicMock(side_effect=lambda *a, **kw: MagicMock())
    rl_units = ModuleType("reportlab.lib.units")
    rl_units.inch = 72
    rl_colors = ModuleType("reportlab.lib.colors")
    rl_colors.grey = "grey"
    rl_platypus = ModuleType("reportlab.platypus")

    # Fake doc that writes some bytes on build()
    fake_doc = MagicMock()
    def fake_build(story):
        pass
    fake_doc.build.side_effect = fake_build
    rl_platypus.SimpleDocTemplate = MagicMock(return_value=fake_doc)
    rl_platypus.Paragraph = MagicMock(return_value=MagicMock())
    rl_platypus.Spacer = MagicMock(return_value=MagicMock())
    rl_platypus.Table = MagicMock(return_value=MagicMock())
    rl_platypus.TableStyle = MagicMock(return_value=MagicMock())
    rl_platypus.HRFlowable = MagicMock(return_value=MagicMock())

    return {
        "reportlab": rl,
        "reportlab.lib": rl_lib,
        "reportlab.lib.pagesizes": rl_pages,
        "reportlab.lib.styles": rl_styles,
        "reportlab.lib.units": rl_units,
        "reportlab.lib.colors": rl_colors,
        "reportlab.platypus": rl_platypus,
    }


def test_generate_pdf_returns_bytes_basic():
    with patch.dict(sys.modules, _mock_reportlab()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        result = exp.generate_pdf(_make_run())
    assert isinstance(result, bytes)


def test_generate_pdf_with_concepts_list():
    with patch.dict(sys.modules, _mock_reportlab()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(concepts=["Gutenberg press", "Print revolution", "Woodblock printing"])
        result = exp.generate_pdf(run)
    assert isinstance(result, bytes)


def test_generate_pdf_with_quiz_items():
    items = [{"question": "Who invented the printing press?",
              "options": {"A": "Gutenberg", "B": "Polo"},
              "answer": "A", "explanation": "Gutenberg invented it in 1430s."}]
    with patch.dict(sys.modules, _mock_reportlab()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(quiz_items=items)
        result = exp.generate_pdf(run)
    assert isinstance(result, bytes)


def test_generate_pdf_with_quiz_items_as_json_string():
    items = [{"question": "Q?", "options": {"A": "Yes", "B": "No"}, "answer": "A", "explanation": ""}]
    with patch.dict(sys.modules, _mock_reportlab()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(output_json=json.dumps({"quiz_items": json.dumps(items)}))
        result = exp.generate_pdf(run)
    assert isinstance(result, bytes)


def test_generate_pdf_no_summary_or_quiz():
    with patch.dict(sys.modules, _mock_reportlab()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(summary=None, output_json="{}")
        run.summary = None
        result = exp.generate_pdf(run)
    assert isinstance(result, bytes)


# ── Anki — missing genanki ────────────────────────────────────────────────────

def test_generate_anki_raises_if_no_genanki():
    with patch.dict(sys.modules, {"genanki": None}):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        with pytest.raises((RuntimeError, ImportError)):
            exp.generate_anki(_make_run())


# ── Anki — happy path with mocked genanki ────────────────────────────────────

def _mock_genanki():
    gn = ModuleType("genanki")
    gn.Model = MagicMock(return_value=MagicMock())
    gn.Deck = MagicMock(return_value=MagicMock())
    gn.Note = MagicMock(return_value=MagicMock())

    # Package writes bytes to the buffer
    fake_pkg = MagicMock()
    def fake_write(buf):
        buf.write(b"PK\x03\x04fake-anki-bytes")
    fake_pkg.write_to_file.side_effect = fake_write
    gn.Package = MagicMock(return_value=fake_pkg)
    return {"genanki": gn}


def test_generate_anki_returns_bytes():
    with patch.dict(sys.modules, _mock_genanki()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        result = exp.generate_anki(_make_run())
    assert isinstance(result, bytes)


def test_generate_anki_with_quiz_items():
    items = [{"question": "What year did Gutenberg perfect the press?",
              "options": {"A": "1448", "B": "1517"},
              "answer": "A", "explanation": "By 1448 the system was perfected."}]
    with patch.dict(sys.modules, _mock_genanki()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(quiz_items=items)
        result = exp.generate_anki(run)
    assert isinstance(result, bytes)


def test_generate_anki_empty_quiz_items():
    with patch.dict(sys.modules, _mock_genanki()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(quiz_items=[])
        result = exp.generate_anki(run)
    assert isinstance(result, bytes)


def test_generate_anki_quiz_items_as_json_string():
    items = [{"question": "Q?", "options": {"A": "Yes"}, "answer": "A", "explanation": ""}]
    with patch.dict(sys.modules, _mock_genanki()):
        import importlib
        import engine.export as exp
        importlib.reload(exp)
        run = _make_run(output_json=json.dumps({"quiz_items": json.dumps(items)}))
        result = exp.generate_anki(run)
    assert isinstance(result, bytes)
