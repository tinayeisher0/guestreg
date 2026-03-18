from pathlib import Path
from datetime import timedelta
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from db import query_all, execute, query_one, add_audit_log
from notifications import send_email_notification
from utils import now_local, fmt_dt, parse_dt, app_timezone_name

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / 'reports'
REPORT_DIR.mkdir(exist_ok=True)


def _to_df(rows, mapping):
    return pd.DataFrame([{k: row.get(v) for k, v in mapping.items()} for row in rows])


def generate_weekly_reports(force=False):
    now = now_local()
    last = query_one('SELECT * FROM report_history ORDER BY created_at DESC LIMIT 1')
    if last and not force:
        last_created = parse_dt(last['created_at'])
        if last_created and now - last_created < timedelta(days=7):
            return None

    report_end = now
    report_start = now - timedelta(days=7)
    s, e = report_start.isoformat(timespec='seconds'), report_end.isoformat(timespec='seconds')

    visitors = query_all('SELECT * FROM visitors WHERE checkin_time >= ? AND checkin_time <= ? ORDER BY checkin_time DESC', (s, e))
    staff = query_all('''SELECT ss.*, st.full_name FROM staff_sessions ss JOIN staff st ON st.id = ss.staff_id
                         WHERE signin_time >= ? AND signin_time <= ? ORDER BY signin_time DESC''', (s, e))
    contractors = query_all('''SELECT cv.*, cj.job_title FROM contractor_visits cv LEFT JOIN contractor_jobs cj ON cj.id = cv.job_id
                               WHERE sign_in_time >= ? AND sign_in_time <= ? ORDER BY sign_in_time DESC''', (s, e))
    alerts = query_all('SELECT * FROM alerts WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC', (s, e))

    stamp = now.strftime('%Y%m%d_%H%M%S')
    excel_path = REPORT_DIR / f'audit_report_{stamp}.xlsx'
    pdf_path = REPORT_DIR / f'audit_report_{stamp}.pdf'

    with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
        _to_df(visitors, {'Visitor':'full_name','Company':'company','Host Staff ID':'person_to_see_staff_id','Check In':'checkin_time','Check Out':'checkout_time','Status':'status'}).to_excel(writer, sheet_name='Visitors', index=False)
        _to_df(staff, {'Staff':'full_name','Sign In':'signin_time','Sign Out':'signout_time','Allowed Until':'allowed_until','Mode':'mode','Status':'status','Signout Method':'signout_method','System Reason':'auto_logout_reason'}).to_excel(writer, sheet_name='Staff Sessions', index=False)
        _to_df(contractors, {'Contractor':'contractor_name','Company':'company','Job':'job_title','In':'sign_in_time','Out':'sign_out_time','Status':'status'}).to_excel(writer, sheet_name='Contractors', index=False)
        _to_df(alerts, {'Type':'alert_type','Message':'message','Created':'created_at'}).to_excel(writer, sheet_name='Alerts', index=False)

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont('Helvetica-Bold', 16)
    c.drawString(50, y, 'Embrace Weekly Audit Report')
    y -= 24
    c.setFont('Helvetica', 10)
    c.drawString(50, y, f'Period: {fmt_dt(s)} to {fmt_dt(e)} ({app_timezone_name()})')
    y -= 30
    summary = [
        f'Visitors signed in: {len(visitors)}',
        f'Staff sessions: {len(staff)}',
        f'Contractor visits: {len(contractors)}',
        f'Alerts raised: {len(alerts)}',
    ]
    for line in summary:
        c.drawString(50, y, line)
        y -= 18
    y -= 10
    c.setFont('Helvetica-Bold', 12)
    c.drawString(50, y, 'Recent alerts')
    y -= 18
    c.setFont('Helvetica', 9)
    for row in alerts[:12]:
        c.drawString(50, y, f"- {row['alert_type']}: {row['message'][:90]}")
        y -= 14
        if y < 60:
            c.showPage()
            y = height - 50
            c.setFont('Helvetica', 9)
    c.save()

    admin = query_one('SELECT * FROM admins ORDER BY id LIMIT 1')
    emailed_to = admin['email'] if admin else None
    if emailed_to:
        send_email_notification(
            emailed_to,
            'Weekly audit report',
            f'Weekly report generated in {app_timezone_name()}. Excel: {excel_path.name} | PDF: {pdf_path.name}'
        )

    execute(
        'INSERT INTO report_history (report_start, report_end, excel_file, pdf_file, emailed_to) VALUES (?, ?, ?, ?, ?)',
        (s, e, str(excel_path.relative_to(BASE_DIR)), str(pdf_path.relative_to(BASE_DIR)), emailed_to)
    )
    add_audit_log('WEEKLY_REPORT', 'system', f'Generated report {excel_path.name}')
    return {'excel': excel_path, 'pdf': pdf_path}
