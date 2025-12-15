# 🐍 Python Agent Documentation

Esta pasta contém o núcleo do sistema Agente Prospectador.

## 🚀 Estratégia de Deploy (Produção)

**RECOMENDAÇÃO: Rode o sistema APENAS no Easypanel em Produção.**

O ambiente local deve ser usado apenas para desenvolvimento e testes pontuais. Rodar localmente e em produção simultaneamente pode causar conflitos de concorrência e duplicidade de mensagens.

### Atualização no Easypanel
Sempre que houver mudanças no código (push para `main`):
1.  Acesse o Easypanel.
2.  Vá em **Deployments**.
3.  Clique em **Deploy** ou **Rebuild** para puxar a versão mais recente.

> [!IMPORTANT]
> **Configuração Crítica**: Certifique-se de que a variável `CHATWOOT_URL` no Easypanel aponta para a raiz da API, SEM sufixos.
>
> *   ✅ Correto: `https://chatwoot.seudominio.com`
> *   ❌ Incorreto: `https://chatwoot.seudominio.com/app/accounts/1/conversations` (Isso quebrará o sync!)

---

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
    *   Caminho correto do volume: `./data:/app/data`

---

## 📜 Histórico de Correções Recentes (Dez 2025)

### 1. Correção de Ignorância de Histórico
*   **Problema**: Agente ignorava conversas passadas e enviava mensagens de introdução repetidas.
*   **Solução**:
    *   `scheduler.py`: Forçado envio contextual sempre que houver histórico, independente do motivo do contato.
    *   `chatwoot_api.py`: Busca de contato melhorada para tentar formatos com e sem `+`.
    *   `agent.py`: Prompt atualizado para PROIBIR explicitamente re-apresentações se houver histórico.

### 2. Sincronização Chatwoot -> Trello
*   **Problema**: Mensagens não estavam indo para o Trello.
*   **Solução**:
    *   Identificado que o processo `scheduler.py` estava parado. Restart do sistema resolveu.
    *   Corrigido `CHATWOOT_URL` no `.env` que estava apontando para URL de navegador, bloqueando a API.

### 3. Alinhamento de Banco de Dados
*   **Problema**: Ambiente local usava `leads.db` na raiz, enquanto Easypanel esperava em `data/leads.db`.
*   **Solução**: Padronizado para usar sempre `data/leads.db` e atualizado `docker-compose.yml` para montar o volume corretamente.
