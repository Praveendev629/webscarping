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
                row_text = row.get_text(separator=' ', strip=True)
                row_text_upper = row_text.upper()

                # Reliable Name Parsing: Look for the text containing the Register Number
                # Format is usually: "PRAVEEN S ( 9541237 )" or "PRAVEEN S - 9541237"
                if str(regno) in row_text:
                    # Heuristic: Remove the regno and common delimiters to find the name
                    clean_text = row_text.replace(str(regno), '').replace('(', '').replace(')', '').replace('-', '').strip()
                    # Filter out other common noise if present
                    clean_text = clean_text.replace("Registration Number", "").replace("Reg No", "").strip()
                    
                    # Assume what's left is the name (if it's not empty and reasonable length)
                    if len(clean_text) > 2 and "NAME" not in extracted_info:
                         extracted_info['NAME'] = clean_text

                if not cols: 
                    continue
                
                # Check for Name Row (fallback if generic "NAME" label exists)
                if "NAME" in row_text_upper and ":" in row_text_upper and "NAME" not in extracted_info:
                    parts = row_text_upper.split(':')
                    if len(parts) > 1:
                        extracted_info['NAME'] = parts[1].strip()

                # Extract Marks / Status
                # Row usually has Subject | Marks | Pass/Fail
                if "TOTAL" in row_text_upper:
                    # Extract the total value
                    for col in cols:
                        if col.text.strip().isdigit(): 
                            extracted_info['TOTAL'] = col.text.strip()
                    # Start looking for Pass/Fail in the same row
                    for col in cols:
                        if col.text.strip().upper() in ['PASS', 'FAIL']:
                            extracted_info['RESULT'] = col.text.strip().upper()

                # Generic Subject-Wise Marks parsing
                # If row has >3 columns, likely a marks row
                if len(cols) >= 3 and "SUBJECT" not in row_text_upper and "TOTAL" not in row_text_upper:
                    subject = cols[0].text.strip()
                    total_marks = cols[-2].text.strip() # Usually 2nd to last is total
                    result = cols[-1].text.strip()      # Last is P/F
                    
                    if subject and total_marks.isdigit():
                         extracted_info[subject] = f"{total_marks} ({result})"

        # Fallback Name extraction (Header row)
        if 'NAME' not in extracted_info and target_table:
             # Sometimes it's in the very first row without the Reg No being obvious
             first_row = target_table.find('tr')
             if first_row:
                 text = first_row.get_text(separator=' ', strip=True)
                 if "(" in text and ")" in text:
                     # Attempt to grab name from "NAME ( REGNO )" pattern
                     parts = text.split('(')
                     if len(parts) > 0 and len(parts[0]) > 2:
                         extracted_info['NAME'] = parts[0].strip()


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
