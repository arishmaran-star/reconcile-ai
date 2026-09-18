document.getElementById("uploadBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("invoiceInput");
    const resultBox = document.getElementById("resultText");

    // 1. Check if a file is selected
    if (fileInput.files.length === 0) {
        alert("Please select an invoice, receipt, or PDF first.");
        return;
    }

    // 2. Prepare the data to send to FastAPI
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file); // 'file' matches the parameter name in main.py

    // 3. Update the UI so the user knows it's working
    resultBox.style.display = "block";
    resultBox.innerText = "Uploading to Python Backend and Gemini AI... Please wait.";

    try {
        // 4. Call your local FastAPI server
        const response = await fetch("http://127.0.0.1:8000/api/extract", {
            method: "POST",
            body: formData
        });

        // 5. Display the final JSON result on the screen
        const data = await response.json();
        resultBox.innerText = JSON.stringify(data, null, 2);
        
    } catch (error) {
        // Handle CORS or server-down errors
        resultBox.innerText = "Error connecting to backend: " + error.message + "\n\nMake sure your Python server is running on port 8000!";
    }
});