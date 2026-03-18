# Embrace Visitor, Staff & Contractor Kiosk

A kiosk-friendly Streamlit MVP for iPad, Android tablet, or a local office mini-PC.

## Features
- Clean logo-first home screen with portal buttons only
- Big red/green occupancy banners
- Visitor sign-in with staff selection and host notification
- Printable visitor badge download
- Contractor portal linked to admin-booked issues/jobs
- Admin confirmation and invoice attachment for completed jobs
- Staff sign-in and sign-out with assigned code
- Weekday rule: 8am to 4pm
- Outside hours: 15-minute limit unless admin created an extended booking
- Weekend / public holiday support using admin-created holiday dates and extended bookings
- Alert escalation to admin for staff overstays
- Weekly Excel + PDF audit report generation and optional email delivery
- Staff QR code generation for quick login links

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Default admin
- Username: `admin`
- PIN: `1234`

## Demo staff
- Sam Ncube → `1001`
- Donna K → `1002`
- Scott M → `1003`
- Nelly P → `1004`

## Email setup (optional)
Create environment variables:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_SENDER`

## SMS setup (optional)
Create environment variables:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

## Kiosk testing
For iPad or Android testing, run this app on a laptop or mini-PC and open it from the tablet browser using the local IP address or a cloud deployment URL.

## Suggested next production steps
- Replace SQLite with PostgreSQL
- Hash staff/admin PINs
- Use proper authentication and HTTPS
- Run background jobs for report sending and alert escalation
- Add camera capture and actual SMS/email integrations
- Deploy on AWS, Azure, or a local Windows mini-PC kiosk
