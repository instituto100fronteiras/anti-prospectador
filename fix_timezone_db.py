from database import get_db_connection
from datetime import datetime, timedelta

def fix_times():
    print("🕵️ Verificando timestamps no futuro (Legado UTC)...")
    conn = get_db_connection()
    now_br = datetime.now()
    
    # Tolerancia de 5 minutos
    future_threshold = now_br + timedelta(minutes=5)
    
    # 1. Select candidates
    cursor = conn.execute("SELECT id, phone, last_contact_date FROM leads")
    leads = cursor.fetchall()
    
    count_fixed = 0
    for row in leads:
        try:
            # Timestamp format: YYYY-MM-DD HH:MM:SS.mL or similar
            ts_str = row['last_contact_date']
            if not ts_str: continue
            
            # Simple parse (SQLite handles standard formats well)
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
            except:
                ts = datetime.strptime(ts_str.split('.')[0], "%Y-%m-%d %H:%M:%S")

            if ts > future_threshold:
                # Found a future date (UTC ghost)
                new_ts = ts - timedelta(hours=3)
                print(f"🔧 Corrigindo {row['phone']}: {ts} -> {new_ts}")
                
                conn.execute("UPDATE leads SET last_contact_date = ? WHERE id = ?", (new_ts, row['id']))
                count_fixed += 1
        except Exception as e:
            print(f"Erro ao processar {row['phone']}: {e}")

    conn.commit()
    conn.close()
    
    if count_fixed > 0:
        print(f"✅ Sucesso: {count_fixed} timestamps corrigidos de UTC para BRT.")
    else:
        print("✅ Nenhum timestamp incorreto encontrado.")

if __name__ == "__main__":
    fix_times()
