import os
import sys
import time
from datetime import datetime
import chatwoot_api
from database import get_db_connection, add_lead, update_lead_status, get_lead_by_phone, init_db

def restore_leads():
    print("🔄 [Restore] Starting Full Import from Chatwoot...")
    
    # Ensure DB exists
    init_db()
    
    page = 1
    total_restored = 0
    total_skipped = 0
    
    while True:
        print(f"🔄 [Restore] Fetching page {page}...")
        conversations = chatwoot_api.list_conversations(page=page, sort_by='last_activity_at')
        
        if not conversations:
            print("✅ [Restore] No more conversations found.")
            break
            
        for conv in conversations:
            try:
                # Extract Lead Info
                meta = conv.get('meta', {})
                sender = meta.get('sender', {})
                phone = sender.get('phone_number')
                name = sender.get('name', 'Cliente Ex-Chatwoot')
                
                if not phone:
                    continue
                    
                # Check if exists locally
                cleaned_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
                
                # We process ALL leads (New or Existing) to ensure status is synced
                existing = get_lead_by_phone(cleaned_phone)
                
                # Fetch History text (Needed for status check)
                messages = chatwoot_api.get_conversation_history(sender.get('id'))
                history_text = chatwoot_api.format_history_for_llm(messages)
                    
                # Determine Status - STRICT MODE
                # Last message determines status
                status = 'contacted' # Default
                if messages and len(messages) > 0:
                    # Assuming messages are sorted chronological (last is newest)
                    last_msg = messages[-1]
                    if last_msg.get('message_type') == 0: # 0 = Incoming (Client)
                        status = 'responded'
                    else:
                        status = 'contacted'
                        
                # Last Activity Date
                last_activity = conv.get('last_activity_at')
                if last_activity:
                    last_date = datetime.fromtimestamp(last_activity)
                else:
                    last_date = datetime.now()

                if existing:
                    # UPDATE existing lead
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute('''
                        UPDATE leads 
                        SET status = ?, last_contact_date = ?, conversation_history = ?
                        WHERE phone = ?
                    ''', (status, last_date, history_text, cleaned_phone))
                    conn.commit()
                    conn.close()
                    print(f"🔄 [Sync] Updated {name} ({cleaned_phone}) -> {status}")
                    
                else:
                    # INSERT new lead
                    lead = {
                        'name': name,
                        'phone': cleaned_phone,
                        'address': str(sender.get('location', '')),
                        'website': '', 
                        'rating': 0,
                        'reviews': 0,
                        'types': 'chatwoot_import',
                        'search_term': 'Importado do Histórico',
                        'language': 'pt'
                    }
                    
                    if add_lead(lead):
                         # Update status immediately after add
                         conn = get_db_connection()
                         c = conn.cursor()
                         c.execute('''
                            UPDATE leads 
                            SET status = ?, last_contact_date = ?, conversation_history = ?
                            WHERE phone = ?
                        ''', (status, last_date, history_text, cleaned_phone))
                         conn.commit()
                         conn.close()
                         print(f"✅ [Restore] Imported {name} ({cleaned_phone}) as {status}")
                         total_restored += 1
                    else:
                         print(f"❌ [Restore] Failed to add {cleaned_phone}")
                    
            except Exception as e:
                print(f"❌ [Restore] Error processing item: {e}")
                
        page += 1
        time.sleep(1) # Rate limit safety
        
    print(f"\n🎉 [Restore Complete] Imported: {total_restored} | Skipped: {total_skipped}")

if __name__ == "__main__":
    restore_leads()
