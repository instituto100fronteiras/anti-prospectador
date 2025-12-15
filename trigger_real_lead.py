import sqlite3
import os
import sys
import agent
import database

# Force DB path to root leads.db where we found the data
database.DB_NAME = "leads.db"

target_phone_partial = "99135-4875" # Unique enough part of +55 45 99135-4875

print(f"--- 🧪 TESTE REAL COM DADOS DO BANCO ---")

conn = database.get_db_connection()
# Find the lead
lead = conn.execute(f"SELECT * FROM leads WHERE phone LIKE '%{target_phone_partial}'").fetchone()

if not lead:
    print("❌ Lead não encontrado no banco leads.db")
    sys.exit(1)
    
lead_dict = dict(lead)
print(f"✅ Lead Encontrado: {lead_dict['name']}")
print(f"   Telefone: {lead_dict['phone']}")
print(f"   Status Atual: {lead_dict['status']}")

# Get History (Simulated or Real if stored)
# The local DB stores 'conversation_history' in a text column, 
# BUT real history comes from Chatwoot API.
# We need to fetch from Chatwoot to be 100% real.
print("\n📡 Buscando histórico no Chatwoot...")
import chatwoot_api

chatwoot_contact = chatwoot_api.get_contact_by_phone(lead_dict['phone'])
if not chatwoot_contact:
    print("⚠️ Contato não encontrado no Chatwoot via API.")
    print("   Tentando usar histórico local do banco como fallback...")
    history = lead_dict.get('conversation_history', '')
else:
    print(f"✅ Contato Chatwoot ID: {chatwoot_contact['id']}")
    msgs = chatwoot_api.get_conversation_history(chatwoot_contact['id'])
    history = chatwoot_api.format_history_for_llm(msgs)

if not history:
    print("❌ Sem histórico encontrado (nem Chatwoot nem Local).")
    print("   Não é possível testar 'contexto' sem histórico.")
    # Inject fake history to PROVE that IF history existed, it would work?
    # User said "enviamos uma proposta no dia 12/12".
    print("   -> Injetando histórico SIMULADO do dia 12/12 para validar lógica:")
    history = """
    Ivair: Olá, aqui é o Ivair da 100fronteiras.
    Cliente: Pode mandar a proposta.
    Ivair: Segue a proposta comercial 2025. (12/12/2025)
    """

print(f"\n📜 Histórico Utilizado ({len(history)} chars):")
print("-" * 40)
print(history.strip())
print("-" * 40)

print("\n🤖 Gerando Mensagem Contextual...")
try:
    parts = agent.generate_contextual_message(lead_dict, history)
    full_msg = "\n".join(parts)
    
    print("\n--- RESPOSTA GERADA ---")
    print(full_msg)
    print("-----------------------")
    
    lower_msg = full_msg.lower()
    if "sou o ivair" in lower_msg or "aqui é o ivair" in lower_msg:
        print("❌ FALHA: Introdução detectada!")
    else:
        print("✅ SUCESSO: Mensagem sem introdução padrão.")
        
except Exception as e:
    print(f"❌ Erro: {e}")
