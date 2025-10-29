import os
import sys
from werkzeug.security import generate_password_hash
from common.db import SessionLocal, init_db
from common.models import Base, User

# ensure path
if __name__ == '__main__':
    init_db(Base)
    email = os.getenv('ADMIN_EMAIL') or (sys.argv[1] if len(sys.argv)>1 else 'admin@example.com')
    pwd = os.getenv('ADMIN_PASSWORD') or (sys.argv[2] if len(sys.argv)>2 else 'changeme')
    sess = SessionLocal()
    existing = sess.query(User).filter_by(email=email).first()
    if existing:
        print('Admin already exists')
    else:
        u = User(email=email, password_hash=generate_password_hash(pwd), is_admin=True, plan='premium')
        sess.add(u); sess.commit()
        print('Admin created:', email)
    sess.close()
