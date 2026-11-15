"""Explicit review-first workflow; no model can set a price."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import json

from .ingest import normalize
from .pricing import approval_policy, money, price_line


def build_quote(paths, context=None, today=None, price_tool=price_line, approval_tool=approval_policy, extractor=None):
    today = today or date.today()
    rfq = normalize(paths, context, extractor=extractor)
    conflict_by_part = {}
    for conflict in rfq["conflicts"]:
        if conflict["field"] in ("material", "qty", "tolerance_mm", "mass_kg", "cycle_min", "finish"):
            conflict_by_part.setdefault(conflict["part_no"], []).append(conflict)
    lines, review = [], []
    for part in rfq["parts"]:
        priced = price_tool(part)
        if part["part_no"] in conflict_by_part:
            priced = {"status": "hold", "part_no": part["part_no"],
                      "reasons": [f"Conflicting {c['field']}: {c['values']} ({', '.join(c['sources'])})" for c in conflict_by_part[part["part_no"]]]}
        line = {"part_no": part["part_no"], "description": part["description"],
                "material": part["material"], "qty": part["qty"], "sources": part["sources"],
                "field_evidence": part.get("field_evidence", {}), **priced}
        lines.append(line)
        if line["status"] == "hold":
            review.append({"part_no": part["part_no"], "owner": "estimator", "status": "open", "reasons": line["reasons"]})
    approval = approval_tool(lines, rfq.get("requested_discount_pct"))
    if rfq.get("requested_discount_pct") and Decimal(str(rfq["requested_discount_pct"])) > Decimal("8"):
        review.append({"part_no": "ALL", "owner": "sales manager", "status": "open",
                       "reasons": [f"Customer requested {rfq['requested_discount_pct']}% off; standard volume discounts only were applied"]})
    if approval["status"] == "pending_manager_approval":
        review.append({"part_no": "QUOTE", "owner": "sales manager", "status": "open", "reasons": approval["reasons"]})
    for issue in rfq.get("extraction_issues", []):
        review.append({"part_no": issue["part_no"], "owner": "estimator", "status": "open",
                       "reasons": [issue["message"]]})
    result = {"quote_no": f"Q-{rfq['rfq_no']}", "rfq_no": rfq["rfq_no"],
              "customer": rfq.get("customer") or "Customer not provided",
              "buyer_name": rfq.get("buyer_name") or "Buyer",
              "buyer_email": rfq.get("buyer_email"), "date": today.isoformat(),
              "valid_until": (today + timedelta(days=30)).isoformat(),
              "currency": "MYR", "delivery": rfq.get("delivery") or "To confirm",
              "requested_discount_pct": rfq.get("requested_discount_pct"),
              "extraction_audit": rfq.get("extraction_audit", []),
              "lines": lines, "total_myr": approval["total_myr"], "approval": approval,
              "review": review,
              "assumptions": [
                  "25% gross margin means selling price = unit cost / 0.75 before volume discount.",
                  "Standard discount is 5% for 500-999 pcs, 8% for 1,000+ pcs, otherwise 0%.",
                  "A quote of MYR 20,000 or more requires sales manager approval (assumed threshold).",
                  "Quoted prices exclude tax, freight and special inspection; lead time requires confirmation.",
                  "Held lines are excluded from the total; no customer email is sent automatically.",
              ]}
    result["email_draft"] = email_draft(result)
    return result


def email_draft(quote):
    holds = [x for x in quote["lines"] if x["status"] == "hold"]
    requests = []
    for h in holds:
        if h["part_no"] == "SPC-050": requests.append("the quantity for SPC-050")
        elif h["part_no"] == "HSG-400": requests.append("a machinability and tolerance review for HSG-400")
        else: requests.append(f"clarification of {h['part_no']} specifications")
    requested = quote.get("requested_discount_pct")
    discount_note = (f"Your request for {requested:g}% off has been referred to our sales manager; the attached draft uses our standard volume discounts. "
                     if requested else "")
    approval = "This quote is pending internal approval and is not yet a final offer. " if quote["approval"]["status"] != "not_required" else ""
    delivery_note = (f"The {quote['delivery']} delivery target is subject to production confirmation. "
                     if quote["delivery"] != "To confirm" else "Please also confirm the delivery target. ")
    return (f"To: {quote.get('buyer_email') or '[buyer email]'}\nSubject: Draft quotation {quote['quote_no']} for {quote['rfq_no']}\n\n"
            f"Dear {quote['buyer_name'].split()[0]},\n\nPlease find attached our draft quotation for the priced items in {quote['rfq_no']}, totaling MYR {quote['total_myr']}. "
            f"{approval}{discount_note}We have placed {', '.join(h['part_no'] for h in holds) or 'no items'} on hold. "
            f"Please confirm {', '.join(requests) if requests else 'the requested delivery date'}. "
            f"{delivery_note}The quotation is valid until {quote['valid_until']}.\n\nBest regards,\nSales Team\n")


def write_outputs(quote, output_dir):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "quote.json").write_text(json.dumps(quote, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "email_draft.txt").write_text(quote["email_draft"], encoding="utf-8")
    (out / "review.json").write_text(json.dumps(quote["review"], indent=2, ensure_ascii=False), encoding="utf-8")
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out / "quotation.pdf"), pagesize=A4, leftMargin=36, rightMargin=36)
    story = [Paragraph("DRAFT QUOTATION", styles["Title"]), Spacer(1, 10),
             Paragraph(f"Quote: {escape(quote['quote_no'])} &nbsp;&nbsp; Date: {quote['date']} &nbsp;&nbsp; Valid until: {quote['valid_until']}", styles["Normal"]),
             Paragraph(f"Customer: {escape(quote['customer'])} &nbsp;&nbsp; Currency: MYR", styles["Normal"]), Spacer(1, 15)]
    table = [["Part", "Material", "Qty", "Unit (MYR)", "Disc.", "Total (MYR)"]]
    for x in quote["lines"]:
        if x["status"] == "priced":
            table.append([x["part_no"], x["material"], str(x["qty"]), x["unit_price"], x["discount_pct"] + "%", x["line_total"]])
    t = Table(table, colWidths=[100,75,50,90,60,100], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0), colors.HexColor("#17324D")),
                           ("TEXTCOLOR",(0,0),(-1,0), colors.white),
                           ("GRID",(0,0),(-1,-1),0.35,colors.lightgrey),
                           ("ALIGN",(2,1),(-1,-1),"RIGHT"), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                           ("BOTTOMPADDING",(0,0),(-1,-1),8), ("TOPPADDING",(0,0),(-1,-1),8)]))
    story += [t, Spacer(1, 10), Paragraph(f"<b>Total: MYR {quote['total_myr']}</b>", styles["Heading2"])]
    story += [Paragraph("Lines on hold", styles["Heading3"])]
    for x in quote["lines"]:
        if x["status"] == "hold": story.append(Paragraph(f"{x['part_no']}: {escape('; '.join(x['reasons']))}", styles["Normal"]))
    story += [Paragraph("Assumptions and status", styles["Heading3"])]
    for item in quote["assumptions"]: story.append(Paragraph("- " + escape(item), styles["Normal"]))
    story.append(Paragraph(f"Approval: {quote['approval']['status'].replace('_',' ')}", styles["Normal"]))
    story.append(Paragraph("Pricing audit", styles["Heading3"]))
    for x in quote["lines"]:
        if x["status"] != "priced": continue
        audit = (f"{x['part_no']}: material MYR {x['material_rate']}/kg; machine {x['machine']} MYR {x['machine_rate']}/min; "
                 f"material {x['material_cost']} + machine {x['machine_cost']} + finish {x['finish_cost']} + setup/unit {x['setup_per_unit']} "
                 f"= cost {x['unit_cost']}; /0.75 = list {x['list_unit']}; discount {x['discount_pct']}% = unit {x['unit_price']}. "
                 f"Source: {', '.join(x['sources'])}.")
        story.append(Paragraph(escape(audit), styles["Normal"]))
        story.append(Spacer(1, 5))
    story.append(Paragraph("Draft for review. Do not send until approved.", styles["Italic"]))
    doc.build(story)
    return out
