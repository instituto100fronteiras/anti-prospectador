import sqlite3
from datetime import datetime, timedelta
from database import get_db_connection, update_lead_status
from whatsapp import check_whatsapp_exists, send_message
from agent import generate_message

# Configuration
FOLLOWUP_DELAYS = {
    1: 3,  # 3 days after initial contact
    2: 7,  # 7 days after first follow-up
    3: 14  # 14 days after second follow-up
}

FOLLOWUP_PROMPTS = {
    1: "O cliente não respondeu ao primeiro contato feito há 3 dias. Gere uma mensagem curta e educada perguntando se ele conseguiu ver a mensagem anterior. Mantenha o tom profissional e amigável de Ivair.",
    2: "O cliente não respondeu há uma semana. Gere uma mensagem trazendo uma novidade ou um benefício específico da 100fronteiras (ex: audiência qualificada, networking). Algo para despertar interesse.",
    3: "Última tentativa. O cliente não responde há duas semanas. Gere uma mensagem de 'break-up' suave, dizendo que não vai mais incomodar, mas deixando as portas abertas para o futuro."
}

def get_due_followups():
    conn = get_db_connection()
    # Find leads that are 'contacted' or in 'follow_up' status
    # AND where next_contact_date is due (or null if it's the first follow-up check)
    
    # Logic:
    # If status='contacted' and follow_up_stage=0 -> Eligible for Stage 1 (check last_contact_date)
    # If follow_up_stage > 0 -> Check next_contact_date
    
    leads = []
    
    # Stage 1 Candidates
    rows = conn.execute("SELECT * FROM leads WHERE status='contacted' AND follow_up_stage=0").fetchall()
    for row in rows:
        last_contact = datetime.strptime(row['last_contact_date'], '%Y-%m-%d %H:%M:%S.%f')
        if (datetime.now() - last_contact).days >= FOLLOWUP_DELAYS[1]:
            leads.append(dict(row))
            
    # Stage 2 & 3 Candidates
    rows = conn.execute("SELECT * FROM leads WHERE status='follow_up' AND next_contact_date <= ?", (datetime.now(),)).fetchall()
    for row in rows:
        leads.append(dict(row))
        
    conn.close()
    return leads

def process_followups(dry_run=True):
    leads = get_due_followups()
    print(f"Found {len(leads)} leads due for follow-up.")
    
    for lead in leads:
        current_stage = lead['follow_up_stage']
        next_stage = current_stage + 1
        
        if next_stage > 3:
            print(f"Lead {lead['name']} finished all follow-ups. Marking as closed.")
            update_lead_status(lead['phone'], 'closed_no_response')
            continue
            
        print(f"--- Processing Follow-up Stage {next_stage} for {lead['name']} ---")
        
        # Generate Message
        prompt_instruction = FOLLOWUP_PROMPTS.get(next_stage)
        
        from agent import generate_followup_message
        message = generate_followup_message(lead, next_stage)
        
        if not message:
            print("Failed to generate message.")
            continue
            
        print(f"Message:\n{message}")
        
        if not dry_run:
            # Send
            jid = check_whatsapp_exists(lead['phone']) # Re-check just in case
            if jid:
                send_message(jid, message)
                
                # Update DB
                conn = get_db_connection()
                next_delay = FOLLOWUP_DELAYS.get(next_stage + 1)
                next_date = None
                if next_delay:
                    next_date = datetime.now() + timedelta(days=next_delay)
                
                c = conn.cursor()
                c.execute('''
                    UPDATE leads 
                    SET status = 'follow_up', 
                        follow_up_stage = ?, 
                        last_contact_date = ?, 
                        next_contact_date = ?,
                        conversation_history = conversation_history || ? || '\n'
                    WHERE id = ?
                ''', (next_stage, datetime.now(), next_date, message, lead['id']))
                conn.commit()
                conn.close()
                print("Follow-up sent and DB updated.")
                
                # Trello Sync
                try:
                    import trello_crm
                    if trello_crm.is_configured():
                        card_name = f"{lead['name']} - {lead['phone']}"
                        card = trello_crm.find_card_by_name(card_name)
                        if card:
                            trello_crm.add_comment(card['id'], f"🔄 Follow-up {next_stage} enviado:\n\n{message}")
                            print(f"      Trello synced (Card ID: {card['id']})")
                        else:
                            print(f"      Trello card not found for {card_name}")
                except Exception as t_err:
                    print(f"      Trello Sync Error: {t_err}")
            else:
                print("WhatsApp invalid.")
        else:
            print("[DRY RUN] Message not sent.")

if __name__ == "__main__":
    process_followups(dry_run=True)
