import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Import your two custom modules
from gemini_parser import extract_invoice_data
from reconciliation import reconcile

app = FastAPI(
    title="Reconcile AI Backend",
    description="Automated invoice extraction and 3-way reconciliation engine."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "active", "service": "Reconcile AI Backend"}

@app.post("/api/extract")
async def process_invoice(file: UploadFile = File(...)):
    """Extracts invoice data via Gemini, then runs 3-way matching against Supabase."""
    temp_file_path = f"temp_{file.filename}"
    
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 1. AI Extraction
        extracted_data = extract_invoice_data(temp_file_path)
        
        # 2. Database Reconciliation
        final_report = reconcile(extracted_data)
        
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    return final_report