from flask import Flask, request, jsonify, render_template, redirect, url_for
from database import update_lead_status, get_lead_by_phone, add_lead, get_dashboard_stats, get_hot_leads, get_recent_activity, get_all_leads, get_analytics_data
import os
import threading
from datetime import datetime
from search import search_leads
from whatsapp import check_whatsapp_exists, format_number, send_message
from agent import generate_message

SEARCH_LOGS = []

def run_search_background(query, num_pages):
    global SEARCH_LOGS
    SEARCH_LOGS.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': f"Iniciando busca por: {query} ({num_pages} pgs)..."})
    
    try:
        leads = search_leads(query, int(num_pages))
        SEARCH_LOGS.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': f"Encontrados {len(leads)} resultados brutos. Validando WhatsApp..."})
        
        new_count = 0
        for i, lead in enumerate(leads):
            # Clean and Check
            raw_phone = lead['phone']
            if not raw_phone: continue
            
            clean_phone = format_number(raw_phone)
            lead['phone'] = clean_phone
            
            # Check DB existance
            existing = get_lead_by_phone(clean_phone)
            if existing:
                continue
                
            # Check WhatsApp
            jid = check_whatsapp_exists(clean_phone)
            if jid:
                # CRITICAL: Use the JID phone number as canonical to avoid duplicates
                # JID format: 554599998888@s.whatsapp.net
                canonical_phone = jid.split('@')[0]
                
                # Check DB existence AGAIN with canonical phone
                if get_lead_by_phone(canonical_phone):
                    print(f"Duplicate found (canonical): {canonical_phone}")
                    continue

                lead['phone'] = canonical_phone
                lead['status'] = 'new'
                lead['types'] = 'google_search' # Tag source
                if add_lead(lead):
                    new_count += 1
                    SEARCH_LOGS.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': f"LEAD NOVO: {lead['name']} ({canonical_phone})"})
            else:
                 # Optional: add as invalid? For now just skip logging to keep noise down
                 pass
                 
        SEARCH_LOGS.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': f"Busca finalizada! {new_count} novos leads adicionados."})
        
    except Exception as e:
        print(f"Search Error: {e}")
        SEARCH_LOGS.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': f"ERRO FATAL: {str(e)}"})

app = Flask(__name__, template_folder='templates')

# --- UI ROUTES ---

@app.route('/')
def dashboard():
    stats = get_dashboard_stats()
    hot_leads = get_hot_leads()
    
    # Process Hot Leads for Template
    processed_leads = []
    for lead in hot_leads:
        # Extract last message
        history = lead['conversation_history'] or ""
        last_msg = history.split('\n')[-1] if history else "Sem histórico"
        if len(last_msg) > 100: last_msg = last_msg[:100] + "..."
        
        # Format time (naive)
        ts = lead['last_contact_date']

        processed_leads.append({
            'name': lead['name'],
            'last_message': last_msg,
            'last_contact_date': time_str,
            'initial': lead['name'][:2].upper()
        })

    # Timeline (Mock/Mapped from recent activity)
    raw_activity = get_recent_activity()
    timeline = []
    for act in raw_activity:
        status = act['status']
        color = "bg-slate-400"
        text_color = "text-slate-500"
        type_label = "Update"
        desc = f"Lead {act['name']} atualizado para {status}"
        
        if status == 'contacted':
            color = "bg-purple-500"
            text_color = "text-purple-500"
            type_label = "Novo Envio"
            desc = f"Robô enviou mensagem para {act['name']}"
        elif status == 'responded':
            color = "bg-green-500"
            text_color = "text-green-500"
            type_label = "Resposta"
            desc = f"Nova resposta de {act['name']}"
        elif status == 'new':
            color = "bg-blue-500"
            text_color = "text-blue-500"
            type_label = "Encontrado"
            desc = f"Novo lead capturado: {act['name']}"
            
        timeline.append({
            'type': type_label,
            'time': str(act['last_contact_date'])[11:16], # Hacky substring for HH:MM
            'description': desc,
            'color': color,
            'text_color': text_color
        })

    return render_template('dashboard.html', 
                           kpi_new_leads=stats['new_leads'],
                           kpi_sent=stats['sent'],
                           kpi_responses=stats['responses'],
                           hot_leads=processed_leads,
                           timeline_events=timeline)

