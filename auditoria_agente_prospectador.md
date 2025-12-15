# 🔍 Auditoria: Agente Prospectador 100fronteiras

## Resumo Executivo

O sistema tem estrutura sólida, mas possui **5 falhas críticas** que podem causar:
- Mensagens duplicadas para o mesmo lead
- Mensagens "frias" para quem já conversou
- Follow-ups para quem já disse "não"
- Perda de contexto em falhas de rede

---

## ✅ O QUE ESTÁ FUNCIONANDO BEM

| Componente | Descrição |
|------------|-----------|
| `scheduler.py:96-110` | Verifica duplicatas nos últimos 7 dias |
| `scheduler.py:115-128` | Busca histórico no Chatwoot antes de enviar |
| `scheduler.py:143-147` | Usa `generate_contextual_message()` se tem histórico |
| `agent.py:generate_contextual_message()` | Gera mensagem baseada em conversa anterior |
| `server.py:636-638` | Webhook Chatwoot atualiza status para 'responded' |
| Auto-refill | Checa Chatwoot antes de adicionar lead como 'new' |

---

## ❌ PROBLEMAS CRÍTICOS IDENTIFICADOS

### 1. 🚨 NÃO VERIFICA QUEM MANDOU A ÚLTIMA MENSAGEM

**Localização:** `scheduler.py` linhas 115-147

**Problema:**
```python
# Atual: apenas checa SE existe histórico
if messages and len(messages) > 0:
    chatwoot_history = chatwoot_api.format_history_for_llm(messages)
```

O código verifica se existe histórico, mas **NÃO verifica**:
- Quem mandou a última mensagem (nós ou o cliente)
- Se estamos aguardando resposta do cliente
- Se o cliente já respondeu algo negativo

**Consequência:** 
Se você mandou mensagem ontem e o cliente ainda não respondeu, o sistema pode mandar outra mensagem hoje porque o lead pode voltar ao status 'new' por algum bug.

---

### 2. 🚨 FALHA DO CHATWOOT IGNORA HISTÓRICO

**Localização:** `scheduler.py` linhas 119-124

**Problema:**
```python
except Exception as ch_err:
    print(f"Chatwoot check failed (will use standard template): {ch_err}")
    # CONTINUA E MANDA TEMPLATE PADRÃO!
```

Se o Chatwoot estiver fora do ar ou der timeout, o sistema **ignora e manda template padrão**.

**Consequência:**
- Cliente que já conversou recebe mensagem como se fosse primeiro contato
- Mensagem duplicada se o histórico existe mas não foi buscado

---

### 3. 🚨 NÃO ANALISA INTENÇÃO/SENTIMENTO DA RESPOSTA

**Localização:** `agent.py` e `followup.py`

**Problema:**
Não existe análise se o cliente:
- Disse "não tenho interesse"
- Pediu para não contatar mais
- Já fechou negócio por outro canal

**Consequência:**
Follow-ups continuam sendo enviados mesmo para leads que já recusaram.

---

### 4. 🚨 RACE CONDITION NO PROCESSAMENTO

**Localização:** `scheduler.py` linha 81

**Problema:**
```python
lead_row = conn.execute("SELECT * FROM leads WHERE status = 'new' ...").fetchone()
# ... processamento ...
update_lead_status(lead['phone'], 'processing')  # LOCK TARDIO
```

O lock só acontece DEPOIS de selecionar o lead. Se o scheduler rodar 2x quase simultaneamente, pode pegar o mesmo lead.

**Consequência:**
Mensagem duplicada em reinicializações rápidas ou execuções paralelas.

---

### 5. 🚨 FALTA CAMPO last_outbound_at

**Localização:** `database.py` (schema)

**Problema:**
Não há campo específico para rastrear:
- Quando foi nossa última mensagem enviada
- Quando foi a última resposta do cliente

O campo `last_contact_date` é genérico e não distingue direção.

**Consequência:**
Impossível saber "já mandei mensagem hoje?" sem consultar Chatwoot.

---

## 🛠️ SOLUÇÕES PROPOSTAS

### Solução 1: Verificar Última Mensagem Antes de Enviar

**Arquivo:** `chatwoot_api.py` (novo método)

