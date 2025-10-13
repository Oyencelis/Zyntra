from flask import Flask, session
import os
from flask_session import Session

def create_app():
    app = Flask(__name__, template_folder='../template', static_folder='../static')
    
    # Setup server-side session
    app.config['SESSION_TYPE'] = 'filesystem'  # Options: 'redis', 'filesystem', 'mongodb', etc.
    app.config['SECRET_KEY'] = os.urandom(24)
    Session(app)

    @app.context_processor
    def inject_user():
        authenticated = session.get('authenticated', None)
        return dict(auth_user=authenticated)

    # Import the routes and register them with the app
    from routes import setup_routes
    setup_routes(app)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)  # Allow automatic reloading of changes

