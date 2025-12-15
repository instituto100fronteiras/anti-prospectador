import sqlite3
from datetime import datetime, timedelta
from database import get_db_connection, update_lead_status
from whatsapp import check_whatsapp_exists, send_message
from agent import generate_message

# Configuration
FOLLOWUP_DELAYS = {
    1: 3,   # 3 days after initial contact
    2: 7,   # 7 days after first follow-up
    3: 14   # 14 days after second follow-up
}

FOLLOWUP_PROMPTS = {
    1: "O cliente não respondeu ao primeiro contato feito há 3 dias. Gere uma mensagem curta e educada perguntando se ele conseguiu ver a mensagem anterior. Mantenha o tom profissional e amigável de Ivair.",
    2: "O cliente não respondeu há uma semana. Gere uma mensagem trazendo uma novidade ou um benefício específico da 100fronteiras (ex: audiência qualificada, networking). Algo para despertar interesse.",
    3: "Última tentativa. O cliente não responde há duas semanas. Gere uma mensagem de 'break-up' suave, dizendo que não vai mais incomodar, mas deixando as portas abertas para o futuro."
}


def get_due_followups():
    """
    Busca leads elegíveis para follow-up.
    VERSÃO CORRIGIDA: Verifica Chatwoot antes de incluir na lista.
    """
    conn = get_db_connection()
    leads = []
    
    # Stage 1 Candidates (contacted, nunca fez follow-up)
    rows = conn.execute("""
        SELECT * FROM leads 
        WHERE status = 'contacted' 
        AND (follow_up_stage = 0 OR follow_up_stage IS NULL)
    """).fetchall()
    
    for row in rows:
        try:
            last_contact = datetime.strptime(row['last_contact_date'], '%Y-%m-%d %H:%M:%S.%f')
        except:
            try:
                last_contact = datetime.strptime(row['last_contact_date'], '%Y-%m-%d %H:%M:%S')
            except:
                continue
                
        if (datetime.now() - last_contact).days >= FOLLOWUP_DELAYS[1]:
            leads.append(dict(row))
            
    # Stage 2 & 3 Candidates
    rows = conn.execute("""
        SELECT * FROM leads 
        WHERE status = 'follow_up' 
        AND next_contact_date <= ?
    """, (datetime.now(),)).fetchall()
    
    for row in rows:
        leads.append(dict(row))
        
    conn.close()
    return leads


def should_followup(lead):
    """
    Verifica no Chatwoot se devemos fazer follow-up para este lead.
    
    Returns:
        tuple: (should_send: bool, reason: str, history: str or None)
    """
    try:
        import chatwoot_api
        
        contact_check = chatwoot_api.should_contact_lead(lead['phone'])
        
        if not contact_check['should_contact']:
            reason = contact_check['reason']
            
            if reason == 'declined':
                return (False, f"Cliente recusou: {contact_check.get('decline_signal', '?')}", None)
            elif reason == 'waiting_response':
                return (False, f"Aguardando resposta (última msg nossa há {contact_check.get('days_since_contact', '?')} dias)", None)
            else:
                return (False, f"Não deve contatar: {reason}", None)
        
        # Verifica se cliente já respondeu (não precisa follow-up)
        if contact_check['reason'] == 'continue_conversation':
            return (False, "Cliente já respondeu - não precisa follow-up", contact_check.get('conversation_history'))
        
        # Pode fazer follow-up
        return (True, contact_check['reason'], contact_check.get('conversation_history'))
        
    except Exception as e:
        print(f"[Followup] Erro verificando Chatwoot: {e}")
        # Em caso de erro, NÃO fazer follow-up (fail-safe)
        return (False, f"Erro Chatwoot: {e}", None)


def process_followups(dry_run=True):
    """
    Processa follow-ups pendentes.
    VERSÃO CORRIGIDA: Verifica Chatwoot antes de cada envio.
    """
    leads = get_due_followups()
    print(f"\n[Follow-up] Found {len(leads)} leads due for follow-up.")
    
    if not leads:
        return
    
    processed = 0
    skipped = 0
    
    for lead in leads:
        current_stage = lead.get('follow_up_stage') or 0
        next_stage = current_stage + 1
        
        print(f"\n--- Lead: {lead['name']} ({lead['phone']}) ---")
        print(f"    Current stage: {current_stage} → Next: {next_stage}")
        
        # Verificação máxima de follow-ups
        if next_stage > 3:
            print(f"    ✓ Finished all follow-ups. Marking as closed.")
            update_lead_status(lead['phone'], 'closed_no_response')
            continue
        
        # =====================================================================
        # VERIFICAÇÃO OBRIGATÓRIA NO CHATWOOT
        # =====================================================================
        print(f"    📡 Verificando Chatwoot...")
        
        should_send, reason, history = should_followup(lead)
        
        if not should_send:
            print(f"    ⛔ SKIP: {reason}")
            
            # Se cliente recusou, marca como declined
            if 'recusou' in reason.lower() or 'declined' in reason.lower():
                update_lead_status(lead['phone'], 'declined')
            # Se cliente já respondeu, marca como responded
            elif 'respondeu' in reason.lower():
                update_lead_status(lead['phone'], 'responded')
            
            skipped += 1
            continue
        
        print(f"    ✅ Pode enviar follow-up. Razão: {reason}")
        
        # =====================================================================
        # GERAR MENSAGEM DE FOLLOW-UP
        # =====================================================================
        from agent import generate_followup_message
        
        # Adiciona histórico ao lead para contexto
        lead['conversation_history'] = history or lead.get('conversation_history', '')
        
        message = generate_followup_message(lead, next_stage)
        
        if not message:
            print("    ❌ Failed to generate message.")
            continue
            
        print(f"    📝 Message preview: {message[:100]}...")
        
        # =====================================================================
        # ENVIAR (se não for dry run)
        # =====================================================================
        if dry_run:
            print("    [DRY RUN] Message not sent.")
            continue
        
        # Verifica WhatsApp
        jid = check_whatsapp_exists(lead['phone'])
        if not jid:
            print("    ❌ WhatsApp invalid.")
            update_lead_status(lead['phone'], 'invalid_number')
            continue
        
        # Envia
        send_message(jid, message)
        
        # Atualiza DB
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
                conversation_history = COALESCE(conversation_history, '') || ? || '\n'
            WHERE id = ?
        ''', (next_stage, datetime.now(), next_date, f"\n🔄 Follow-up {next_stage}:\n{message}", lead['id']))
        conn.commit()
        conn.close()
        
        print(f"    ✅ Follow-up {next_stage} sent!")
        processed += 1
        
        # Sync com Trello
        try:
            import trello_crm
            if trello_crm.is_configured():
                card = trello_crm.find_card_by_phone(lead['phone'])
                if card:
                    trello_crm.add_comment(card['id'], f"🔄 Follow-up {next_stage}:\n\n{message}")
                    print(f"    📋 Trello synced")
        except Exception as t_err:
            print(f"    ⚠️ Trello error: {t_err}")
        
        # Delay entre leads para não parecer spam
        import time
        time.sleep(5)
    
    print(f"\n[Follow-up] Summary: {processed} sent, {skipped} skipped")


if __name__ == "__main__":
    import sys
    
    # Parse args
    dry_run = '--send' not in sys.argv
    
    if dry_run:
        print("=== FOLLOW-UP DRY RUN ===")
        print("Use --send to actually send messages")
    else:
        print("=== FOLLOW-UP LIVE MODE ===")
    
    process_followups(dry_run=dry_run)
