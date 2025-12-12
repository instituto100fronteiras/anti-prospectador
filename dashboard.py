import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import subprocess
from database import get_db_connection, update_lead_status, init_db
from search import search_leads
from agent import generate_message, PROMPT_TEMPLATES
import trello_crm

# Initialize DB on startup
init_db()
from whatsapp import check_whatsapp_exists, send_message, format_number
from scraper import scrape_website

st.set_page_config(page_title="Agente Prospectador", layout="wide")

st.title("🕵️ Agente Prospectador 100fronteiras")

# Sidebar for Navigation
page = st.sidebar.selectbox("Navegação", ["Visão Geral", "Buscar Leads", "Chat em Tempo Real", "Gerenciar Leads", "Analytics", "Configurações"])

if page == "Buscar Leads":
    st.header("Nova Busca")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Termo de Busca", placeholder="Ex: construtoras em foz do iguaçu")
    with col2:
        num_pages = st.number_input("Páginas", min_value=1, max_value=5, value=1)
        
    if st.button("🔍 Iniciar Busca"):
        if not query:
            st.warning("Digite um termo de busca.")
        else:
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            status_text.text("Buscando no Google Maps...")
            
            # We can't easily stream the console output from search_leads here without refactoring
            # So we'll just run it and show results
            try:
                leads = search_leads(query, num_pages)
                progress_bar.progress(20)
                status_text.text(f"Encontrados {len(leads)} leads. Verificando WhatsApp...")
                
                new_leads_count = 0
                valid_leads_count = 0
                
                for i, lead in enumerate(leads):
                    # Progress update
                    progress = 20 + int((i / len(leads)) * 80)
                    progress_bar.progress(progress)
                    status_text.text(f"Processando {i+1}/{len(leads)}: {lead['name']}")
                    
                    # Clean Phone
                    lead['phone'] = format_number(lead['phone'])
                    
                    # Check if exists in DB
                    conn = get_db_connection()
                    exists = conn.execute("SELECT 1 FROM leads WHERE phone = ?", (lead['phone'],)).fetchone()
                    conn.close()
                    
                    if not exists:
                        # Check WhatsApp Validity BEFORE saving as 'new'
                        jid = check_whatsapp_exists(lead['phone'])
                        
                        if jid:
                            lead['status'] = 'new'
                            valid_leads_count += 1
                        else:
                            lead['status'] = 'invalid_number'
                            
                        # Add to DB
                        from database import add_lead
                        if add_lead(lead):
                            new_leads_count += 1
                            
                status_text.success(f"Busca concluída! {new_leads_count} processados. {valid_leads_count} são WhatsApp válidos e prontos para contato.")
                
            except Exception as e:
                st.error(f"Erro na busca: {e}")

elif page == "Analytics":
    st.header("📊 Desempenho dos Prompts (A/B/C)")
    
    conn = get_db_connection()
    
    # Overview Metrics
    total = conn.execute("SELECT COUNT(*) FROM leads WHERE prompt_version IS NOT NULL").fetchone()[0]
    st.metric("Total de Testes Iniciados", total)
    
    # Detailed Breakdown
    query = """
        SELECT 
            prompt_version,
            COUNT(*) as enviados,
            SUM(CASE WHEN status = 'responded' THEN 1 ELSE 0 END) as respostas,
            ROUND(CAST(SUM(CASE WHEN status = 'responded' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as conversao
        FROM leads 
        WHERE prompt_version IS NOT NULL
        GROUP BY prompt_version
    """
    df_analytics = pd.read_sql_query(query, conn)
    conn.close()
    
    if not df_analytics.empty:
        st.dataframe(df_analytics, use_container_width=True)
        
        # Simple Bar Chart
        st.caption("Taxa de Conversão por Prompt")
        st.bar_chart(df_analytics.set_index('prompt_version')['conversao'])
    else:
        st.info("Ainda não há dados suficientes para gerar métricas de prompts.")
        
    with st.expander("📝 Ver Modelos de Prompts (A/B/C)"):
        st.markdown("### Prompt A")
        st.code(PROMPT_TEMPLATES.get('A'))
        st.markdown("### Prompt B")
        st.code(PROMPT_TEMPLATES.get('B'))
        st.markdown("### Prompt C")
        st.code(PROMPT_TEMPLATES.get('C'))
        
    st.markdown("---")
    st.header("🏢 Desempenho por Setor (Termo Buscado)")
    
    query_sector = """
        SELECT 
            search_term as setor,
            COUNT(*) as enviados,
            SUM(CASE WHEN status = 'responded' THEN 1 ELSE 0 END) as respostas,
            ROUND(CAST(SUM(CASE WHEN status = 'responded' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as conversao
        FROM leads 
        WHERE search_term IS NOT NULL
        GROUP BY search_term
        ORDER BY conversao DESC
    """
    df_sector = pd.read_sql_query(query_sector, conn)

    if not df_sector.empty:
        st.dataframe(df_sector, use_container_width=True)
        st.caption("Taxa de Conversão por Setor")
        st.bar_chart(df_sector.set_index('setor')['conversao'])
    else:
        st.info("Ainda não há dados de setores (novos leads capturados pelo robô).")

