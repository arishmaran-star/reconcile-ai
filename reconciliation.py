"""
3-Way Reconciliation Engine (Supabase-backed)
----------------------------------------------
Compares Gemini-extracted invoice data (as produced by gemini_parser.py,
which returns a `line_items` array) against the PO + GRN records stored
in Supabase, and returns a match status + suggested resolution.

Assumed Supabase table: "purchase_orders"
Expected columns (rename below in `get_erp_record` if yours differ):
    po_number, vendor_name, vendor_udyam_number,
    po_qty, po_unit_price, po_amount, po_date,
    grn_number, grn_qty, grn_date, grn_status
"""

import os
import logging
from supabase import create_client, Client

logger = logging.getLogger("reconciliation-engine")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Name of the table holding your PO + GRN records — change if yours differs
SUPABASE_TABLE = os.getenv("SUPABASE_PO_TABLE", "purchase_orders")

_supabase_client: Client = None


def get_supabase_client() -> Client:
    """Lazily creates and caches the Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in the environment (.env)"
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def load_erp_record(po_number: str):
    """Fetches a single PO/GRN record from Supabase by po_number.
    Returns a dict matching the old mock_erp.json record shape, or None."""
    if not po_number:
        return None

    try:
        client = get_supabase_client()
        response = (
            client.table(SUPABASE_TABLE)
            .select("*")
            .eq("po_number", po_number)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.error("Supabase lookup failed for PO %s: %s", po_number, str(e))
        return None


def normalize_extracted_invoice(extracted):
    """
    Converts the gemini_parser.py output (vendor_name, invoice_number, po_number,
    date, total_amount, line_items[]) into the flat fields the match engine needs:
    billed_qty, unit_price, total_amount.

    - billed_qty  = sum of quantities across all line items
    - unit_price  = the line item's own price if there's a single line item,
                    otherwise a derived (total_amount / billed_qty) average
    """
    line_items = extracted.get("line_items") or []

    total_qty = 0
    has_valid_qty = False
    for item in line_items:
        qty = item.get("quantity")
        if isinstance(qty, (int, float)):
            total_qty += qty
            has_valid_qty = True

    billed_qty = total_qty if has_valid_qty else None

    unit_price = None
    if len(line_items) == 1 and isinstance(line_items[0].get("unit_price"), (int, float)):
        unit_price = line_items[0]["unit_price"]
    elif billed_qty and extracted.get("total_amount") is not None:
        try:
            unit_price = round(float(extracted["total_amount"]) / billed_qty, 2)
        except (ZeroDivisionError, TypeError):
            unit_price = None

    return {
        "invoice_number": extracted.get("invoice_number"),
        "po_number": extracted.get("po_number"),
        "vendor_name": extracted.get("vendor_name"),
        "date": extracted.get("date"),
        "billed_qty": billed_qty,
        "unit_price": unit_price,
        "total_amount": extracted.get("total_amount"),
        "line_items": line_items,
    }


def perform_three_way_match(invoice_data, erp_record):
    """
    Deterministic reconciliation logic. Returns:
        status: str
        exceptions: list[dict]  each with 'type' and 'detail'
        ai_resolution: str
    """
    exceptions = []

    billed_qty = invoice_data.get("billed_qty")
    unit_price = invoice_data.get("unit_price")
    total_amount = invoice_data.get("total_amount")

    grn_qty = erp_record.get("grn_qty")
    po_unit_price = erp_record.get("po_unit_price")
    po_qty = erp_record.get("po_qty")

    # --- Rule 1: Quantity check (Invoice vs GRN - what was ACTUALLY received) ---
    if billed_qty is not None and grn_qty is not None:
        if billed_qty > grn_qty:
            shortfall = billed_qty - grn_qty
            exceptions.append({
                "type": "QUANTITY_MISMATCH",
                "detail": (
                    f"Invoice bills for {billed_qty:g} units, but GRN confirms only "
                    f"{grn_qty:g} units were actually received. Shortfall of {shortfall:g} units."
                ),
            })
        elif billed_qty < grn_qty:
            exceptions.append({
                "type": "UNDER_BILLING",
                "detail": (
                    f"Invoice bills for {billed_qty:g} units, which is LESS than the "
                    f"{grn_qty:g} units received per GRN. Vendor may be under-billing."
                ),
            })

    # --- Rule 2: Price check (Invoice vs PO agreed rate) ---
    if unit_price is not None and po_unit_price is not None:
        if round(float(unit_price), 2) != round(float(po_unit_price), 2):
            exceptions.append({
                "type": "PRICE_MISMATCH",
                "detail": (
                    f"Invoice unit price is Rs {unit_price:g}, but the agreed PO rate is "
                    f"Rs {po_unit_price:g} per unit."
                ),
            })

    # --- Rule 3: Arithmetic check (does billed_qty * unit_price = total_amount) ---
    if billed_qty is not None and unit_price is not None and total_amount is not None:
        expected_total = round(float(billed_qty) * float(unit_price), 2)
        if abs(expected_total - round(float(total_amount), 2)) > 1.0:  # tolerate rounding of Re 1
            exceptions.append({
                "type": "CALCULATION_MISMATCH",
                "detail": (
                    f"Billed qty ({billed_qty:g}) x unit price (Rs {unit_price:g}) = "
                    f"Rs {expected_total:g}, but invoice total states Rs {total_amount:g}."
                ),
            })

    # --- Rule 4: Over-ordering check (Invoice qty vs original PO qty) ---
    if billed_qty is not None and po_qty is not None and billed_qty > po_qty:
        exceptions.append({
            "type": "EXCEEDS_PO_QUANTITY",
            "detail": (
                f"Invoice bills for {billed_qty:g} units, which exceeds the original "
                f"PO quantity of {po_qty:g} units."
            ),
        })

    # --- Derive final status + resolution ---
    if not exceptions:
        status = "MATCHED: Approved for Payment"
        ai_resolution = (
            "All three documents (PO, GRN, Invoice) are in agreement. No manual "
            "intervention required — route directly to payment queue."
        )
        return status, exceptions, ai_resolution

    exception_types = {e["type"] for e in exceptions}

    if "QUANTITY_MISMATCH" in exception_types:
        status = "EXCEPTION: Quantity Mismatch"
        ai_resolution = "Suggest requesting a Credit Note for the missing items."
    elif "PRICE_MISMATCH" in exception_types:
        status = "EXCEPTION: Price Mismatch"
        ai_resolution = (
            "Suggest requesting a revised invoice matching the contracted PO rate, "
            "or a formal rate-variance approval from procurement before payment."
        )
    elif "CALCULATION_MISMATCH" in exception_types:
        status = "EXCEPTION: Calculation Mismatch"
        ai_resolution = (
            "Suggest sending the invoice back to the vendor for arithmetic correction "
            "(quantity x rate does not equal the stated total)."
        )
    elif "EXCEEDS_PO_QUANTITY" in exception_types:
        status = "EXCEPTION: Exceeds PO Quantity"
        ai_resolution = (
            "Suggest verifying if a PO amendment exists; otherwise reject the excess "
            "quantity and request a corrected invoice."
        )
    else:
        status = "EXCEPTION: Under-billing Flagged"
        ai_resolution = (
            "Invoice amount is lower than goods received — flag for finance review "
            "in case the vendor is owed additional payment in a follow-up invoice."
        )

    if len(exception_types) > 1:
        ai_resolution += " Note: multiple discrepancies detected — see 'exceptions' list for full detail."

    return status, exceptions, ai_resolution


def reconcile(extracted_invoice: dict):
    """
    High-level entrypoint: takes the raw dict returned by gemini_parser.extract_invoice_data()
    and returns the full reconciliation payload (invoice data, ERP data, status, resolution).
    """
    if "error" in extracted_invoice:
        return {
            "invoice_data": extracted_invoice,
            "erp_data": None,
            "match_status": "EXTRACTION_FAILED",
            "exceptions": [{"type": "EXTRACTION_ERROR", "detail": extracted_invoice["error"]}],
            "ai_resolution": "Suggest re-uploading a clearer invoice image or entering details manually.",
        }

    invoice_data = normalize_extracted_invoice(extracted_invoice)
    po_number = invoice_data.get("po_number")

    erp_record = load_erp_record(po_number)

    if erp_record is None:
        return {
            "invoice_data": invoice_data,
            "erp_data": None,
            "match_status": "EXCEPTION: PO Not Found in ERP",
            "exceptions": [{
                "type": "PO_NOT_FOUND",
                "detail": (
                    f"Extracted PO number '{po_number}' does not match any PO record "
                    "in Supabase. Verify the PO number on the invoice."
                ),
            }],
            "ai_resolution": (
                "Suggest routing to procurement to confirm the correct PO number "
                "before this invoice can be matched or paid."
            ),
        }

    status, exceptions, ai_resolution = perform_three_way_match(invoice_data, erp_record)

    return {
        "invoice_data": invoice_data,
        "erp_data": erp_record,
        "match_status": status,
        "exceptions": exceptions,
        "ai_resolution": ai_resolution,
    }