@app.route('/api/feed')
def get_feed_html():
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 10))
    
    activities = get_recent_activity(limit=limit, offset=offset)
    
    # Pre-fetch Trello cards to speed up or just do it in loop (slow but simpler for now)
    import trello_crm
    
    html_output = ""
    for lead in activities:
        # Prepare data
        status = lead['status']
        icon = "⚪"
        desc = "Interação detectada"
        
        if status == 'new': icon, desc = ("✨", "Novo Lead detectado")
        elif status == 'contacted': icon, desc = ("🤖", "Robô enviou mensagem")
        elif status == 'responded': icon, desc = ("📩", "Cliente respondeu")
        elif 'follow_up' in status: icon, desc = ("⏰", f"Follow-up ({status})")
        elif status == 'closed_deal': icon, desc = ("💰", "Venda Fechada!")
        elif status == 'invalid_number': icon, desc = ("🚫", "Número Inválido")
        
        phone_display = lead['phone'] or "N/A"
        time_display = str(lead['last_contact_date'])[11:16] if lead['last_contact_date'] else "--:--"
        
        # Links - Direct Trello Card Link
        trello_link = "#"
        trello_style = "opacity-50 cursor-not-allowed" # Disabled style by default
        
        try:
            if lead['phone'] and trello_crm.is_configured():
                card = trello_crm.find_card_by_phone(lead['phone'])
                if card:
                    trello_link = card.get('shortUrl', card.get('url'))
                    trello_style = "hover:underline hover:bg-[#0079bf]/20 transition-colors"
                else:
                    # Fallback to search if not found, but user wanted direct link. 
                    # If not found, maybe show "Create"? Or just search.
                    # Let's keep search as fallback but clearly marked? 
                    # User said "puxar link", so if it exists use it.
                    trello_link = f"https://trello.com/search?q={lead['phone']}"
                    trello_style = "hover:underline hover:bg-[#0079bf]/20 transition-colors"
        except:
             pass

        chatwoot_link = os.getenv("CHATWOOT_URL", "#")
        
        prompt_badge = ""
        if lead.get('prompt_version'):
            prompt_badge = f'<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-[#283539] text-gray-400 border border-gray-700">📝 Prompt {lead["prompt_version"]}</span>'

        # Message Preview
        msg_preview = ""
        if lead['conversation_history']:
             # Basic escaping for HTML safety would be good here, but for now assuming internal safe data
            esc_history = lead['conversation_history'].replace("<", "&lt;").replace(">", "&gt;")
            msg_preview = f"""
            <details class="group mt-2">
                <summary class="list-none cursor-pointer text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 select-none">
                    <span class="material-symbols-outlined text-[14px] transition-transform group-open:rotate-180">expand_more</span>
                    Ver mensagem enviada
                </summary>
                <div class="mt-2 text-xs text-gray-400 bg-[#111618] p-3 rounded border border-[#283539] whitespace-pre-wrap">{esc_history}</div>
            </details>
            """

        html_output += f"""
        <div class="relative pl-8 pb-8 border-l border-[#283539] last:border-0 last:pb-0">
            <div class="absolute -left-[13px] top-0 w-6 h-6 rounded-full bg-[#161b1d] border border-[#283539] flex items-center justify-center text-sm shadow-sm">
                {icon}
            </div>
            <div class="flex flex-col gap-1">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-mono text-text-secondary">{time_display}</span>
                    <span class="text-sm font-bold text-white">{lead['name']}</span>
                </div>
                <div class="text-sm text-gray-300">
                    {desc} <span class="text-gray-500 text-xs">📞 {phone_display}</span>
                </div>
                
                <div class="flex flex-wrap items-center gap-3 mt-1">
                     <a href="{trello_link}" target="_blank" class="flex items-center gap-1 text-[11px] text-[#0079bf] bg-[#0079bf]/10 px-2 py-0.5 rounded {trello_style}">
                        📋 Trello
                    </a>
                    <a href="{chatwoot_link}" target="_blank" class="flex items-center gap-1 text-[11px] text-[#9966CC] hover:underline bg-[#9966CC]/10 px-2 py-0.5 rounded hover:bg-[#9966CC]/20 transition-colors">
                        🟣 Chatwoot
                    </a>
                    {prompt_badge}
                </div>
                {msg_preview}
            </div>
        </div>
        """
        
    return html_output

@app.route('/leads', methods=['GET'])
def leads_page():
    # Stats for sidebar or top
    stats = get_dashboard_stats()
    return render_template('leads.html', 
                           leads_today_count=stats['new_leads'],
                           total_leads_count=stats['new_leads'] + stats['sent'] + stats['responses'] + 900, # Mock total or add distinct count
                           recent_results=SEARCH_LOGS) 

