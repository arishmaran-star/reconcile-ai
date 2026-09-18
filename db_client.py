import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file!")

# Initialize Supabase client
supabase: Client = create_client(url, key)

def get_erp_data(po_number: str):
    """
    Fetches Purchase Order and Goods Receipt Note data for a given PO number.
    Returns a dictionary containing po_record and grn_record.
    """
    po_res = supabase.table("purchase_orders").select("*").eq("po_number", po_number).execute()
    grn_res = supabase.table("goods_receipt_notes").select("*").eq("po_number", po_number).execute()

    po_data = po_res.data[0] if po_res.data else None
    grn_data = grn_res.data[0] if grn_res.data else None

    return {
        "po_record": po_data,
        "grn_record": grn_data
    }