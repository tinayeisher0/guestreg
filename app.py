from pathlib import Path
from datetime import datetime, date, time as dt_time
import io
import base64
import shutil

import pandas as pd
import qrcode
import streamlit as st
import streamlit.components.v1 as components

from db import init_db, query_all, query_one, execute, add_audit_log
from notifications import notify_staff_visit, notify_staff_overstay, escalate_to_admin, notify_remaining_staff_confirmation
from reports import generate_weekly_reports
from utils import (
    now_local,
    is_business_hours,
    allowed_until_for_signin,
    fmt_dt,
    parse_dt,
    building_status,
    is_public_holiday,
    get_active_booking,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'uploads'
INVOICE_DIR = UPLOAD_DIR / 'invoices'
DOC_DIR = UPLOAD_DIR / 'contractor_docs'
BADGE_DIR = UPLOAD_DIR / 'badges'
QR_DIR = UPLOAD_DIR / 'staff_qr'
ASSET_DIR = BASE_DIR / 'assets'
LOGO_PATH = ASSET_DIR / 'logo.png'
INACTIVITY_SECONDS = 90
HOME_REFRESH_SECONDS = 180

st.set_page_config(page_title='Embrace Kiosk', layout='wide', initial_sidebar_state='collapsed')
init_db()
for p in [INVOICE_DIR, DOC_DIR, BADGE_DIR, QR_DIR, ASSET_DIR]:
    p.mkdir(parents=True, exist_ok=True)



def bootstrap_state():
    st.session_state.setdefault('page', 'home')
    st.session_state.setdefault('admin_logged_in', False)
    st.session_state.setdefault('last_activity_ts', datetime.now().timestamp())


def register_activity(page_name: str):
    st.session_state['last_activity_ts'] = datetime.now().timestamp()
    st.session_state['last_page_rendered'] = page_name



def check_inactivity():
    now_ts = datetime.now().timestamp()
    last_ts = st.session_state.get('last_activity_ts', now_ts)
    page = st.session_state.get('page', 'home')
    timeout = INACTIVITY_SECONDS if page != 'home' else HOME_REFRESH_SECONDS
    if now_ts - last_ts > timeout and page != 'home':
        st.session_state['page'] = 'home'
        st.session_state['flash_banner'] = {
            'color': '#0f766e',
            'text': 'Session timed out. Kiosk has returned to the home screen.'
        }



def inject_watchdog(seconds: int):
    components.html(
        f"""
        <script>
        (function() {{
          const timeoutMs = {seconds} * 1000;
          let timer;
          function resetTimer() {{
            clearTimeout(timer);
            timer = setTimeout(() => {{
              window.parent.location.reload();
            }}, timeoutMs);
          }}
          ['click','touchstart','keydown','mousemove'].forEach(evt => {{
            window.parent.document.addEventListener(evt, resetTimer, {{passive:true}});
          }});
          resetTimer();
        }})();
        </script>
        """,
        height=0,
    )



def load_css():
    st.markdown(
        '''
        <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] {display:none !important;}
        header {visibility:hidden;}
        .block-container {max-width: 980px; padding-top: 0.2rem; padding-bottom: 0.8rem;}
        .stApp {
            background: linear-gradient(180deg, #fbfbfb 0%, #f7f7f7 100%);
        }
        .panel, .glass, .hero-box {
            background: rgba(255,255,255,0.97);
            border: 1px solid #ececec;
            border-radius: 28px;
            box-shadow: 0 20px 45px rgba(0,0,0,0.06);
        }
        .panel {padding: 1rem 1rem 0.95rem 1rem;}
        .hero-box {padding: 1.1rem;}
        .compact-title {font-size: 1.35rem; font-weight: 800; color: #222; margin-bottom: 0.2rem; text-align:center;}
        .muted {color:#707070; text-align:center; font-size:0.96rem;}
        .logo-zone {display:flex; justify-content:center; align-items:center; width:100%; margin: 0.2rem 0 0.15rem 0;}
        .logo-zone img {display:block; margin:0 auto; object-fit:contain;}
        .welcome-label {color:#111111 !important; text-align:center; font-size:1.45rem; font-weight:800; margin:0.1rem 0 0.55rem 0;}
        .banner {
            border-radius: 28px;
            padding: 1.25rem 1rem;
            color: white;
            text-align: center;
            font-weight: 900;
            font-size: 1.8rem;
            line-height: 1.2;
            margin: 0.6rem 0 0.8rem 0;
            box-shadow: 0 14px 32px rgba(0,0,0,0.16);
        }
        .banner-sub {
            margin-top: 0.6rem;
            font-size: 1rem;
            font-weight: 700;
            opacity: 0.98;
        }
        .message-card {
            border-radius: 26px;
            padding: 1.4rem 1.15rem;
            text-align:center;
            font-weight:800;
            font-size:1.55rem;
            margin: 0.8rem 0 0.9rem 0;
            box-shadow: 0 12px 26px rgba(0,0,0,0.12);
        }
        .message-card p {font-size: 1.02rem; font-weight: 600; margin-top: 0.45rem;}
        .msg-red {background: linear-gradient(180deg, #ef4444, #b91c1c); color:white;}
        .msg-green {background: linear-gradient(180deg, #22c55e, #15803d); color:white;}
        .msg-orange {background: linear-gradient(180deg, #fb923c, #ea580c); color:white;}
        .kiosk-btn button {
            min-height: 64px !important;
            border-radius: 999px !important;
            background: linear-gradient(180deg, #ff7a3a, #ff6430) !important;
            border: 0 !important;
            color: #ffffff !important;
            font-size: 1rem !important;
            font-weight: 800 !important;
            box-shadow: 0 10px 25px rgba(255,100,48,0.28) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .kiosk-btn button *,
        .stButton button *,
        .soft-btn button *,
        button[kind=primary] *,
        button[kind=secondary] * {
            color:#ffffff !important;
            opacity:1 !important;
            visibility:visible !important;
            -webkit-text-fill-color:#ffffff !important;
        }
        .stButton button, .soft-btn button, button[kind=primary], button[kind=secondary] {
            color:#ffffff !important;
            opacity:1 !important;
            visibility:visible !important;
            -webkit-text-fill-color:#ffffff !important;
            text-shadow:none !important;
        }
        .soft-btn button {
            border-radius: 18px !important;
            min-height: 52px !important;
            font-weight: 700 !important;
        }
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stTextArea textarea {
            border-radius: 16px !important;
            min-height: 52px;
            color: #111111 !important;
            background: #ffffff !important;
        }
        .stTextInput input::placeholder, .stTextArea textarea::placeholder {
            color: #6b7280 !important;
            opacity: 1 !important;
        }
        .stSelectbox div[data-baseweb="select"] span,
        .stTextInput label,
        .stTextArea label,
        .stSelectbox label,
        .stDateInput label,
        .stTimeInput label,
        .stFileUploader label,
        .stCheckbox label,
        .stRadio label,
        .stNumberInput label,
        .stMultiSelect label,
        .stMarkdown,
        p, li, h1, h2, h3, h4, h5, h6 {
            color: #111111 !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }
        .stTabs [data-baseweb="tab"] {
            color: #111111 !important;
            background: #f3f4f6 !important;
            border-radius: 14px 14px 0 0 !important;
            font-weight: 700 !important;
            border-bottom: 3px solid transparent !important;
        }
        .stTabs [aria-selected="true"] {
            color: #ea580c !important;
            background: #ffffff !important;
            border-bottom: 3px solid #ea580c !important;
        }
        .stFileUploader section {
            border-radius: 18px !important;
        }
        .small-note {text-align:center; color:#8c8c8c; font-size:0.82rem; margin-top:0.35rem;}
        .gallery-manager-card {background:#fff; border:1px solid #ececec; border-radius:22px; padding:0.75rem; box-shadow:0 8px 22px rgba(0,0,0,0.05);}
        .gallery-label {font-size:0.9rem; font-weight:700; color:#111; text-align:center; margin-top:0.35rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .gallery-help {color:#525252; font-size:0.92rem; margin-bottom:0.45rem;}
        .qr-center-container {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center !important;
            justify-content: center;
            text-align: center;
            margin-top: 0.3rem;
            margin-bottom: 0.05rem;
        }
        .qr-title {
            color: #111111 !important;
            font-size: 0.82rem;
            font-weight: 800;
            text-align: center;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.4rem;
        }
        .qr-image {
            width: 138px;
            border-radius: 18px;
            background: #ffffff;
            padding: 10px;
            box-shadow: 0 10px 24px rgba(0,0,0,0.22);
            display: block;
            margin: 0 auto;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )



def image_to_data_uri(path: Path) -> str:
    mime = 'image/png'
    if path.suffix.lower() in ['.jpg', '.jpeg']:
        mime = 'image/jpeg'
    elif path.suffix.lower() == '.webp':
        mime = 'image/webp'
    data = base64.b64encode(path.read_bytes()).decode('utf-8')
    return f'data:{mime};base64,{data}'



def save_uploaded_file(uploaded_file, target_dir: Path):
    if not uploaded_file:
        return None
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_file.name}"
    filepath = target_dir / filename
    with open(filepath, 'wb') as f:
        f.write(uploaded_file.getbuffer())
    return str(filepath.relative_to(BASE_DIR))



def qr_png_bytes(payload: str):
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def infer_runtime_url() -> str | None:
    try:
        headers = getattr(st, 'context', None).headers
        host = headers.get('Host') or headers.get('host')
        proto = headers.get('X-Forwarded-Proto') or headers.get('x-forwarded-proto') or 'https'
        if host:
            return f'{proto}://{host}'
    except Exception:
        pass
    return None


def get_home_qr_url() -> str:
    inferred = infer_runtime_url()
    if inferred:
        return inferred
    return 'http://localhost:8501'


def render_home_qr():
    public_url = get_home_qr_url()
    qr_bytes = qr_png_bytes(public_url)
    qr_b64 = base64.b64encode(qr_bytes).decode('utf-8')
    st.markdown(
        f"""
        <div class="qr-center-container">
            <div class="qr-title">Access From Mobile</div>
            <img src="data:image/png;base64,{qr_b64}" class="qr-image">
        </div>
        """,
        unsafe_allow_html=True,
    )



def show_logo(width=240):
    if LOGO_PATH.exists():
        data_uri = image_to_data_uri(LOGO_PATH)
        st.markdown(
            f"<div class='logo-zone'><img src='{data_uri}' style='width:{width}px; max-width:72vw; height:auto; display:block; margin:0 auto;'></div>",
            unsafe_allow_html=True,
        )



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


def session_is_after_hours(session_row):
    return session_row.get('mode') in ('AFTER_HOURS_15_MIN', 'BOOKED_EXTENDED')


def session_is_stale(session_row):
    reference = parse_dt(session_row.get('last_activity_at')) or parse_dt(session_row.get('signin_time'))
    if not reference:
        return False
    if session_is_after_hours(session_row):
        return now_local() > reference.replace(second=0, microsecond=0) and (now_local() - reference).total_seconds() > 15 * 60
    return (now_local() - reference).total_seconds() > 8 * 60 * 60


def auto_logout_expired_afterhours_sessions():
    open_sessions = get_open_staff_sessions()
    now = now_local()
    changed = 0
    for sess in open_sessions:
        if not session_is_after_hours(sess):
            continue
        allowed_until = parse_dt(sess.get('allowed_until'))
        if allowed_until and now > allowed_until:
            execute(
                'UPDATE staff_sessions SET status = ?, signout_time = ?, auto_logout_reason = ? WHERE id = ? AND status = ?',
                ('AUTO_LOGGED_OUT', now.isoformat(timespec='seconds'), 'After-hours inactivity timeout', sess['id'], 'OPEN')
            )
            add_audit_log('AUTO_LOGOUT', sess['full_name'], 'After-hours inactivity timeout')
            changed += 1
    if changed:
        st.session_state['flash_banner'] = {'class': 'msg-orange', 'title': 'After-hours session closed', 'text': 'Expired after-hours sessions were logged out automatically.'}



def get_open_visitor_sessions():
    return query_all(
        '''
        SELECT v.*, s.full_name AS staff_name
        FROM visitors v
        LEFT JOIN staff s ON s.id = v.person_to_see_staff_id
        WHERE v.status = 'IN'
        ORDER BY v.checkin_time DESC
        '''
    )



def get_open_contractor_visits():
    return query_all(
        '''
        SELECT cv.*, cj.job_title
        FROM contractor_visits cv
        LEFT JOIN contractor_jobs cj ON cj.id = cv.job_id
        WHERE cv.status = 'IN'
        ORDER BY cv.sign_in_time DESC
        '''
    )



def check_overstays():
    auto_logout_expired_afterhours_sessions()
    open_sessions = get_open_staff_sessions()
    admin = query_one('SELECT * FROM admins ORDER BY id LIMIT 1')
    now = now_local()
    for sess in open_sessions:
        allowed_until = parse_dt(sess['allowed_until'])
        if not allowed_until:
            continue
        if now > allowed_until and not sess['reminder_sent']:
            notify_staff_overstay(sess['staff_id'], sess['full_name'], sess['email'])
            execute('UPDATE staff_sessions SET reminder_sent = 1 WHERE id = ?', (sess['id'],))
        elif now > allowed_until and sess['reminder_sent'] and not sess['escalated_to_admin']:
            if now > allowed_until.replace(second=0, microsecond=0):
                escalate_to_admin(admin['email'] if admin else None, sess['full_name'], admin['phone'] if admin else None)
                execute('UPDATE staff_sessions SET escalated_to_admin = 1 WHERE id = ?', (sess['id'],))



def render_flash_banner():
    flash = st.session_state.pop('flash_banner', None)
    if flash:
        st.markdown(
            f"<div class='message-card {flash.get('class','msg-orange')}'>{flash['title']}<p>{flash.get('text','')}</p></div>",
            unsafe_allow_html=True,
        )



def occupancy_banner(open_rows=None):
    if open_rows is None:
        open_rows = get_open_staff_sessions()
    state, color, message = building_status(open_rows)
    if open_rows:
        lines = ' • '.join([f"{r['full_name']} (ext {r['extension'] or 'N/A'})" for r in open_rows[:5]])
        sub = 'Please wait here so the staff member can respond, or call them using the extension shown below.'
        st.markdown(
            f"<div class='banner' style='background:{color};'>{message}<div class='banner-sub'>{sub}<br>{lines}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='banner' style='background:linear-gradient(180deg,#22c55e,#15803d);'>Thank you. No one is in the building.<div class='banner-sub'>Please lock doors and arm the alarm.</div></div>",
            unsafe_allow_html=True,
        )



def home_screen():
    register_activity('home')
    show_logo(500)
    st.markdown("<div class='welcome-label'>Welcome to Embrace</div>", unsafe_allow_html=True)
    render_flash_banner()
    r1 = st.columns(2)
    with r1[0]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Visitor Sign In', use_container_width=True, key='visitor_home'):
            st.session_state['page'] = 'visitor'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with r1[1]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Staff', use_container_width=True, key='staff_home'):
            st.session_state['page'] = 'staff_choice'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    r2 = st.columns(2)
    with r2[0]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Contractor', use_container_width=True, key='contractor_home'):
            st.session_state['page'] = 'contractor'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with r2[1]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Admin', use_container_width=True, key='admin_home'):
            st.session_state['page'] = 'admin_login'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>{now_local().strftime('%A %d %b %Y • %I:%M %p')}</div>", unsafe_allow_html=True)
    render_home_qr()



def back_home_button():
    st.markdown("<div class='soft-btn'>", unsafe_allow_html=True)
    if st.button('Home', use_container_width=True):
        st.session_state['page'] = 'home'
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)



def staff_choice():
    register_activity('staff_choice')
    show_logo(220)
    render_flash_banner()
    cols = st.columns(2)
    with cols[0]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Staff Login', use_container_width=True, key='staff_in_btn'):
            st.session_state['page'] = 'staff_in'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<div class='kiosk-btn'>", unsafe_allow_html=True)
        if st.button('Staff Logout', use_container_width=True, key='staff_out_btn'):
            st.session_state['page'] = 'staff_out'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    back_home_button()



def visitor_portal():
    register_activity('visitor')
    show_logo(220)
    render_flash_banner()
    st.markdown("<div class='panel'><div class='compact-title'>Visitor Sign In</div></div>", unsafe_allow_html=True)
    back_home_button()
    staff_rows = query_all('SELECT * FROM staff WHERE is_active = 1 ORDER BY full_name')
    with st.form('visitor_form'):
        full_name = st.text_input('Full name *')
        company = st.text_input('Company / organisation')
        phone = st.text_input('Phone number *')
        email = st.text_input('Email')
        staff_options = {f"{r['full_name']} {'• In office' if r['is_in_office'] else '• Away'}": r for r in staff_rows}
        selected_label = st.selectbox('Staff member to see *', list(staff_options.keys())) if staff_options else None
        purpose = st.text_input('Purpose of visit')
        submitted = st.form_submit_button('Sign in visitor', use_container_width=True)
    if submitted:
        if not full_name or not phone or not selected_label:
            st.error('Please complete the required fields.')
        else:
            staff = staff_options[selected_label]
            badge = f"V-{datetime.now().strftime('%H%M%S')}"
            execute(
                '''INSERT INTO visitors (full_name, company, phone, email, person_to_see_staff_id, purpose, status, checkin_time, badge_number)
                   VALUES (?, ?, ?, ?, ?, ?, 'IN', ?, ?)''',
                (full_name, company, phone, email, staff['id'], purpose, now_local().isoformat(timespec='seconds'), badge)
            )
            add_audit_log('VISITOR_SIGNIN', full_name, f'Visitor signed in to see {staff["full_name"]}')
            badge_bytes = qr_png_bytes(f'visitor:{badge}|{full_name}')
            badge_file = BADGE_DIR / f'{badge}.png'
            badge_file.write_bytes(badge_bytes)
            if staff['is_in_office']:
                notify_staff_visit(staff['id'], staff['full_name'], staff['email'], full_name)
                st.markdown(f"<div class='message-card msg-orange'>Thank you, {full_name}<p>{staff['full_name']} has been notified to come to the front desk.</p></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='message-card msg-red'>Thank you, {full_name}<p>{staff['full_name']} is marked away. Reception may call extension {staff['extension'] or 'N/A'}.</p></div>", unsafe_allow_html=True)
            st.download_button('Download Visitor Badge', data=badge_bytes, file_name=f'{badge}.png', mime='image/png', use_container_width=True)
    st.write('')
    open_visitors = get_open_visitor_sessions()
    if open_visitors:
        options = {f"{r['full_name']} • {r['staff_name'] or 'No host'}": r for r in open_visitors}
        chosen = st.selectbox('Visitor sign out', list(options.keys()))
        if st.button('Sign out visitor', use_container_width=True):
            row = options[chosen]
            execute('UPDATE visitors SET status = ?, checkout_time = ? WHERE id = ?', ('OUT', now_local().isoformat(timespec='seconds'), row['id']))
            add_audit_log('VISITOR_SIGNOUT', row['full_name'], 'Visitor signed out')
            st.session_state['flash_banner'] = {'class': 'msg-green', 'title': 'Visitor signed out', 'text': 'Thank you for visiting Embrace Healthcare Solutions.'}
            st.session_state['page'] = 'home'
            st.rerun()



def contractor_portal():
    register_activity('contractor')
    show_logo(220)
    render_flash_banner()
    st.markdown("<div class='panel'><div class='compact-title'>Contractor Portal</div></div>", unsafe_allow_html=True)
    back_home_button()
    jobs = query_all("SELECT * FROM contractor_jobs WHERE status IN ('BOOKED', 'IN_PROGRESS') ORDER BY scheduled_for")
    with st.form('contractor_form'):
        contractor_name = st.text_input('Contractor full name *')
        company = st.text_input('Company *')
        phone = st.text_input('Phone number')
        email = st.text_input('Email')
        job_map = {f"#{j['id']} • {j['job_title']} • {j['location']}": j for j in jobs}
        selected_job_label = st.selectbox('Booked issue / job *', list(job_map.keys())) if job_map else None
        work_summary = st.text_input('Work summary')
        attachment = st.file_uploader('Optional site document / photo', type=['pdf', 'png', 'jpg', 'jpeg'])
        submitted = st.form_submit_button('Sign in contractor', use_container_width=True)
    if submitted:
        if not contractor_name or not company or not selected_job_label:
            st.error('Please complete the required fields.')
        else:
            job = job_map[selected_job_label]
            attachment_path = save_uploaded_file(attachment, DOC_DIR)
            execute(
                '''INSERT INTO contractor_visits (contractor_name, company, phone, email, job_id, sign_in_time, work_summary, status, attachment_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'IN', ?)''',
                (contractor_name, company, phone, email, job['id'], now_local().isoformat(timespec='seconds'), work_summary, attachment_path)
            )
            execute("UPDATE contractor_jobs SET status = 'IN_PROGRESS' WHERE id = ?", (job['id'],))
            add_audit_log('CONTRACTOR_SIGNIN', contractor_name, f'Signed into job #{job["id"]}')
            st.markdown("<div class='message-card msg-orange'>Contractor signed in<p>Please proceed to the booked issue location.</p></div>", unsafe_allow_html=True)
    st.write('')
    open_contractors = get_open_contractor_visits()
    if open_contractors:
        options = {f"{r['contractor_name']} • {r['job_title'] or 'No job'}": r for r in open_contractors}
        chosen = st.selectbox('Contractor sign out', list(options.keys()))
        work_done = st.text_area('Work completed summary')
        if st.button('Sign out contractor', use_container_width=True):
            row = options[chosen]
            execute('UPDATE contractor_visits SET status = ?, sign_out_time = ?, work_summary = COALESCE(?, work_summary) WHERE id = ?', ('OUT', now_local().isoformat(timespec='seconds'), work_done or None, row['id']))
            add_audit_log('CONTRACTOR_SIGNOUT', row['contractor_name'], 'Contractor signed out')
            st.session_state['flash_banner'] = {'class': 'msg-green', 'title': 'Contractor signed out', 'text': 'Admin can now confirm the completed job and attach the invoice.'}
            st.session_state['page'] = 'home'
            st.rerun()



def staff_signin():
    register_activity('staff_in')
    show_logo(220)
    render_flash_banner()
    st.markdown("<div class='panel'><div class='compact-title'>Staff Login</div><div class='muted'>Weekdays 8am to 4pm are standard. Outside these hours the stay is limited unless an admin booking exists.</div></div>", unsafe_allow_html=True)
    back_home_button()
    params = st.query_params
    prefill_code = params.get('staff_code', '') if hasattr(params, 'get') else ''
    staff_rows = query_all('SELECT * FROM staff WHERE is_active = 1 ORDER BY full_name')
    names = [r['full_name'] for r in staff_rows]
    chosen_name = st.selectbox('Staff member', names) if names else None
    code = st.text_input('Assigned code', type='password', value=prefill_code)
    if chosen_name:
        staff = next(r for r in staff_rows if r['full_name'] == chosen_name)
        booking = get_active_booking(staff['id'])
        if booking:
            st.info(f"Active after-hours booking found until {fmt_dt(booking['end_at'])}.")
        elif not is_business_hours(now_local()):
            if now_local().weekday() >= 5 or is_public_holiday(now_local()):
                st.warning('Weekend or public holiday detected. Without booking, stay is limited to 15 minutes.')
            else:
                st.warning('Outside standard hours. Without booking, stay is limited to 15 minutes.')
    if st.button('Log in staff', use_container_width=True):
        if not chosen_name:
            st.error('No staff available.')
        else:
            staff = next(r for r in staff_rows if r['full_name'] == chosen_name)
            if code != staff['code']:
                st.error('Incorrect code.')
            else:
                existing = query_one('SELECT * FROM staff_sessions WHERE staff_id = ? AND status = ?', (staff['id'], 'OPEN'))
                if existing:
                    st.warning('This staff member already has an open session.')
                else:
                    allowed_until, mode = allowed_until_for_signin(staff['id'], now_local())
                    ts = now_local().isoformat(timespec='seconds')
                    execute('INSERT INTO staff_sessions (staff_id, signin_time, status, mode, allowed_until, last_activity_at) VALUES (?, ?, ?, ?, ?, ?)', (staff['id'], ts, 'OPEN', mode, allowed_until.isoformat(timespec='seconds'), ts))
                    add_audit_log('STAFF_SIGNIN', staff['full_name'], f'Mode={mode}')
                    st.session_state['flash_banner'] = {'class': 'msg-red', 'title': f'Welcome {staff["full_name"]}', 'text': f'You are now logged into the building. Allowed until {fmt_dt(allowed_until.isoformat(timespec="seconds"))}.'}
                    st.session_state['page'] = 'staff_choice'
                    st.rerun()



def staff_signout():
    register_activity('staff_out')
    show_logo(220)
    render_flash_banner()
    st.markdown("<div class='panel'><div class='compact-title'>Staff Logout</div><div class='muted'>Enter your own details to sign out. Building status appears only after your logout is processed.</div></div>", unsafe_allow_html=True)
    back_home_button()
    open_staff = get_open_staff_sessions()
    if not open_staff:
        st.markdown("<div class='message-card msg-green'>No staff currently signed in<p>Thank you. No one is in the building. Please lock doors and arm the alarm.</p></div>", unsafe_allow_html=True)
        return

    options = {f"{r['full_name']} • signed in {fmt_dt(r['signin_time'])}": r for r in open_staff}
    chosen = st.selectbox('Open session', list(options.keys()))
    row = options[chosen]
    code_out = st.text_input('Assigned code', type='password')

    stale_others = [r for r in open_staff if r['id'] != row['id'] and session_is_stale(r)]
    if stale_others:
        st.warning('Some other open sessions look stale. You can use manual override if those staff already left.')
        stale_df = pd.DataFrame([
            {
                'Staff': r['full_name'],
                'Signed in': fmt_dt(r['signin_time']),
                'Last activity': fmt_dt(r.get('last_activity_at') or r.get('signin_time')),
                'Allowed until': fmt_dt(r.get('allowed_until')),
                'Extension': r['extension'] or '-',
                'Mode': r['mode'],
            }
            for r in stale_others
        ])
        st.dataframe(stale_df, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        logout_now = st.button('Log out staff', use_container_width=True)
    with c2:
        open_override = st.button('Manual override forgotten logout', use_container_width=True)

    if logout_now:
        staff = query_one('SELECT * FROM staff WHERE id = ?', (row['staff_id'],))
        if not staff or code_out != staff['code']:
            st.error('Incorrect code.')
        else:
            execute('UPDATE staff_sessions SET status = ?, signout_time = ?, last_activity_at = ? WHERE id = ?', ('CLOSED', now_local().isoformat(timespec='seconds'), now_local().isoformat(timespec='seconds'), row['id']))
            add_audit_log('STAFF_SIGNOUT', row['full_name'], 'Staff signed out')
            remaining_open = get_open_staff_sessions()
            if remaining_open:
                names = ' • '.join([f"{r['full_name']} (ext {r['extension'] or 'N/A'})" for r in remaining_open[:5]])
                st.markdown(f"<div class='message-card msg-red'>You are logged out<p>Another staff member is still in the building: {names}</p></div>", unsafe_allow_html=True)
            else:
                st.session_state['flash_banner'] = {'class': 'msg-green', 'title': 'You are logged out', 'text': 'Thank you. No one is in the building. Please lock doors and arm the alarm.'}
                st.session_state['page'] = 'staff_choice'
                st.rerun()

    if open_override:
        staff = query_one('SELECT * FROM staff WHERE id = ?', (row['staff_id'],))
        if not staff or code_out != staff['code']:
            st.error('Enter your own correct code first before using manual override.')
        else:
            candidates = [r for r in open_staff if r['id'] != row['id']]
            if not candidates:
                st.info('There are no other open sessions to override.')
            else:
                override_options = {f"{r['full_name']} • last activity {fmt_dt(r.get('last_activity_at') or r.get('signin_time'))}": r for r in candidates}
                selected_override = st.selectbox('Select forgotten session to close', list(override_options.keys()), key='override_session_select')
                reason = st.selectbox('Override reason', ['Staff already left', 'Staff forgot to logout', 'Admin instructed closure', 'Duplicate session'], key='override_reason')
                if st.button('Confirm manual override', use_container_width=True, key='confirm_override_btn'):
                    target = override_options[selected_override]
                    execute(
                        'UPDATE staff_sessions SET status = ?, signout_time = ?, override_closed_by = ?, override_reason = ?, last_activity_at = ? WHERE id = ? AND status = ?',
                        ('OVERRIDE_CLOSED', now_local().isoformat(timespec='seconds'), row['full_name'], reason, now_local().isoformat(timespec='seconds'), target['id'], 'OPEN')
                    )
                    add_audit_log('MANUAL_OVERRIDE_LOGOUT', row['full_name'], f"Closed {target['full_name']} session. Reason: {reason}")
                    st.success(f"{target['full_name']} was logged out by manual override.")
                    st.rerun()


def admin_login():
    register_activity('admin_login')
    show_logo(220)
    st.markdown("<div class='panel'><div class='compact-title'>Admin Portal</div><div class='muted'>Authorised admin only</div></div>", unsafe_allow_html=True)
    back_home_button()
    with st.form('admin_login_form'):
        username = st.text_input('Username')
        pin = st.text_input('PIN', type='password')
        submit = st.form_submit_button('Login', use_container_width=True)
    if submit:
        admin = query_one('SELECT * FROM admins WHERE username = ? AND pin = ?', (username, pin))
        if admin:
            st.session_state['admin_logged_in'] = True
            st.session_state['page'] = 'admin'
            st.rerun()
        else:
            st.error('Invalid admin credentials.')



def admin_portal():
    register_activity('admin')
    st.markdown("<div class='compact-title'>Admin Portal</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 3])
    with c1:
        if st.button('Home', use_container_width=True):
            st.session_state['page'] = 'home'
            st.session_state['admin_logged_in'] = False
            st.rerun()
    with c2:
        if st.button('Generate Weekly Report Now', use_container_width=True):
            report = generate_weekly_reports(force=True)
            if report:
                st.success('Weekly report generated.')
    tabs = st.tabs(['Dashboard', 'Jobs & Invoices', 'Staff', 'Bookings & Holidays', 'Kiosk Display', 'Reports', 'Alerts', 'Audit'])

    with tabs[0]:
        open_staff = get_open_staff_sessions()
        open_visitors = get_open_visitor_sessions()
        open_contractors = get_open_contractor_visits()
        a, b, c, d = st.columns(4)
        a.metric('Staff in building', len(open_staff))
        b.metric('Visitors onsite', len(open_visitors))
        c.metric('Contractors onsite', len(open_contractors))
        d.metric('Time', now_local().strftime('%I:%M %p'))
        occupancy_banner(open_staff)
        if open_staff:
            st.dataframe(pd.DataFrame([{'Staff':r['full_name'],'Signed in':fmt_dt(r['signin_time']),'Allowed until':fmt_dt(r['allowed_until']),'Extension':r['extension'] or '-','Mode':r['mode']} for r in open_staff]), use_container_width=True, hide_index=True)
        if open_visitors:
            st.dataframe(pd.DataFrame([{'Visitor':r['full_name'],'Host':r['staff_name'],'Purpose':r['purpose'] or '-','In':fmt_dt(r['checkin_time'])} for r in open_visitors]), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader('Book contractor issue')
        with st.form('job_form'):
            c1, c2 = st.columns(2)
            with c1:
                job_title = st.text_input('Job title')
                issue = st.text_area('Issue description')
                location = st.text_input('Location')
            with c2:
                contractor_company = st.text_input('Preferred contractor company')
                scheduled_for = st.text_input('Scheduled for (YYYY-MM-DD HH:MM)')
                created_by = st.text_input('Created by', value='admin')
            submit_job = st.form_submit_button('Create job', use_container_width=True)
        if submit_job:
            execute('INSERT INTO contractor_jobs (job_title, issue_description, location, contractor_company, scheduled_for, status, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)', (job_title, issue, location, contractor_company, scheduled_for, 'BOOKED', created_by))
            add_audit_log('JOB_BOOKED', created_by, job_title)
            st.success('Booked job created.')
            st.rerun()
        jobs = query_all('SELECT * FROM contractor_jobs ORDER BY id DESC')
        if jobs:
            options = {f"#{j['id']} • {j['job_title']} • {j['status']}": j for j in jobs}
            selected = st.selectbox('Choose job', list(options.keys()))
            note = st.text_area('Admin confirmation note')
            invoice = st.file_uploader('Attach invoice', type=['pdf', 'png', 'jpg', 'jpeg'])
            c1, c2 = st.columns(2)
            with c1:
                if st.button('Confirm Completed Job', use_container_width=True):
                    row = options[selected]
                    invoice_path = save_uploaded_file(invoice, INVOICE_DIR)
                    execute('UPDATE contractor_jobs SET status = ?, completed_at = ?, invoice_file = COALESCE(?, invoice_file), admin_confirmation_note = ? WHERE id = ?', ('COMPLETED', now_local().isoformat(timespec='seconds'), invoice_path, note, row['id']))
                    add_audit_log('JOB_CONFIRMED', 'admin', f'Job #{row["id"]} confirmed')
                    st.success('Job confirmed.')
                    st.rerun()
            with c2:
                if st.button('Reopen Job', use_container_width=True):
                    row = options[selected]
                    execute('UPDATE contractor_jobs SET status = ?, admin_confirmation_note = ? WHERE id = ?', ('BOOKED', note, row['id']))
                    st.warning('Job reopened.')
                    st.rerun()
            st.dataframe(pd.DataFrame([{'ID':j['id'],'Title':j['job_title'],'Location':j['location'],'Company':j['contractor_company'],'Scheduled':j['scheduled_for'],'Status':j['status'],'Invoice':j['invoice_file'] or '-'} for j in jobs]), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader('Add or update staff')
        with st.form('staff_add_form'):
            c1, c2 = st.columns(2)
            with c1:
                full_name = st.text_input('Full name')
                code = st.text_input('Assigned code')
                email = st.text_input('Email')
            with c2:
                extension = st.text_input('Extension')
                in_office = st.checkbox('Normally in office', value=True)
                submit_staff = st.form_submit_button('Add staff', use_container_width=True)
        if submit_staff:
            execute('INSERT INTO staff (full_name, code, email, extension, is_active, is_in_office) VALUES (?, ?, ?, ?, 1, ?)', (full_name, code, email, extension, 1 if in_office else 0))
            add_audit_log('STAFF_CREATED', 'admin', full_name)
            st.success('Staff member added.')
            st.rerun()
        staff_rows = query_all('SELECT * FROM staff ORDER BY full_name')
        if staff_rows:
            labels = {f"{r['full_name']} • ext {r['extension'] or '-'}": r for r in staff_rows}
            selected_staff_label = st.selectbox('Select staff', list(labels.keys()))
            row = labels[selected_staff_label]
            qurl = f"https://your-kiosk-url/?staff_code={row['code']}"
            qr_bytes = qr_png_bytes(qurl)
            st.download_button('Download Staff QR', data=qr_bytes, file_name=f"staff_{row['full_name'].replace(' ','_')}.png", mime='image/png', use_container_width=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button('Mark In Office', use_container_width=True):
                    execute('UPDATE staff SET is_in_office = 1 WHERE id = ?', (row['id'],))
                    st.success('Updated.')
                    st.rerun()
            with c2:
                if st.button('Mark Away', use_container_width=True):
                    execute('UPDATE staff SET is_in_office = 0 WHERE id = ?', (row['id'],))
                    st.warning('Updated.')
                    st.rerun()
            st.dataframe(pd.DataFrame([{'Staff':r['full_name'],'Email':r['email'] or '-','Extension':r['extension'] or '-','Office Status':'In office' if r['is_in_office'] else 'Away'} for r in staff_rows]), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader('Public holidays')
        with st.form('holiday_form'):
            holiday_date = st.date_input('Holiday date', value=date.today())
            holiday_label = st.text_input('Label')
            if st.form_submit_button('Add holiday', use_container_width=True):
                try:
                    execute('INSERT INTO public_holidays (holiday_date, label) VALUES (?, ?)', (holiday_date.isoformat(), holiday_label))
                    st.success('Holiday added.')
                    st.rerun()
                except Exception:
                    st.warning('Holiday already exists.')
        holidays = query_all('SELECT * FROM public_holidays ORDER BY holiday_date DESC')
        if holidays:
            st.dataframe(pd.DataFrame([{'Date':r['holiday_date'],'Label':r['label'] or '-'} for r in holidays]), use_container_width=True, hide_index=True)

        st.subheader('Book extended staff stay for weekends / holidays / after-hours')
        staff_rows = query_all('SELECT * FROM staff WHERE is_active = 1 ORDER BY full_name')
        with st.form('booking_form'):
            staff_labels = {r['full_name']: r for r in staff_rows}
            staff_name = st.selectbox('Staff', list(staff_labels.keys())) if staff_rows else None
            c1, c2 = st.columns(2)
            with c1:
                start_date = st.date_input('Start date', value=date.today(), key='bk_sd')
                start_time = st.time_input('Start time', value=dt_time(17, 0), key='bk_st')
            with c2:
                end_date = st.date_input('End date', value=date.today(), key='bk_ed')
                end_time = st.time_input('End time', value=dt_time(18, 0), key='bk_et')
            reason = st.text_input('Reason')
            approved_by = st.text_input('Approved by', value='admin')
            if st.form_submit_button('Create booking', use_container_width=True) and staff_name:
                staff = staff_labels[staff_name]
                start_at = datetime.combine(start_date, start_time).isoformat(timespec='seconds')
                end_at = datetime.combine(end_date, end_time).isoformat(timespec='seconds')
                execute('INSERT INTO afterhours_bookings (staff_id, start_at, end_at, reason, approved_by) VALUES (?, ?, ?, ?, ?)', (staff['id'], start_at, end_at, reason, approved_by))
                add_audit_log('AFTERHOURS_BOOKING', approved_by, f"{staff['full_name']} until {end_at}")
                st.success('Booking created.')
                st.rerun()
        bookings = query_all('''SELECT ab.*, s.full_name FROM afterhours_bookings ab JOIN staff s ON s.id = ab.staff_id ORDER BY start_at DESC''')
        if bookings:
            st.dataframe(pd.DataFrame([{'Staff':r['full_name'],'Start':fmt_dt(r['start_at']),'End':fmt_dt(r['end_at']),'Reason':r['reason'] or '-','Approved By':r['approved_by'] or '-'} for r in bookings]), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader('Kiosk Display Preview')
        show_logo(320)
        st.markdown("<div class='welcome-label'>Welcome to Embrace</div>", unsafe_allow_html=True)
        occupancy_banner()
        st.markdown("<div class='message-card msg-green'>You are logged out<p>Thank you. Please lock doors and arm the alarm.</p></div>", unsafe_allow_html=True)
        st.markdown("<div class='message-card msg-red'>Welcome back<p>You are logged in. Building status has been updated.</p></div>", unsafe_allow_html=True)

    with tabs[5]:
        reports = query_all('SELECT * FROM report_history ORDER BY created_at DESC')
        if reports:
            df = pd.DataFrame([{'Created':fmt_dt(r['created_at']),'Period Start':fmt_dt(r['report_start']),'Period End':fmt_dt(r['report_end']),'Excel':r['excel_file'],'PDF':r['pdf_file'],'Emailed To':r['emailed_to'] or '-'} for r in reports])
            st.dataframe(df, use_container_width=True, hide_index=True)
            latest = reports[0]
            excel_path = BASE_DIR / latest['excel_file'] if latest['excel_file'] else None
            pdf_path = BASE_DIR / latest['pdf_file'] if latest['pdf_file'] else None
            c1, c2 = st.columns(2)
            if excel_path and excel_path.exists():
                with c1:
                    st.download_button('Download Latest Excel', data=excel_path.read_bytes(), file_name=excel_path.name, mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
            if pdf_path and pdf_path.exists():
                with c2:
                    st.download_button('Download Latest PDF', data=pdf_path.read_bytes(), file_name=pdf_path.name, mime='application/pdf', use_container_width=True)
        else:
            st.info('No reports generated yet.')

    with tabs[6]:
        alerts = query_all('SELECT * FROM alerts ORDER BY created_at DESC LIMIT 200')
        if alerts:
            st.dataframe(pd.DataFrame([{'Time':fmt_dt(r['created_at']),'Type':r['alert_type'],'Message':r['message'],'Read':'Yes' if r['is_read'] else 'No'} for r in alerts]), use_container_width=True, hide_index=True)
        else:
            st.info('No alerts recorded.')

    with tabs[7]:
        logs = query_all('SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 400')
        if logs:
            st.dataframe(pd.DataFrame([{'Time':fmt_dt(r['created_at']),'Event':r['event_type'],'Actor':r['actor'],'Details':r['details']} for r in logs]), use_container_width=True, hide_index=True)
        else:
            st.info('No audit logs yet.')



def main():
    load_css()
    bootstrap_state()
    check_inactivity()
    check_overstays()
    try:
        generate_weekly_reports(force=False)
    except Exception:
        pass

    page = st.session_state['page']
    inject_watchdog(INACTIVITY_SECONDS if page != 'home' else HOME_REFRESH_SECONDS)

    if page == 'home':
        home_screen()
    elif page == 'visitor':
        visitor_portal()
    elif page == 'contractor':
        contractor_portal()
    elif page == 'staff_choice':
        staff_choice()
    elif page == 'staff_in':
        staff_signin()
    elif page == 'staff_out':
        staff_signout()
    elif page == 'admin_login':
        admin_login()
    elif page == 'admin' and st.session_state.get('admin_logged_in'):
        admin_portal()
    else:
        st.session_state['page'] = 'home'
        st.rerun()


if __name__ == '__main__':
    main()
