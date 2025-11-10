# tests/test_app.py
import pytest
from app import app, db
from models import ShortURL, Click
import os


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # in-memory БД для тестов
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.drop_all()


def test_shorten_url_creates_new_link(client):
    """Тест: создание новой короткой ссылки"""
    response = client.post('/shorten', json={'url': 'https://example.com'})
    assert response.status_code == 201
    data = response.get_json()
    assert 'short_id' in data
    assert len(data['short_id']) == 6

    # Проверяем, что запись появилась в БД
    with app.app_context():
        record = ShortURL.query.first()
        assert record.original_url == 'https://example.com'


def test_shorten_url_returns_existing_for_same_user_and_url(client):
    """Тест: одинаковый URL от одного пользователя — тот же short_id"""
    payload = {'url': 'https://example.com'}
    resp1 = client.post('/shorten', json=payload)
    resp2 = client.post('/shorten', json=payload)

    assert resp1.status_code == 201
    assert resp2.status_code == 200  # уже существует
    assert resp1.get_json()['short_id'] == resp2.get_json()['short_id']


def test_redirect_to_url(client):
    """Тест: редирект по короткой ссылке"""
    # Сначала создадим ссылку
    resp = client.post('/shorten', json={'url': 'https://example.com'})
    short_id = resp.get_json()['short_id']

    # Запрос на редирект
    redirect_resp = client.get(f'/{short_id}', follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers['Location'] == 'https://example.com'

    # Проверим, что клик записан
    with app.app_context():
        record = ShortURL.query.filter_by(short_id=short_id).first()
        assert record.click_count == 1

        click = Click.query.first()
        assert click.short_id == short_id
        assert click.ip_address == '127.0.0.1'


def test_stats_endpoint(client):
    """Тест: получение статистики по короткой ссылке"""
    # Создаём ссылку
    resp = client.post('/shorten', json={'url': 'https://example.com'})
    short_id = resp.get_json()['short_id']

    # Делаем клик
    client.get(f'/{short_id}')

    # Получаем статистику
    stats_resp = client.get(f'/stats/{short_id}')
    assert stats_resp.status_code == 200
    data = stats_resp.get_json()
    assert data['short_id'] == short_id
    assert data['original_url'] == 'https://example.com'
    assert data['click_count'] == 1
    assert '127.0.0.1' in data['unique_ips']


def test_redirect_nonexistent_short_id(client):
    """Тест: редирект по несуществующему short_id → 404"""
    resp = client.get('/nonexistent123')
    assert resp.status_code == 404


def test_stats_nonexistent_short_id(client):
    """Тест: статистика по несуществующему short_id → 404"""
    resp = client.get('/stats/nonexistent123')
    assert resp.status_code == 404


def test_shorten_missing_url(client):
    """Тест: ошибка при отсутствии поля 'url'"""
    resp = client.post('/shorten', json={})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()