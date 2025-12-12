import os
import requests
import re
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("EVOLUTION_API_URL")
INSTANCE = os.getenv("EVOLUTION_INSTANCE")
API_KEY = os.getenv("EVOLUTION_API_KEY")

def format_number(phone):
    # Remove non-digits
    clean_phone = re.sub(r'\D', '', phone)
    
    # Basic validation for Brazil numbers (usually 10 or 11 digits without country code, or 12/13 with)
    # If it starts with 55, keep it. If not, assume it needs 55? 
    # SerpAPI usually returns formatted numbers like "+55 45 9..."
    
    if not clean_phone.startswith('55'):
        clean_phone = '55' + clean_phone
        
    return clean_phone

def check_whatsapp_exists(phone):
    # Try to check if number exists on WhatsApp
    # This endpoint might vary based on Evolution API version
    # Based on n8n workflow, it uses /chat/whatsappNumbers/{instance}
    
    url = f"{API_URL}/chat/whatsappNumbers/{INSTANCE}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    
    # 1. Clean the input first (remove non-digits)
    clean_phone = re.sub(r'\D', '', phone)
    
    # Validation/Heuristics
    numbers_to_check = []
    
    # Heuristic for Brazil Numbers:
    # 55 + DDD (2) + 9 + 8 digits = 13
    # 55 + DDD (2) + 8 digits = 12
    # We should try both logic for any input >= 12 chars
    
    if len(clean_phone) >= 12:
        # Assume it includes country code 55 (if user provided it, or if stripped)
        # Note: Scrapers usually provide +55.
        
        # Try as is (clean)
        numbers_to_check.append(clean_phone)
        
        # Try removing 9 if it's 13 digits (force 8 digit format)
        if len(clean_phone) == 13 and clean_phone[4] == '9':
             numbers_to_check.append(clean_phone[:4] + clean_phone[5:])
             
        # Try adding 9 if it's 12 digits (force 9 digit format)
        if len(clean_phone) == 12:
             numbers_to_check.append(clean_phone[:4] + '9' + clean_phone[4:])

    # Fallback: if cleaning failed or short, just try the original just in case
    if not numbers_to_check:
        numbers_to_check.append(phone)
    
    payload = {
        "numbers": list(set(numbers_to_check)) # Remove duplicates
    }
    
    print(f"DEBUG: Checking WhatsApp for numbers: {payload['numbers']}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        print(f"DEBUG: Evolution API Response: {data}")
        
        # Check for API errors
        if isinstance(data, dict) and (data.get('isBoom') or data.get('error')):
            print(f"DEBUG: Evolution API Error: {data.get('output', {}).get('payload', {}).get('message', 'Unknown Error')}")
            return None
            
        # Check if any number exists
        if isinstance(data, list):
            for item in data:
                print(f"DEBUG: Item check: {item}")
                if isinstance(item, dict) and item.get('exists'):
                    return item.get('jid')
                
        return None
    except Exception as e:
        print(f"Error checking WhatsApp: {e}")
        return None

def send_message(jid, text):
    url = f"{API_URL}/message/sendText/{INSTANCE}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Extract number from JID
    number = jid.split('@')[0]
    
    payload = {
        "number": number,
        "text": text
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None
