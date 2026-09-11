#!/usr/bin/env python3
"""Create the accuracy-reviewed GG customer one-pager as a single-page PDF."""

from pathlib import Path
from textwrap import wrap

OUT = Path(__file__).resolve().parents[1] / "deliverables" / "GG_OnePager_Updated.pdf"


def esc(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("—", "-").replace("→", ">")


commands = []
NAVY = (.08, .17, .22)
TEAL = (.13, .34, .43)
SLATE = (.24, .29, .33)
LIGHT = (.95, .97, .98)
WHITE = (1, 1, 1)


def rect(x, y, w, h, color):
    commands.append(f"{color[0]} {color[1]} {color[2]} rg {x} {y} {w} {h} re f")


def line(x1, y1, x2, y2, color=(.82, .86, .88), width=.5):
    commands.append(f"{color[0]} {color[1]} {color[2]} RG {width} w {x1} {y1} m {x2} {y2} l S")


def txt(x, y, value, size=8, bold=False, color=SLATE):
    font = "F2" if bold else "F1"
    commands.append(f"BT /{font} {size} Tf {color[0]} {color[1]} {color[2]} rg {x} {y} Td ({esc(value)}) Tj ET")


def paragraph(x, y, value, width, size=8, leading=9.6, bold=False, color=SLATE):
    chars = max(12, int(width / (size * .50)))
    for row in wrap(value, chars, break_long_words=False):
        txt(x, y, row, size, bold, color)
        y -= leading
    return y


def bullet(x, y, value, width, size=7.7):
    txt(x, y, "•", size, True, TEAL)
    return paragraph(x + 10, y, value, width - 10, size, 9.2)


# Minimal title area
txt(40, 810, "GenuineGigs", 10.5, True, TEAL)
txt(40, 780, "AI-assisted procurement and plant coordination", 19, True, NAVY)
txt(40, 756, "for manufacturing teams", 19, True, NAVY)
intro = ("GenuineGigs works alongside the existing ERP to help employees complete procurement and inbound-material work faster. "
         "Role-specific assistants prepare documents, compare supplier quotations, coordinate tasks and governed follow-ups, and "
         "guide users through each step while employees retain control over approvals and commercial decisions.")
paragraph(40, 733, intro, 515, 8.6, 10.4)

# Problems table
txt(40, 680, "Problems addressed", 12, True, NAVY)
x0, split, x2 = 44, 278, 551
top, header_bottom = 662, 640
rect(x0, header_bottom, split-x0, top-header_bottom, TEAL)
rect(split, header_bottom, x2-split, top-header_bottom, TEAL)
txt(51, 647, "Current difficulty", 8.6, True, WHITE)
txt(285, 647, "How GenuineGigs helps", 8.6, True, WHITE)
rows = [
    ("Work is spread across email, Excel, PDFs, calls and ERP screens.", "Brings requirements, supplier documents, tasks, approvals and status into one connected workflow."),
    ("Supplier quotations take hours to read and compare manually.", "Extracts prices, taxes, freight, dates, terms and deviations from PDF, image or Excel quotations, then prepares a comparison for review."),
    ("Managers spend time chasing updates and pending approvals.", "Prepares follow-ups and creates governed internal update requests for the responsible role; highlights overdue tasks and blockers."),
    ("Handoffs between Purchase, Gate, Stores and Quality are disconnected.", "Carries PO, receipt, inspection, evidence and exception context across departments while keeping role ownership clear."),
    ("Employees depend on experienced colleagues to understand procedures.", "Role assistants explain the next step, retrieve relevant records and help prepare the required document or action in plain language."),
]
y_top = header_bottom
heights = [31, 42, 42, 42, 42]
for i, ((left, right), h) in enumerate(zip(rows, heights)):
    y_bottom = y_top - h
    if i % 2 == 0:
        rect(x0, y_bottom, x2-x0, h, LIGHT)
    paragraph(51, y_top-11, left, 218, 7.4, 8.7)
    paragraph(285, y_top-11, right, 255, 7.4, 8.7)
    line(x0, y_bottom, x2, y_bottom)
    y_top = y_bottom
line(x0, header_bottom, x2, header_bottom); line(split, y_top, split, top); line(x0, y_top, x0, top); line(x2, y_top, x2, top)

# Workflow
wf_title_y = y_top - 23
txt(40, wf_title_y, "How the workflow runs", 12, True, NAVY)
labels = ["Requirement", "Supplier request", "Quotation review", "Comparison & approval", "Purchase order", "Gate, Store & Quality"]
box_y, box_h, box_w = wf_title_y - 50, 38, 83
for i, label in enumerate(labels):
    x = 40 + i*86
    rect(x, box_y, box_w, box_h, LIGHT)
    txt(x+6, box_y+24, str(i+1), 8, True, TEAL)
    paragraph(x+6, box_y+13, label, box_w-12, 7, 8, True, NAVY)

# Employee / manager columns
section_y = box_y - 25
txt(40, section_y, "What employees and managers can do", 12, True, NAVY)
left_x, right_x, col_w = 50, 304, 240
txt(left_x, section_y-21, "Role assistants", 9.2, True, TEAL)
role_items = [
    "Create a material requirement in natural language for an authorized role.",
    "Upload supplier quotations and prepare a verified comparison.",
    "Prepare RFQs, approval summaries and purchase-order drafts for authorized review.",
    "Explain pending work, procedures and record status.",
    "Prepare follow-ups while keeping final actions under human control.",
]
ly = section_y-38
for item in role_items:
    ly = bullet(left_x, ly, item, col_w) - 4

txt(right_x, section_y-21, "Management visibility and coordination", 9.2, True, TEAL)
manager_items = [
    "See decisions, overdue work, blockers and handoffs by role.",
    "Delegate structured objectives through validated reporting lines with context, constraints and due dates.",
    "Request updates without exposing private employee-agent conversations.",
    "Keep source documents, calculations, approvals and actions traceable.",
    "Retain human approval for supplier release, awards, POs and ERP posting.",
]
ry = section_y-38
for item in manager_items:
    ry = bullet(right_x, ry, item, col_w) - 4

# Value row
value_y = min(ly, ry) - 13
txt(40, value_y, "Expected business value", 12, True, NAVY)
cards = [
    ("Faster cycle times", "Less time from requirement to supplier request and approval."),
    ("Fewer manual errors", "Structured extraction, validation and source-backed comparison."),
    ("Less follow-up effort", "Clear ownership, governed reminders and escalation."),
    ("Better auditability", "Traceable history across documents, tasks, decisions and receipts."),
]
card_y, card_h, card_w = value_y - 61, 48, 124
for i, (h, body) in enumerate(cards):
    x = 40 + i*128
    rect(x, card_y, card_w, card_h, LIGHT)
    txt(x+7, card_y+33, h, 7.7, True, TEAL)
    paragraph(x+7, card_y+21, body, card_w-14, 6.8, 8)

# ERP footer
footer_y = card_y - 17
txt(40, footer_y, "Works with the existing ERP", 8.7, True, TEAL)
footer = ("The ERP remains the system of record. GenuineGigs acts as the work and coordination layer above it, with controlled, "
          "approval-gated integration boundaries for master data, purchase orders and other authorized ERP transactions.")
paragraph(171, footer_y, footer, 384, 7.3, 8.8)

# PDF serialization
stream = "\n".join(commands).encode("latin-1", "replace")
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
    f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
]
pdf = bytearray(b"%PDF-1.4\n")
offsets = [0]
for i, obj in enumerate(objects, 1):
    offsets.append(len(pdf)); pdf.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
xref = len(pdf)
pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]:
    pdf.extend(f"{offset:010d} 00000 n \n".encode())
pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
OUT.write_bytes(pdf)
print(OUT)
