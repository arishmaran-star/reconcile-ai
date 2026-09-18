import os
import json
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types

# 1. Load the secret API key from the .env file
load_dotenv()

# 2. Initialize the modern GenAI Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def extract_invoice_data(image_path: str):
    """Takes an image path, sends it to Gemini 3.5 Flash, and returns structured JSON."""
    
    # 3. Load the physical image file
    try:
        img = Image.open(image_path)
    except FileNotFoundError:
        return {"error": f"Could not find image at {image_path}"}

    # 4. The System Prompt
    prompt = """
    You are an enterprise Accounts Payable AI. Extract the following data from the provided invoice image.
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

    print("Sending to Gemini... (this takes about 2 seconds)")
    
    # 5. Call the modern API endpoint using the latest Flash model
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[prompt, img],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # 6. Convert the raw text string back into a real Python dictionary
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
    test_image = "test_invoice.jpg"
    
    result = extract_invoice_data(test_image)
    
    print("\n--- EXTRACTION RESULT ---")
    print(json.dumps(result, indent=2))