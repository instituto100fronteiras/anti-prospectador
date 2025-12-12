#!/bin/bash
echo "🚀 Iniciando Sistema Stitch (Agente + Painel)..."

# 1. Kill potential duplicates
echo "🧹 Limpando processos antigos..."
pkill -f "python3 server.py"
pkill -f "python3 scheduler.py"
pkill -f "streamlit run dashboard.py"

# Wait a moment for ports to free up
sleep 2

# 2. Start Flask Server (The new Dashboard & Webhook Receiver)
echo "🔌 Iniciando Painel & Webhook (server.py)..."
nohup python3 server.py > server.log 2>&1 &
SERVER_PID=$!
echo "   PID: $SERVER_PID"

# 3. Start Scheduler (The Robot)
echo "🤖 Iniciando Robô de Prospecção (scheduler.py)..."
nohup python3 scheduler.py > scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo "   PID: $SCHEDULER_PID"

echo ""
echo "✅ Sistema Ativo!"
echo "   - Painel: http://localhost:5001"
echo "   - Logs do Servidor: server.log"
echo "   - Logs do Robô: scheduler.log"
echo ""
echo "Para parar tudo: pkill -f python3"
