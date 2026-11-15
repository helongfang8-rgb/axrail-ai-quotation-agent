"""Deterministic pricing. All monetary arithmetic uses Decimal."""
from decimal import Decimal, ROUND_HALF_UP

MATERIAL_MYR_PER_KG = {"AL6061": Decimal("18.00"), "SS304": Decimal("22.00")}
MACHINE_RATE_MYR_PER_MIN = {"3-axis": Decimal("2.00"), "5-axis": Decimal("3.50")}
SETUP_MYR = Decimal("250.00")
ANODISE_MYR = Decimal("1.50")
MARGIN = Decimal("0.25")


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_line(part):
    """Return quote arithmetic or explicit hold reasons; never guess a table value."""
    reasons = []
    qty = part.get("qty")
    if not isinstance(qty, int) or qty <= 0:
        reasons.append("Quantity is missing or invalid")
    material = str(part.get("material") or "").upper().strip()
    if material not in MATERIAL_MYR_PER_KG:
        reasons.append(f"No standard material price for {material or 'unknown material'}")
    try:
        tolerance = Decimal(str(part["tolerance_mm"]))
        mass = Decimal(str(part["mass_kg"]))
        cycle = Decimal(str(part["cycle_min"]))
        if tolerance <= 0 or mass <= 0 or cycle <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError, ArithmeticError):
        reasons.append("Tolerance, mass or cycle time is missing or invalid")
        tolerance = None
    machine = None
    if tolerance is not None:
        if tolerance < Decimal("0.02"):
            reasons.append("Tolerance tighter than ±0.02 mm has no standard machine rate")
        elif tolerance < Decimal("0.05"):
            machine = "5-axis"
        else:
            machine = "3-axis"
    finish = str(part.get("finish") or "none").lower().strip()
    if finish not in ("none", "anodise"):
        reasons.append(f"No standard finish price for {finish}")
    if reasons:
        return {"status": "hold", "reasons": reasons, "part_no": part.get("part_no")}

    material_cost = mass * MATERIAL_MYR_PER_KG[material]
    machine_cost = cycle * MACHINE_RATE_MYR_PER_MIN[machine]
    finish_cost = ANODISE_MYR if finish == "anodise" else Decimal("0")
    setup_per_unit = SETUP_MYR / Decimal(qty)
    unit_cost = material_cost + machine_cost + finish_cost + setup_per_unit
    list_unit = money(unit_cost / (Decimal("1") - MARGIN))
    discount = Decimal("0.08") if qty >= 1000 else Decimal("0.05") if qty >= 500 else Decimal("0")
    sell_unit = money(list_unit * (Decimal("1") - discount))
    line_total = money(sell_unit * qty)
    return {
        "status": "priced", "part_no": part["part_no"], "qty": qty,
        "machine": machine, "material_rate": str(MATERIAL_MYR_PER_KG[material]),
        "machine_rate": str(MACHINE_RATE_MYR_PER_MIN[machine]),
        "material_cost": str(money(material_cost)), "machine_cost": str(money(machine_cost)),
        "finish_cost": str(money(finish_cost)), "setup_per_unit": str(money(setup_per_unit)),
        "unit_cost": str(money(unit_cost)), "list_unit": str(list_unit),
        "discount_pct": str(discount * 100), "unit_price": str(sell_unit),
        "line_total": str(line_total),
        "rule": "(mass × material rate + cycle × machine rate + finish + 250/qty) / (1−0.25), then volume discount",
    }


def approval_policy(lines, requested_discount_pct=None):
    """Conservative, stated assumption: MYR 20,000+ or non-standard discount needs approval."""
    total = sum((Decimal(x["line_total"]) for x in lines if x["status"] == "priced"), Decimal("0"))
    requested = Decimal(str(requested_discount_pct or 0))
    reasons = []
    if total >= Decimal("20000"):
        reasons.append("Quote total is at least MYR 20,000")
    if requested > Decimal("8"):
        reasons.append(f"Customer requested {requested}% discount above the standard maximum of 8%")
    if any(x["status"] == "hold" for x in lines):
        reasons.append("One or more lines require estimator review")
    return {"status": "pending_manager_approval" if reasons else "not_required", "reasons": reasons, "total_myr": str(money(total))}
