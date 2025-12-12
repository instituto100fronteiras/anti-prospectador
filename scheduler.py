import schedule
import time
import random
import datetime
from database import get_db_connection, add_lead, update_lead_status, get_lead_by_phone, update_lead_prompt_version
from search import search_leads
from scraper import scrape_website
from agent import generate_message
from followup import process_followups
from whatsapp import check_whatsapp_exists, send_message, format_number

# Configuration
SEARCH_CITIES = [
    "Foz do Iguaçu, Brasil",
    "Ciudad del Este, Paraguai", 
    "Puerto Iguazú, Argentina", 
    "Hernandarias, Paraguai", 
    "Presidente Franco, Paraguai"
]

SEARCH_SECTORS = [
    "consultório odontológico", "clínica de estética", "escritório de advocacia", 
    "arquitetura", "engenharia civil", "imobiliária", "escola particular", 
    "agência de marketing", "hotel", "restaurante", "loja de móveis", 
    "concessionária", "pet shop", "academia", "clínica médica", "laboratório",
    "contabilidade", "seguradora", "empresa de energia solar", "startup"
]

def is_within_business_hours():
    now = datetime.datetime.now()
    
    # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    if now.weekday() > 4:
        return False
        
    current_time = now.time()
    
    # Window 1: 09:00 - 11:40
    start1 = datetime.time(9, 0)
    end1 = datetime.time(11, 40)
    
    # Window 2: 14:00 - 17:20
    start2 = datetime.time(14, 0)
    end2 = datetime.time(17, 20)
    
    is_window1 = start1 <= current_time <= end1
    is_window2 = start2 <= current_time <= end2
    
    # Check Vacation Period (Dec 23 - Jan 6)
    # 2025-12-23 to 2026-01-05 (Back on 6th)
    current_date = now.date()
    vacation_start = datetime.date(2025, 12, 23)
    vacation_end = datetime.date(2026, 1, 5) # Inclusive, so it runs on 6th? No, waits until after 5th.
    
    if vacation_start <= current_date <= vacation_end:
        print(f"[Job] Vacation Mode: Paused until {vacation_end + datetime.timedelta(days=1)}.")
        return False
    
    return is_window1 or is_window2

def auto_refill_leads():
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'new'").fetchone()[0]
    conn.close()
    
    print(f"[Auto-Refill] Current new leads: {count}")
    
    if count < 5:
        print("[Auto-Refill] Low inventory. Searching for more leads...")
        sector = random.choice(SEARCH_SECTORS)
        city = random.choice(SEARCH_CITIES)
        query = f"{sector} em {city}"
        
        print(f"[Auto-Refill] Searching: '{query}'")
        try:
            leads = search_leads(query, num_pages=1) # Search 1 page to check quality
            
            added_count = 0
            for lead in leads:
                # Clean phone
                lead['phone'] = format_number(lead['phone'])
                
                conn = get_db_connection()
                exists = conn.execute("SELECT 1 FROM leads WHERE phone = ?", (lead['phone'],)).fetchone()
                conn.close()
                
                if not exists:
                    # Validate WhatsApp immediately
                    jid = check_whatsapp_exists(lead['phone'])
                    if jid:
                        lead['status'] = 'new'
                        if add_lead(lead):
                            added_count += 1
                    else:
                        print(f"      Skipping invalid number: {lead['phone']}")
                        # Do not add to DB
                        pass
                        
            print(f"[Auto-Refill] Added {added_count} leads.")
            
        except Exception as e:
            print(f"[Auto-Refill] Error searching: {e}")

