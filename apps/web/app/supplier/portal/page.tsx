"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiUrl } from "@/lib/api";

type Row = Record<string, unknown>;
type PortalContext = { purchase_order: Row; lines: Row[]; acknowledgement?: Row | null; deliveries: Row[]; expires_at: string };
type RfqContext = { supplier_request: Row; lines: Row[]; response_status: string; expires_at: string };
const text = (value: unknown) => value == null ? "" : String(value);

async function publicRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const payload = await response.json(); message = text(payload.detail || message); } catch { /* preserve safe message */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function SupplierPortalContent() {
  const token = useSearchParams().get("token") || "";
  const [context, setContext] = useState<PortalContext | null>(null);
  const [rfqContext, setRfqContext] = useState<RfqContext | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!token) return;
    try { setContext(await publicRequest<PortalContext>(`/supplier/pos/${encodeURIComponent(token)}`)); setRfqContext(null); }
    catch {
      try { setRfqContext(await publicRequest<RfqContext>(`/supplier/rfqs/${encodeURIComponent(token)}`)); setContext(null); }
      catch (error) { setStatus(error instanceof Error ? error.message : "Supplier link is unavailable"); }
    }
  }, [token]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function submitJson(event: FormEvent<HTMLFormElement>, path: string, success: string) {
    event.preventDefault(); setBusy(true); setStatus("");
    const form = new FormData(event.currentTarget); const body: Row = Object.fromEntries(form.entries());
    if (path.includes("/clarifications") && !body.external_message_id) body.external_message_id = crypto.randomUUID();
    for (const key of ["confirmed_quantity", "expected_quantity"]) if (key in body) body[key] = Number(body[key]);
    try {
      await publicRequest(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      setStatus(success); event.currentTarget.reset(); await refresh();
    } catch (error) { setStatus(error instanceof Error ? error.message : "Request failed"); }
    finally { setBusy(false); }
  }
  async function uploadEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setStatus(""); const form = new FormData(event.currentTarget);
    const asnId = text(form.get("asn_id")); form.delete("asn_id");
    try {
      await publicRequest(`/supplier/pos/${encodeURIComponent(token)}/deliveries/${encodeURIComponent(asnId)}/documents`, { method: "POST", body: form });
      setStatus("Dispatch evidence uploaded for validation."); event.currentTarget.reset(); await refresh();
    } catch (error) { setStatus(error instanceof Error ? error.message : "Upload failed"); }
    finally { setBusy(false); }
  }
  async function submitDeliveryUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setStatus(""); const form = new FormData(event.currentTarget);
    const asnId = text(form.get("asn_id"));
    const body = {
      external_update_id: crypto.randomUUID(),
      revised_expected_delivery: text(form.get("revised_expected_delivery")),
      reason: text(form.get("reason")),
    };
    try {
      await publicRequest(`/supplier/pos/${encodeURIComponent(token)}/deliveries/${encodeURIComponent(asnId)}/updates`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      setStatus("Delivery commitment updated. Stores and Procurement have been notified."); event.currentTarget.reset(); await refresh();
    } catch (error) { setStatus(error instanceof Error ? error.message : "Delivery update failed"); }
    finally { setBusy(false); }
  }
  async function uploadInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setStatus(""); const form = new FormData(event.currentTarget);
    try {
      await publicRequest(`/supplier/pos/${encodeURIComponent(token)}/invoices`, { method: "POST", body: form });
      setStatus("Invoice uploaded. The buyer will verify the extracted values before matching."); event.currentTarget.reset();
    } catch (error) { setStatus(error instanceof Error ? error.message : "Invoice upload failed"); }
    finally { setBusy(false); }
  }
  async function submitQuote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setStatus(""); const form = new FormData(event.currentTarget);
    const lines = (rfqContext?.lines || []).flatMap((line) => {
      const lineId = text(line.id); const price = text(form.get(`unit_price_${lineId}`));
      if (!price) return [];
      return [{ rfq_line_id: lineId, quantity: Number(form.get(`quantity_${lineId}`)), unit_price: Number(price), gst_rate: Number(form.get(`gst_${lineId}`) || 0), promised_date: text(form.get(`date_${lineId}`)), deviation_notes: text(form.get(`deviation_${lineId}`)) }];
    });
    const body = { quote_number: text(form.get("quote_number")), quote_date: text(form.get("quote_date")), validity_date: text(form.get("validity_date")), payment_terms: text(form.get("payment_terms")), currency: text(form.get("currency") || "INR"), exchange_rate_to_inr: Number(form.get("exchange_rate_to_inr") || 1), lines };
    try { await publicRequest(`/supplier/rfqs/${encodeURIComponent(token)}/quotes`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); setStatus("Quotation submitted for buyer verification. You may submit a later revision before the request closes."); event.currentTarget.reset(); await refresh(); }
    catch (error) { setStatus(error instanceof Error ? error.message : "Quotation submission failed"); } finally { setBusy(false); }
  }
  async function uploadQuoteEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setStatus(""); const form = new FormData(event.currentTarget);
    try {
      await publicRequest(`/supplier/rfqs/${encodeURIComponent(token)}/quotes/evidence`, { method: "POST", body: form });
      setStatus("Quotation evidence uploaded for validation and buyer review."); event.currentTarget.reset();
    } catch (error) { setStatus(error instanceof Error ? error.message : "Evidence upload failed"); }
    finally { setBusy(false); }
  }
  if (!token) return <main className="supplier-portal-shell"><section className="action-panel"><h1>Supplier link required</h1><p>Open the secure link provided with the purchase order.</p></section></main>;
  if (!context && !rfqContext) return <main className="supplier-portal-shell"><section className="action-panel"><h1>Loading supplier request…</h1>{status && <div className="error-banner">{status}</div>}</section></main>;
  if (rfqContext) { const rfq = rfqContext.supplier_request; const declined = rfqContext.response_status === "no_bid"; return <main className="supplier-portal-shell">
    <header className="supplier-portal-header"><div><span className="brand-mark">GG</span><div><strong>GenuineGigs Supplier Portal</strong><small>Secure quotation response</small></div></div><span className="status-pill good">Link verified</span></header>
    <section className="action-panel"><div className="panel-head"><div><div className="section-kicker">Supplier request</div><h1>{text(rfq.business_number)}</h1><p>Responses due {text(rfq.deadline)} · {text(rfq.status).replaceAll("_", " ")}</p></div>{Boolean(rfq.document_available) && <a className="small-action" href={apiUrl(`/supplier/rfqs/${encodeURIComponent(token)}/document`)} target="_blank" rel="noreferrer">View final request</a>}</div><div className="business-card-grid">{rfqContext.lines.map((line) => <article className="business-record-card" key={text(line.id)}><strong>{text(line.quantity)} {text(line.uom)}</strong><span>{text(line.description)}</span><span>Required by {text(line.need_by_date)}</span></article>)}</div></section>
    {!declined && <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Your quotation</div><h2>Quote all or selected lines</h2><p>Leave a line price blank to submit a partial bid. Every submission becomes a new reviewable revision.</p></div></div><form className="ops-form supplier-quote-form" onSubmit={submitQuote}><label>Quote number<input name="quote_number" required /></label><label>Quote date<input name="quote_date" type="date" required /></label><label>Valid until<input name="validity_date" type="date" required /></label><label>Payment terms<input name="payment_terms" required /></label><label>Currency<input name="currency" defaultValue="INR" required /></label><label>Rate to INR<input name="exchange_rate_to_inr" type="number" min="0.000001" step="0.000001" defaultValue="1" required /></label>{rfqContext.lines.map((line) => <fieldset className="span-2 supplier-quote-line" key={text(line.id)}><legend>{text(line.description)} · requested {text(line.quantity)} {text(line.uom)}</legend><label>Quantity<input name={`quantity_${text(line.id)}`} type="number" min="0.001" max={Number(line.quantity)} step="0.001" defaultValue={Number(line.quantity)} /></label><label>Unit price<input name={`unit_price_${text(line.id)}`} type="number" min="0" step="0.01" /></label><label>Tax %<input name={`gst_${text(line.id)}`} type="number" min="0" step="0.01" defaultValue="18" /></label><label>Promised date<input name={`date_${text(line.id)}`} type="date" defaultValue={text(line.need_by_date)} /></label><label className="span-2">Deviation or clarification<input name={`deviation_${text(line.id)}`} /></label></fieldset>)}<button className="action-button" disabled={busy}>Submit quotation</button></form></section>}
    {!declined && <details className="inline-workflow"><summary>Unable to quote?</summary><form className="ops-form" onSubmit={(event) => void submitJson(event, `/supplier/rfqs/${encodeURIComponent(token)}/no-bid`, "No-bid response recorded.")}><label className="span-2">Reason<textarea name="reason" minLength={3} required /></label><button className="small-action" disabled={busy}>Decline this request</button></form></details>}
    {rfqContext.response_status === "responded" && <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Supporting evidence</div><h2>Attach your quotation document</h2><p>The file is quarantined and validated before the buyer reviews it.</p></div></div><form className="ops-form" onSubmit={uploadQuoteEvidence}><label className="span-2">PDF, image, or XLSX<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" required /></label><button className="action-button" disabled={busy}>Upload quotation evidence</button></form></section>}
    {declined && <div className="confirmation-strip"><strong>No-bid response recorded.</strong> The buyer has been notified.</div>}
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Clarification</div><h2>Ask the buyer a question</h2></div></div><form className="ops-form" onSubmit={(event) => void submitJson(event, `/supplier/portal/${encodeURIComponent(token)}/clarifications`, "Clarification delivered to the buyer.")}><label>Subject<input name="subject" /></label><label className="span-2">Message<textarea name="message" required /></label><button className="small-action" disabled={busy}>Send clarification</button></form></section>
    {status && <div className="confirmation-strip" role="status">{status}</div>}
  </main>; }
  const poContext = context as PortalContext;
  const po = poContext.purchase_order; const accepted = text(poContext.acknowledgement?.status) === "accepted";
  return <main className="supplier-portal-shell">
    <header className="supplier-portal-header"><div><span className="brand-mark">GG</span><div><strong>GenuineGigs Supplier Portal</strong><small>Secure purchase-order response</small></div></div><span className="status-pill good">Link verified</span></header>
    <section className="action-panel"><div className="panel-head"><div><div className="section-kicker">Purchase order</div><h1>{text(po.business_number)}</h1><p>{text(po.currency)} · {text(po.payment_terms)} · {text(po.status).replaceAll("_", " ")}</p></div>{Boolean(po.document_available) && <a className="small-action" href={apiUrl(`/supplier/pos/${encodeURIComponent(token)}/document`)} target="_blank" rel="noreferrer">View final order</a>}</div>
      <div className="business-card-grid">{poContext.lines.map((line) => <article className="business-record-card" key={text(line.id)}><strong>{text(line.quantity)} {text(line.uom)}</strong><span>Unit price {text(line.unit_price)} {text(po.currency)}</span><span>Required by {text(line.need_by_date)}</span></article>)}</div>
    </section>
    {!poContext.acknowledgement && <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Your response</div><h2>Confirm or request a change</h2></div></div><form className="ops-form" onSubmit={(event) => void submitJson(event, `/supplier/pos/${encodeURIComponent(token)}/acknowledgements`, "Purchase-order response recorded.")}><label>Response<select name="status" required><option value="accepted">Accept order</option><option value="change_requested">Request a change</option><option value="rejected">Reject order</option></select></label><label>Confirmed quantity<input name="confirmed_quantity" type="number" min="0" step="0.001" required /></label><label>Confirmed delivery<input name="confirmed_delivery" type="date" required /></label><label className="span-2">Notes<textarea name="notes" /></label><button className="action-button" disabled={busy}>Submit response</button></form></section>}
    {poContext.acknowledgement && <section className="confirmation-strip"><div><strong>Response recorded: {text(poContext.acknowledgement.status).replaceAll("_", " ")}</strong><span>Confirmed {text(poContext.acknowledgement.confirmed_quantity)} for {text(poContext.acknowledgement.confirmed_delivery)}</span></div></section>}
    {accepted && <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Delivery update</div><h2>Submit dispatch details</h2><p>Use a unique dispatch reference for each partial delivery.</p></div></div><form className="ops-form" onSubmit={(event) => void submitJson(event, `/supplier/pos/${encodeURIComponent(token)}/deliveries`, "Delivery notice submitted to Stores.")}><label>Expected quantity<input name="expected_quantity" type="number" min="0.001" step="0.001" required /></label><label>Expected delivery<input name="expected_delivery" type="date" required /></label><label>Dispatch reference<input name="dispatch_reference" required /></label><label>Vehicle number<input name="vehicle_number" /></label><button className="action-button" disabled={busy}>Submit delivery notice</button></form>
      {poContext.deliveries.length > 0 && <form className="ops-form" onSubmit={uploadEvidence}><label>Delivery<select name="asn_id" required>{poContext.deliveries.map((delivery) => <option value={text(delivery.id)} key={text(delivery.id)}>{text(delivery.business_number)} · {text(delivery.dispatch_reference)}</option>)}</select></label><label>Evidence type<select name="purpose"><option value="supplier_dispatch_document">Dispatch document</option><option value="supplier_certificate">Material certificate</option></select></label><label className="span-2">PDF, image, or XLSX<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" required /></label><button className="action-button" disabled={busy}>Upload evidence</button></form>}
      {poContext.deliveries.length > 0 && <details className="inline-workflow"><summary>Delivery date changed?</summary><form className="ops-form" onSubmit={submitDeliveryUpdate}><label>Delivery<select name="asn_id" required>{poContext.deliveries.map((delivery) => <option value={text(delivery.id)} key={text(delivery.id)}>{text(delivery.business_number)} · currently {text(delivery.expected_delivery)}</option>)}</select></label><label>Revised delivery<input name="revised_expected_delivery" type="date" required /></label><label className="span-2">Reason<textarea name="reason" minLength={3} required /></label><button className="action-button" disabled={busy}>Update commitment</button></form></details>}
    </section>}
    {accepted && <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Invoice submission</div><h2>Upload your invoice</h2><p>The buyer verifies extracted commercial values before matching. Uploading does not approve payment.</p></div></div><form className="ops-form" onSubmit={uploadInvoice}><label className="span-2">PDF, image, or XLSX<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" required /></label><button className="action-button" disabled={busy}>Upload invoice</button></form></section>}
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Clarification</div><h2>Send a question or response</h2></div></div><form className="ops-form" onSubmit={(event) => void submitJson(event, `/supplier/portal/${encodeURIComponent(token)}/clarifications`, "Clarification delivered to the responsible buyer.")}><label>Subject<input name="subject" /></label><label className="span-2">Message<textarea name="message" required /></label><button className="small-action" disabled={busy}>Send clarification</button></form></section>
    {status && <div className={status.toLowerCase().includes("failed") || status.toLowerCase().includes("invalid") ? "error-banner" : "confirmation-strip"} role="status">{status}</div>}
  </main>;
}

export default function SupplierPortalPage() {
  return <Suspense fallback={<main className="supplier-portal-shell">Loading…</main>}><SupplierPortalContent /></Suspense>;
}
