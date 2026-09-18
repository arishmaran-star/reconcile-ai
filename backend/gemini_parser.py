import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Load the secret API key from the .env file
load_dotenv()

# 2. Initialize the modern GenAI Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def extract_invoice_data(file_path: str):
    """Takes a file path (JPG, PNG, or PDF), sends it to Gemini, and returns structured JSON."""
    
    # 3. Upload the file securely to Gemini's servers (Supports PDF, JPG, PNG)
    try:
        print(f"Uploading {file_path} to Gemini...")
        uploaded_document = client.files.upload(file=file_path)
    except Exception as e:
        return {"error": f"Failed to upload file to AI: {str(e)}"}

    # 4. The System Prompt
    prompt = """
    You are an enterprise Accounts Payable AI. Extract the following data from the provided invoice document.
    You MUST return ONLY a valid JSON object. Do not include markdown formatting or explanations.
    
    Required JSON structure:
    {
        "vendor_name": "String",
        "invoice_number": "String",
        "po_number": "String or null if missing",
        "date": "YYYY-MM-DD",
        "total_amount": Float,
        "line_items": [
            {
                "description": "String",
                "quantity": Integer,
                "unit_price": Float,
                "total": Float
            }
        ]
    }
    """

    print("Analyzing document... (this takes about 2-5 seconds)")
    
    # 5. Call the API using the uploaded document
    try:
        # Note: Depending on your API key, you may need to use 'gemini-1.5-flash' or 'gemini-2.5-flash'
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[prompt, uploaded_document],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # 6. Clean up: Delete the file from Google's servers for data privacy
        client.files.delete(name=uploaded_document.name)
        
        # 7. Convert the raw text string back into a real Python dictionary
        extracted_data = json.loads(response.text)
        return extracted_data
        
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_output": response.text}
    except Exception as e:
        return {"error": f"API Connection Error: {str(e)}"}

# ==========================================
# TEST BLOCK: Run this file directly to test
# ==========================================
if __name__ == "__main__":
    # You can now test this with a PDF, JPG, or PNG!
    test_file = "test_invoice.pdf" 
    
    # Only run the test if the file actually exists on your computer
    if os.path.exists(test_file):
        result = extract_invoice_data(test_file)
        print("\n--- EXTRACTION RESULT ---")
        print(json.dumps(result, indent=2))
    else:
        print(f"To test, please place a file named '{test_file}' in this folder.")