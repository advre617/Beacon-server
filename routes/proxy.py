from flask import Blueprint, request, jsonify, g
import requests
import time
from middlewares.auth import login_required

bp = Blueprint('proxy', __name__, url_prefix='/api/proxy')

# Максимальный размер ответа — 5 MB
MAX_RESPONSE_SIZE = 5 * 1024 * 1024

FORBIDDEN_HOSTS = {
    'localhost', '127.0.0.1', '0.0.0.0',
    '::1', 'metadata.google.internal',
}


def _is_forbidden(url: str) -> bool:
    """Блокируем запросы к локальным адресам (SSRF защита)."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ''
        if host in FORBIDDEN_HOSTS:
            return True
        # блокируем 169.254.x.x (AWS metadata и т.п.)
        if host.startswith('169.254.'):
            return True
        return False
    except Exception:
        return True


@bp.route('/request', methods=['POST'])
@login_required
def proxy_request():
    """
    Проксирует произвольный HTTP запрос от имени сервера.

    Body (JSON):
    {
        "method":  "GET" | "POST" | ...,
        "url":     "https://example.com/api/foo",
        "headers": { "X-Custom": "value" },   // опционально
        "body":    "raw string body",          // опционально
        "params":  { "key": "value" },         // query params
        "timeout": 15                          // секунды, default 10
    }

    Response (JSON):
    {
        "status":      200,
        "status_text": "OK",
        "headers":     { ... },
        "body":        "...",          // строка
        "body_json":   { ... },        // если ответ — валидный JSON
        "elapsed_ms":  142,
        "size_bytes":  1024,
        "redirects":   [ { "url": ..., "status": ... } ],
        "error":       null            // или строка с ошибкой
    }
    """
    data = request.get_json(force=True, silent=True) or {}

    method  = (data.get('method') or 'GET').upper()
    url     = (data.get('url') or '').strip()
    headers = data.get('headers') or {}
    body    = data.get('body')
    params  = data.get('params') or {}
    timeout = min(int(data.get('timeout') or 10), 30)

    # Валидация
    if not url:
        return jsonify({"error": "url is required"}), 400

    if not url.startswith(('http://', 'https://')):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    if _is_forbidden(url):
        return jsonify({"error": "Requests to this host are not allowed"}), 403

    # Убираем заголовки, которые могут сломать запрос
    skip_headers = {'host', 'content-length', 'transfer-encoding', 'connection'}
    clean_headers = {k: v for k, v in headers.items()
                     if k.lower() not in skip_headers}

    # Идентифицируем себя
    clean_headers.setdefault('User-Agent', 'Beacon-Tester/1.0')

    start = time.time()
    redirects = []

    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=clean_headers,
            params=params or None,
            data=body.encode('utf-8') if isinstance(body, str) else None,
            timeout=timeout,
            allow_redirects=True,
            stream=True,           # стримим чтобы не грузить всё сразу
        )

        # Собираем историю редиректов
        for r in resp.history:
            redirects.append({
                "url":    r.url,
                "status": r.status_code,
            })

        elapsed_ms = int((time.time() - start) * 1000)

        # Читаем тело с ограничением
        raw_bytes = b''
        truncated = False
        for chunk in resp.iter_content(chunk_size=65536):
            raw_bytes += chunk
            if len(raw_bytes) > MAX_RESPONSE_SIZE:
                truncated = True
                break

        size_bytes = len(raw_bytes)

        # Декодируем
        encoding = resp.encoding or 'utf-8'
        try:
            body_str = raw_bytes.decode(encoding, errors='replace')
        except (LookupError, UnicodeDecodeError):
            body_str = raw_bytes.decode('utf-8', errors='replace')

        # Пробуем распарсить JSON
        body_json = None
        ct = resp.headers.get('content-type', '')
        if 'json' in ct:
            try:
                import json
                body_json = json.loads(body_str)
            except Exception:
                pass

        # Заголовки ответа
        resp_headers = dict(resp.headers)

        return jsonify({
            "status":      resp.status_code,
            "status_text": resp.reason,
            "headers":     resp_headers,
            "body":        body_str,
            "body_json":   body_json,
            "elapsed_ms":  elapsed_ms,
            "size_bytes":  size_bytes,
            "truncated":   truncated,
            "redirects":   redirects,
            "error":       None,
        })

    except requests.exceptions.SSLError as e:
        return jsonify({
            "status": None, "status_text": None,
            "headers": {}, "body": None, "body_json": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "size_bytes": 0, "truncated": False,
            "redirects": redirects,
            "error": f"SSL Error: {str(e)}",
        })

    except requests.exceptions.ConnectionError as e:
        return jsonify({
            "status": None, "status_text": None,
            "headers": {}, "body": None, "body_json": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "size_bytes": 0, "truncated": False,
            "redirects": redirects,
            "error": f"Connection Error: {str(e)}",
        })

    except requests.exceptions.Timeout:
        return jsonify({
            "status": None, "status_text": None,
            "headers": {}, "body": None, "body_json": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "size_bytes": 0, "truncated": False,
            "redirects": redirects,
            "error": f"Timeout after {timeout}s — server did not respond",
        })

    except requests.exceptions.TooManyRedirects:
        return jsonify({
            "status": None, "status_text": None,
            "headers": {}, "body": None, "body_json": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "size_bytes": 0, "truncated": False,
            "redirects": redirects,
            "error": "Too many redirects",
        })

    except Exception as e:
        return jsonify({
            "status": None, "status_text": None,
            "headers": {}, "body": None, "body_json": None,
            "elapsed_ms": int((time.time() - start) * 1000),
            "size_bytes": 0, "truncated": False,
            "redirects": [],
            "error": f"Unexpected error: {str(e)}",
        })