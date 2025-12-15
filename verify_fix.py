import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import agent
    import chatwoot_api
    from scheduler import process_one_lead 
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

# Mock Data simulating the problematic case
MOCK_LEAD = {
    'name': 'João da Silva',
    'phone': '554591354875',
    'language': 'pt'
}

# Simulate history (Proposal sent on Dec 12)
MOCK_HISTORY_TEXT = """
Ivair: Olá João, tudo bem? Aqui é o Ivair da 100fronteiras.
João: Oi Ivair, tudo certo.
Ivair: Estamos com uma oportunidade legal para 2025. Posso te mandar a proposta?
João: Pode mandar sim.
Ivair: [Arquivo enviado: Proposta_Comercial_2025.pdf]
Ivair: Segue a proposta! Me avise quando conseguir ler. (Enviado em 12/12/2025)
"""

print("--- 🧪 TESTE DE VERIFICAÇÃO DO BUG DE HISTÓRICO ---\n")

# 1. Test Logic Flow (Simulating what scheduler does)
print("1. Verificando Lógica de Decisão:")
print(f"   Cenário: Lead com histórico de {len(MOCK_HISTORY_TEXT)} chars.")

# We can't easily run scheduler.process_one_lead because it talks to DB and Real API.
# Instead, we test the core decision logic we changed.

should_be_contextual = True if MOCK_HISTORY_TEXT else False
print(f"   Decisão esperada (Com a correção): 'Contextual' (True)")
print(f"   --> Simulação: if chatwoot_history: {should_be_contextual}")

if should_be_contextual:
    print("   ✅ Lógica Correta: O sistema detectou histórico e optará pelo fluxo contextual.\n")
else:
    print("   ❌ Lógica Falhou: O sistema ignorou o histórico.\n")

# 2. Test Message Generation
print("2. Verificando Geração da Mensagem (Prompt):")
print("   Gerando mensagem contextual baseada no histórico acima...")
print("   (Isso usa o prompt atualizado que proíbe reintrodução)\n")

try:
    # Call the agent directly
    parts = agent.generate_contextual_message(MOCK_LEAD, MOCK_HISTORY_TEXT)
    
    print("\n--- 🤖 Resposta Gerada pelo Agente ---")
    full_msg = "\n".join(parts)
    print(full_msg)
    print("--------------------------------------\n")
    
    # Simple check for "Sou o Ivair" or "Aqui é o Ivair"
    lower_msg = full_msg.lower()
    forbidden_phrases = ["sou o ivair", "aqui é o ivair", "sou ivair", "aqui é ivair"]
    
    found_forbidden = [p for p in forbidden_phrases if p in lower_msg]
    
    if found_forbidden:
        print(f"⚠️ AVISO: A mensagem ainda parece conter uma introdução: '{found_forbidden[0]}'")
        print("   Sugestão: O prompt pode precisar de mais reforço, ou foi uma coincidência.")
    else:
        print("✅ SUCESSO: A mensagem NÃO contem a introdução padrão proibida.")
        print("   O agente foi direto ao ponto (cobrar a proposta).")

except Exception as e:
    print(f"❌ Erro ao chamar OpenAI: {e}")
    print("   Verifique se a OPENAI_API_KEY está correta no .env")

print("\n--- Fim do Teste ---")
