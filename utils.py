from __future__ import annotations

from datetime import datetime, time, timedelta, date
from zoneinfo import ZoneInfo
from db import query_all

APP_TIMEZONE = ZoneInfo('Australia/Perth')
BUSINESS_START = time(8, 0)
BUSINESS_END = time(16, 30)
AFTER_HOURS_LIMIT_MINUTES = 15
NORMAL_HOURS_GRACE_MINUTES = 15


def now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def app_timezone_name() -> str:
    return 'Australia/Perth'


def ensure_local(dt: datetime | None) -> datetime:
    if dt is None:
        return now_local()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=APP_TIMEZONE)
    return dt.astimezone(APP_TIMEZONE)


def is_weekday(dt: datetime | None = None) -> bool:
    dt = ensure_local(dt)
    return dt.weekday() < 5


def is_public_holiday(dt: datetime | None = None) -> bool:
    dt = ensure_local(dt)
    holiday = query_all('SELECT 1 FROM public_holidays WHERE holiday_date = ?', (dt.date().isoformat(),))
    return bool(holiday)


def is_business_day(dt: datetime | None = None) -> bool:
    dt = ensure_local(dt)
    return is_weekday(dt) and not is_public_holiday(dt)


def is_business_hours(dt: datetime | None = None) -> bool:
    dt = ensure_local(dt)
    current = dt.timetz().replace(tzinfo=None)
    return is_business_day(dt) and BUSINESS_START <= current <= BUSINESS_END


def get_active_booking(staff_id: int, dt: datetime | None = None):
    dt = ensure_local(dt)
    rows = query_all(
        '''SELECT * FROM afterhours_bookings
           WHERE staff_id = ? AND start_at <= ? AND end_at >= ?
           ORDER BY start_at DESC LIMIT 1''',
        (staff_id, dt.isoformat(timespec='seconds'), dt.isoformat(timespec='seconds')),
    )
    return rows[0] if rows else None


def business_day_end(dt: datetime | None = None) -> datetime:
    dt = ensure_local(dt)
    return dt.replace(hour=BUSINESS_END.hour, minute=BUSINESS_END.minute, second=0, microsecond=0)


def allowed_until_for_signin(staff_id: int | None = None, dt: datetime | None = None) -> tuple[datetime, str]:
    dt = ensure_local(dt)
    if is_business_hours(dt):
        return business_day_end(dt) + timedelta(minutes=NORMAL_HOURS_GRACE_MINUTES), 'NORMAL_WEEKDAY'
    if staff_id:
        booking = get_active_booking(staff_id, dt)
        if booking:
            return parse_dt(booking['end_at']) or (dt + timedelta(minutes=AFTER_HOURS_LIMIT_MINUTES)), 'BOOKED_EXTENDED'
    return dt + timedelta(minutes=AFTER_HOURS_LIMIT_MINUTES), 'AFTER_HOURS_15_MIN'


def session_window_for_row(session_row: dict, reference_dt: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    sign_in = parse_dt(session_row.get('signin_time'))
    allowed_until = parse_dt(session_row.get('allowed_until'))
    reference_dt = ensure_local(reference_dt or sign_in or now_local())
    mode = session_row.get('mode')

    if mode == 'NORMAL_WEEKDAY' and sign_in:
        remind_at = business_day_end(sign_in)
        logout_at = allowed_until or (remind_at + timedelta(minutes=NORMAL_HOURS_GRACE_MINUTES))
        return remind_at, logout_at

    if allowed_until:
        remind_at = allowed_until - timedelta(minutes=5)
        if remind_at < (sign_in or allowed_until):
            remind_at = sign_in or allowed_until
        return remind_at, allowed_until

    return None, None


def fmt_dt(value: str | datetime | None) -> str:
    if not value:
        return '-'
    dt = value if isinstance(value, datetime) else parse_dt(value)
    if not dt:
        return str(value)
    return ensure_local(dt).strftime('%d %b %Y %I:%M %p AWST')


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return ensure_local(dt)
    except ValueError:
        return None


def building_status(open_staff_rows) -> tuple[str, str, str]:
    if open_staff_rows:
        first = open_staff_rows[0]
        ext = first['extension'] or 'N/A'
        msg = f"Someone is still in the building. Please wait for staff response or call extension {ext}."
        return 'RED', '#b91c1c', msg
    return 'GREEN', '#15803d', 'Thank you. No one is in the building. Lock doors and arm the alarm.'


def current_operating_mode(dt: datetime | None = None) -> str:
    dt = ensure_local(dt)
    if is_public_holiday(dt):
        return 'PUBLIC_HOLIDAY'
    if not is_weekday(dt):
        return 'WEEKEND'
    if is_business_hours(dt):
        return 'BUSINESS_HOURS'
    return 'AFTER_HOURS'


def current_date_local() -> date:
    return now_local().date()