@app.route('/leads/search', methods=['POST'])
def search_handler():
    term = request.form.get('term')
    pages = request.form.get('pages', 1)
    
    print(f"Starting search for {term} ({pages} pages)")
    
    # Start Background Thread
    threading.Thread(target=run_search_background, args=(term, pages)).start()
    
    return redirect('/leads')

import csv
import io
from flask import Response, make_response

# ... existing imports ...

@app.route('/manage/export')
def export_leads():
    leads = get_all_leads()
    
    # Create CSV in memory
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Header
    if leads:
        header = leads[0].keys()
        cw.writerow(header)
        for lead in leads:
             cw.writerow(lead.values())
             
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=leads_100fronteiras.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/manage')
def manage_page():
    leads = get_all_leads()
    
    # Handle selection
    selected_phone = request.args.get('selected_phone')
    selected_lead = None
    if selected_phone:
        selected_lead = get_lead_by_phone(selected_phone)
        
    return render_template('management.html', leads=leads, selected_lead=selected_lead)

@app.route('/manage/actions/generate', methods=['POST'])
def generate_msg_action():
    phone = request.form.get('phone')
    version = request.form.get('version', 'A')
    
    lead = get_lead_by_phone(phone)
    if not lead: return jsonify({'error': 'Lead not found'}), 404
    
    # Generate
    # We might need to scrape if not cached, but for speed let's just generate
    msg = generate_message(lead, version=version)
    
    # Check if this was an AJAX request or Form submit
    # For MVP, let's assume simple Form submit? 
    # Actually, for "Generate" usually we want to see it before sending. 
    # So we should probably redirect back to Manage with the generated text pre-filled?
    # Or return JSON if we use JS.
    
    return jsonify({'message': msg})

@app.route('/manage/actions/send', methods=['POST'])
def send_msg_action():
    phone = request.form.get('phone')
    message = request.form.get('message')
    
    jid = check_whatsapp_exists(phone)
    if jid:
        # Check for splits
        parts = message.split('|||')
        full_log = ""
        
        for part in parts:
            if not part.strip(): continue
            send_message(jid, part.strip())
            full_log += f"{part.strip()}\n"
            # Import time to sleep if needed, but for now loop is enough (API usually queues)
            import time
            time.sleep(1.5) # Small human delay
            
        update_lead_status(phone, 'contacted', f"🤖 Ivair (Manual via Dashboard):\n\n{full_log.strip()}")
        print(f"Manual message sent to {phone}")
    else:
        print(f"Invalid Number: {phone}")
        
    return redirect(url_for('manage_page', selected_phone=phone))

@app.route('/manage/actions/status', methods=['POST'])
def set_status_action():
    phone = request.form.get('phone')
    status = request.form.get('status')
    
    update_lead_status(phone, status, "Status alterado manualmente pelo Dashboard")
    return redirect(url_for('manage_page', selected_phone=phone))

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/settings/revalidate', methods=['POST'])
def revalidate_action():
    # In a real app we'd thread this. For now just mock/quick return
    print("Starting Re-validation of 'new' leads...")
    
    def run_revalidation():
        leads = get_all_leads()
        count = 0
        for lead in leads:
            if lead['status'] == 'new':
                jid = check_whatsapp_exists(lead['phone'])
                if not jid:
                     update_lead_status(lead['phone'], 'invalid_number', "Invalidado na Re-validação")
                     count += 1
        print(f"Re-validation complete. Invalidated {count} leads.")

    threading.Thread(target=run_revalidation).start()
    
    return redirect('/settings')


# --- WEBHOOKS (EXISTING) ---
@app.route('/analytics')
def analytics_page():
    data = get_analytics_data()
    return render_template('analytics.html', analytics_data=data)

@app.route('/chat')
def chat_page():
    phone_filter = request.args.get('phone')
    all_leads = get_all_leads() # Potentially heavy, optimise later
    
    # Filter for active chats (those with history)
    active_chats = []
    selected_chat = None
    
    for l in all_leads:
        history = l['conversation_history']
        if history:
            chat_obj = {
                'name': l['name'],
                'phone': l['phone'],
                'last_contact': str(l['last_contact_date'])[5:16],
                'messages': []
            }
            
            # Parse messages (simple split by newline for MVP, improved parsing needed)
            # Format in DB is usually: "Sender: Message"
            raw_msgs = history.split('\n')
            for m in raw_msgs:
                if not m.strip(): continue
                is_agent = "Ivair" in m or "Chatwoot Agent" in m
                sender = "Agente" if is_agent else l['name']
                content = m.split(':', 1)[1] if ':' in m else m
                
                chat_obj['messages'].append({
                    'is_agent': is_agent,
                    'sender': sender,
                    'content': content
                })
            
            active_chats.append(chat_obj)
            
            if phone_filter and l['phone'] == phone_filter:
                selected_chat = chat_obj

    # Default to first if none selected
    if not selected_chat and active_chats:
        selected_chat = active_chats[0]

    return render_template('chat.html', active_chats=active_chats, selected_chat=selected_chat)

