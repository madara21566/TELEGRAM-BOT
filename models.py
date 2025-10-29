from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    telegram_id = Column(String, nullable=True)
    plan = Column(String, default='free')
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    projects = relationship('Project', back_populates='owner')

class Project(Base):
    __tablename__ = 'projects'
    id = Column(String, primary_key=True)
    owner_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String)
    zip_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_deployed = Column(DateTime, nullable=True)
    status = Column(String, default='uploaded')
    public_url = Column(String, nullable=True)
    uptime_seconds = Column(Integer, default=0)
    owner = relationship('User', back_populates='projects')

class Backup(Base):
    __tablename__ = 'backups'
    id = Column(Integer, primary_key=True)
    project_id = Column(String)
    path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ActivityLog(Base):
    __tablename__ = 'activity_logs'
    id = Column(Integer, primary_key=True)
    project_id = Column(String, nullable=True)
    user_id = Column(Integer, nullable=True)
    level = Column(String, default='info')
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
