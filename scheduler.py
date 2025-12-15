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
    current_date = now.date()
    vacation_start = datetime.date(2025, 12, 23)
    vacation_end = datetime.date(2026, 1, 5)
    
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
            leads = search_leads(query, num_pages=1)
            
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
                        # Check Chatwoot before adding as 'new'
                        import chatwoot_api
                        cw_contact = chatwoot_api.get_contact_by_phone(lead['phone'])
                        
                        if cw_contact:
                            print(f"[Auto-Refill] Found in Chatwoot: {lead['phone']} ({cw_contact.get('name')}). Importing as 'contacted'.")
                            lead['status'] = 'contacted'
                        else:
                            lead['status'] = 'new'
                        
                        if add_lead(lead):
                            added_count += 1
                    else:
                        print(f"      Skipping invalid number: {lead['phone']}")
                        
            print(f"[Auto-Refill] Added {added_count} leads.")
            
        except Exception as e:
            print(f"[Auto-Refill] Error searching: {e}")


def process_one_lead():
    """
    Processa um lead da fila.
    
    VERSÃO CORRIGIDA com:
    - Lock atômico (previne race condition)
    - Verificação OBRIGATÓRIA no Chatwoot
    - Fail-safe: não envia se Chatwoot falhar
    - Análise de quem mandou última mensagem
    - Detecção de sinais de recusa
    """
    if not is_within_business_hours():
        print("[Job] Outside business hours. Skipping.")
        return

    print("\n" + "=" * 60)
    print("[Job] Starting process for one lead...")
    print("=" * 60)
    
    # =========================================================================
    # PASSO 1: SELECIONAR LEAD COM LOCK ATÔMICO
    # =========================================================================
    conn = get_db_connection()
    
    # Seleciona um lead 'new' aleatório
    lead_row = conn.execute("""
        SELECT * FROM leads 
        WHERE status = 'new' 
        ORDER BY RANDOM() 
        LIMIT 1
    """).fetchone()
    
    if not lead_row:
        conn.close()
        print("[Job] No new leads available.")
        auto_refill_leads()
        return
    
    lead = dict(lead_row)
    lead_id = lead['id']
    
    # Lock atômico - marca como 'processing' imediatamente
    cursor = conn.execute("""
        UPDATE leads 
        SET status = 'processing'
        WHERE id = ? AND status = 'new'
    """, (lead_id,))
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        print(f"[Job] Lead {lead_id} já foi pego por outro processo. Tentando próximo...")
        return process_one_lead()
    
    conn.close()
    print(f"[Job] 🔒 Lead locked: {lead['name']} ({lead['phone']})")
    
    # =========================================================================
    # PASSO 2: VERIFICAÇÃO DE DUPLICATA NO BANCO LOCAL
    # =========================================================================
    conn = get_db_connection()
    recent_contact = conn.execute("""
        SELECT id, name, last_contact_date, status
        FROM leads 
        WHERE phone = ? 
        AND status IN ('contacted', 'responded', 'follow_up_1', 'follow_up_2', 'follow_up_3', 'declined')
        AND last_contact_date > datetime('now', '-7 days')
        AND id != ?
    """, (lead['phone'], lead['id'])).fetchone()
    conn.close()
    
    if recent_contact:
        recent = dict(recent_contact)
        print(f"      ⚠️ DUPLICATA NO BANCO!")
        print(f"         Phone {lead['phone']} já foi contatado:")
        print(f"         Lead ID {recent['id']} ({recent['name']})")
        print(f"         Status: {recent['status']}")
        print(f"         Data: {recent['last_contact_date']}")
        
        conn = get_db_connection()
        conn.execute("UPDATE leads SET status = 'duplicate' WHERE id = ?", (lead['id'],))
        conn.commit()
        conn.close()
        return
    
    # =========================================================================
    # PASSO 3: VERIFICAÇÃO OBRIGATÓRIA NO CHATWOOT
    # =========================================================================
    print("      📡 Verificando Chatwoot (OBRIGATÓRIO)...")
    
    chatwoot_history = None
    contact_reason = None
    
    try:
        import chatwoot_api
        
        # Usa função que analisa se deve contatar
        contact_check = chatwoot_api.should_contact_lead(lead['phone'])
        
        reason = contact_check['reason']
        print(f"      Resultado Chatwoot: {reason}")
        
        # === SE NÃO DEVE CONTATAR ===
        if not contact_check['should_contact']:
            
            if reason == 'waiting_response':
                days = contact_check.get('days_since_contact', '?')
                print(f"      ⏳ AGUARDANDO RESPOSTA")
                print(f"         Última mensagem NOSSA há {days} dias")
                print(f"         Não vamos mandar outra mensagem ainda.")
                update_lead_status(lead['phone'], 'contacted')
                return
                
            elif reason == 'declined':
                signal = contact_check.get('decline_signal', 'não especificado')
                print(f"      🚫 CLIENTE RECUSOU!")
                print(f"         Sinal detectado: '{signal}'")
                update_lead_status(lead['phone'], 'declined')
                
                # Atualiza Trello
                try:
                    import trello_crm
                    if trello_crm.is_configured():
                        card = trello_crm.find_card_by_phone(lead['phone'])
                        if card:
                            trello_crm.add_comment(card['id'], f"🚫 Lead RECUSOU\nSinal: {signal}")
                            trello_crm.move_card(card['id'], "Arquivados")
                except:
                    pass
                return
            
            else:
                print(f"      ❌ Não deve contatar. Razão: {reason}")
                update_lead_status(lead['phone'], 'skipped')
                return
        
        # === PODE CONTATAR ===
        chatwoot_history = contact_check.get('conversation_history')
        contact_reason = reason
        last_from = contact_check.get('last_message_from')
        days_since = contact_check.get('days_since_contact')
        
        print(f"      ✅ Pode contatar!")
        print(f"         Razão: {contact_reason}")
        if last_from:
            who = 'CLIENTE' if last_from == 'them' else 'NÓS'
            print(f"         Última msg de: {who}")
        if days_since is not None:
            print(f"         Há {days_since} dias")
        if chatwoot_history:
            print(f"         Histórico: {len(chatwoot_history)} chars")
    
    except Exception as ch_err:
        # =====================================================================
        # CRÍTICO: Se Chatwoot falhar, NÃO enviar!
        # =====================================================================
        print(f"      ❌ ERRO CRÍTICO no Chatwoot: {ch_err}")
        print(f"      🛑 ABORTANDO para prevenir duplicata")
        print(f"      Lead volta para 'new' para tentar depois")
        
        update_lead_status(lead['phone'], 'new')
        return
    
    # =========================================================================
    # PASSO 4: PREPARAR MENSAGEM
    # =========================================================================
    try:
        # Scrape website se disponível
        website_content = None
        if lead.get('website'):
            print(f"      🌐 Scraping {lead['website']}...")
            try:
                website_content = scrape_website(lead['website'])
            except Exception as scrape_err:
                print(f"      ⚠️ Scrape falhou: {scrape_err}")
        
        # Decide tipo de mensagem
        message_parts = None
        chosen_version = None
        
        if chatwoot_history:
            # Tem histórico - gera mensagem contextual
            print("      🧠 Gerando mensagem CONTEXTUAL...")
            from agent import generate_contextual_message
            message_parts = generate_contextual_message(lead, chatwoot_history)
            chosen_version = "CONTEXTUAL"
            
        else:
            # Sem histórico - usa templates A/B/C
            chosen_version = random.choice(['A', 'B', 'C'])
            language = lead.get('language', 'pt')
            
            if language == 'es':
                final_version = f"{chosen_version}_ES"
            else:
                final_version = chosen_version
            
            from agent import PROMPT_TEMPLATES
            message_parts = PROMPT_TEMPLATES.get(
                final_version, 
                PROMPT_TEMPLATES.get(chosen_version, PROMPT_TEMPLATES['A'])
            )
            
            print(f"      📝 Usando template {final_version}")
        
        if not message_parts:
            print("      ❌ Falha ao gerar mensagem. Abortando.")
            update_lead_status(lead['phone'], 'error_generating')
            return
        
        # =====================================================================
        # PASSO 5: ENVIAR MENSAGEM
        # =====================================================================
        print(f"      📤 Enviando {len(message_parts)} partes via WhatsApp...")
        
        jid = check_whatsapp_exists(lead['phone'])
        
        if not jid:
            print("      ❌ Número WhatsApp inválido. Removendo lead.")
            conn = get_db_connection()
            conn.execute("DELETE FROM leads WHERE phone = ?", (lead['phone'],))
            conn.commit()
            conn.close()
            return
        
        # Envia cada parte com delay
        full_message_log = []
        
        for i, part in enumerate(message_parts):
            if not part or not part.strip():
                continue
                
            preview = part[:50] + "..." if len(part) > 50 else part
            print(f"         Parte {i+1}/{len(message_parts)}: {preview}")
            send_message(jid, part)
            full_message_log.append(part)
            
            # Delay entre partes (exceto última)
            if i < len(message_parts) - 1:
                delay = random.randint(5, 10)
                print(f"         ⏱️ Aguardando {delay}s...")
                time.sleep(delay)
        
        # =====================================================================
        # PASSO 6: ATUALIZAR STATUS
        # =====================================================================
        full_message = "\n\n".join(full_message_log)
        
        update_lead_status(
            lead['phone'], 
            'contacted', 
            f"🤖 Ivair (v{chosen_version}):\n\n{full_message}"
        )
        update_lead_prompt_version(lead['phone'], chosen_version)
        
        # Sync com Trello
        try:
            import trello_crm
            if trello_crm.is_configured():
                card_id = trello_crm.create_card(lead, list_name="Contato Frio")
                if card_id:
                    trello_crm.add_comment(
                        card_id, 
                        f"🤖 Agente enviou (v{chosen_version}):\n\n{full_message}"
                    )
                    print(f"      📋 Trello sincronizado")
        except Exception as t_err:
            print(f"      ⚠️ Erro Trello: {t_err}")
        
        print(f"      ✅ SUCESSO! Lead {lead['name']} contatado.")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"[Job] ❌ Erro processando lead {lead['name']}: {e}")
        import traceback
        traceback.print_exc()
        update_lead_status(lead['phone'], 'error_sending')


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    
    print("=== Auto-Scheduler Started ===")
    print("Schedule: Mon-Fri | 09:00-11:40 & 14:00-17:20 | Every 30 mins")
    print("Version: 2.0 (Anti-Duplicata)")
    
    try:
        # Ensure Database is Initialized
        from database import init_db
        print("[Startup] Initializing database...")
        init_db()
        
        # Initialize Trello Lists
        try:
            import trello_crm
            if trello_crm.is_configured():
                trello_crm.create_list("Contato Frio")
                trello_crm.create_list("Conexão")
                trello_crm.create_list("A Prospectar")
                trello_crm.create_list("Arquivados")  # Para leads que recusaram
        except Exception as e:
            print(f"Warning: Could not init Trello lists: {e}")

        # Run once at startup
        auto_refill_leads()
        
        print("[Job] Executing immediate start-up run...")
        process_one_lead()
        
        # Schedule
        schedule.every(30).minutes.do(process_one_lead)
        schedule.every(1).hours.do(auto_refill_leads)
        schedule.every(4).hours.do(process_followups, dry_run=False)

        # Chatwoot <-> Trello Sync
        from sync_chatwoot_trello import run_sync
        schedule.every(15).minutes.do(run_sync)

        while True:
            schedule.run_pending()
            time.sleep(60)
            
    except Exception as e:
        print(f"CRITICAL SCHEDULER CRASH: {e}")
        import traceback
        traceback.print_exc()
        raise e
