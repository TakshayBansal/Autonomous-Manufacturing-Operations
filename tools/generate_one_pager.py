#!/usr/bin/env python3
"""Generate the customer one-pager as minimal, dependency-free DOCX and PDF files."""

from pathlib import Path
from textwrap import wrap
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"

TITLE = "GenuineGigs — Manufacturing Operations Layer"
TAGLINE = "A governed system of work that sits above your ERP"
INTRO = (
    "GenuineGigs sits on top of existing ERP systems such as SAP or Oracle. The ERP remains the system of record; "
    "GenuineGigs connects the work, people, documents, decisions, approvals, and exceptions around it."
)

SECTIONS = [
    ("Streamline procurement", "Connect requirements, RFQs, supplier quotations, verified comparisons, approvals, purchase orders, gate entry, receipt, and quality inspection in one guided flow. Every stage shows the owner, next action, due date, evidence, and blocker."),
    ("Help employees work faster", "Each employee gets a role agent that understands assigned work and connected records. It can prepare RFQs and messages, extract quotations, flag missing information and risk, build comparisons, explain decisions, and prepare the next step."),
    ("Ease delegation and follow-ups", "Manager agents can review formal team status, identify overdue work, and delegate clear objectives through the reporting hierarchy. Employee agents receive the relevant context, expected outcome, constraints, and due date."),
    ("Connect departments", "Structured handoffs carry the right records and evidence between procurement, plant management, gate, stores, and quality. Teams coordinate from the same process while retaining their own responsibility and authority."),
]

FLOW = "Requirement → RFQ → Quotations → Comparison → Approval → PO → Gate → Store → Quality"

AGENT_ACTIONS = [
    "Explain what needs attention and why",
    "Prepare RFQs, messages, checklists, and follow-ups",
    "Extract and organize supplier quotation data",
    "Highlight missing information, delays, deviations, and blockers",
    "Prepare verified comparisons and summarize supporting evidence",
]

VALUE = (
    "Reduce manual coordination, prepare procurement work faster, surface delays earlier, improve delegation and follow-through, "
    "and maintain a reliable trail of documents and decisions—without disrupting the systems that already run the business."
)

FOOTER = "Agents prepare and recommend. Authorized people approve, issue, post, update inventory, and close exceptions."


def p(text, style=None):
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    return f'<w:p><w:pPr>{style_xml}</w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def make_docx():
    body = [p(TITLE, "Title"), p(TAGLINE, "Subtitle"), p(INTRO, "Lead"), p("ONE CONNECTED PROCUREMENT FLOW", "Heading1"), p(FLOW, "Flow")]
    for heading, text in SECTIONS:
        body.append(p(heading.upper(), "Heading1"))
        body.append(p(f"{heading}: {text}", "Bullet"))
    body.append(p("WHAT ROLE AGENTS CAN DO", "Heading1"))
    for action in AGENT_ACTIONS:
        body.append(p("• " + action, "Bullet"))
    body.extend([p("THE RESULT", "Heading1"), p(VALUE), p(FOOTER, "Callout")])
    sect = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="650" w:right="720" w:bottom="650" w:left="720" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join(body) + sect + '</w:body></w:document>'
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="17"/><w:color w:val="27323A"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="65" w:line="220" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
    <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:spacing w:after="30"/></w:pPr><w:rPr><w:b/><w:color w:val="123B4A"/><w:sz w:val="38"/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:pPr><w:spacing w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="D06232"/><w:sz w:val="23"/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Lead"><w:name w:val="Lead"/><w:pPr><w:spacing w:after="110"/></w:pPr><w:rPr><w:b/><w:sz w:val="18"/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:pPr><w:spacing w:before="80" w:after="35"/></w:pPr><w:rPr><w:b/><w:color w:val="123B4A"/><w:sz w:val="18"/><w:caps/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Bullet"><w:name w:val="Bullet"/><w:pPr><w:ind w:left="240" w:hanging="160"/><w:spacing w:after="48"/></w:pPr><w:rPr><w:sz w:val="16"/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Flow"><w:name w:val="Flow"/><w:pPr><w:shd w:fill="EAF1F3"/><w:spacing w:before="30" w:after="55"/><w:ind w:left="100" w:right="100"/></w:pPr><w:rPr><w:b/><w:color w:val="123B4A"/><w:sz w:val="16"/></w:rPr></w:style>
    <w:style w:type="paragraph" w:styleId="Callout"><w:name w:val="Callout"/><w:pPr><w:shd w:fill="123B4A"/><w:spacing w:before="80" w:after="0"/><w:ind w:left="100" w:right="100"/></w:pPr><w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="17"/></w:rPr></w:style>
    </w:styles>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    with ZipFile(OUT / "genuinegigs-customer-one-pager.docx", "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", doc_rels)


def pdf_escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("→", ">")


def make_pdf():
    commands = []
    def txt(x, y, text, size=9, bold=False, color=(0.15, .20, .23)):
        r, g, b = color
        commands.append(f"BT /{'F2' if bold else 'F1'} {size} Tf {r} {g} {b} rg {x} {y} Td ({pdf_escape(text)}) Tj ET")
    def para(x, y, text, width, size=8.2, leading=10.2, bold=False):
        chars = max(20, int(width / (size * .50)))
        for line in wrap(text, chars, break_long_words=False):
            txt(x, y, line, size, bold)
            y -= leading
        return y
    navy=(.07,.23,.29); orange=(.82,.38,.17); white=(1,1,1)
    txt(38, 811, TITLE, 12, True, navy); txt(38, 793, TAGLINE, 9, False, orange)
    commands.append("0.82 0.38 0.17 rg 38 782 519 1 re f")
    y = para(38, 762, INTRO, 519, 9.1, 11.2, False)
    txt(38, y-5, "ONE CONNECTED PROCUREMENT FLOW", 8.5, True, orange); y -= 20
    commands.append(f"0.92 0.95 0.96 rg 38 {y-16} 519 24 re f")
    txt(48, y-8, FLOW, 8, True, navy); y -= 40
    left_x, right_x, col_w = 38, 306, 251
    top = y
    ly = top; ry = top
    for i, (h, t) in enumerate(SECTIONS):
        x = left_x if i < 2 else right_x
        yy = ly if i < 2 else ry
        txt(x, yy, h, 8.5, True, navy); yy -= 11
        yy = para(x, yy, t, col_w, 7.8, 9.4) - 8
        if i < 2: ly = yy
        else: ry = yy
    y = min(ly, ry) - 2
    txt(38, y, "WHAT ROLE AGENTS CAN DO", 9, True, orange); y -= 17
    for action in AGENT_ACTIONS:
        txt(44, y, "• " + action, 8, False, navy); y -= 13
    txt(38, y-1, "HUMAN AUTHORITY STAYS CLEAR", 9, True, orange); y -= 18
    y = para(38, y, "Agents prepare and recommend. Authorized people approve suppliers, issue purchase orders, post to ERP, update inventory, and close exceptions.", 519, 8, 9.8)
    txt(38, y-2, "THE RESULT", 9, True, orange); y -= 19
    y = para(38, y, VALUE, 519, 8, 9.8)
    box_y = max(36, y-43)
    commands.append(f"0.07 0.23 0.29 rg 30 {box_y} 535 34 re f")
    para(42, box_y+21, FOOTER, 511, 8.3, 10, True)
    stream = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf)); pdf.extend(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref = len(pdf); pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    (OUT / "genuinegigs-customer-one-pager.pdf").write_bytes(pdf)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    make_docx()
    make_pdf()
    print("Generated DOCX and PDF in", OUT)
