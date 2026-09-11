# Procurement product domain

The procurement domain is GenuineGigs' requirement-to-receipt execution layer:
requirements, RFQs, supplier quotations, comparisons, negotiations, awards,
purchase orders, inbound receipts, inspections, invoices, and exceptions.

- `plans/` contains the chronological design and implementation contracts.
- `handoffs/` contains repository and engineering handoffs.
- `reviews/` contains historical implementation audits.
- Supporting architecture is in `docs/architecture/agentic-procurement-os.md`,
  `procurement-v2.md`, and `industrial-v1.md`.

The backend predates domain packaging and is still being modularized. Shared
tables remain in `app/db/models.py`; procurement services remain stable at their
current import paths to avoid breaking the mature workflow surface.
