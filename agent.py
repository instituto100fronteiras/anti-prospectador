import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ivair, você é o representante comercial da 100fronteiras — portal de comunicação e eventos culturais da região da Tríplice Fronteira. Sua missão é prospectar e converter clientes corporativos que desejam aumentar sua visibilidade na região através de parcerias editoriais e patrocínios.

Atua como consultor comercial especializado em comunicação digital, eventos culturais (como o 100fronteiras JAZZ Festival) e conteúdo editorial para empresas que buscam impacto regional.

Você NUNCA soa robótico. Comunicação natural, direta e profissional. Fala como especialista em comunicação regional que entende as necessidades locais.

**SEUS DIFERENCIAIS:**
- Portal consolidado na Tríplice Fronteira com audiência fiel
- Expertise em eventos culturais (JAZZ Festival, outros)
- Relacionamento com órgãos públicos e empresas regionais  
- Produção editorial especializada em turismo, cultura e negócios locais
- Métricas de alcance e engajamento comprovadas

⚠️ **LIMITADOR**: Máximo **60 tokens** por resposta.

🎯 **OBJETIVO**: Converter prospects em parceiros comerciais da 100fronteiras com naturalidade e expertise regional.

🧠 **DADOS CONHECIDOS:**
- Portal ativo há anos na região da Tríplice Fronteira
- Cobertura editorial: turismo, cultura, eventos, negócios locais
- Eventos próprios: 100fronteiras JAZZ Festival (4ª edição)
- Parcerias institucionais: prefeituras, Itaipu, Sanepar, órgãos estaduais
- Produtos: matérias patrocinadas, cobertura de eventos, revista, parcerias em eventos

💬 **TOM**: Profissional experiente, conhecedor da região, direto nas propostas, focado em resultados mensuráveis.

Sempre adapte ao perfil do cliente. Construa relacionamento com expertise — nunca force venda.

##**MENSAGEM INICIAL:**
"Olá, ótima semana! Aqui é [seu nome] da 100fronteiras, com quem falo aí na empresa? Estamos preparando a edição comemorativa de novo formato pelos 20 anos da Revista 100fronteiras e pensei em vocês pelo legado que vocês constroem."

🔄 Conduza com conhecimento regional e dados concretos de audiência.
"""

PROMPT_TEMPLATES = {
    'A': [
        "Boa tarde!",
        "Aqui é o Ivair, do portal 100fronteiras 👋",
        "A Revista 100fronteiras completa 20 anos em 2026 e estamos montando parcerias estratégicas pra essa edição comemorativa.",
        "Vocês já fecharam o planejamento de marketing pro ano que vem? Queria trocar uma ideia com vocês!"
    ],
    'B': [
        "Olá, ótima semana!",
        "Aqui é o Ivair, da 100fronteiras. Com quem eu falo aí no comercial?",
        "Em 2026 a gente comemora 20 anos de portal e revista e estamos buscando marcas que são referência na região.",
        "Lembrei de vocês! Posso explicar como podemos trabalhar juntos?"
    ],
    'C': [
        "E aí, tudo bem?",
        "Sou o Ivair do 100fronteiras, portal de turismo e cultura da Tríplice Fronteira.",
        "Estamos preparando uma edição especial pelos 20 anos da revista e queremos convidar empresas parceiras pra fazer parte.",
        "Vocês teriam interesse em conhecer a proposta? 🤝"
    ],
    'A_ES': [
        "¡Buenas tardes!",
        "Soy Ivair, del portal 100fronteiras 👋",
        "La Revista 100fronteiras cumple 20 años en 2026 y estamos armando alianzas estratégicas para esa edición conmemorativa.",
        "¿Ya cerraron la planificación de marketing para el próximo año? ¡Me gustaría conversar con ustedes!"
    ],
    'B_ES': [
        "¡Hola, excelente semana!",
        "Soy Ivair, de 100fronteiras. ¿Con quién hablo del área comercial?",
        "En 2026 celebramos 20 años del portal y revista. Buscamos marcas que son referentes en la región.",
        "¡Me acordé de ustedes! ¿Puedo explicarles cómo podemos trabajar juntos?"
    ],
    'C_ES': [
        "¿Qué tal, todo bien?",
        "Soy Ivair de 100fronteiras, portal de turismo y cultura de la Triple Frontera.",
        "Estamos preparando una edición especial por los 20 años de la revista y queremos invitar empresas socias a participar.",
        "¿Les interesaría conocer la propuesta? 🤝"
    ]
}


def generate_message(lead_data, website_content=None, version='A'):
    
    # Language Detection/Selection
    language = lead_data.get('language', 'pt')
    
    # Adjust version for language
    final_version = version
    if language == 'es' and not version.endswith('_ES'):
        final_version = f"{version}_ES"
        
    # Check if template exists, fallback to A or A_ES
    template = PROMPT_TEMPLATES.get(final_version)
    if not template:
        # Fallback logic
        if language == 'es':
             template = PROMPT_TEMPLATES['A_ES']
        else:
             template = PROMPT_TEMPLATES['A']
    
    context_info = ""
    if website_content:
        context_info = f"\n    CONTEÚDO DO SITE DO CLIENTE (Apenas para contexto, mas tente seguir fielmente o template escolhido):\n    {website_content[:1000]}..."

    user_prompt = f"""
    Siga ESTRITAMENTE o modelo abaixo para gerar a mensagem. Apenas substitua os placeholders entre chaves ou colchetes ([Nome], [Empresa]) pelos dados reais do lead. 
    Se não tiver o nome da pessoa, adapte ligeiramente para não ficar estranho (ex: "Olá equipe da [Empresa]").
    
    DADOS DO LEAD:
    Nome: {lead_data.get('name')}
    Empresa: {lead_data.get('name')} (Use este nome para empresa)
    Idioma: {language}
    
    MODELO OBRIGATÓRIO (Versão {final_version}):
    ---
    {template}
    ---
    
    INSTRUÇÃO CRÍTICA DE FORMATAÇÃO:
    Divida a mensagem em 3 ou 4 partes curtas e naturais (como balões de chat), separadas EXATAMENTE por "|||". 
    NÃO coloque "Parte 1" ou números. Apenas o texto separado por |||.
    
    Exemplo:
    Olá [Nome], tudo bem?|||Aqui é o Ivair...|||Vi que vocês...
    
    Gere apenas a mensagem final, sem aspas. Mantenha o idioma do modelo ({language}).
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=300, # Increased for multiple bubbles
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating message: {e}")
        return None

