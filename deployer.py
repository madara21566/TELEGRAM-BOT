import os, zipfile, shutil, tarfile
from pathlib import Path
from flask import Flask, request, jsonify
import docker
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from common.db import SessionLocal, init_db
from common.models import Base, User, Project, Backup, ActivityLog

DATA = Path('/app/data')
PROJECTS = DATA / 'projects'
PROJECTS.mkdir(parents=True, exist_ok=True)
BACKUPS = DATA / 'backups'
BACKUPS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
client = docker.from_env()

init_db(Base)
sess_global = SessionLocal()

scheduler = BackgroundScheduler()
scheduler.start()

def extract_zip(project_id, zip_name):
    proj = PROJECTS / project_id
    zip_path = proj / zip_name
    workdir = proj / 'work'
    if workdir.exists(): shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(workdir)
    return workdir

def create_backup(project_id):
    projdir = PROJECTS / project_id / 'work'
    if not projdir.exists():
        return None
    out = BACKUPS / f"{project_id}_{int(datetime.utcnow().timestamp())}.tar.gz"
    with tarfile.open(out, 'w:gz') as tar:
        tar.add(str(projdir), arcname='work')
    sess = SessionLocal()
    sess.add(Backup(project_id=project_id, path=str(out)))
    sess.commit(); sess.close()
    return str(out)

def schedule_auto_stop(project_id, hours=12):
    job_id = f'auto_stop_{project_id}'
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    run_date = datetime.utcnow() + timedelta(hours=hours)
    scheduler.add_job(func=auto_stop_project, trigger='date', run_date=run_date, id=job_id, args=[project_id])

def auto_stop_project(project_id):
    try:
        c = client.containers.get(f'proj_{project_id}')
        c.stop(); c.remove()
        sess = SessionLocal(); p = sess.query(Project).filter_by(id=project_id).first()
        if p: p.status='stopped'; sess.commit(); sess.close()
    except Exception as e:
        sess = SessionLocal(); sess.add(ActivityLog(project_id=project_id, level='error', message=f'Auto-stop failed: {e}')); sess.commit(); sess.close()

@app.route('/deploy', methods=['POST'])
def deploy():
    data = request.get_json() or {}
    pid = data.get('project_id'); zip_name = data.get('zip_name'); user_id = data.get('user_id')
    if not pid or not zip_name:
        return 'Missing fields', 400
    proj = PROJECTS / pid
    if not (proj / zip_name).exists():
        return 'ZIP not found', 404
    workdir = extract_zip(pid, zip_name)
    image_tag = f'proj_{pid}:latest'
    try:
        # build
        client.images.build(path=str(workdir), tag=image_tag, rm=True)
    except Exception as e:
        sess = SessionLocal(); sess.add(ActivityLog(project_id=pid, level='error', message=f'Build failed: {e}')); sess.commit(); sess.close()
        return f'Build failed: {e}', 500
    # stop existing
    try:
        for c in client.containers.list(all=True, filters={'name':f'proj_{pid}'}):
            try: c.stop(timeout=2); c.remove()
            except: pass
    except: pass
    try:
        cont = client.containers.run(image_tag, name=f'proj_{pid}', detach=True, mem_limit='512m')
    except Exception as e:
        sess = SessionLocal(); sess.add(ActivityLog(project_id=pid, level='error', message=f'Run failed: {e}')); sess.commit(); sess.close()
        return f'Run failed: {e}', 500
    sess = SessionLocal()
    project = sess.query(Project).filter_by(id=pid).first()
    if not project:
        project = Project(id=pid, owner_id=user_id, name=pid, zip_name=zip_name, status='running')
        sess.add(project)
    else:
        project.status='running'; project.last_deployed=datetime.utcnow()
    sess.commit(); sess.close()
    create_backup(pid)
    # schedule auto-stop for free users
    sess = SessionLocal(); owner = sess.query(User).get(user_id) if user_id else None
    if owner and owner.plan=='free':
        schedule_auto_stop(pid, hours=12)
    sess.close()
    url = os.getenv('BASE_URL','http://localhost:8080') + f'/projects/{pid}'
    return jsonify({'project_id': pid, 'url': url})

@app.route('/status/<pid>')
def status(pid):
    try:
        c = client.containers.get(f'proj_{pid}')
        return jsonify({'id': pid, 'status': c.status, 'image': c.image.tags})
    except docker.errors.NotFound:
        return 'Not found', 404
    except Exception as e:
        return str(e), 500

@app.route('/logs/<pid>')
def logs(pid):
    try:
        c = client.containers.get(f'proj_{pid}')
        return c.logs(tail=500).decode('utf-8', errors='ignore')
    except Exception as e:
        return str(e), 500

@app.route('/stop/<pid>', methods=['POST'])
def stop(pid):
    try:
        c = client.containers.get(f'proj_{pid}')
        c.stop(); c.remove()
        sess = SessionLocal(); p = sess.query(Project).filter_by(id=pid).first();
        if p: p.status='stopped'; sess.commit(); sess.close()
        return 'Stopped'
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
