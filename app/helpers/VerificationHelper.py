import random
# pyrefly: ignore [missing-import]
import bcrypt
from datetime import datetime, timedelta
from typing import Optional

# pyrefly: ignore [missing-import]
from flask import current_app, session
# pyrefly: ignore [missing-import]
from flask_mail import Message
# pyrefly: ignore [missing-import]
from extensions import mail

def generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"

def hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()

def verify_otp(otp: str, hashed: str) -> bool:
    return bcrypt.checkpw(otp.encode(), hashed.encode())

def get_otp_expiry() -> datetime:
    ttl_minutes = current_app.config.get('OTP_TTL_MINUTES', 5)
    return datetime.utcnow() + timedelta(minutes=ttl_minutes)

def send_email_code(email: str, otp: str) -> bool:
    subject = 'Your Zyntra email verification code'
    ttl_minutes = current_app.config.get('OTP_TTL_MINUTES', 5)
    body = (
        f"Hi!\n\nUse this code to verify your Zyntra email: {otp}\n\n"
        f"This code expires in {ttl_minutes} minute(s). If you did not attempt to sign up, ignore this message."
    )
    try:
        msg = Message(
            subject=subject,
            recipients=[email],
            body=body,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Email failed: {e}")
        return False

def store_email_otp(email: str):
    if 'email_otp_hash' in session:
        return

    otp = generate_otp()
    hashed = hash_otp(otp)
    expiry = get_otp_expiry()
    session['email_otp_hash'] = hashed
    session['email_otp_expiry'] = expiry.isoformat()
    session['email_otp_attempts'] = 3
    session['email_for_verification'] = email

    send_email_code(email, otp)

def check_email_otp(user_input: str) -> dict:
    hashed = session.get('email_otp_hash')
    expiry_iso = session.get('email_otp_expiry')
    attempts = session.get('email_otp_attempts', 0)

    if not hashed or not expiry_iso:
        return {'success': False, 'message': "No OTP requested."}

    expiry = datetime.fromisoformat(expiry_iso)

    if datetime.utcnow() > expiry:
        session.pop('email_otp_hash', None)
        return {'success': False, 'message': "OTP expired."}

    if attempts <= 0:
        return {'success': False, 'message': "No attempts left."}

    if verify_otp(user_input, hashed):
        session.pop('email_otp_hash', None)
        session.pop('email_otp_expiry', None)
        session.pop('email_otp_attempts', None)
        session.pop('email_for_verification', None)
        return {'success': True, 'message': "Email verified!"}

    session['email_otp_attempts'] = attempts - 1
    return {
        'success': False,
        'message': f"Invalid email code. You have {attempts-1} attempt(s) left."
    }

def seconds_until_resend(last_sent_at: Optional[datetime]) -> int:
    if not last_sent_at:
        return 0
    cooldown = current_app.config.get('OTP_RESEND_COOLDOWN_SECONDS', 60)
    now = datetime.utcnow()
    delta = last_sent_at + timedelta(seconds=cooldown) - now
    return max(int(delta.total_seconds()), 0)
