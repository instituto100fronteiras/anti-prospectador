#!/bin/bash
echo "🚀 Iniciando Agente Prospectador em Segundo Plano..."

# Kill existing instances to avoid duplicates
pkill -f scheduler.py
pkill -f server.py
pkill -f dashboard.py

# Start Server (Webhook)
nohup python3 server.py > server.log 2>&1 &
echo "✅ Servidor (Webhook) iniciado (PID $!)"

# Start Scheduler (Automation)
nohup python3 scheduler.py > scheduler.log 2>&1 &
echo "✅ Agendador (Scheduler) iniciado (PID $!)"

# Start Dashboard
nohup streamlit run dashboard.py > dashboard.log 2>&1 &
echo "✅ Dashboard iniciado (PID $!)"

echo ""
echo "🎉 Tudo rodando! Você pode fechar este terminal agora."
echo "Para parar tudo depois, use: pkill -f python"
echo "Acesse o Dashboard em: http://localhost:8501"
