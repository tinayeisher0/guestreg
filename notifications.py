import os
import smtplib
from email.mime.text import MIMEText
from db import add_alert, add_audit_log


def send_email_notification(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    host = os.getenv('SMTP_HOST')
    port = os.getenv('SMTP_PORT')
    username = os.getenv('SMTP_USERNAME')
    password = os.getenv('SMTP_PASSWORD')
    sender = os.getenv('SMTP_SENDER', username or 'noreply@example.com')

    if not all([host, port, username, password]) or not to_email:
        return False, 'SMTP not configured or recipient missing. Alert stored in app only.'

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to_email

    try:
        with smtplib.SMTP(host, int(port)) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(sender, [to_email], msg.as_string())
        return True, 'Email sent successfully.'
    except Exception as exc:
        return False, f'Email failed: {exc}'


def send_sms_notification(to_phone: str, body: str) -> tuple[bool, str]:
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_FROM_NUMBER')
    if not all([sid, token, from_number, to_phone]):
        return False, 'SMS not configured. Alert stored in app only.'
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_number, to=to_phone)
        return True, 'SMS sent successfully.'
    except Exception as exc:
        return False, f'SMS failed: {exc}'


def notify_staff_visit(staff_id: int, staff_name: str, staff_email: str | None, visitor_name: str):
    message = f'{visitor_name} is at the front desk waiting to see {staff_name}.'
    add_alert('VISITOR_ARRIVAL', 'staff', staff_id, message)
    ok, detail = send_email_notification(staff_email or '', 'Visitor waiting at front desk', message)
    add_audit_log('NOTIFICATION', staff_name, detail)


def notify_staff_overstay(staff_id: int, staff_name: str, staff_email: str | None, staff_phone: str | None = None):
    message = f'{staff_name} is still signed in after the allowed time. Please log out or contact admin.'
    add_alert('STAFF_OVERSTAY', 'staff', staff_id, message)
    ok1, detail1 = send_email_notification(staff_email or '', 'Please log out from building kiosk', message)
    ok2, detail2 = send_sms_notification(staff_phone or '', message)
    add_audit_log('NOTIFICATION', staff_name, f'{detail1} | {detail2}')


def escalate_to_admin(admin_email: str | None, staff_name: str, admin_phone: str | None = None):
    message = f'Admin attention required: {staff_name} has not logged out after reminder.'
    add_alert('ADMIN_ESCALATION', 'admin', None, message)
    ok1, detail1 = send_email_notification(admin_email or '', 'Staff logout escalation', message)
    ok2, detail2 = send_sms_notification(admin_phone or '', message)
    add_audit_log('NOTIFICATION', 'admin', f'{detail1} | {detail2}')


def notify_remaining_staff_confirmation(staff_id: int, staff_name: str, staff_email: str | None, extension: str | None, departed_staff_name: str):
    message = (
        f"{departed_staff_name} has logged out. You are still recorded as being in the building. "
        f"Please confirm you are still on site or use the kiosk to log out if you have already left. "
        f"Your extension is {extension or 'N/A'}."
    )
    add_alert('REMAINING_STAFF_CONFIRM', 'staff', staff_id, message)
    ok, detail = send_email_notification(staff_email or '', 'Please confirm you are still in the building', message)
    add_audit_log('NOTIFICATION', staff_name, detail)