def generate_followup_message(lead_data, stage):
    instructions = {
        1: "O cliente não respondeu ao primeiro contato feito há 3 dias. Gere uma mensagem curta e educada perguntando se ele conseguiu ver a mensagem anterior. Mantenha o tom profissional e amigável de Ivair.",
        2: "O cliente não respondeu há uma semana. Gere uma mensagem trazendo uma novidade ou um benefício específico da 100fronteiras (ex: audiência qualificada, networking). Algo para despertar interesse.",
        3: "Última tentativa. O cliente não responde há duas semanas. Gere uma mensagem de 'break-up' suave, dizendo que não vai mais incomodar, mas deixando as portas abertas para o futuro."
    }
    
    instruction = instructions.get(stage, "Gere uma mensagem de follow-up.")
    
    user_prompt = f"""
    Olá Ivair, preciso de um follow-up para este cliente:
    Nome: {lead_data.get('name')}
    
    Histórico da conversa:
    {lead_data.get('conversation_history', '')}
    
    Instrução: {instruction}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=100,
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating follow-up: {e}")
        return None


def generate_contextual_message(lead_data, conversation_history):
    """
    Generate a contextual message based on previous Chatwoot conversation history.
    Used when re-engaging with a contact that has prior interactions.
    """
    language = lead_data.get('language', 'pt')
    
    user_prompt = f"""
    Você precisa gerar uma mensagem de retomada de conversa para este lead.
    
    DADOS DO LEAD:
    Nome: {lead_data.get('name')}
    Empresa: {lead_data.get('name')}
    Idioma: {language}
    
    HISTÓRICO DA CONVERSA ANTERIOR (Chatwoot):
    {conversation_history}
    
    INSTRUÇÕES:
    1. Leia o histórico acima e entenda o contexto da conversa anterior
    2. Gere uma mensagem natural que retome a conversa de forma contextualizada
    3. Não repita informações já ditas, mas faça referência ao que foi conversado
    4. Mantenha o tom profissional e amigável do Ivair
    5. Foque em avançar a conversa sobre a parceria com a 100fronteiras
    6. A mensagem deve ser dividida em 4 partes curtas (para envio sequencial)
    7. Retorne APENAS as 4 partes separadas por "|||"
    
    Exemplo de formato de resposta:
    Oi [Nome], tudo bem?|||Retomando nossa conversa sobre [assunto]...|||[Continuação contextual]|||[Pergunta ou call-to-action]
    
    Gere as 4 partes agora:
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=250,
            temperature=0.5
        )
        
        # Parse response into 4 parts
        message = response.choices[0].message.content.strip()
        parts = [p.strip() for p in message.split('|||')]
        
        # Ensure we have exactly 4 parts
        if len(parts) < 4:
            parts.extend([""] * (4 - len(parts)))
        
        return parts[:4]  # Return only first 4 parts
    except Exception as e:
        print(f"Error generating contextual message: {e}")
        return None

def analyze_conversation_for_name(history_text):
    """
    Analyzes the conversation history to identify the Lead's Name or Company Name.
    Returns JSON: {"name": "Found Name", "confidence": "high/medium/low"}
    """
    if not history_text or len(history_text) < 50:
        return None

    user_prompt = f"""
    Analise o histórico de conversa abaixo e tente identificar o NOME DA PESSOA ou NOME DA EMPRESA com quem o Ivair está falando.
    
    HISTÓRICO:
    {history_text}
    
    Regras:
    1. Se o cliente se apresentou (ex: "Aqui é o João"), use "João".
    2. Se for uma empresa (ex: "Somos da Arquitetura X"), use "Arquitetura X".
    3. Se não tiver certeza, retorne null.
    
    Retorne APENAS um JSON válido:
    {{
        "name": "Nome Encontrado ou null",
        "type": "person/company",
        "confidence": "high/low"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente que extrai dados de CRM."},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=100,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error analyzing name: {e}")
        return None
