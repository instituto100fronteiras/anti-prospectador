import trello_crm

print("=== Verificando Conexão Trello ===")
if trello_crm.is_configured():
    print("Credenciais encontradas.")
    lists = trello_crm.get_lists()
    if lists:
        print("\n✅ Conexão bem sucedida! Colunas encontradas:")
        for name, id in lists.items():
            print(f"- {name} (ID: {id})")
            
        print("\nVerifique se os nomes acima conferem com o que o robô espera:")
        print("1. 'Prospecção' (Para onde vão novos leads)")
        print("2. 'Contato Inicial' (Para onde vão após envio)")
        print("3. 'Respondido' (Para onde vão se responderem)")
    else:
        print("❌ Falha ao buscar colunas. Verifique o ID do Board e o Token.")
else:
    print("❌ Credenciais não configuradas corretamente no .env")
