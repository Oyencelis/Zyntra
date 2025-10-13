from flask import render_template, session

def dashboardIndex():
    active_menu = ['dashboard', 'analytics']
    return render_template('views/dashboard/index.html', menu = active_menu)