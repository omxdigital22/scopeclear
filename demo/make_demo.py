"""Builds the fictional demo case. Every name and company here is invented."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "inputs"
SCRIPTS = Path(__file__).parent / "scripts"
OUT.mkdir(exist_ok=True); SCRIPTS.mkdir(exist_ok=True)

ss = getSampleStyleSheet()
h1, h2, body = ss["Title"], ss["Heading2"], ss["BodyText"]
bullet = ParagraphStyle("b", parent=body, leftIndent=14, bulletIndent=2, spaceAfter=4)

def footer(c, d):
    c.setFont("Helvetica", 8)
    c.drawString(40, 25, "FICTIONAL DEMO DATA - Kestrel Hardware Distributors is an invented company.")
    c.drawRightString(555, 25, f"Page {d.page}")

def bl(t): return Paragraph(t, bullet, bulletText="-")

pages = [
    [Paragraph("Billing and Collections System - Proposal v1.0", h1),
     Paragraph("Prepared for Kestrel Hardware Distributors, 2 October 2026", body), Spacer(1, 12),
     Paragraph("1. Overview", h2),
     Paragraph("Kestrel supplies hardware to around 200 retail shops. Billing is done on paper and "
               "collections are tracked in a notebook. This proposal covers a simple billing and "
               "collections system for the office and delivery staff.", body),
     Paragraph("2. Users", h2),
     Paragraph("The system will support 5 staff users: 1 owner, 2 billing staff and 2 delivery staff.", body),
     bl("The owner can see all invoices, collections and reports."),
     bl("Billing staff create invoices and record payments."),
     bl("Delivery staff see the invoices for their route.")],
    [Paragraph("3. Invoicing and payments", h2),
     bl("Create GST invoices from the product list."),
     bl("Record customer payments in cash only."),
     bl("Each invoice is marked Paid in full when the cash is received."),
     bl("All payments are recorded in a single collections account."),
     bl("Print invoices on A4 paper.")],
    [Paragraph("4. Reports", h2),
     bl("Daily collections report, downloadable as PDF."),
     bl("Outstanding invoices list for each customer."),
     Paragraph("5. Notifications", h2),
     Paragraph("Customer notifications are not included in this phase.", body)],
    [Paragraph("6. Out of scope", h2),
     bl("Online payments and payment gateways."),
     bl("WhatsApp or SMS messages to customers."),
     bl("Integration with accounting software."),
     Paragraph("7. Commercials and timeline", h2),
     Paragraph("Shared separately after the scope is confirmed.", body)],
]
story = []
for i, p in enumerate(pages):
    story += p
    if i < len(pages) - 1: story.append(PageBreak())
SimpleDocTemplate(str(OUT / "proposal_v1.pdf"), pagesize=A4, topMargin=50, bottomMargin=50).build(
    story, onFirstPage=footer, onLaterPages=footer)

(OUT / "whatsapp_chat_12oct.txt").write_text(
"""[12/10/2026, 10:14] Rahul (Kestrel): Hi team, few changes after our meeting
[12/10/2026, 10:15] Rahul (Kestrel): Please send payment reminders to customers on WhatsApp
[12/10/2026, 10:16] Rahul (Kestrel): Daily collections report should come in Excel also
[12/10/2026, 10:18] Rahul (Kestrel): We need only 3 users now, not 5
[12/10/2026, 10:19] Rahul (Kestrel): Thanks
""")

voice = {
 "voice_note_1_13oct": [
  "Hi, Rahul here from Kestrel.",
  "One important thing. Many customers do not pay the full amount at once.",
  "Someone pays part in cash and the rest later by UPI.",
  "And the UPI money comes into our second bank account, not the main one.",
  "So the system should handle partial payments across multiple accounts.",
  "Please make sure the balance is tracked properly."],
 "voice_note_2_14oct": [
  "Hi, Rahul again.",
  "About the Excel report, forget it, PDF is fine.",
  "Also, some regular customers get a discount on every invoice.",
  "My brother will tell you which customers and how much."],
}
for stem, lines in voice.items():
    (SCRIPTS / f"{stem}.txt").write_text("\n".join(lines) + "\n")

img_lines = ["Invoice changes", "1. Show customer GSTIN", "2. Add 'Delivered by' name"]
(SCRIPTS / "invoice_note_15oct.txt").write_text("\n".join(img_lines) + "\n")
im = Image.new("RGB", (720, 1280), "#FFF8D6")
d = ImageDraw.Draw(im)
try:
    f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    f3 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
except OSError:
    f1 = f2 = f3 = ImageFont.load_default()
d.rectangle([0, 0, 720, 110], fill="#F2E7B0")
d.text((40, 38), "Notes", font=f2, fill="#6B5B12")
d.text((50, 190), img_lines[0], font=f1, fill="#222")
d.text((50, 300), img_lines[1], font=f2, fill="#222")
d.text((50, 380), img_lines[2], font=f2, fill="#222")
d.text((40, 1230), "Fictional demo screenshot", font=f3, fill="#8A7A30")
im.save(OUT / "invoice_note_15oct.png")
print("ok")