```python
def should_contact_lead(phone):
    """
    Analisa se devemos enviar mensagem para este lead.
    
    Returns:
        dict: {
            'should_contact': bool,
            'reason': str,
            'last_message_from': 'us' | 'them' | None,
            'last_message_at': datetime | None,
            'conversation_history': str | None
        }
    """
    contact = get_contact_by_phone(phone)
    
    if not contact:
        return {
            'should_contact': True,
            'reason': 'new_contact',
            'last_message_from': None,
            'last_message_at': None,
            'conversation_history': None
        }
    
    messages = get_conversation_history(contact['id'])
    
    if not messages or len(messages) == 0:
        return {
            'should_contact': True,
            'reason': 'no_history',
            'last_message_from': None,
            'last_message_at': None,
            'conversation_history': None
        }
    
    # Ordenar por data (mais recente primeiro)
    sorted_msgs = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=True)
    last_msg = sorted_msgs[0]
    
    # message_type: 0 = incoming (cliente), 1 = outgoing (nós)
    last_from = 'them' if last_msg.get('message_type') == 0 else 'us'
    last_at = last_msg.get('created_at')
    
    history = format_history_for_llm(messages)
    
    # REGRAS DE DECISÃO
    
    # 1. Se última mensagem foi NOSSA e há menos de 3 dias → NÃO CONTATAR (aguardar resposta)
    if last_from == 'us':
        from datetime import datetime, timedelta
        try:
            last_date = datetime.fromisoformat(last_at.replace('Z', '+00:00'))
            if datetime.now(last_date.tzinfo) - last_date < timedelta(days=3):
                return {
                    'should_contact': False,
                    'reason': 'waiting_response',
                    'last_message_from': last_from,
                    'last_message_at': last_at,
                    'conversation_history': history
                }
        except:
            pass
    
    # 2. Se última mensagem foi DELES → verificar se é negativa
    if last_from == 'them':
        content = last_msg.get('content', '').lower()
        negative_signals = [
            'não tenho interesse',
            'no tengo interés',
            'não preciso',
            'não quero',
            'para de',
            'não me ligue',
            'não entre em contato',
            'remove',
            'sair da lista'
        ]
        
        if any(signal in content for signal in negative_signals):
            return {
                'should_contact': False,
                'reason': 'declined',
                'last_message_from': last_from,
                'last_message_at': last_at,
                'conversation_history': history
            }
        
        # Cliente respondeu positivamente ou neutro → CONTATAR com contexto
        return {
            'should_contact': True,
            'reason': 'continue_conversation',
            'last_message_from': last_from,
            'last_message_at': last_at,
            'conversation_history': history
        }
    
    # Default: pode contatar
    return {
        'should_contact': True,
        'reason': 'default',
        'last_message_from': last_from,
        'last_message_at': last_at,
        'conversation_history': history
    }
```

---

### Solução 2: Modificar scheduler.py para Usar Verificação

**Substituir bloco lines 115-147 por:**

```python
# 1. VERIFICAÇÃO OBRIGATÓRIA - Não prosseguir se Chatwoot falhar
print("      Verificando Chatwoot (OBRIGATÓRIO)...")
try:
    import chatwoot_api
    
    contact_check = chatwoot_api.should_contact_lead(lead['phone'])
    
    if not contact_check['should_contact']:
        reason = contact_check['reason']
        print(f"      ⛔ NÃO CONTATAR: {reason}")
        
        if reason == 'waiting_response':
            # Manter como 'contacted', não voltar para 'new'
            update_lead_status(lead['phone'], 'contacted')
            print("      Status mantido como 'contacted' (aguardando resposta)")
        elif reason == 'declined':
            update_lead_status(lead['phone'], 'declined')
            print("      Marcado como 'declined' (cliente recusou)")
        
        return  # SAI DA FUNÇÃO, NÃO ENVIA NADA
    
    chatwoot_history = contact_check['conversation_history']
    last_from = contact_check['last_message_from']
    
    print(f"      ✅ Pode contatar. Razão: {contact_check['reason']}")
    if last_from:
        print(f"      Última mensagem de: {'Cliente' if last_from == 'them' else 'Nós'}")

except Exception as ch_err:
    # CRÍTICO: Se Chatwoot falhar, NÃO ENVIAR
    print(f"      ❌ ERRO CRÍTICO Chatwoot: {ch_err}")
    print(f"      Abortando envio para evitar duplicata. Lead volta para 'new'.")
    update_lead_status(lead['phone'], 'new')
    return  # SAI DA FUNÇÃO
```

---

### Solução 3: Lock Atômico no Início

**Modificar scheduler.py linha 76-82:**

```python
# LOCK ATÔMICO - Previne race condition
conn = get_db_connection()
cursor = conn.execute("""
    UPDATE leads 
    SET status = 'processing' 
    WHERE status = 'new' 
    AND id = (
        SELECT id FROM leads 
        WHERE status = 'new' 
        ORDER BY RANDOM() 
        LIMIT 1
    )
    RETURNING *
""")
lead_row = cursor.fetchone()
conn.commit()
conn.close()

if not lead_row:
    print("[Job] No new leads available (or all locked).")
    auto_refill_leads()
    return

lead = dict(lead_row)
print(f"[Job] Locked and selected: {lead['name']} ({lead['phone']})")
```

---

### Solução 4: Análise de Intenção com IA

**Adicionar em agent.py:**

