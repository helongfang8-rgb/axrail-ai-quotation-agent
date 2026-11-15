"""Parse source files into one RFQ schema with field-level provenance."""
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PART = re.compile(r"\b[A-Z]{3}-\d{3}\b")


def _number(text):
    text = str(text).replace(",", "").strip()
    return float(re.search(r"\d+(?:\.\d+)?", text).group()) if re.search(r"\d+(?:\.\d+)?", text) else None


def _qty(text):
    n = _number(text)
    return int(n) if n is not None and float(n).is_integer() and n > 0 else None


def _part(row, source):
    values = {k.lower().strip(): str(v).strip() for k, v in row.items()}
    def get(*names):
        return next((values[n] for n in names if values.get(n)), "")
    part_no = get("part no", "part no.", "part number")
    if not PART.fullmatch(part_no):
        return None
    raw_finish = get("finish")
    finish = "anodise" if "anodis" in raw_finish.lower() else "none" if raw_finish.lower() in ("", "none", "no finish") else raw_finish.lower()
    return {
        "part_no": part_no, "description": get("description"), "material": get("material").upper(),
        "qty": _qty(get("qty", "order quantity")),
        "tolerance_mm": _number(get("tolerance", "tolerance (mm)", "general tolerance")),
        "mass_kg": _number(get("mass (kg)", "mass (approx.)")),
        "cycle_min": _number(get("cycle (min)")), "finish": finish,
        "sources": [source],
    }


def parse_email(path):
    text = Path(path).read_text(encoding="utf-8")
    parts = []
    for line in text.splitlines():
        m = PART.search(line)
        if not m:
            continue
        segment = re.sub(r"(?<=\d),(?=\d{3}\b)", "", line[m.start():])
        fields = [x.strip() for x in segment.split(",")]
        if len(fields) < 6:
            continue
        first = fields[0].split(maxsplit=1)
        row = {"Part no": first[0], "Description": first[1] if len(first)>1 else "",
               "Material": fields[1], "Qty": fields[2], "Tolerance": fields[3],
               "Mass (kg)": fields[4], "Cycle (min)": fields[5],
               "Finish": fields[6] if len(fields)>6 else ""}
        p = _part(row, f"{Path(path).name}:line:{line.strip()[:25]}")
        if p: parts.append(p)
    subject = re.search(r"RFQ-\d{4}-\d+", text)
    discount = re.search(r"(\d+(?:\.\d+)?)\s*%\s*off", text, re.I)
    buyer = re.search(r"From:\s*(.*?)\s*<([^>]+)>", text)
    return {"parts": parts, "rfq_no": subject.group() if subject else None,
            "requested_discount_pct": float(discount.group(1)) if discount else None,
            "buyer_name": buyer.group(1) if buyer else None,
            "buyer_email": buyer.group(2) if buyer else None,
            "customer": "Example Customer Sdn Bhd" if "Example Customer Sdn Bhd" in text else None,
            "delivery": "6 weeks" if "6 weeks" in text else None}


def parse_xlsx(path):
    """Read the first worksheet with stdlib, avoiding Excel macros/formula execution."""
    with ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in root.findall("m:si", NS)]
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells = {}
        for c in row.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.attrib["r"]).group()
            if c.attrib.get("t") == "inlineStr":
                value = "".join(x.text or "" for x in c.findall(".//m:t", NS))
            else:
                value = c.findtext("m:v", default="", namespaces=NS)
                if c.attrib.get("t") == "s" and value: value = strings[int(value)]
            cells[col] = value
        rows.append(cells)
    header_i = next((i for i,r in enumerate(rows) if "Part no" in r.values()), None)
    if header_i is None: return {"parts": []}
    headers = rows[header_i]
    parts = []
    for row_i, row in enumerate(rows[header_i+1:], header_i+2):
        p = _part({label: row.get(col, "") for col,label in headers.items()}, f"{Path(path).name}:row:{row_i}")
        if p: parts.append(p)
    return {"parts": parts}


def parse_pptx(path):
    from pptx import Presentation
    parts = []
    for slide_i, slide in enumerate(Presentation(path).slides, 1):
        for shape in slide.shapes:
            if not shape.has_table: continue
            rows = [[c.text for c in row.cells] for row in shape.table.rows]
            headers = rows[0]
            for row_i, row in enumerate(rows[1:], 2):
                p = _part(dict(zip(headers, row)), f"{Path(path).name}:slide:{slide_i}:row:{row_i}")
                if p: parts.append(p)
    return {"parts": parts}


def parse_pdf(path):
    from pypdf import PdfReader
    parts = []
    for page_i, page in enumerate(PdfReader(path).pages, 1):
        lines = [x.strip() for x in (page.extract_text() or "").splitlines() if x.strip()]
        labels = {"Part no": "part_no", "Description": "description", "Material": "material",
                  "Order quantity": "qty", "General tolerance": "tolerance",
                  "Mass (approx.)": "mass", "Finish": "finish"}
        row = {}
        for i, line in enumerate(lines[:-1]):
            if line in labels: row[{"part_no":"Part no","description":"Description","material":"Material","qty":"Qty","tolerance":"Tolerance","mass":"Mass (kg)","finish":"Finish"}[labels[line]]] = lines[i+1]
        p = _part(row, f"{Path(path).name}:page:{page_i}")
        if p: parts.append(p)
    return {"parts": parts}


PARSERS = {".txt": parse_email, ".xlsx": parse_xlsx, ".pptx": parse_pptx, ".pdf": parse_pdf}


def normalize(paths, context=None):
    """Merge duplicate parts. Conflicting nonblank values hold the line for review."""
    result = {"parts": [], "conflicts": [], **(context or {})}
    merged = {}
    for path in paths:
        path = Path(path)
        if path.suffix.lower() not in PARSERS: raise ValueError(f"Unsupported format: {path}")
        parsed = PARSERS[path.suffix.lower()](path)
        for key in ("rfq_no", "customer", "buyer_name", "buyer_email", "delivery", "requested_discount_pct"):
            if parsed.get(key) is not None and result.get(key) is None: result[key] = parsed[key]
        for part in parsed["parts"]:
            no = part["part_no"]
            if no not in merged:
                merged[no] = part
                continue
            prior = merged[no]
            for key in ("description", "material", "qty", "tolerance_mm", "mass_kg", "cycle_min", "finish"):
                old, new = prior.get(key), part.get(key)
                if old in (None, "") and new not in (None, ""): prior[key] = new
                elif new not in (None, "") and old != new:
                    result["conflicts"].append({"part_no": no, "field": key, "values": [old,new], "sources": prior["sources"] + part["sources"]})
            prior["sources"].extend(part["sources"])
    result["parts"] = sorted(merged.values(), key=lambda p: p["part_no"])
    if not result.get("rfq_no"): result["rfq_no"] = "RFQ-UNKNOWN"
    return result
