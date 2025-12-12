import time
import random
import sys
from database import init_db, add_lead, get_lead_by_phone, update_lead_status
from search import search_leads
from agent import generate_message
from whatsapp import format_number, check_whatsapp_exists, send_message

from scraper import scrape_website

def main():
    print("=== Agente Prospectador 100fronteiras ===")
    
    # Initialize DB
    init_db()
    
    # Get search query
    query = input("O que você deseja buscar? (ex: 'construtoras em foz do iguaçu'): ")
    if not query:
        print("Busca vazia. Saindo.")
        return

    num_pages = input("Quantas páginas buscar? (padrão 1, max 5): ")
    try:
        num_pages = int(num_pages)
        if num_pages > 5: num_pages = 5
        if num_pages < 1: num_pages = 1
    except:
        num_pages = 1
        
    dry_run = input("Modo de teste (Dry Run)? (s/n) [s]: ").lower() != 'n'
    
    print(f"\nIniciando busca por '{query}' ({num_pages} páginas)...")
    leads = search_leads(query, num_pages)
    print(f"Encontrados {len(leads)} leads.")
    
    for i, lead in enumerate(leads):
        print(f"\n--- Processando {i+1}/{len(leads)}: {lead['name']} ---")
        
        # 1. Check DB
        formatted_phone = format_number(lead['phone'])
        existing_lead = get_lead_by_phone(formatted_phone)
        
        if existing_lead:
            print(f"Lead já existe no banco (Status: {existing_lead['status']}). Pulando.")
            continue
            
        # 2. Save to DB
        lead['phone'] = formatted_phone
        if add_lead(lead):
            print("Salvo no banco de dados.")
        else:
            print("Erro ao salvar no banco.")
            continue
            
        # 3. Check WhatsApp
        print("Verificando WhatsApp...")
        jid = check_whatsapp_exists(formatted_phone)
        
        if not jid:
            print(f"Número {formatted_phone} não possui WhatsApp válido. Marcando como inválido.")
            update_lead_status(formatted_phone, 'invalid_number')
            continue
            
        print(f"WhatsApp encontrado: {jid}")
        
        # 4. Scrape Website (New)
        website_content = None
        if lead.get('website'):
            print(f"Enriquecendo dados do site: {lead['website']}...")
            website_content = scrape_website(lead['website'])
        
        # 5. Generate Message
        print("Gerando mensagem com IA...")
        message = generate_message(lead, website_content)
        if not message:
            print("Falha ao gerar mensagem.")
            continue
            
        print(f"Mensagem gerada:\n---\n{message}\n---")
        
        # 5. Send Message
        if dry_run:
            print("[DRY RUN] Mensagem NÃO enviada.")
            update_lead_status(formatted_phone, 'dry_run_generated', message)
        else:
            print("Enviando mensagem...")
            result = send_message(jid, message)
            if result:
                print("Mensagem enviada com sucesso!")
                update_lead_status(formatted_phone, 'contacted', message)
            else:
                print("Erro ao enviar mensagem.")
        
        # 6. Wait to avoid spamming
        delay = random.randint(10, 30)
        print(f"Aguardando {delay} segundos...")
        time.sleep(delay)

    print("\nProcesso finalizado!")

if __name__ == "__main__":
    main()
