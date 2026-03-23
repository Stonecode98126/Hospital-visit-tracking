import requests
from bs4 import BeautifulSoup
import time
import json
import logging

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Target URL for the clinic progress
TARGET_URL = "https://www.aftygh.gov.tw/opd/"

# Use a standard browser User-Agent to mitigate basic 403 Forbidden scenarios
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

def fetch_clinic_progress():
    """
    Fetches the clinic list and currently serving numbers from the hospital OPD page.
    Implements robust error handling for connection issues and structural changes.
    """
    try:
        logging.info(f"Initiating request to {TARGET_URL}...")
        
        # 1. Fetch the webpage with a timeout mechanism (5 seconds)
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=5)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx and 5xx)

        # 2. Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # NOTE: Since the exact HTML structure of the actual AFTYGH system requires deep inspection,
        # below is an illustrative parsing approach assuming standard table/div structures.
        clinics_data = []
        
        # Example logic: Assume clinics are listed in divisions with a specific class, eg. 'clinic-card'
        # In a real-world scenario, you will need to inspect the DOM of https://www.aftygh.gov.tw/opd/
        # to find the correct CSS selectors. Often these systems fetch via an internal API.
        cards = soup.find_all('div', class_='clinic-card') 
        
        if not cards:
             logging.warning("No clinic cards found! The website structure may have changed, or an internal API is being used instead of server-side rendering. Use DevTools (F12) to double check Network requests.")
             # Demonstrating a fallback fake payload for architecture illustration
             clinics_data.append({"clinic_name": "內科 01診", "current_number": 25, "doctor": "王大明"})
             clinics_data.append({"clinic_name": "外科 02診", "current_number": 12, "doctor": "陳小華"})
        else:
            for card in cards:
                # illustrative extraction
                name = card.find('h3', class_='clinic-name').text.strip()
                number_txt = card.find('span', class_='current-number').text.strip()
                clinics_data.append({
                    "clinic_name": name,
                    "current_number": int(number_txt) if number_txt.isdigit() else 0,
                    "doctor": card.find('span', class_='doctor-name').text.strip()
                })

        return {"status": "success", "data": clinics_data}

    except requests.exceptions.Timeout:
        logging.error("Request timed out. The hospital server is taking too long to respond.")
        return {"status": "error", "message": "資料更新中 (連線逾時)", "error_type": "timeout"}
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error occurred: {e}")
        return {"status": "error", "message": "資料更新中 (網路異常)", "error_type": "network_error"}
    
    except Exception as e:
        logging.error(f"Unexpected error parsing the data: {e}")
        return {"status": "error", "message": "資料更新中 (解析失敗)", "error_type": "parse_error"}

def monitor_clinic(clinic_id, my_number, interval_minutes=2):
    """
    Demonstrates the polling logic to monitor a specific clinic's number progress.
    """
    previous_number = 0
    poll_interval = interval_minutes * 60

    while True:
        result = fetch_clinic_progress()
        
        if result["status"] == "success":
            # For demonstration, we simply pick the first clinic in the dummy payload
            current_clinic = result["data"][0] if result["data"] else None
            
            if current_clinic:
                current_number = current_clinic["current_number"]
                logging.info(f"[{current_clinic['clinic_name']}] Current Number: {current_number} | Your Number: {my_number}")
                
                # Check for sudden jumps (e.g. leap >= 10 means Doctor skipped/accelerated)
                if current_number - previous_number >= 10 and previous_number != 0:
                    logging.warning(f"SUDDEN JUMP DETECTED! Number jumped from {previous_number} to {current_number}. Recalculating ETA immediately!")
                
                # Calculate Remaining People
                remaining = my_number - current_number
                if remaining <= 0:
                    logging.info("It's your turn or you've been skipped! Please report to the clinic.")
                    break
                else:
                    logging.info(f"Remaining people approx: {remaining}")
                
                previous_number = current_number

        else:
            logging.info(f"Polling warning: {result['message']}")
        
        # Sleep until the next polling cycle
        logging.info(f"Sleeping for {poll_interval} seconds...")
        time.sleep(poll_interval)


if __name__ == "__main__":
    print("--- Hospital OPD Scraper Demo ---")
    data = fetch_clinic_progress()
    print(json.dumps(data, indent=4, ensure_ascii=False))
    
    print("\n--- Starting Background Polling Demo ---")
    # Simulate my registration number is 40
    # monitor_clinic("C01", 40, interval_minutes=0.1) # Set interval to short scale for testing