elif page == "Visão Geral":
    st.title("📊 Visão Geral do Dia")
    
    conn = get_db_connection()
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # --- KPIs ---
    # 1. New Leads Today
    new_leads_count = conn.execute(f"SELECT COUNT(*) FROM leads WHERE DATE(created_at) = '{today_str}'").fetchone()[0]
    
    # 2. Responded Today (Approximate by status + last_contact)
    responded_count = conn.execute(f"SELECT COUNT(*) FROM leads WHERE status = 'responded' AND DATE(last_contact_date) = '{today_str}'").fetchone()[0]
    
    # 3. Active Contacts Today (Sent/Follow-up)
    contacted_count = conn.execute(f"SELECT COUNT(*) FROM leads WHERE status IN ('contacted', 'follow_up_1', 'follow_up_2', 'follow_up_3') AND DATE(last_contact_date) = '{today_str}'").fetchone()[0]
    
    kp1, kp2, kp3 = st.columns(3)
    kp1.metric("🆕 Novos Leads (Hoje)", new_leads_count, help="Leads que entraram na base hoje")
    kp2.metric("💬 Respostas (Hoje)", responded_count, help="Clientes que responderam hoje")
    kp3.metric("🤖 Envios do Robô (Hoje)", contacted_count, help="Mensagens iniciais ou follow-ups enviados hoje")
    
    st.markdown("---")
    
    # --- RECENT RETURNS (Highlights) ---
    recent_responses = conn.execute("""
        SELECT name, phone, last_contact_date, conversation_history 
        FROM leads 
        WHERE status = 'responded' 
        ORDER BY last_contact_date DESC 
        LIMIT 3
    """).fetchall()
    
    if recent_responses:
        st.subheader("🔥 Últimos Retornos (Quentes)")
        cols = st.columns(len(recent_responses))
        for idx, row in enumerate(recent_responses):
            lead = dict(row)
            # Find last client msg
            last_msg = "..."
            if lead['conversation_history']:
                lines = lead['conversation_history'].split('\n')
                # Try to find last line not starting with Agent prefix
                for line in reversed(lines):
                    if line.strip() and "Ivair" not in line and "Agente" not in line:
                        last_msg = line[:50] + "..." if len(line) > 50 else line
                        break
            
            with cols[idx]:
                st.info(f"**{lead['name']}**\n\n🕒 {lead['last_contact_date'][11:16]}\n\n💬 _{last_msg}_")

    st.markdown("---")

    # --- TIMELINE (Visual Feed) ---
    st.subheader("⏳ Linha do Tempo (Últimas 10 Ações)")
    
    timeline_leads = conn.execute("""
        SELECT id, name, phone, status, last_contact_date, prompt_version, conversation_history 
        FROM leads 
        WHERE last_contact_date IS NOT NULL 
        ORDER BY last_contact_date DESC 
        LIMIT 10
    """).fetchall()
    
    # Get Chatwoot base URL
    chatwoot_base = os.getenv("CHATWOOT_URL", "").replace("/conversations", "")
    
    for row in timeline_leads:
        lead = dict(row)
        time_only = lead['last_contact_date'][11:16] # HH:MM
        phone_display = lead['phone'] if lead['phone'] else "N/A"
        
        icon = "⚪"
        action_desc = "Interação detectada"
        
        if lead['status'] == 'new':
            icon = "✨"
            action_desc = "Novo Lead detectado"
        elif lead['status'] == 'contacted':
            icon = "🤖"
            action_desc = "Robô enviou mensagem"
        elif lead['status'] == 'responded':
            icon = "📩"
            action_desc = "Cliente respondeu"
        elif 'follow_up' in lead['status']:
            icon = "⏰"
            action_desc = f"Follow-up ({lead['status']})"
        elif lead['status'] == 'closed_deal':
            icon = "💰"
            action_desc = "Venda Fechada!"
        elif lead['status'] == 'invalid_number':
            icon = "🚫"
            action_desc = "Número Inválido"
        
        # Build links
        links_html = ""
        
        # Trello Link
        try:
            if trello_crm.is_configured():
                card = trello_crm.find_card_by_phone(lead['phone'])
                if card and card.get('shortUrl'):
                    links_html += f'<a href="{card["shortUrl"]}" target="_blank" style="margin-left: 10px; color: #0079bf;">📋 Trello</a>'
        except:
            pass
        
        # Chatwoot Link
        if chatwoot_base:
            chatwoot_search = f"{chatwoot_base}/contacts?q={phone_display.replace('+', '').replace(' ', '')}"
            links_html += f'<a href="{chatwoot_search}" target="_blank" style="margin-left: 10px; color: #9966CC;">🟣 Chatwoot</a>'
        
        # Prompt Version Badge (if contacted)
        if lead['status'] == 'contacted' and lead.get('prompt_version'):
            prompt_ver = lead['prompt_version']
            links_html += f'<span style="margin-left: 10px; background-color: #444; padding: 2px 8px; border-radius: 3px; font-size: 0.85em;">📝 Prompt {prompt_ver}</span>'

        st.markdown(f"""
        <div style="
            padding: 10px; 
            border-left: 3px solid #ccc; 
            margin-bottom: 10px; 
            background-color: #262730; 
            border-radius: 5px;">
            <span style="font-size: 1.2em; margin-right: 10px;">{icon}</span>
            <strong>{time_only}</strong> - 
            <span style="color: #4da6ff;">{lead['name']}</span>: 
            {action_desc}
            <span style="color: #888; font-size: 0.9em; margin-left: 10px;">📞 {phone_display}</span>
            {links_html}
        </div>
        """, unsafe_allow_html=True)
        
        # Show message preview if contacted
        if lead['status'] == 'contacted' and lead.get('conversation_history'):
            with st.expander(f"📄 Ver mensagem enviada (Prompt {lead.get('prompt_version', '?')})"):
                st.text(lead['conversation_history'][:500])

    conn.close()