def process_one_lead():
    if not is_within_business_hours():
        print("[Job] Outside business hours. Skipping.")
        return

    print("[Job] Starting process for one lead...")
    
    conn = get_db_connection()
    # Pick a random 'new' lead
    # Using ORDER BY RANDOM() is inefficient for huge tables but fine here
    lead_row = conn.execute("SELECT * FROM leads WHERE status = 'new' ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    
    if not lead_row:
        print("[Job] No new leads available.")
        auto_refill_leads() # Trigger refill immediately if empty
        return

    lead = dict(lead_row)
    print(f"[Job] Selected lead: {lead['name']} ({lead['phone']}) - Lang: {lead.get('language')}")
    
    # LOCK LEAD IMMEDIATELY to prevent duplicates if crashed/stopped
    update_lead_status(lead['phone'], 'processing')
    
    # DUPLICATE PREVENTION: Check if this phone was already contacted recently
    conn = get_db_connection()
    recent_contact = conn.execute("""
        SELECT id, name, last_contact_date 
        FROM leads 
        WHERE phone = ? 
        AND status IN ('contacted', 'responded', 'follow_up_1', 'follow_up_2', 'follow_up_3')
        AND last_contact_date > datetime('now', '-7 days')
        AND id != ?
    """, (lead['phone'], lead['id'])).fetchone()
    conn.close()
    
    if recent_contact:
        recent = dict(recent_contact)
        print(f"      ⚠️ DUPLICATE DETECTED! Phone {lead['phone']} was already contacted:")
        print(f"         Lead ID {recent['id']} ({recent['name']}) on {recent['last_contact_date']}")
        print(f"      Skipping to avoid duplicate message. Marking current lead as duplicate.")
        
        # Mark this lead as duplicate/invalid to prevent future attempts
        conn = get_db_connection()
        conn.execute("UPDATE leads SET status = 'duplicate' WHERE id = ?", (lead['id'],))
        conn.commit()
        conn.close()
        return
    
    try:
        # 1. Check Chatwoot for existing conversation history
        print("      Checking Chatwoot for conversation history...")
        chatwoot_history = None
        try:
            import chatwoot_api
            contact = chatwoot_api.get_contact_by_phone(lead['phone'])
            if contact:
                print(f"      Found Chatwoot contact: {contact.get('name')}")
                messages = chatwoot_api.get_conversation_history(contact['id'])
                if messages and len(messages) > 0:
                    chatwoot_history = chatwoot_api.format_history_for_llm(messages)
                    print(f"      Found {len(messages)} previous messages in Chatwoot")
        except Exception as ch_err:
            print(f"      Chatwoot check failed (will use standard template): {ch_err}")
        
        # 2. Scrape website
        website_content = None
        if lead['website']:
            print(f"      Scraping {lead['website']}...") 
            website_content = scrape_website(lead['website'])
        
        # 3. Generate message based on context
        message_parts = None
        chosen_version = None
        
        if chatwoot_history:
            # Use AI to generate contextual message based on history
            print("      Generating contextual message based on Chatwoot history...")
            from agent import generate_contextual_message
            message_parts = generate_contextual_message(lead, chatwoot_history)
            chosen_version = "CONTEXTUAL"
        else:
            # Use standard A/B/C templates
            chosen_version = random.choice(['A', 'B', 'C'])
            
            # Adjust for language
            language = lead.get('language', 'pt')
            final_version = chosen_version
            if language == 'es':
                final_version = f"{chosen_version}_ES"
            
            # Get message parts from template
            from agent import PROMPT_TEMPLATES
            message_parts = PROMPT_TEMPLATES.get(final_version, PROMPT_TEMPLATES.get(chosen_version, PROMPT_TEMPLATES['A']))
            print(f"      Using template version {final_version} ({len(message_parts)} parts)...")
        
        if message_parts:
            # 4. Send (Multi-part with delays for human-like behavior)
            print("      Sending WhatsApp (Multi-part)...")
            jid = check_whatsapp_exists(lead['phone'])
            
            if jid:
                full_message_log = []
                
                for i, part in enumerate(message_parts):
                    print(f"      Sending part {i+1}/{len(message_parts)}...")
                    send_message(jid, part)
                    full_message_log.append(part)
                    
                    # Delay between parts (except after last message)
                    if i < len(message_parts) - 1:
                        delay = random.randint(5, 10) # 5-10 seconds
                        print(f"      Waiting {delay}s before next part...")
                        time.sleep(delay)
                
                # 5. Update DB with full conversation
                full_message = "\n\n".join(full_message_log)
                update_lead_status(lead['phone'], 'contacted', f"🤖 Ivair (v{chosen_version}):\n\n{full_message}")
                update_lead_prompt_version(lead['phone'], chosen_version)
                
                # 6. Trello Sync
                try:
                    import trello_crm
                    if trello_crm.is_configured():
                        card_id = trello_crm.create_card(lead, list_name="Contato Frio")
                        
                        if card_id:
                            trello_crm.add_comment(card_id, f"🤖 Agente enviou (v{chosen_version}):\n\n{full_message}")
                            print(f"      Trello synced (Card ID: {card_id} -> Contato Frio)")
                except Exception as t_err:
                    print(f"      Trello Sync Error: {t_err}")

                print("      Success! Lead contacted.")
            else:
                print("      Invalid WhatsApp (unexpected, should have been filtered). Deleting from DB.")
                conn = get_db_connection()
                conn.execute("DELETE FROM leads WHERE phone = ?", (lead['phone'],))
                conn.commit()
                conn.close()
        else:
            print("      Failed to get message template.")
            # Revert to 'new' or mark as 'error' so we don't lose it?
            # Safe to revert to 'new' if it was just an empty template error
            update_lead_status(lead['phone'], 'new')
            
    except Exception as e:
        print(f"[Job] Error processing lead {lead['name']}: {e}")
        # Mark as error to avoid infinite loop
        update_lead_status(lead['phone'], 'error_sending')

if __name__ == "__main__":
    import sys
    # Enable unbuffered output programmatically just in case
    sys.stdout.reconfigure(line_buffering=True)
    
    print("=== Auto-Scheduler Started ===")
    print("Schedule: Mon-Fri | 09:00-11:40 & 14:00-17:20 | Every 30 mins")
    
    try:
        # Initialize Trello Lists (Ensure they exist or just checking)
        # User requested specific lists: 'Contato Frio', 'Conexão'
        try:
            import trello_crm
            if trello_crm.is_configured():
                # We assume these lists exist or we create them if missing?
                # Let's create them just in case to avoid errors, using the names user gave.
                trello_crm.create_list("Contato Frio")
                trello_crm.create_list("Conexão")
                # 'A Prospectar' is manual, so we don't necessarily need to autocreate it, but good practice.
                trello_crm.create_list("A Prospectar")
        except Exception as e:
            print(f"Warning: Could not init Trello lists: {e}")

        # Run once at startup to check/refill
        auto_refill_leads()
        
        # Run the first job immediately as requested by user to see it working
        print("[Job] Executing immediate start-up run...")
        process_one_lead()
        
        # Schedule layout
        schedule.every(30).minutes.do(process_one_lead)
        
        # Ideally checking refill more often?
        schedule.every(1).hours.do(auto_refill_leads)

        # Follow-ups (Check every 4 hours)
        schedule.every(4).hours.do(process_followups, dry_run=False)

        # Chatwoot <-> Trello Sync (Every 15 mins)
        from sync_chatwoot_trello import run_sync
        schedule.every(15).minutes.do(run_sync)

        while True:
            schedule.run_pending()
            time.sleep(60) # Sleep 1 minute to save CPU
            
    except Exception as e:
        print(f"CRITICAL SCHEDULER CRASH: {e}")
        import traceback
        traceback.print_exc()
        raise e
