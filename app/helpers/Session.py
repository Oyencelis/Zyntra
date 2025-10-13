from flask import session, g

def setSession(session_name, object):
    session.permanent = True  
    session[session_name] = object

def sessionRemove(session_name):
    session.pop(session_name, None)
