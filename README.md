# 🐍 Python Agent Documentation

Esta pasta contém o núcleo do sistema Agente Prospectador.

## 📂 Arquivos Principais

### `server.py`
Servidor Flask que gerencia:
*   **Webhooks**: Recebe eventos do Chatwoot (novas mensagens, atualizações).
*   **Dashboard**: Interface gráfica (`http://localhost:5001`) para visualizar status, logs e configurações.
*   **API Interna**: Endpoints para interagir com o sistema.

### `scheduler.py`
O "coração" da automação. Utiliza a biblioteca `schedule` para rodar tarefas periodicamente:
*   Verifica leads no Trello.
*   Envia mensagens de follow-up.
*   Sincroniza estados com Chatwoot.
*   Executa as funções de prospecção do `agent.py`.

### `agent.py`
Lógica de IA e prospecção.
*   Interage com LLMs (OpenAI).
*   Define prompts e fluxos de conversa.
*   Toma decisões baseadas no contexto do lead.

### `entrypoint.sh`
Script de inicialização do container Docker.
1.  Inicia a restauração de histórico (`restore_from_chatwoot.py`).
2.  Inicia o `scheduler.py` em background (com loop de reinício automático).
3.  Inicia o `server.py` em primeiro plano (mantendo o container ativo).

## 🔧 Variáveis de Ambiente (.env)

O sistema depende de várias variáveis de ambiente. Um exemplo de `.env`:

```ini
OPENAI_API_KEY=sk-...
CHATWOOT_API_URL=...
CHATWOOT_API_TOKEN=...
TRELLO_API_KEY=...
TRELLO_API_TOKEN=...
```

## 🐛 Troubleshooting

### Logs
*   O `scheduler.py` e `server.py` escrevem logs padrão.
*   Em caso de erro no Docker, use `docker logs agente_prospectador`.

### Banco de Dados
*   O arquivo `leads.db` armazena o estado local dos leads.
*   Ele é persistido via volume no Docker para não perder dados entre restarts.