elif page == "Gerenciar Leads":
    st.header("Base de Leads")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["Todos", "new", "contacted", "responded", "follow_up", "closed_no_response", "invalid_number"])
    
    conn = get_db_connection()
    query = "SELECT * FROM leads"
    params = []
    
    if status_filter != "Todos":
        query += " WHERE status = ?"
        params.append(status_filter)
        
    query += " ORDER BY created_at DESC"
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Export Button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar como CSV (para Google Sheets)",
        data=csv,
        file_name='leads_100fronteiras.csv',
        mime='text/csv',
    )
    
    st.dataframe(df, use_container_width=True)
    
    # Action Section
    st.subheader("Ações Manuais")
    
    selected_lead_id = st.number_input("ID do Lead para Ação", min_value=0, value=0)
    
    if selected_lead_id > 0:
        lead_row = df[df['id'] == selected_lead_id]
        if not lead_row.empty:
            lead = lead_row.iloc[0].to_dict()
            st.info(f"Selecionado: **{lead['name']}** ({lead['phone']})")
            
            # Show History
            if lead.get('conversation_history'):
                with st.expander("📜 Histórico de Conversa", expanded=True):
                    st.text(lead['conversation_history'])
            
            # Show assigned prompt version if exists
            current_version = lead.get('prompt_version')
            if current_version:
                 st.caption(f"Versão de Prompt Atribuída: **{current_version}**")
            
            # Trello Link
            if trello_crm.is_configured():
                with st.spinner("Buscando no Trello..."):
                    card = trello_crm.find_card_by_phone(lead['phone'])
                    if card:
                        st.markdown(f"🔗 **[Abrir Card no Trello]({card.get('shortUrl', card.get('url'))})**")
                    else:
                        st.caption("Nenhum card encontrado no Trello.")

            action = st.radio("Ação", ["Gerar Mensagem (IA)", "Enviar Mensagem Manual", "Marcar como Respondido"])
            
            if action == "Gerar Mensagem (IA)":
                # Option to choose version manually or random
                version_choice = st.selectbox("Versão do Prompt", ["Aleatório", "A", "B", "C"], index=0)
                
                if st.button("Gerar"):
                    with st.spinner("Gerando..."):
                        website_content = None
                        if lead['website']:
                            website_content = scrape_website(lead['website'])
                        
                        # Logic for choosing version
                        if version_choice == "Aleatório":
                            import random
                            chosen_version = random.choice(['A', 'B', 'C'])
                        else:
                            chosen_version = version_choice
                            
                        msg = generate_message(lead, website_content, version=chosen_version)
                        st.text_area("Mensagem Sugerida", value=msg, height=200)
                        
                        # Store selection in session state or just remind user (since we save on send)
                        st.session_state['last_generated_version'] = chosen_version
                        
            elif action == "Enviar Mensagem Manual":
                msg_to_send = st.text_area("Mensagem", height=150)
                if st.button("Enviar WhatsApp"):
                    jid = check_whatsapp_exists(lead['phone'])
                    if jid:
                        send_message(jid, msg_to_send)
                        # Detect if we just generated a prompt version
                        version_used = st.session_state.get('last_generated_version', None)
                        
                        update_lead_status(lead['phone'], 'contacted', msg_to_send)
                        
                        if version_used:
                             from database import update_lead_prompt_version
                             update_lead_prompt_version(lead['phone'], version_used)
                             
                        # Trello Sync
                        try:
                            import trello_crm
                            if trello_crm.is_configured():
                                # Try to find or create card
                                # If manual send, likely first contact or follow-up. 
                                # Use 'Contato Frio' as default if creating.
                                card_id = trello_crm.create_card(lead, list_name="Contato Frio")
                                if card_id:
                                    trello_crm.add_comment(card_id, f"📝 Envio Manual (Dashboard):\n\n{msg_to_send}")
                                    st.success(f"Enviado e sincronizado com Trello! (Card: {card_id})")
                                else:
                                    st.success("Enviado! (Erro ao criar card Trello)")
                        except Exception as t_err:
                            st.error(f"Erro Trello: {t_err}")
                            st.success("Enviado no WhatsApp, mas falha no Trello.")
                    else:
                        st.error("Número inválido no WhatsApp.")

            elif action == "Marcar como Respondido":
                if st.button("Confirmar"):
                    update_lead_status(lead['phone'], 'responded', "Marcado manualmente via Dashboard")
                    st.success("Atualizado!")
                    st.rerun()

