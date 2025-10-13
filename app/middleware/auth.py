from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            flash('You need to log in first.', 'warning')
            return redirect(url_for('login_page'))  # Redirect to the login page
        return f(*args, **kwargs)
    return decorated_function

    