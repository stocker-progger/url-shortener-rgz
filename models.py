# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ShortURL(db.Model):
    __tablename__ = 'short_urls'
    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(10), unique=True, nullable=False, index=True)
    original_url = db.Column(db.String(512), nullable=False)
    user_id = db.Column(db.String(64), nullable=True)  # опционально
    click_count = db.Column(db.Integer, default=0)

class Click(db.Model):
    __tablename__ = 'clicks'
    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(10), db.ForeignKey('short_urls.short_id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6-совместимо
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)