elif page == "Chat em Tempo Real":
    st.header("💬 Central de Mensagens")
    
    # Auto-refresh button
    if st.button("🔄 Atualizar Conversas"):
        st.rerun()
    
    conn = get_db_connection()
    
    # 1. Stagnation Alert Logic (> 10 days inactive)
    stagnant_query = """
        SELECT * FROM leads 
        WHERE last_contact_date < datetime('now', '-10 days') 
        AND status NOT IN ('closed_no_response', 'invalid_number')
    """
    stagnant_leads = conn.execute(stagnant_query).fetchall()
    
    if stagnant_leads:
        with st.expander(f"⚠️ Alerta: {len(stagnant_leads)} Leads sem interação há mais de 10 dias!", expanded=True):
            st.dataframe(
                pd.DataFrame([dict(row) for row in stagnant_leads])[["name", "phone", "last_contact_date", "status"]],
                use_container_width=True
            )
            st.warning("Considere enviar uma mensagem manual ou arquivar estes leads.")
    
    st.divider()
    
    # 2. Chat View - Get leads with conversation history
    chat_query = """
        SELECT * FROM leads 
        WHERE conversation_history IS NOT NULL AND conversation_history != ''
        ORDER BY last_contact_date DESC
        LIMIT 50
    """
    active_chats = conn.execute(chat_query).fetchall()
    conn.close()
    
    if not active_chats:
        st.info("Nenhuma conversa ativa encontrada. Aguardando mensagens...")
    else:
        # Layout: Sidebar list of chats, Main area for messages
        col_list, col_chat = st.columns([1, 2])
        
        with col_list:
            st.subheader("📋 Conversas Ativas")
            selected_chat_index = st.radio(
                "Selecione um Lead:",
                range(len(active_chats)),
                format_func=lambda x: f"{active_chats[x]['name'][:15]}..."
            )
        
        with col_chat:
            lead = dict(active_chats[selected_chat_index])
            st.subheader(f"👤 {lead['name']}")
            st.caption(f"📞 {lead['phone']} | Status: {lead['status']} | Último: {lead['last_contact_date']}")
            
            # Trello Link
            if trello_crm.is_configured():
                card = trello_crm.find_card_by_phone(lead['phone'])
                if card:
                    st.markdown(f"🔗 **[Ver no Trello]({card.get('shortUrl', card.get('url'))})**")
            
            st.divider()
            
            # Parse and display bubbles
            history = lead['conversation_history']
            if history:
                lines = history.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    
                    is_agent = False
                    if any(x in line for x in ["Agente", "Ivair", "Chatwoot Agent", "Follow-up", "Envio"]):
                        is_agent = True
                    
                    # Style
                    if is_agent:
                        st.markdown(f"""
                        <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                            <div style="background-color: #dcf8c6; color: black; padding: 10px; border-radius: 10px; max-width: 70%;">
                                {line}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                         st.markdown(f"""
                        <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                            <div style="background-color: #ffffff; color: black; border: 1px solid #ddd; padding: 10px; border-radius: 10px; max-width: 70%;">
                                {line}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            
            # Quick Reply Box
            st.divider()
            with st.form(key=f"reply_form_{lead['id']}"):
                reply_text = st.text_input("Resposta Rápida (Enviar como Ivair)")
                if st.form_submit_button("Enviar 🚀"):
                    if reply_text:
                        jid = check_whatsapp_exists(lead['phone'])
                        if jid:
                            send_message(jid, reply_text)
                            update_lead_status(lead['phone'], 'contacted', f"🤖 Ivair (WhatsApp):\n\n{reply_text}")
                            
                            # Trello Sync
                            if trello_crm.is_configured():
                                card = trello_crm.find_card_by_phone(lead['phone'])
                                if card:
                                    trello_crm.add_comment(card['id'], f"📝 Envio Rápido (Chat):\n\n{reply_text}")
                            
                            st.success("Enviado!")
                            st.rerun()
                        else:
                            st.error("Número inválido.")
    
    # Chatwoot Link at the bottom
    st.divider()
    chatwoot_url = os.getenv("CHATWOOT_URL")
    if chatwoot_url:
        st.markdown(f"🟣 **[Abrir Chatwoot em Nova Aba]({chatwoot_url})**")

elif page == "Configurações":
    st.header("Configurações")
    st.info("As configurações são carregadas do arquivo .env")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Verificar Conexão WhatsApp"):
            # Simple check
            st.write("Para verificar, tente enviar uma mensagem para você mesmo na aba 'Gerenciar Leads'.")
            
    with col2:
        st.subheader("Manutenção da Base")
        if st.button("🧹 Re-validar Números (Limpeza)"):
            conn = get_db_connection()
            # Get all leads likely to be messaged (new, contacted, follow_up)
            # We don't want to re-validate invalid ones (unless checking if they became valid?)
            # Let's check 'new' ones mainly, or maybe all active statuses
            leads_to_check = conn.execute("SELECT * FROM leads WHERE status IN ('new')").fetchall()
            conn.close()
            
            st.write(f"Verificando {len(leads_to_check)} leads com status 'new'...")
            
            progress = st.progress(0)
            status_t = st.empty()
            
            cleaned_count = 0
            
            for i, row in enumerate(leads_to_check):
                lead = dict(row)
                
                # Progress
                progress.progress(int((i / len(leads_to_check)) * 100))
                status_t.text(f"Verificando: {lead['name']} ({lead['phone']})")
                
                # Check
                # We might need to re-clean the phone just in case
                clean_p = format_number(lead['phone'])
                
                jid = check_whatsapp_exists(clean_p)
                
                if not jid:
                    update_lead_status(lead['phone'], 'invalid_number', "Marcado como inválido durante limpeza")
                    cleaned_count += 1
                
            progress.progress(100)
            status_t.success(f"Limpeza concluída! {cleaned_count} leads inválidos foram removidos da lista 'new'.")
