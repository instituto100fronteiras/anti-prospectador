import sys
import chatwoot_api
import trello_crm
from database import get_db_connection

TARGET_PHONE = "5545999831200"

print(f"--- 🔄 MANUAL SYNC FOR {TARGET_PHONE} ---")

# 1. Fetch from Chatwoot
contact = None

# FORCE ID 844
print("⚠️ Forcing ID 844 (Found via debug listing)...")
contact = {'id': 844, 'name': 'Clínica Odontológica (Manual)', 'phone_number': '+554599831200'}

if not contact:
    print(f"❌ Contact not found in Chatwoot for {TARGET_PHONE}.")
    print("   Trying manual search debug...")
    # Debug search
    import requests
    import os
    headers = {"api_access_token": os.getenv("CHATWOOT_API_TOKEN"), "Content-Type": "application/json"}
    base_url = os.getenv('CHATWOOT_URL')
    print(f"   BASE URL: '{base_url}'")
    url = f"{base_url}/api/v1/accounts/1/contacts/search"
    
    queries = [
        TARGET_PHONE, 
        f"+{TARGET_PHONE}",
        "Central Saúde",
        "Clínica Odontológica",
        "+55 45 99983-1200", 
        "55 45 99983 1200"
    ]
    
    for q in queries:
        print(f"   Searching q='{q}'...")
        res = requests.get(url, headers=headers, params={"q": q})
        data = res.json()
        if data.get('payload') and len(data['payload']) > 0:
            contact = data['payload'][0]
            print(f"   ✅ FOUND via '{q}'! ID: {contact['id']}")
            break
        else:
            print(f"   Status: {res.status_code}, Found: 0")
            
    if not contact:
        print("❌ Exhausted all search options. Contact really not found.")
        sys.exit(1)
            

print(f"   Found Contact: {contact.get('name')} (ID: {contact['id']})")

messages = chatwoot_api.get_conversation_history(contact['id'])
if not messages:
    print("❌ No messages found.")
    sys.exit(1)

print(f"   Found {len(messages)} messages.")

# Format latest messages
formatted_msgs = []
for msg in messages[-5:]: # Last 5
    sender = "Cliente" if msg.get('message_type') == 0 else "Ivair"
    content = msg.get('content', '')
    if content:
        formatted_msgs.append(f"**{sender}**: {content}")

update_text = "\n".join(formatted_msgs)
final_comment = f"💬 **Sincronização Manual**\n\n{update_text}"

# 2. Update Trello
print("\n2. Updating Trello...")
if not trello_crm.is_configured():
    print("❌ Trello not configured.")
    sys.exit(1)

# Try to find by phone
card = trello_crm.find_card_by_phone(TARGET_PHONE)

if not card:
    print("⚠️ Card not found not found by phone search.")
    print("   Attempting to use the shortLink from user request if possible...")
    # Getting the ID related to shortLink 'l92XPdJG' would require a specific API call not in our lib.
    # But let's rely on the phone search first as it should work if the card title has the number.
else:
    print(f"   Found Card: {card['name']} (ID: {card['id']})")
    trello_crm.add_comment(card['id'], final_comment)
    print("✅ Comment added successfully!")
