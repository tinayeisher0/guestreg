import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'visitor_kiosk.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        '''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            email TEXT,
            extension TEXT,
            is_active INTEGER DEFAULT 1,
            is_in_office INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            email TEXT,
            person_to_see_staff_id INTEGER,
            purpose TEXT,
            status TEXT DEFAULT 'IN',
            checkin_time TEXT,
            checkout_time TEXT,
            badge_number TEXT,
            notes TEXT,
            FOREIGN KEY(person_to_see_staff_id) REFERENCES staff(id)
        );

        CREATE TABLE IF NOT EXISTS staff_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            signin_time TEXT NOT NULL,
            signout_time TEXT,
            status TEXT DEFAULT 'OPEN',
            mode TEXT DEFAULT 'NORMAL',
            allowed_until TEXT,
            reminder_sent INTEGER DEFAULT 0,
            escalated_to_admin INTEGER DEFAULT 0,
            FOREIGN KEY(staff_id) REFERENCES staff(id)
        );

        CREATE TABLE IF NOT EXISTS contractor_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_title TEXT NOT NULL,
            issue_description TEXT,
            location TEXT,
            contractor_company TEXT,
            scheduled_for TEXT,
            status TEXT DEFAULT 'BOOKED',
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            invoice_file TEXT,
            admin_confirmation_note TEXT
        );

        CREATE TABLE IF NOT EXISTS contractor_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_name TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            email TEXT,
            job_id INTEGER,
            sign_in_time TEXT,
            sign_out_time TEXT,
            work_summary TEXT,
            status TEXT DEFAULT 'IN',
            attachment_file TEXT,
            FOREIGN KEY(job_id) REFERENCES contractor_jobs(id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS public_holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_date TEXT NOT NULL UNIQUE,
            label TEXT
        );

        CREATE TABLE IF NOT EXISTS afterhours_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            reason TEXT,
            approved_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(staff_id) REFERENCES staff(id)
        );

        CREATE TABLE IF NOT EXISTS report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_start TEXT,
            report_end TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            excel_file TEXT,
            pdf_file TEXT,
            emailed_to TEXT
        );

        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        '''
    )

    ensure_column(cur, 'staff', 'extension', 'TEXT')
    ensure_column(cur, 'admins', 'phone', 'TEXT')
    ensure_column(cur, 'staff_sessions', 'last_activity_at', 'TEXT')
    ensure_column(cur, 'staff_sessions', 'override_closed_by', 'TEXT')
    ensure_column(cur, 'staff_sessions', 'override_reason', 'TEXT')
    ensure_column(cur, 'staff_sessions', 'auto_logout_reason', 'TEXT')
    ensure_column(cur, 'staff_sessions', 'signout_method', 'TEXT')
    seed_defaults(cur)
    conn.commit()
    conn.close()


def ensure_column(cur, table, column, coltype):
    cols = [r['name'] for r in cur.execute(f'PRAGMA table_info({table})').fetchall()]
    if column not in cols:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {coltype}')


def seed_defaults(cur):
    cur.execute('SELECT COUNT(*) AS c FROM admins')
    if cur.fetchone()['c'] == 0:
        cur.execute(
            'INSERT INTO admins (username, pin, email, phone) VALUES (?, ?, ?, ?)',
            ('admin', '1234', 'admin@example.com', '+610400000000')
        )

    cur.execute('SELECT COUNT(*) AS c FROM staff')
    if cur.fetchone()['c'] == 0:
        staff_seed = [
            ('Sam Ncube', '1001', 'sam@example.com', '101', 1, 1),
            ('Donna K', '1002', 'donna@example.com', '102', 1, 1),
            ('Scott M', '1003', 'scott@example.com', '103', 1, 0),
            ('Nelly P', '1004', 'nelly@example.com', '104', 1, 1),
        ]
        cur.executemany(
            'INSERT INTO staff (full_name, code, email, extension, is_active, is_in_office) VALUES (?, ?, ?, ?, ?, ?)',
            staff_seed,
        )

    cur.execute('SELECT COUNT(*) AS c FROM contractor_jobs')
    if cur.fetchone()['c'] == 0:
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        jobs = [
            ('Aircon Service', 'Inspect and service reception air conditioner', 'Reception', 'CoolTech WA', now, 'BOOKED', 'admin'),
            ('CCTV Fault', 'Camera 3 offline near front gate', 'Front Gate', 'TJ Electrical & CCTV', now, 'BOOKED', 'admin'),
        ]
        cur.executemany(
            'INSERT INTO contractor_jobs (job_title, issue_description, location, contractor_company, scheduled_for, status, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)',
            jobs,
        )


def add_audit_log(event_type: str, actor: str, details: str):
    conn = get_connection()
    conn.execute(
        'INSERT INTO audit_logs (event_type, actor, details) VALUES (?, ?, ?)',
        (event_type, actor, details),
    )
    conn.commit()
    conn.close()


def add_alert(alert_type: str, target_type: str, target_id: int | None, message: str):
    conn = get_connection()
    conn.execute(
        'INSERT INTO alerts (alert_type, target_type, target_id, message) VALUES (?, ?, ?, ?)',
        (alert_type, target_type, target_id, message),
    )
    conn.commit()
    conn.close()
    add_audit_log('ALERT_CREATED', target_type or 'system', message)


def _row_to_dict(row):
    return dict(row) if row is not None else None


def query_all(sql: str, params=()):
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_one(sql: str, params=()):
    conn = get_connection()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return _row_to_dict(row)


def execute(sql: str, params=()):
    conn = get_connection()
    cur = conn.execute(sql, params)
    conn.commit()
    lastrowid = cur.lastrowid
    conn.close()
    return lastrowid


def execute_many(sql: str, params_seq):
    conn = get_connection()
    conn.executemany(sql, params_seq)
    conn.commit()
    conn.close()
