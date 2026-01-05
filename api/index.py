from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import urllib3

# Disable insecure request warnings if necessary (tnresults sometimes has SSL issues)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://tnresults.nic.in/rdopex.htm",
    "Origin": "https://tnresults.nic.in",
    "Content-Type": "application/x-www-form-urlencoded"
}

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    regno = data.get('regno')
    dob = data.get('dob')

    if not regno or not dob:
        return jsonify({"success": False, "error": "Missing regno or dob"}), 400

    url = "https://tnresults.nic.in/rdopex.asp"
    payload = {
        "regno": regno,
        "dob": dob,
        "B1": "Get Marks"
    }

    try:
        # verify=False is used because government sites sometimes have certificate issues
        response = requests.post(url, data=payload, headers=HEADERS, verify=False, timeout=10)
        
        if response.status_code != 200:
             return jsonify({"success": False, "error": f"External server returned {response.status_code}"}), 502

        soup = BeautifulSoup(response.text, 'html.parser')

        # Basic validation: Check for "Invalid Register Number" text
        if "Invalid Register Number" in response.text:
            return jsonify({"success": False, "error": "Invalid Register Number"}), 200

        # Attempt to extract data
        # Since we don't know the exact table structure, we'll look for common patterns or generic table parsing
        # Plan: Extract all tables and Convert to JSON
        tables_data = []
        tables = soup.find_all('table')
        
        extracted_info = {}
        
        # Try to find Name (usually in a cell) -> Basic Heuristic
        # Often structure is <tr><td>NAME</td><td>ACTUAL NAME</td></tr>
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = [ele.text.strip() for ele in row.find_all('td')]
                if len(cols) >= 2:
                    # Capture Key-Value pairs like "NAME : PRAVEEN"
                    key = cols[0].replace(':', '').strip().upper()
                    value = cols[1].replace(':', '').strip()
                    extracted_info[key] = value

        # Check if we found meaningful data
        if not extracted_info:
             # Fallback: Just return successful connection but no data found
             return jsonify({
                 "success": False, 
                 "error": "Data not found or format changed",
                 "raw_preview": response.text[:200]
             }), 200

        return jsonify({
            "success": True,
            "data": extracted_info
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Vercel requires this for the WSGI application
if __name__ == '__main__':
    app.run(debug=True)
