import os
import threading
import sqlite3
import datetime
from flask import Flask, render_template_string, request, redirect, session, send_file
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from NIKALLLLLLL import (
    start, set_filename, set_contact_name, set_limit, set_start,
    set_vcf_start, make_vcf_command, merge_command, done_merge,
    handle_document, handle_text
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("FLASK_SECRET", "supersecret")

DB_FILE = "bot_stats.db"

# ✅ DB INIT

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    user_id INTEGER,
                    username TEXT,
                    action TEXT,
                    timestamp TEXT
                )''')
    conn.commit()
    conn.close()

def log_action(user_id, username, action):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, username or 'N/A', action, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

start_time = datetime.datetime.now()

# ✅ Flask App
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

@flask_app.route('/')
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM logs")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM logs WHERE action='makevcf'")
    total_files = c.fetchone()[0]

    c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC")
    logs = c.fetchall()
    conn.close()

    uptime = str(datetime.datetime.now() - start_time).split('.')[0]

    return render_template_string("""
    <html><head><title>Bot Status</title></head><body>
    <h2>✅ Telegram Bot Live Status</h2>
    <p>🕒 <b>Uptime:</b> {{ uptime }}</p>
    <p>👥 <b>Total Users:</b> {{ total_users }}</p>
    <p>📁 <b>Total Files Generated:</b> {{ total_files }}</p>
    <hr>
    <h3>📋 Full User History</h3>
    <table border="1" cellpadding="5">
        <tr><th>No.</th><th>Username</th><th>User ID</th><th>Action</th><th>Time</th></tr>
        {% for row in logs %}
        <tr>
            <td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td>
        </tr>
        {% endfor %}
    </table>
    <p><a href="/admin">🔐 Admin Panel</a></p>
    </body></html>
    """, uptime=uptime, total_users=total_users, total_files=total_files, logs=logs)

@flask_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        return "❌ Incorrect password"
    return '''<h2>🔐 Admin Login</h2>
        <form method="post">
        Password: <input type="password" name="password" />
        <input type="submit" value="Login" />
        </form>'''

@flask_app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Filters
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    query = "SELECT username, user_id, action, timestamp FROM logs"
    if start_date and end_date:
        query += f" WHERE date(timestamp) BETWEEN '{start_date}' AND '{end_date}'"
    query += " ORDER BY timestamp DESC"

    c.execute(query)
    logs = c.fetchall()
    c.execute("SELECT action, COUNT(*) FROM logs GROUP BY action")
    stats = c.fetchall()
    conn.close()

    chart_data = {s[0]: s[1] for s in stats}

    return render_template_string("""
    <h2>🔐 Admin Panel</h2>
    <form method="post">
        📅 From: <input type="date" name="start_date">
        To: <input type="date" name="end_date">
        <input type="submit" value="Filter">
    </form>
    <form method="post" action="/admin/broadcast">
        <textarea name="message" placeholder="Broadcast message"></textarea>
        <br><input type="submit" value="📢 Broadcast to All Users">
    </form>
    <form method="post" action="/admin/delete_user">
        <input type="text" name="user_id" placeholder="User ID to delete logs">
        <input type="submit" value="🗑️ Delete User Logs">
    </form>
    <br>
    <a href="/admin/download">📥 Download CSV</a> |
    <a href="/admin/clear" onclick="return confirm('Are you sure?')">🗑️ Clear All Logs</a> |
    <a href="/admin/logout">🚪 Logout</a>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <canvas id="chart" width="400" height="200"></canvas>
    <script>
        const ctx = document.getElementById('chart').getContext('2d');
        new Chart(ctx, {
            type: 'pie',
            data: {
                labels: {{ chart_data.keys()|list }},
                datasets: [{
                    label: 'Command Usage',
                    data: {{ chart_data.values()|list }},
                    backgroundColor: ['red', 'green', 'blue', 'orange', 'purple']
                }]
            }
        });
    </script>

    <table border="1" cellpadding="5">
    <tr><th>No.</th><th>Username</th><th>User ID</th><th>Action</th><th>Time</th></tr>
    {% for row in logs %}
    <tr><td>{{ loop.index }}</td><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td></tr>
    {% endfor %}
    </table>
    """, logs=logs, chart_data=chart_data)

@flask_app.route('/admin/broadcast', methods=['POST'])
def broadcast():
    if not session.get('admin'):
        return redirect('/admin')
    message = request.form.get('message')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM logs")
    users = c.fetchall()
    conn.close()
    for u in users:
        try:
            application.bot.send_message(chat_id=u[0], text=message)
        except:
            pass
    return redirect('/admin/dashboard')

@flask_app.route('/admin/delete_user', methods=['POST'])
def delete_user_logs():
    if not session.get('admin'):
        return redirect('/admin')
    uid = request.form.get('user_id')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM logs WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    return redirect('/admin/dashboard')

@flask_app.route('/admin/download')
def download_csv():
    if not session.get('admin'):
        return redirect('/admin')
    import csv
    filename = 'bot_logs.csv'
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, user_id, action, timestamp FROM logs ORDER BY timestamp DESC")
    logs = c.fetchall()
    conn.close()
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Username', 'User ID', 'Action', 'Time'])
        writer.writerows(logs)
    return send_file(filename, as_attachment=True)

@flask_app.route('/admin/clear')
def clear_logs():
    if not session.get('admin'):
        return redirect('/admin')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
    return redirect('/admin/dashboard')

@flask_app.route('/admin/logout')
def logout():
    session.pop('admin', None)
    return redirect('/admin')

# ✅ Wrapper for handlers to auto-log usage
def track_usage(handler_func, command_name):
    async def wrapper(update, context):
        user = update.effective_user
        log_action(user.id, user.username, command_name)
        return await handler_func(update, context)
    return wrapper

init_db()

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", track_usage(start, "start")))
application.add_handler(CommandHandler("setfilename", track_usage(set_filename, "setfilename")))
application.add_handler(CommandHandler("setcontactname", track_usage(set_contact_name, "setcontactname")))
application.add_handler(CommandHandler("setlimit", track_usage(set_limit, "setlimit")))
application.add_handler(CommandHandler("setstart", track_usage(set_start, "setstart")))
application.add_handler(CommandHandler("setvcfstart", track_usage(set_vcf_start, "setvcfstart")))
application.add_handler(CommandHandler("makevcf", track_usage(make_vcf_command, "makevcf")))
application.add_handler(CommandHandler("merge", track_usage(merge_command, "merge")))
application.add_handler(CommandHandler("done", track_usage(done_merge, "done")))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(MessageHandler(filters.TEXT, handle_text))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    application.run_polling()
        
