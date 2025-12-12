import requests
import re
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TRELLO_API_KEY")
TOKEN = os.getenv("TRELLO_TOKEN")
BOARD_ID = os.getenv("TRELLO_BOARD_ID")
BASE_URL = "https://api.trello.com/1"

def get_all_cards():
    url = f"{BASE_URL}/boards/{BOARD_ID}/cards"
    query = {
        'fields': 'id,name,desc,idList,dateLastActivity',
        'key': API_KEY,
        'token': TOKEN
    }
    response = requests.get(url, params=query)
    return response.json()

def get_card_actions(card_id):
    url = f"{BASE_URL}/cards/{card_id}/actions"
    query = {
        'filter': 'commentCard',
        'key': API_KEY,
        'token': TOKEN
    }
    response = requests.get(url, params=query)
    if response.status_code == 200:
        return response.json()
    return []

def add_comment(card_id, text):
    url = f"{BASE_URL}/cards/{card_id}/actions/comments"
    query = {
        'text': text,
        'key': API_KEY,
        'token': TOKEN
    }
    requests.post(url, params=query)

def archive_card(card_id):
    url = f"{BASE_URL}/cards/{card_id}"
    query = {
        'closed': 'true',
        'key': API_KEY,
        'token': TOKEN
    }
    requests.put(url, params=query)

def extract_phone(card_name):
    # Try to extract phone from "Name - Phone" format
    # Our agent uses "Name - Phone"
    # Match last sequence of digits if > 8 chars
    match = re.search(r'(\d{8,})', card_name)
    if match:
        return match.group(1)
    return None

def deduplicate():
    print("Fetching all cards...")
    cards = get_all_cards()
    print(f"Total cards: {len(cards)}")
    
    # Group by Phone
    by_phone = {}
    by_name = {}
    
    for card in cards:
        # 1. By Phone
        phone = extract_phone(card['name'])
        if phone:
            if phone not in by_phone:
                by_phone[phone] = []
            by_phone[phone].append(card)
        
        # 2. By Name (Normalized)
        name_clean = card['name'].strip().lower()
        if name_clean not in by_name:
            by_name[name_clean] = []
        by_name[name_clean].append(card)

    duplicates_found = 0
    merged_count = 0
    
    processed_ids = set()

    # Process Phone Duplicates
    for phone, grouped_cards in by_phone.items():
        if len(grouped_cards) > 1:
            # Check if any already processed
            if any(c['id'] in processed_ids for c in grouped_cards):
                continue
                
            duplicates_found += 1
            print(f"\n--- Processing Phone Duplicates for {phone} ---")
            
            sorted_cards = sorted(grouped_cards, key=lambda x: x['id'])
            master = sorted_cards[0]
            duplicates = sorted_cards[1:]
            
            _merge_cards(master, duplicates)
            processed_ids.add(master['id'])
            for d in duplicates:
                processed_ids.add(d['id'])
            merged_count += len(duplicates)

    # Process Name Duplicates
    for name, grouped_cards in by_name.items():
        if len(grouped_cards) > 1:
             # Check if any already processed (to avoid double merging)
            if any(c['id'] in processed_ids for c in grouped_cards):
                continue
                
            duplicates_found += 1
            print(f"\n--- Processing Name Duplicates for '{name}' ---")
            
            sorted_cards = sorted(grouped_cards, key=lambda x: x['id'])
            master = sorted_cards[0]
            duplicates = sorted_cards[1:]
            
            _merge_cards(master, duplicates)
            processed_ids.add(master['id'])
            for d in duplicates:
                processed_ids.add(d['id'])
            merged_count += len(duplicates)

    print(f"\nCompleted! Found {duplicates_found} sets of duplicates. Merged {merged_count} cards.")

def _merge_cards(master, duplicates):
    print(f"Master: {master['name']} ({master['id']})")
    for dup in duplicates:
        print(f"  Merging Duplicate: {dup['name']} ({dup['id']})")
        
        # 1. Fetch comments/activity
        actions = get_card_actions(dup['id'])
        
        # 2. Add history to Master
        merge_note = f"⚠️ **Mesclado do cartão duplicado [{dup['name']}]**\n"
        
        # Copy description if master is empty, else append as comment
        if dup['desc'].strip() and dup['desc'] != master['desc']:
             merge_note += f"\n**Descrição Original:**\n{dup['desc']}\n"
        
        # Copy comments
        if actions:
            merge_note += "\n**Histórico de Comentários:**\n"
            for action in actions:
                data = action.get('data', {})
                text = data.get('text', '')
                author = action.get('memberCreator', {}).get('fullName', 'Desconhecido')
                # Filter out system updates if needed, but keeping text is safe
                if text:
                    merge_note += f"- {author}: {text}\n"
        
        add_comment(master['id'], merge_note)
        
        # 3. Archive Duplicate
        archive_card(dup['id'])
        print("    -> Merged and Archived.")

if __name__ == "__main__":
    deduplicate()
