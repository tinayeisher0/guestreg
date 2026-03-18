from __future__ import annotations

from db import query_all, query_one, execute, add_audit_log
from notifications import notify_staff_overstay, escalate_to_admin
from utils import now_local, parse_dt, session_window_for_row, current_date_local


MIDNIGHT_RESET_KEY = 'last_midnight_reset_date'


def get_open_staff_sessions():
    return query_all(
        '''
        SELECT ss.*, s.full_name, s.email, s.extension
        FROM staff_sessions ss
        JOIN staff s ON s.id = ss.staff_id
        WHERE ss.status = 'OPEN'
        ORDER BY ss.signin_time DESC
        '''
    )


def _get_state(key: str) -> str | None:
    row = query_one('SELECT value FROM system_state WHERE key = ?', (key,))
    return row['value'] if row else None


def _set_state(key: str, value: str):
    existing = _get_state(key)
    if existing is None:
        execute('INSERT INTO system_state (key, value) VALUES (?, ?)', (key, value))
    else:
        execute('UPDATE system_state SET value = ? WHERE key = ?', (value, key))


def reset_open_sessions_at_midnight() -> int:
    today = current_date_local().isoformat()
    if _get_state(MIDNIGHT_RESET_KEY) == today:
        return 0

    open_sessions = get_open_staff_sessions()
    count = 0
    if open_sessions:
        now = now_local().isoformat(timespec='seconds')
        for sess in open_sessions:
            execute(
                '''UPDATE staff_sessions
                   SET status = ?, signout_time = ?, signout_method = ?, auto_logout_reason = ?, last_activity_at = ?
                   WHERE id = ? AND status = ?''',
                ('AUTO_LOGGED_OUT', now, 'SYSTEM_MIDNIGHT_RESET', 'Automatic midnight session clearance', now, sess['id'], 'OPEN')
            )
            add_audit_log('MIDNIGHT_RESET_LOGOUT', sess['full_name'], 'Session closed automatically at local midnight')
            count += 1
    _set_state(MIDNIGHT_RESET_KEY, today)
    return count


def process_staff_session_rules() -> dict:
    reset_count = reset_open_sessions_at_midnight()
    open_sessions = get_open_staff_sessions()
    admin = query_one('SELECT * FROM admins ORDER BY id LIMIT 1')
    now = now_local()
    reminder_count = 0
    auto_logout_count = 0

    for sess in open_sessions:
        remind_at, logout_at = session_window_for_row(sess, now)
        if logout_at and now >= logout_at:
            execute(
                '''UPDATE staff_sessions
                   SET status = ?, signout_time = ?, signout_method = ?, auto_logout_reason = ?, last_activity_at = ?
                   WHERE id = ? AND status = ?''',
                ('AUTO_LOGGED_OUT', now.isoformat(timespec='seconds'), 'SYSTEM_TIMEOUT', 'Automatic timeout based on roster rules', now.isoformat(timespec='seconds'), sess['id'], 'OPEN')
            )
            add_audit_log('AUTO_LOGOUT', sess['full_name'], f"Automatic timeout. Mode={sess.get('mode')}")
            auto_logout_count += 1
            continue

        if remind_at and now >= remind_at and not sess.get('reminder_sent'):
            notify_staff_overstay(sess['staff_id'], sess['full_name'], sess.get('email'))
            execute('UPDATE staff_sessions SET reminder_sent = 1 WHERE id = ?', (sess['id'],))
            reminder_count += 1
            continue

        if logout_at and now >= logout_at and sess.get('reminder_sent') and not sess.get('escalated_to_admin'):
            # kept for completeness, though auto-logout usually happens first
            escalate_to_admin(admin['email'] if admin else None, sess['full_name'], admin['phone'] if admin else None)
            execute('UPDATE staff_sessions SET escalated_to_admin = 1 WHERE id = ?', (sess['id'],))

    return {
        'midnight_resets': reset_count,
        'reminders': reminder_count,
        'auto_logouts': auto_logout_count,
    }
