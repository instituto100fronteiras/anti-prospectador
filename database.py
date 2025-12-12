import sqlite3
import os
from datetime import datetime

# Determine DB path provided by env or default to local data dir
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_NAME = os.path.join(DATA_DIR, "leads.db")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            address TEXT,
            website TEXT,
            rating REAL,
            reviews INTEGER,
            types TEXT,
            status TEXT DEFAULT 'new',
            last_contact_date TIMESTAMP,
            next_contact_date TIMESTAMP,
            follow_up_stage INTEGER DEFAULT 0,
            conversation_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(phone)
        )
    ''')
    
    # Migration: Add columns if they don't exist (for existing db)
    try:
        c.execute('ALTER TABLE leads ADD COLUMN next_contact_date TIMESTAMP')
    except sqlite3.OperationalError:
        pass # Column likely exists
        
    try:
        c.execute('ALTER TABLE leads ADD COLUMN follow_up_stage INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass # Column likely exists

    try:
        c.execute('ALTER TABLE leads ADD COLUMN prompt_version TEXT')
    except sqlite3.OperationalError:
        pass # Column likely exists

    try:
        c.execute('ALTER TABLE leads ADD COLUMN search_term TEXT')
    except sqlite3.OperationalError:
        pass # Column likely exists

    try:
        c.execute('ALTER TABLE leads ADD COLUMN language TEXT')
    except sqlite3.OperationalError:
        pass # Column likely exists
        
    conn.commit()
    conn.close()

def update_lead_prompt_version(phone, version):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE leads SET prompt_version = ? WHERE phone = ?', (version, phone))
    conn.commit()
    conn.close()

def add_lead(lead_data):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO leads (name, phone, address, website, rating, reviews, types, search_term, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_data.get('name'),
            lead_data.get('phone'),
            lead_data.get('address'),
            lead_data.get('website'),
            lead_data.get('rating'),
            lead_data.get('reviews'),
            lead_data.get('types'),
            lead_data.get('search_term'),
            lead_data.get('language')
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_lead_by_phone(phone):
    conn = get_db_connection()
    lead = conn.execute('SELECT * FROM leads WHERE phone = ?', (phone,)).fetchone()
    conn.close()
    return lead

def update_lead_status(phone, status, message=None):
    conn = get_db_connection()
    c = conn.cursor()
    if message:
        c.execute('''
            UPDATE leads 
            SET status = ?, last_contact_date = ?, conversation_history = COALESCE(conversation_history, '') || ? || '\n'
            WHERE phone = ?
        ''', (status, datetime.now(), message, phone))
    else:
        c.execute('''
            UPDATE leads 
            SET status = ?, last_contact_date = ?
            WHERE phone = ?
        ''', (status, datetime.now(), phone))
    conn.commit()
    conn.close()

def get_dashboard_stats():
    conn = get_db_connection()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # KPIs
    new_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE date(created_at) = ?", (today,)).fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM leads WHERE status IN ('contacted', 'follow_up_1', 'follow_up_2') AND date(last_contact_date) = ?", (today,)).fetchone()[0]
    # Responses logic might need tuning based on actual status usage
    responses = conn.execute("SELECT COUNT(*) FROM leads WHERE status IN ('responded', 'connected') AND date(last_contact_date) = ?", (today,)).fetchone()[0]
    
    conn.close()
    return {
        "new_leads": new_leads,
        "sent": sent,
        "responses": responses
    }

def get_hot_leads(limit=5):
    conn = get_db_connection()
    leads = conn.execute("""
        SELECT * FROM leads 
        WHERE status IN ('responded', 'connected')
        ORDER BY last_contact_date DESC 
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in leads]

def get_recent_activity(limit=10, offset=0):
    conn = get_db_connection()
    leads = conn.execute("""
         SELECT * FROM leads 
         WHERE last_contact_date IS NOT NULL
         ORDER BY last_contact_date DESC 
         LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    return [dict(row) for row in leads]

def get_all_leads():
    conn = get_db_connection()
    leads = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in leads]

def get_analytics_data():
    conn = get_db_connection()
    # Group by prompt_version
    # Ensure prompt_version column exists (it should via init_db)
    try:
        rows = conn.execute("""
            SELECT 
                prompt_version, 
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('responded', 'connected') THEN 1 ELSE 0 END) as responded
            FROM leads 
            WHERE prompt_version IS NOT NULL
            GROUP BY prompt_version
        """).fetchall()
    except:
        rows = []
        
    conn.close()
    
    data = []
    for r in rows:
        total = r['total']
        resp = r['responded']
        conv = round((resp / total * 100), 1) if total > 0 else 0
        data.append({
            "prompt_version": r['prompt_version'],
            "enviados": total,
            "respostas": resp,
            "conversao": conv
        })
    return data