@app.route('/chat/send', methods=['POST'])
def chat_send():
    phone = request.form.get('phone')
    message = request.form.get('message')
    
    # Logic to send via Evolution API
    # from whatsapp import send_message
    # send_message(phone, message)
    
    # Update DB
    update_lead_status(phone, 'contacted', f"🤖 Ivair (Manual): {message}")
    
    return redirect(f'/chat?phone={phone}')


# --- WEBHOOKS (EXISTING) ---

@app.route('/webhook/evolution', methods=['POST'])
def evolution_webhook():
    data = request.json
    
    # Evolution API sends various events. We care about 'messages.upsert'
    event_type = data.get('type')
    
    if event_type == 'message': # Check exact event name in Evolution docs/logs
        message_data = data.get('data', {})
        key = message_data.get('key', {})
        from_me = key.get('fromMe', False)
        
        # Handle ALL messages (from_me or not)
        remote_jid = key.get('remoteJid') 
        
        if remote_jid and '@s.whatsapp.net' in remote_jid: # Only individual chats
            phone = remote_jid.split('@')[0]
            
            # Get message content
            message_content = ""
            message_obj = message_data.get('message', {})
            if 'conversation' in message_obj:
                message_content = message_obj['conversation']
            elif 'extendedTextMessage' in message_obj:
                message_content = message_obj['extendedTextMessage'].get('text', '')
            
            if not message_content:
                return jsonify({"status": "ignored", "reason": "no text"}), 200

            # 1. Check / Create Lead in DB
            lead = get_lead_by_phone(phone)
            if not lead:
                push_name = message_data.get('pushName', 'Desconhecido')
                print(f"Creating new lead from WhatsApp: {push_name} ({phone})")
                new_lead_data = {
                    'name': push_name,
                    'phone': phone,
                    'address': '',
                    'website': '',
                    'rating': 0,
                    'reviews': 0,
                    'types': 'whatsapp_contact',
                    'search_term': 'WhatsApp Orgânico',
                    'language': 'pt' # Default
                }
                add_lead(new_lead_data)
                lead = get_lead_by_phone(phone) # Refresh logic

            # 2. Determine Sender & Status Update
            if from_me:
                sender_prefix = "🤖 Ivair (WhatsApp):"
                # Keep status unless it was new
                new_status = lead['status'] if lead else 'contacted'
                if new_status == 'new': new_status = 'contacted'
            else:
                sender_prefix = "📩 Cliente:"
                new_status = 'responded'

            # 3. Update DB History
            # This ensures Dashboard Chat works for EVERYONE
            if lead:
                update_lead_status(phone, new_status, f"{sender_prefix}\n\n{message_content}")



            # Trello Sync Logic
            try:
                import trello_crm
                if trello_crm.is_configured():
                    # Check if lead exists in DB to get Name
                    lead = get_lead_by_phone(phone)
                    
                    
                    # 1. Try to find card by PHONE (Robust duplicate check)
                    card = trello_crm.find_card_by_phone(phone)
                    
                    if not card:
                         # Fallback search by Name (if available) just in case
                         if lead:
                             card_name = f"{lead['name']} - {phone}"
                             card = trello_crm.find_card_by_name(card_name)
                         else:
                             push_name = message_data.get('pushName', 'Desconhecido')
                             card_name = f"{push_name} - {phone}"
                             # Try generic search for this name+phone combo
                             if not card:
                                  card = trello_crm.find_card_by_name(card_name)
                    
                    # 2. If not found, create it (Only if it's a client msg or we want to capture everything)
                    # User said: "mesmo se nao estao na planilha... criar um"
                    if not card:
                        # Create dummy lead data for creation
                        dummy_lead = {
                            'name': lead['name'] if lead else message_data.get('pushName', 'Desconhecido'),
                            'phone': phone,
                            'website': '',
                            'rating': '',
                            'reviews': '',
                            'search_term': 'WhatsApp Web/Orgânico',
                            'address': ''
                        }
                        # Create in 'Conexão' if they responded, or 'Contato Frio' if we started? 
                        # If from_me -> We started -> 'Contato Frio'
                        # If not from_me -> They started/responded -> 'Conexão'
                        target_list = "Contato Frio" if from_me else "Conexão"
                        
                        print(f"Creating new Trello card for {card_name} in {target_list}...")
                        card_id = trello_crm.create_card(dummy_lead, list_name=target_list)
                        if card_id:
                            card = {'id': card_id}
                    
                    # 3. Log Message
                    if card:
                        trello_crm.add_comment(card['id'], f"{sender_prefix}\n\n{message_content}")
                        
                        # Move card if needed (e.g. if we get a response, move to Conexão)
                        if not from_me:
                            trello_crm.move_card(card['id'], "Conexão")

            except Exception as t_err:
                print(f"Trello Sync Error (Webhook): {t_err}")

            return jsonify({"status": "success", "message": "Processed"}), 200

    return jsonify({"status": "ignored"}), 200

