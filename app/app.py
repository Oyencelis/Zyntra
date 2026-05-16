# app.py or factory file
# pyrefly: ignore [missing-import]
from flask import Flask, session
import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from flask_session import Session
from extensions import mail
from helpers.template_filters import register_template_filters


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

def str_to_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return value.lower() in {'1', 'true', 't', 'yes', 'y'}

def create_app():
    app = Flask(__name__, template_folder='../template', static_folder='../static')
    
    # Core config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-prod')
    app.config['SESSION_TYPE'] = 'filesystem'

    # Mail configuration
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = str_to_bool(os.environ.get('MAIL_USE_TLS', 'true'))
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = (
        os.environ.get('MAIL_DEFAULT_SENDER')
        or os.environ.get('MAIL_USERNAME')
        or "serisuaruse@gmail.com"
    )

    # OTP / verification config
    app.config['OTP_TTL_MINUTES'] = int(os.environ.get('OTP_TTL_MINUTES', 5))
    app.config['OTP_RESEND_COOLDOWN_SECONDS'] = int(os.environ.get('OTP_RESEND_COOLDOWN_SECONDS', 60))

    Session(app)
    mail.init_app(app)

    @app.context_processor
    def inject_user():
        authenticated = session.get('authenticated', None)
        return dict(auth_user=authenticated)

    from routes import setup_routes
    setup_routes(app)
    register_template_filters(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
