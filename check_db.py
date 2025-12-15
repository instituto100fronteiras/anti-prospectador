import sqlite3
import os

files = ["leads.db", "data/leads.db"]
target_phone = "5545999831200"

print(f"Searching for {target_phone}...")

for db_file in files:
    if not os.path.exists(db_file):
        print(f"❌ {db_file}: File not found")
        continue
        
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        
        # Check table
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'").fetchone()
        if not tables:
             print(f"⚠️ {db_file}: Table 'leads' not found. (Empty DB?)")
             conn.close()
             continue
             
        # Check lead
        lead = conn.execute("SELECT * FROM leads WHERE phone = ?", (target_phone,)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        
        print(f"📂 {db_file}:")
        print(f"   Total Leads: {count}")
        if lead:
            print(f"   ✅ TARGET FOUND! Status: {lead['status']}")
            print(f"   Name: {lead['name']}")
            print(f"   Histórico len: {len(lead['conversation_history'] or '')}")
        else:
            print(f"   ❌ Target NOT found.")
            print("   Listing all phones in DB:")
            all_leads = conn.execute("SELECT phone, name FROM leads").fetchall()
            print(f"   Listing {len(all_leads)} leads:")
            for l in all_leads:
                print(f"   - '{l['phone']}' ({l['name']})")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ {db_file}: Error - {e}")
