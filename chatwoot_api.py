import os
import requests
from dotenv import load_dotenv

load_dotenv()

CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")

raw_url = os.getenv("CHATWOOT_URL", "")
# Sanitize URL: remove /app/... or /conversations...
if "/app" in raw_url:
    CHATWOOT_URL = raw_url.split("/app")[0]
elif "/conversations" in raw_url:
    CHATWOOT_URL = raw_url.split("/conversations")[0]
else:
    CHATWOOT_URL = raw_url

# Remove trailing slash
CHATWOOT_URL = CHATWOOT_URL.rstrip('/')

CHATWOOT_ACCOUNT_ID = "1"  # Usually 1, adjust if needed

def get_contact_by_phone(phone):
    """
    Search for a contact in Chatwoot by phone number.
    Returns contact data if found, None otherwise.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return None
    
    # Clean phone number
    clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Search contacts
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/search"
        params = {"q": clean_phone}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('payload') and len(data['payload']) > 0:
                return data['payload'][0]  # Return first match
        
        return None
    except Exception as e:
        print(f"Error searching Chatwoot contact: {e}")
        return None


def get_conversation_history(contact_id):
    """
    Get conversation history for a contact from Chatwoot.
    Returns a list of messages or None.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return None
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Get contact's conversations
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/{contact_id}/conversations"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('payload') and len(data['payload']) > 0:
                # Get the most recent conversation
                conversation_id = data['payload'][0]['id']
                
                # Get messages from that conversation
                messages_url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
                messages_response = requests.get(messages_url, headers=headers, timeout=10)
                
                if messages_response.status_code == 200:
                    messages_data = messages_response.json()
                    return messages_data.get('payload', [])
        
        return None
    except Exception as e:
        print(f"Error fetching Chatwoot conversation: {e}")
        return None


def format_history_for_llm(messages):
    """
    Format Chatwoot messages into a readable history for LLM.
    """
    if not messages:
        return None
    
    formatted = []
    for msg in messages[-10:]:  # Last 10 messages
        sender = "Cliente" if msg.get('message_type') == 0 else "Ivair"
        content = msg.get('content', '')
        if content:
            formatted.append(f"{sender}: {content}")
    
    return "\n".join(formatted) if formatted else None

def list_conversations(page=1, sort_by='last_activity_at'):
    """
    List conversations from Chatwoot.
    Useful for polling updates.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return []
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        # This endpoint lists all conversations
        # Status 'open' is default, but we might want 'all' to capture resolved ones too if they had activity?
        # Usually for sync we want arguably everything that changed.
        # But 'mine' or 'all' depends on assignment. Let's try to get all.
        
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
        params = {
            "page": page, 
            "sort_by": sort_by,
            # "status": "all" # Optional, if we want resolved chats too
        }

        # print(f"DEBUG: Calling {url}")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                return data.get('data', {}).get('payload', [])
            except ValueError:
                print(f"DEBUG: Invalid JSON. Response text: {response.text}")
                return []
        else:
            print(f"DEBUG: Chatwoot API Error {response.status_code}: {response.text} (URL: {url})")
        
        return []
    except Exception as e:
        print(f"Error listing Chatwoot conversations: {e}")
        return []
