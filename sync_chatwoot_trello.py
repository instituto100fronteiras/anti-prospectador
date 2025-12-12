import os
import json
import time
from datetime import datetime, timedelta
import chatwoot_api
import trello_crm
from database import get_db_connection

# File to store the last sync timestamp
STATE_FILE = "sync_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # Default: sync from 24h ago if no state exists
    return {"last_sync_timestamp": (datetime.now() - timedelta(days=1)).timestamp()}

def save_state(timestamp):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({"last_sync_timestamp": timestamp}, f)
    except Exception as e:
        print(f"Error saving sync state: {e}")

def run_sync():
    print("🔄 [Sync] Starting Chatwoot -> Trello sync...")
    
    state = load_state()
    last_sync_ts = state.get("last_sync_timestamp", 0)
    last_sync_dt = datetime.fromtimestamp(last_sync_ts)
    
    print(f"🔄 [Sync] Fetching conversations updated since {last_sync_dt}...")
    
    # Simple pagination loop
    page = 1
    processed_count = 0
    
    # We will update the timestamp to NOW at the start (or end), 
    # but to be safe against long running jobs, we capture start time.
    current_run_ts = datetime.now().timestamp()
    
    while True:
        conversations = chatwoot_api.list_conversations(page=page)
        if not conversations:
            break
            
        # Conversations are usually sorted by last_activity_at desc
        # So if we hit one older than last_sync, we can stop (optimization)
        
        should_continue = True
        
        for conv in conversations:
            last_activity = conv.get('last_activity_at') # Unix timestamp usually
            if not last_activity: continue
            
            # Chatwoot timestamp might be int (seconds)
            if last_activity <= last_sync_ts:
                should_continue = False
                break
                
            # Process this conversation
            try:
                process_conversation(conv, last_sync_ts)
                processed_count += 1
            except Exception as e:
                print(f"❌ [Sync] Error processing conversation {conv.get('id')}: {e}")
        
        if not should_continue:
            break
            
        page += 1
        # Safety break
        if page > 10: break
        
    print(f"✅ [Sync] Finished. Processed {processed_count} updated conversations.")
    save_state(current_run_ts)

def process_conversation(conv, last_sync_ts):
    # 1. Get Contact Info
    meta = conv.get('meta', {})
    sender = meta.get('sender', {})
    phone = sender.get('phone_number')
    name = sender.get('name', 'Cliente Desconhecido')
    
    if not phone:
        # Cannot sync without phone identifier
        return

    print(f"   -> Processing update for {name} ({phone})")
    
    # 2. Get Messages for context
    messages = chatwoot_api.get_conversation_history(sender.get('id'))
    if not messages: return

    # Filter messages newer than last sync
    new_messages = []
    
    for msg in messages:
        try:
            # Handle Created At
            created_at = msg.get('created_at')
            msg_ts = 0
            
            if isinstance(created_at, int):
                msg_ts = created_at
            elif isinstance(created_at, str) and created_at.isdigit():
                 msg_ts = int(created_at)
            
            # Identify Sender
            # 0 = Incoming (Client), 1 = Outgoing (Agent/Ivair)
            msg_type = msg.get('message_type')
            sender_name = "Cliente" if msg_type == 0 else "Ivair"
            
            # Strict > check to avoid dupes if sync runs fast
            if msg_ts > last_sync_ts:
                # Format Time (e.g. 14:30)
                time_str = datetime.fromtimestamp(msg_ts).strftime('%H:%M')
                
                content = msg.get('content', '')
                if content:
                    new_messages.append(f"⏰ [{time_str}] **{sender_name}**: {content}")
                    
        except Exception as e:
            print(f"      Error parsing message: {e}")
            continue

    if not new_messages:
        return # Nothing new to sync

    # 3. Find/Create Trello Card
    if not trello_crm.is_configured():
        print("      ⚠️ Trello not configured.")
        return

    card = trello_crm.find_card_by_phone(phone)
    
    # Combined Update Text
    update_block = "\n".join(new_messages)
    header = "💬 **Nova Interação no Chatwoot**"
    final_comment = f"{header}\n{update_block}\n_(Via Sync Automático)_"
    
    if card:
        # 1. Deduplication: Check if last comment is identical
        last_comment = trello_crm.get_last_comment(card['id'])
        if last_comment and update_block in last_comment:
            print(f"      Skipping duplicate comment for {card['name']}")
        else:
            # Update existing
            trello_crm.add_comment(card['id'], final_comment)
            print(f"      Updated Trello Card: {card['name']} with {len(new_messages)} new messages")
            
        # 2. Intelligent Renaming (Cost Saving: Only if name looks like a phone number)
        # Check if card name starts with + or digit (indicates phone number)
        current_name = card['name']
        is_phone_name = current_name.strip().startswith('+') or current_name.strip()[0].isdigit()
        
        if is_phone_name:
             # We have new context, let's try to extract a name
             print(f"      🕵️‍♂️ Analyzing conversation to rename card: {current_name}")
             from agent import analyze_conversation_for_name
             
             # Use full history strictly for analysis
             full_history = chatwoot_api.format_history_for_llm(messages)
             recognition = analyze_conversation_for_name(full_history)
             
             if recognition and recognition.get('name') and recognition.get('confidence') == 'high':
                 new_name = f"{recognition['name']} - {phone}"
                 print(f"      ✨ Renaming card to: {new_name}")
                 trello_crm.update_card(card['id'], name=new_name)
    else:
        # Create new
        lead_data = {
            'name': name,
            'phone': phone,
            'website': '',
            'search_term': 'Chatwoot Inbound',
            'address': str(sender.get('location', ''))
        }
        
        target_list = "Leads a Qualificar"
        trello_crm.create_list(target_list)
        
        card_id = trello_crm.create_card(lead_data, list_name=target_list)
        if card_id:
            trello_crm.add_comment(card_id, "🔔 **Novo Lead vindo do Chatwoot**\n" + final_comment)
            print(f"      Created New Trello Card in '{target_list}'")

if __name__ == "__main__":
    run_sync()
