import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")

raw_url = os.getenv("CHATWOOT_URL", "")
# Sanitize URL: remove /app/... or /conversations...
if "/app" in raw_url:
    CHATWOOT_URL = raw_url.split("/app")[0]
elif "/conversations" in raw_url:
    CHATWOOT_URL = raw_url.split("/conversations")[0]
else:
    CHATWOOT_URL = raw_url

# Remove trailing slash
CHATWOOT_URL = CHATWOOT_URL.rstrip('/')

CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")


def get_contact_by_phone(phone):
    """
    Search for a contact in Chatwoot by phone number.
    Returns contact data if found, None otherwise.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return None
    
    # Clean phone number
    clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Search contacts - Try CLEAN version first (e.g. 5545...)
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/search"
        params = {"q": clean_phone}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('payload') and len(data['payload']) > 0:
                return data['payload'][0]  # Return first match

        # Try w/ PLUS (e.g. +5545...) if not found
        params = {"q": f"+{clean_phone}"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('payload') and len(data['payload']) > 0:
                 return data['payload'][0]
        
        return None
    except Exception as e:
        print(f"Error searching Chatwoot contact: {e}")
        return None


def get_conversation_history(contact_id):
    """
    Get conversation history for a contact from Chatwoot.
    Returns a list of messages or None.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return None
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Get contact's conversations
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/{contact_id}/conversations"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('payload') and len(data['payload']) > 0:
                # Get the most recent conversation
                conversation_id = data['payload'][0]['id']
                
                # Get messages from that conversation
                messages_url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
                messages_response = requests.get(messages_url, headers=headers, timeout=10)
                
                if messages_response.status_code == 200:
                    messages_data = messages_response.json()
                    return messages_data.get('payload', [])
        
        return None
    except Exception as e:
        print(f"Error fetching Chatwoot conversation: {e}")
        return None


def format_history_for_llm(messages):
    """
    Format Chatwoot messages into a readable history for LLM.
    """
    if not messages:
        return None
    
    formatted = []
    for msg in messages[-10:]:  # Last 10 messages
        sender = "Cliente" if msg.get('message_type') == 0 else "Ivair"
        content = msg.get('content', '')
        if content:
            formatted.append(f"{sender}: {content}")
    
    return "\n".join(formatted) if formatted else None


