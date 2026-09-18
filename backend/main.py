import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import your Gemini extraction logic
from gemini_parser import extract_invoice_data

app = FastAPI()

# --- SECURITY FIX: ALLOW FRONTEND TO CONNECT (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows any frontend (like your local index.html) to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MSME VENDOR ENDPOINT ---
@app.post("/api/extract")
async def extract_invoice(file: UploadFile = File(...)):
    """Receives file from frontend, saves it temporarily, and sends to Gemini."""
    try:
        # Save the uploaded file locally so Gemini can read it
        temp_file_path = f"temp_{file.filename}"
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Call your Gemini parser logic
        ai_result = extract_invoice_data(temp_file_path)
        
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        # Optional: Add your reconciliation.py logic here to check Supabase
            
        return ai_result

    except Exception as e:
        return {"error": str(e)}

# --- ENTERPRISE BUYER ENDPOINTS ---
class PurchaseOrder(BaseModel):
    po_number: str
    vendor_name: str
    po_qty: int
    po_unit_price: float
    grn_qty: int

@app.get("/api/buyer/dashboard")
async def get_buyer_dashboard():
    """Fetches all processed AI reconciliations for the Enterprise finance team."""
    try:
        from db_client import supabase 
        response = supabase.table("reconciliation_results").select("*").order("created_at", desc=True).execute()
        return {"status": "success", "dashboard_data": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/buyer/create-po")
async def create_purchase_order(po: PurchaseOrder):
    """Allows the Enterprise ERP to push new Purchase Orders into the database."""
    try:
        from db_client import supabase
        data = po.model_dump()
        response = supabase.table("purchase_orders").insert(data).execute()
        return {"status": "success", "message": f"PO {po.po_number} securely added to ERP."}
    except Exception as e:
        return {"status": "error", "message": str(e)}