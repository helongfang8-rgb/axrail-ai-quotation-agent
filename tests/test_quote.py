from datetime import date
from decimal import Decimal
from pathlib import Path
import json
from quotation_agent.pricing import price_line
from quotation_agent.workflow import build_quote

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "inputs"
CONTEXT = json.loads((ROOT / "demo_context.json").read_text())


def test_worked_example_and_margin():
    p = {"part_no":"BRK-100","material":"AL6061","qty":500,"tolerance_mm":0.10,
         "mass_kg":0.40,"cycle_min":6,"finish":"anodise"}
    result = price_line(p)
    assert result["unit_cost"] == "21.20"
    assert result["list_unit"] == "28.27"
    assert result["discount_pct"] == "5.00"
    assert result["unit_price"] == "26.86"
    assert result["line_total"] == "13430.00"


def test_missing_rates_and_qty_hold():
    base = {"part_no":"X","material":"SS304","qty":1,"tolerance_mm":0.1,
            "mass_kg":1,"cycle_min":2,"finish":"none"}
    assert price_line({**base,"qty":None})["status"] == "hold"
    assert price_line({**base,"material":"Ti Gr5","tolerance_mm":0.005})["status"] == "hold"


def test_email_and_attachment_quote_match():
    a = build_quote([INPUT / "rfq_email.txt"], CONTEXT, date(2026,11,13))
    b = build_quote([INPUT / "part_list.xlsx", INPUT / "part_spec.pptx"], CONTEXT, date(2026,11,13))
    for q in (a,b):
        assert q["total_myr"] == "74684.00"
        assert {x["part_no"] for x in q["lines"] if x["status"] == "hold"} == {"SPC-050","HSG-400"}
        assert q["approval"]["status"] == "pending_manager_approval"
    assert [(x["part_no"],x["status"],x.get("unit_price")) for x in a["lines"]] == [(x["part_no"],x["status"],x.get("unit_price")) for x in b["lines"]]


def test_pdf_conflict_holds_cover():
    files = [INPUT / x for x in ("rfq_email.txt","part_list.xlsx","part_spec.pptx","drawing_CVR-310_RevB.pdf")]
    q = build_quote(files, CONTEXT, date(2026,11,13))
    cover = next(x for x in q["lines"] if x["part_no"] == "CVR-310")
    assert cover["status"] == "hold"
    assert "Conflicting qty" in cover["reasons"][0]
    assert q["total_myr"] == "24334.00"