def list_conversations(page=1, sort_by='last_activity_at'):
    """
    List conversations from Chatwoot.
    Useful for polling updates.
    """
    if not CHATWOOT_API_TOKEN or not CHATWOOT_URL:
        return []
    
    try:
        headers = {
            "api_access_token": CHATWOOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
        params = {
            "page": page, 
            "sort_by": sort_by,
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                return data.get('data', {}).get('payload', [])
            except ValueError:
                print(f"DEBUG: Invalid JSON. Response text: {response.text}")
                return []
        else:
            print(f"DEBUG: Chatwoot API Error {response.status_code}: {response.text} (URL: {url})")
        
        return []
    except Exception as e:
        print(f"Error listing Chatwoot conversations: {e}")
        return []


# =============================================================================
# NOVAS FUNÇÕES - VERIFICAÇÃO ANTI-DUPLICATA
# =============================================================================

# Sinais de que o cliente NÃO QUER ser contatado
NEGATIVE_SIGNALS = [
    # Português
    'não tenho interesse',
    'não estou interessado',
    'sem interesse',
    'não preciso',
    'não quero',
    'para de mandar',
    'pare de mandar',
    'não me ligue',
    'não me liga',
    'não entre em contato',
    'remove',
    'sair da lista',
    'desinscrever',
    'bloquear',
    'spam',
    'não autorizo',
    'já tenho',
    'não obrigado',
    'nao obrigado',
    'nao tenho interesse',
    'nao quero',
    # Espanhol
    'no tengo interés',
    'no estoy interesado',
    'sin interés',
    'no necesito',
    'no quiero',
    'deja de mandar',
    'no me llame',
    'eliminar',
    'salir de la lista',
    'no gracias',
]

# Dias para esperar antes de fazer follow-up
DAYS_BEFORE_FOLLOWUP = 3


def should_contact_lead(phone):
    """
    Analisa se devemos enviar mensagem para este lead.
    
    CRÍTICO: Esta função DEVE ser chamada ANTES de qualquer envio.
    Se retornar should_contact=False, NÃO ENVIAR MENSAGEM.
    
    Args:
        phone: Número do telefone (sem formatação)
    
    Returns:
        dict: {
            'should_contact': bool,
            'reason': str,
            'last_message_from': 'us' | 'them' | None,
            'last_message_at': str | None,
            'conversation_history': str | None,
            'days_since_contact': int | None,
            'decline_signal': str | None
        }
    
    Reasons:
        - 'new_contact': Contato não existe no Chatwoot (primeiro contato)
        - 'no_history': Contato existe mas sem mensagens
        - 'waiting_response': Última msg foi nossa há menos de X dias
        - 'declined': Cliente sinalizou que não quer
        - 'continue_conversation': Cliente respondeu, podemos continuar
        - 'follow_up_due': Nossa msg antiga, pode fazer follow-up
    """
    
    # Tenta buscar contato no Chatwoot
    contact = get_contact_by_phone(phone)
    
    if not contact:
        return {
            'should_contact': True,
            'reason': 'new_contact',
            'last_message_from': None,
            'last_message_at': None,
            'conversation_history': None,
            'days_since_contact': None,
            'decline_signal': None
        }
    
    # Busca histórico de mensagens
    messages = get_conversation_history(contact['id'])
    
    if not messages or len(messages) == 0:
        return {
            'should_contact': True,
            'reason': 'no_history',
            'last_message_from': None,
            'last_message_at': None,
            'conversation_history': None,
            'days_since_contact': None,
            'decline_signal': None
        }
    
    # Ordena por data (mais recente primeiro)
    sorted_msgs = sorted(
        messages, 
        key=lambda x: x.get('created_at', ''), 
        reverse=True
    )
    last_msg = sorted_msgs[0]
    
    # Determina quem mandou a última mensagem
    # Chatwoot: message_type 0 = incoming (cliente), 1 = outgoing (nós/agente)
    msg_type = last_msg.get('message_type')
    last_from = 'them' if msg_type == 0 else 'us'
    last_at = last_msg.get('created_at')
    
    # Formata histórico para LLM
    history = format_history_for_llm(messages)
    
    # Calcula dias desde última mensagem
    days_since = None
    try:
        if last_at:
            last_at_clean = last_at.replace('Z', '+00:00')
            last_date = datetime.fromisoformat(last_at_clean)
            now = datetime.now(timezone.utc)
            days_since = (now - last_date).days
    except Exception as e:
        print(f"[should_contact] Erro ao parsear data: {e}")
    
    # === REGRA 1: Se última mensagem foi NOSSA ===
    if last_from == 'us':
        if days_since is not None and days_since < DAYS_BEFORE_FOLLOWUP:
            # Muito recente - aguardar resposta do cliente
            return {
                'should_contact': False,
                'reason': 'waiting_response',
                'last_message_from': last_from,
                'last_message_at': last_at,
                'conversation_history': history,
                'days_since_contact': days_since,
                'decline_signal': None
            }
        else:
            # Mais de X dias - pode fazer follow-up
            return {
                'should_contact': True,
                'reason': 'follow_up_due',
                'last_message_from': last_from,
                'last_message_at': last_at,
                'conversation_history': history,
                'days_since_contact': days_since,
                'decline_signal': None
            }
    
    # === REGRA 2: Se última mensagem foi DO CLIENTE ===
    if last_from == 'them':
        content = (last_msg.get('content') or '').lower()
        
        # Verifica sinais negativos
        detected_signal = None
        for signal in NEGATIVE_SIGNALS:
            if signal in content:
                detected_signal = signal
                break
        
        if detected_signal:
            return {
                'should_contact': False,
                'reason': 'declined',
                'last_message_from': last_from,
                'last_message_at': last_at,
                'conversation_history': history,
                'days_since_contact': days_since,
                'decline_signal': detected_signal
            }
        
        # Cliente respondeu (não negativamente) → continuar conversa
        return {
            'should_contact': True,
            'reason': 'continue_conversation',
            'last_message_from': last_from,
            'last_message_at': last_at,
            'conversation_history': history,
            'days_since_contact': days_since,
            'decline_signal': None
        }
    
    # FALLBACK: Pode contatar
    return {
        'should_contact': True,
        'reason': 'default',
        'last_message_from': last_from,
        'last_message_at': last_at,
        'conversation_history': history,
        'days_since_contact': days_since,
        'decline_signal': None
    }


def get_last_message_info(phone):
    """
    Retorna informações da última mensagem para um número.
    Útil para debug e logs.
    
    Returns:
        dict ou None: {
            'content': str (preview truncado),
            'from': 'cliente' | 'nós',
            'at': str (timestamp ISO),
            'total_messages': int
        }
    """
    contact = get_contact_by_phone(phone)
    if not contact:
        return None
    
    messages = get_conversation_history(contact['id'])
    if not messages:
        return None
    
    sorted_msgs = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=True)
    last = sorted_msgs[0]
    
    return {
        'content': (last.get('content', '') or '')[:100],  # Trunca para preview
        'from': 'cliente' if last.get('message_type') == 0 else 'nós',
        'at': last.get('created_at'),
        'total_messages': len(messages)
    }


def analyze_conversation_sentiment(phone):
    """
    Analisa o sentimento geral da conversa com um lead.
    Útil para priorizar leads mais engajados.
    
    Returns:
        dict: {
            'engagement_score': float (0-1),
            'client_messages': int,
            'our_messages': int,
            'last_interaction': str,
            'sentiment': 'positive' | 'neutral' | 'negative' | 'unknown'
        }
    """
    contact = get_contact_by_phone(phone)
    if not contact:
        return {
            'engagement_score': 0,
            'client_messages': 0,
            'our_messages': 0,
            'last_interaction': None,
            'sentiment': 'unknown'
        }
    
    messages = get_conversation_history(contact['id'])
    if not messages:
        return {
            'engagement_score': 0,
            'client_messages': 0,
            'our_messages': 0,
            'last_interaction': None,
            'sentiment': 'unknown'
        }
    
    client_msgs = [m for m in messages if m.get('message_type') == 0]
    our_msgs = [m for m in messages if m.get('message_type') == 1]
    
    # Score simples: proporção de mensagens do cliente
    total = len(messages)
    engagement = len(client_msgs) / total if total > 0 else 0
    
    # Sentimento baseado na última mensagem do cliente
    sentiment = 'neutral'
    if client_msgs:
        last_client = sorted(client_msgs, key=lambda x: x.get('created_at', ''), reverse=True)[0]
        content = (last_client.get('content') or '').lower()
        
        positive_words = ['sim', 'ok', 'bom', 'ótimo', 'legal', 'interessante', 'quero', 'pode', 'vamos']
        negative_words = ['não', 'nao', 'nunca', 'pare', 'spam']
        
        if any(w in content for w in positive_words):
            sentiment = 'positive'
        elif any(w in content for w in negative_words):
            sentiment = 'negative'
    
    last_msg = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=True)[0]
    
    return {
        'engagement_score': round(engagement, 2),
        'client_messages': len(client_msgs),
        'our_messages': len(our_msgs),
        'last_interaction': last_msg.get('created_at'),
        'sentiment': sentiment
    }
