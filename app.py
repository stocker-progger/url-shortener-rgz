# app.py
import os
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, redirect, abort
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db, ShortURL, Click

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///urls.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Инициализация кэширования (SimpleCache — в памяти, подходит для демо)
cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 3600  # 1 час
})

# Функция для определения ключа лимитирования при создании ссылки
def get_user_key():
    # Используем заголовок X-User-ID, если задан; иначе — IP
    user_id = request.headers.get("X-User-ID")
    return user_id or get_remote_address()

# Инициализация лимитера
limiter = Limiter(
    app=app,
    key_func=get_remote_address,  # по умолчанию — IP, но в эндпоинтах переопределим
    default_limits=[]
)

db.init_app(app)

# Создание таблиц при запуске (в production лучше использовать миграции)
with app.app_context():
    db.create_all()


def generate_short_id(length=6):
    """Генерация уникального короткого идентификатора"""
    return secrets.token_urlsafe(length)[:length]


@app.route('/shorten', methods=['POST'])
@limiter.limit("10 per day", key_func=get_user_key)
def shorten_url():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "Field 'url' is required"}), 400

    original_url = data['url']
    user_id = request.headers.get("X-User-ID") or data.get("user_id")  # поддерживаем оба варианта

    # Проверка: не создавал ли этот пользователь уже такую ссылку?
    existing = ShortURL.query.filter_by(original_url=original_url, user_id=user_id).first()
    if existing:
        return jsonify({"short_id": existing.short_id}), 200

    short_id = generate_short_id()
    # Убедимся, что short_id уникален (маловероятно, но возможно коллизия)
    while ShortURL.query.filter_by(short_id=short_id).first():
        short_id = generate_short_id()

    new_url = ShortURL(
        short_id=short_id,
        original_url=original_url,
        user_id=user_id
    )
    db.session.add(new_url)
    db.session.commit()

    return jsonify({"short_id": short_id}), 201


@app.route('/<short_id>')
@limiter.limit(
    "100 per day",
    key_func=lambda: f"{request.view_args.get('short_id', 'unknown')}_{get_remote_address()}"
)
def redirect_to_url(short_id):
    # Попытка получить из кэша
    cached_url = cache.get(f"redirect_{short_id}")
    if cached_url:
        original_url = cached_url
    else:
        record = ShortURL.query.filter_by(short_id=short_id).first()
        if not record:
            abort(404)
        original_url = record.original_url
        # Кэшируем на 1 час
        cache.set(f"redirect_{short_id}", original_url)

    # Сбор статистики: IP и клики
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr).split(',')[0].strip()

    # Определяем начало текущего дня (UTC)
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    # Проверяем, был ли уже клик с этого IP сегодня по этой ссылке
    existing_click = Click.query.filter(
        Click.short_id == short_id,
        Click.ip_address == ip,
        Click.timestamp >= today_start
    ).first()

    if not existing_click:
        # Новый уникальный клик сегодня
        new_click = Click(short_id=short_id, ip_address=ip)
        record.click_count += 1
        db.session.add(new_click)
        db.session.commit()

    return redirect(original_url)


@app.route('/stats/<short_id>')
def get_stats(short_id):
    record = ShortURL.query.filter_by(short_id=short_id).first_or_404()
    clicks = Click.query.filter_by(short_id=short_id).all()
    unique_ips = list({click.ip_address for click in clicks})  # уникальные IP

    return jsonify({
        "short_id": short_id,
        "original_url": record.original_url,
        "click_count": record.click_count,
        "unique_ips": unique_ips
    })


if __name__ == '__main__':
    app.run(debug=True)