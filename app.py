import os
from flask import Flask, render_template, request, redirect, url_for
from common.db import init_db, SessionLocal
from common.models import Base, User, Project, ActivityLog, Backup

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'change-me')

init_db(Base)
DATA_DIR = '/app/data'
PROJECTS_DIR = os.path.join(DATA_DIR, 'projects')

@app.route('/')
def index():
    sess = SessionLocal()
    users = sess.query(User).count()
    projects = sess.query(Project).count()
    running = sess.query(Project).filter_by(status='running').count()
    logs = sess.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(30).all()
    sess.close()
    return render_template('index.html', users=users, projects=projects, running=running, logs=logs)

# Admin simple pages
@app.route('/admin')
def admin_index():
    sess = SessionLocal()
    users = sess.query(User).all()
    projects = sess.query(Project).all()
    sess.close()
    return render_template('admin_index.html', users=users, projects=projects)

@app.route('/projects/<pid>')
def project_page(pid):
    return f'Project {pid}'

@app.route('/editor/<pid>', methods=['GET','POST'])
def editor(pid):
    path = request.args.get('path', 'main.py')
    workdir = os.path.join(DATA_DIR, 'projects', pid, 'work')
    target = os.path.join(workdir, path)
    if request.method == 'POST':
        content = request.form.get('content', '')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f: f.write(content)
        return 'Saved'
    text = ''
    if os.path.exists(target):
        with open(target,'r',encoding='utf-8') as f: text = f.read()
    return render_template('editor.html', pid=pid, path=path, content=text)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