```python
def analyze_lead_intent(conversation_history):
    """
    Analisa o histórico e determina a intenção/status do lead.
    
    Returns:
        dict: {
            'intent': 'interested' | 'neutral' | 'declined' | 'busy' | 'unknown',
            'confidence': float (0-1),
            'suggested_action': str,
            'next_contact_days': int | None
        }
    """
    
    user_prompt = f"""
    Analise este histórico de conversa comercial e determine a intenção do cliente:
    
    HISTÓRICO:
    {conversation_history}
    
    Classifique a intenção do cliente:
    - "interested": Demonstrou interesse, quer saber mais
    - "neutral": Não se posicionou claramente
    - "declined": Recusou ou pediu para não contatar
    - "busy": Disse que está ocupado/volta depois
    - "unknown": Não é possível determinar
    
    Retorne APENAS JSON válido:
    {{
        "intent": "interested|neutral|declined|busy|unknown",
        "confidence": 0.0 a 1.0,
        "suggested_action": "Descrição curta da próxima ação",
        "next_contact_days": número ou null
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um analista de CRM."},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error analyzing intent: {e}")
        return {
            'intent': 'unknown',
            'confidence': 0,
            'suggested_action': 'Verificar manualmente',
            'next_contact_days': None
        }
```

---

### Solução 5: Adicionar Campos no Database

**Modificar schema em database.py:**

```python
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            address TEXT,
            website TEXT,
            rating REAL,
            reviews INTEGER,
            types TEXT,
            search_term TEXT,
            status TEXT DEFAULT 'new',
            conversation_history TEXT,
            prompt_version TEXT,
            language TEXT DEFAULT 'pt',
            
            -- NOVOS CAMPOS
            last_outbound_at TIMESTAMP,      -- Nossa última mensagem
            last_inbound_at TIMESTAMP,       -- Última do cliente
            lead_intent TEXT,                -- interested/neutral/declined/busy
            intent_confidence REAL,          -- 0-1
            decline_reason TEXT,             -- Se declined, por quê?
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_contact_date TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
```

---

## 📋 CHECKLIST DE IMPLEMENTAÇÃO

- [ ] Criar método `should_contact_lead()` em `chatwoot_api.py`
- [ ] Modificar `scheduler.py` para usar verificação obrigatória
- [ ] Implementar lock atômico no SELECT/UPDATE
- [ ] Adicionar `analyze_lead_intent()` em `agent.py`
- [ ] Atualizar schema do banco com novos campos
- [ ] Criar migration para banco existente
- [ ] Testar com cenários:
  - [ ] Lead novo (nunca contatado)
  - [ ] Lead que já contatamos, sem resposta
  - [ ] Lead que respondeu positivamente
  - [ ] Lead que recusou
  - [ ] Falha de conexão Chatwoot

---

## 🔄 FLUXO CORRIGIDO

```
┌─────────────────────────────────────────────────────────────────┐
│                     SCHEDULER EXECUTA                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. LOCK ATÔMICO: SELECT + UPDATE em transação única           │
│     → Previne race condition                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. should_contact_lead(phone)                                  │
│     → Busca histórico Chatwoot                                 │
│     → Analisa última mensagem                                  │
│     → Verifica sinais negativos                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
    ┌──────────────┐               ┌──────────────┐
    │ NÃO CONTATAR │               │ PODE CONTATAR│
    │              │               │              │
    │ • waiting    │               │ • new_contact│
    │ • declined   │               │ • continue   │
    └──────┬───────┘               └──────┬───────┘
           │                               │
           ▼                               ▼
    ┌──────────────┐               ┌──────────────┐
    │ Atualiza     │               │ Tem histórico│
    │ status e SAI │               │ Chatwoot?    │
    └──────────────┘               └──────┬───────┘
                                          │
                            ┌─────────────┴─────────────┐
                            │                           │
                            ▼                           ▼
                    ┌──────────────┐           ┌──────────────┐
                    │ SIM          │           │ NÃO          │
                    │              │           │              │
                    │ generate_    │           │ Template     │
                    │ contextual() │           │ A/B/C        │
                    └──────┬───────┘           └──────┬───────┘
                           │                          │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                            ┌──────────────────────┐
                            │ ENVIA MENSAGEM       │
                            │ Atualiza DB + Trello │
                            └──────────────────────┘
```

---

## ⚠️ AÇÕES IMEDIATAS RECOMENDADAS

1. **URGENTE**: Implementar fail-safe do Chatwoot (Solução 2)
   - Atualmente se Chatwoot falha, manda mensagem sem contexto

2. **ALTA**: Adicionar verificação "última mensagem foi nossa?"
   - Evita duplicatas e spam

3. **MÉDIA**: Lock atômico para race condition
   - Importante para estabilidade

4. **BAIXA**: Análise de intenção com IA
   - Melhoria de qualidade, não crítico
