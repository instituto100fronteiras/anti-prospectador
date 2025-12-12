import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TRELLO_API_KEY")
TOKEN = os.getenv("TRELLO_TOKEN")
BOARD_ID = os.getenv("TRELLO_BOARD_ID") # Short ID or Long ID

BASE_URL = "https://api.trello.com/1"

def is_configured():
    return bool(API_KEY and TOKEN and BOARD_ID)

def get_lists():
    if not is_configured(): return {}
    
    url = f"{BASE_URL}/boards/{BOARD_ID}/lists"
    query = {
        'key': API_KEY,
        'token': TOKEN
    }
    try:
        response = requests.get(url, params=query)
        if response.status_code == 200:
            lists = response.json()
            return {l['name']: l['id'] for l in lists}
        else:
            print(f"Error getting Trello lists: {response.text}")
            return {}
    except Exception as e:
        print(f"Error connecting to Trello: {e}")
        return {}

# Cache lists to avoid frequent API calls
_lists_cache = {}

def create_list(name):
    if not is_configured(): return None
    
    # Check if exists first
    list_id = get_list_id(name)
    if list_id: return list_id
    
    url = f"{BASE_URL}/boards/{BOARD_ID}/lists"
    query = {
        'name': name,
        'pos': 'bottom',
        'key': API_KEY,
        'token': TOKEN
    }
    try:
        response = requests.post(url, params=query)
        if response.status_code == 200:
            data = response.json()
            # Update cache
            _lists_cache[name] = data['id']
            return data['id']
        else:
            print(f"Error creating list '{name}': {response.text}")
            return None
    except Exception as e:
        print(f"Error creating list: {e}")
        return None

def get_list_id(name):
    global _lists_cache
    if not _lists_cache:
        _lists_cache = get_lists()
    
    # Try exact match
    if name in _lists_cache:
        return _lists_cache[name]
        
    # Try partial match (case insensitive)
    name_lower = name.lower()
    for l_name, l_id in _lists_cache.items():
        if name_lower in l_name.lower():
            return l_id
            
    return None

def find_card(query_str):
    if not is_configured(): return None
    
    # Search for card on board
    url = f"{BASE_URL}/search"
    query = {
        'query': f"board:{BOARD_ID} {query_str}",
        'modelTypes': 'cards',
        'card_fields': 'id,name,idList,url,shortUrl',
        'key': API_KEY,
        'token': TOKEN
    }
    
    try:
        response = requests.get(url, params=query)
        results = response.json()
        cards = results.get('cards', [])
        if cards:
            return cards[0] # Return first match
        return None
    except Exception as e:
        print(f"Error searching Trello card: {e}")
        return None

def find_card_by_phone(phone):
    # Search by phone number (likely in description or title)
    return find_card(phone)

def find_card_by_name(card_name):
    # Search by specific name attribute
    return find_card(f"name:\"{card_name}\"")

def create_card(lead_data, list_name="Prospecção"):
    if not is_configured(): 
        print("Trello not configured. Skipping create_card.")
        return None

    card_name = f"{lead_data['name']} - {lead_data['phone']}"
    
    # Check duplicate by PHONE first (more robust)
    existing_card = find_card_by_phone(lead_data['phone'])
    if existing_card:
        print(f"Card already exists (found by phone). ID: {existing_card['id']}")
        return existing_card['id']

    # Fallback: Check by name (if phone was formatted differently in search vs card)
    existing_card_name = find_card_by_name(card_name)
    if existing_card_name:
         print(f"Card already exists (found by name). ID: {existing_card_name['id']}")
         return existing_card_name['id']
    
    list_id = get_list_id(list_name)
    if not list_id:
        # Fallback to first list if specific one not found
        if _lists_cache:
            list_id = list(_lists_cache.values())[0]
        else:
            print(f"Could not find list '{list_name}' and no lists available.")
            return None
            
    url = f"{BASE_URL}/cards"
    
    desc = f"""
    **Telefone:** {lead_data.get('phone')}
    **Site:** {lead_data.get('website') or 'N/A'}
    **Avaliação:** {lead_data.get('rating')} ({lead_data.get('reviews')} reviews)
    **Setor:** {lead_data.get('search_term') or 'N/A'}
    **Endereço:** {lead_data.get('address')}
    
    **Contexto:**
    Lead capturado via Google Maps.
    """
    
    query = {
        'idList': list_id,
        'name': card_name,
        'desc': desc,
        'pos': 'top',
        'key': API_KEY,
        'token': TOKEN
    }
    
    try:
        response = requests.post(url, params=query)
        if response.status_code == 200:
            card = response.json()
            return card['id']
        else:
            print(f"Error creating card: {response.text}")
            return None
    except Exception as e:
        print(f"Error creating card: {e}")
        return None

def add_comment(card_id, text):
    if not is_configured() or not card_id: return
    
    url = f"{BASE_URL}/cards/{card_id}/actions/comments"
    query = {
        'text': text,
        'key': API_KEY,
        'token': TOKEN
    }
    try:
        requests.post(url, params=query)
    except Exception as e:
        print(f"Error commenting on card: {e}")

def move_card(card_id, list_name):
    if not is_configured() or not card_id: return
    
    list_id = get_list_id(list_name)
    if not list_id: return

    url = f"{BASE_URL}/cards/{card_id}"
    query = {
        'idList': list_id,
        'key': API_KEY,
        'token': TOKEN
    }
    try:
        requests.put(url, params=query)
    except Exception as e:
        print(f"Error moving card: {e}")