# --- CHATWOOT WEBHOOK ---
@app.route('/webhook/chatwoot', methods=['POST'])
def chatwoot_webhook():
    """
    Receives events from Chatwoot (message_created, conversation_created, etc.)
    and syncs them to our Database and Trello.
    """
    data = request.json
    event = data.get('event')
    
    print(f"[Chatwoot Webhook] Event: {event}")
    
    if event == 'message_created':
        message_data = data.get('message', {})
        conversation = data.get('conversation', {})
        sender = data.get('sender', {})
        
        # Get phone number from conversation meta
        phone = None
        meta = conversation.get('meta', {})
        contact_inbox = conversation.get('contact_inbox', {})
        
        # Try to get phone from sender or meta
        if sender.get('phone_number'):
            phone = sender['phone_number'].replace('+', '').replace(' ', '').replace('-', '')
        elif meta.get('sender', {}).get('phone_number'):
            phone = meta['sender']['phone_number'].replace('+', '').replace(' ', '').replace('-', '')
        
        if not phone:
            print("[Chatwoot] Could not extract phone number.")
            return jsonify({"status": "ignored", "reason": "no phone"}), 200
        
        # Message Content
        message_content = message_data.get('content', '')
        message_type = message_data.get('message_type') # 0=incoming, 1=outgoing
        sender_name = sender.get('name', 'Chatwoot User')
        
        if not message_content:
            return jsonify({"status": "ignored", "reason": "no content"}), 200
        
        # Determine sender
        if message_type == 1: # Outgoing (Agent)
            sender_prefix = "🗣️ Chatwoot Agent:"
            new_status = 'contacted'
        else: # Incoming (Client)
            sender_prefix = f"📩 Cliente ({sender_name}):"
            new_status = 'responded'
        
        # 1. Check / Create Lead in DB
        lead = get_lead_by_phone(phone)
        if not lead:
            print(f"[Chatwoot] Creating new lead: {sender_name} ({phone})")
            new_lead_data = {
                'name': sender_name,
                'phone': phone,
                'address': '',
                'website': '',
                'rating': 0,
                'reviews': 0,
                'types': 'chatwoot_contact',
                'search_term': 'Chatwoot/Orgânico',
                'language': 'pt'
            }
            add_lead(new_lead_data)
            lead = get_lead_by_phone(phone)
        
        # 2. Update DB History
        if lead:
            update_lead_status(phone, new_status, f"{sender_prefix}\n\n{message_content}")
        
        # 3. Trello Sync
        try:
            import trello_crm
            if trello_crm.is_configured():
                card = trello_crm.find_card_by_phone(phone)
                
                if not card:
                    # Create card
                    dummy_lead = {
                        'name': lead['name'] if lead else sender_name,
                        'phone': phone,
                        'website': '',
                        'rating': '',
                        'reviews': '',
                        'search_term': 'Chatwoot/Orgânico',
                        'address': ''
                    }
                    target_list = "Contato Frio" if message_type == 1 else "Conexão"
                    card_id = trello_crm.create_card(dummy_lead, list_name=target_list)
                    if card_id:
                        card = {'id': card_id}
                
                if card:
                    trello_crm.add_comment(card['id'], f"{sender_prefix}\n\n{message_content}")
                    if message_type != 1: # Client replied
                        trello_crm.move_card(card['id'], "Conexão")
        except Exception as t_err:
            print(f"[Chatwoot] Trello Sync Error: {t_err}")
        
        return jsonify({"status": "success", "event": event}), 200
    
    elif event == 'conversation_created':
        # Log new conversation start
        print(f"[Chatwoot] New conversation started: {data.get('id')}")
        return jsonify({"status": "logged"}), 200
    
    return jsonify({"status": "ignored", "event": event}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
