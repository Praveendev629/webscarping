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

        # Refined Parsing Logic based on Browser Inspection
        # The main results are usually in a <div class="design"> or similar
        # We look for the table that contains "NAME" or "Register No"
        
        extracted_info = {}
        tables = soup.find_all('table')
        
        target_table = None
        for table in tables:
            text_content = table.get_text()
            if "Example" in text_content: # Skip instructions table if any
                continue
            if "NAME" in text_content or "REGISTER NUMBER" in text_content or "Register No" in text_content:
                target_table = table
                break
        
        if not target_table:
             # Fallback: Try the div class 'design' which usually holds the result
             design_div = soup.find('div', class_='design')
             if design_div:
                 target_table = design_div.find('table')

        if target_table:
            rows = target_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if not cols: 
                    continue
                
                # Check for Name Row (often has "Name" label)
                row_text = row.get_text(separator=' ', strip=True).upper()
                if "NAME" in row_text and ":" in row_text:
                    # Format might be "NAME : PRAVEEN S"
                    parts = row_text.split(':')
                    if len(parts) > 1:
                        extracted_info['NAME'] = parts[1].strip()
                elif "NAME" in row_text:
                     # Sometimes just "NAME PRAVEEN S"
                     extracted_info['NAME'] = row_text.replace("NAME", "").replace(":", "").strip()

                # Extract Marks / Status
                # Row usually has Subject | Marks | Pass/Fail
                # We will look for the specific "Total" row or "Pass/Fail"
                if "TOTAL" in row_text:
                    # Extract the total value
                    for col in cols:
                        if col.text.strip().isdigit():  # Basic heuristic for Total
                            extracted_info['TOTAL'] = col.text.strip()
                            
                    # Start looking for Pass/Fail in the same row
                    for col in cols:
                        if col.text.strip().upper() in ['PASS', 'FAIL']:
                            extracted_info['RESULT'] = col.text.strip().upper()

                # Generic Subject-Wise Marks parsing
                # If row has >3 columns, likely a marks row
                if len(cols) >= 3 and "SUBJECT" not in row_text and "TOTAL" not in row_text:
                    # Heuristic: Col 0 = Subject, Last Col = Pass/Fail, Col -2 = Total
                    subject = cols[0].text.strip()
                    total_marks = cols[-2].text.strip() # Usually 2nd to last is total
                    result = cols[-1].text.strip()      # Last is P/F
                    
                    if subject and total_marks.isdigit():
                         extracted_info[subject] = f"{total_marks} ({result})"

        # If name is still missing, try the very first row of the table (common in TN results)
        if 'NAME' not in extracted_info and target_table:
            first_row = target_table.find('tr')
            if first_row:
                 # Extract text like "Register No: 123 Name: ABC"
                 text = first_row.get_text(separator=' ', strip=True)
                 if "NAME" in text.upper():
                     # Try to grab text after "NAME"
                     import re
                     match = re.search(r'NAME\s*[:\-]?\s*([A-Za-z\s\.]+)', text, re.IGNORECASE)
                     if match:
                         extracted_info['NAME'] = match.group(1).strip()


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
