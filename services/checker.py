import requests
import socket
import time
from datetime import datetime
from urllib.parse import urlparse

def check_endpoint(endpoint):
    start_time = time.time()
    endpoint_id = str(endpoint['_id'])
    url = endpoint['url']
    method = endpoint.get('method', 'GET').upper()
    expected_status = endpoint.get('expected_status', 200)
    timeout = endpoint.get('timeout', 10)

    result = {
        "endpoint_id": endpoint_id,
        "status": "down",
        "latency_ms": None,
        "http_status": None,
        "error_message": None,
        "checked_at": datetime.utcnow()
    }

    try:
        # ── Заголовки ──
        headers = {'User-Agent': 'Beacon-Monitor/1.0'}

        # Кастомные заголовки из настроек
        for h in endpoint.get('headers') or []:
            if h.get('key'):
                headers[h['key']] = h.get('value', '')

        # ── Аутентификация ──
        auth = None
        auth_type = endpoint.get('auth_type', 'none')

        if auth_type == 'bearer':
            token = endpoint.get('auth_bearer_token', '')
            if token:
                headers['Authorization'] = f'Bearer {token}'

        elif auth_type == 'basic':
            user = endpoint.get('auth_basic_user', '')
            pwd = endpoint.get('auth_basic_pass', '')
            if user:
                auth = (user, pwd)

        elif auth_type == 'api_key':
            key_header = endpoint.get('auth_api_key_header', 'X-API-Key')
            key_value = endpoint.get('auth_api_key_value', '')
            if key_header and key_value:
                headers[key_header] = key_value

        # ── Тело запроса ──
        body = None
        if method in ('POST', 'PUT', 'PATCH') and endpoint.get('body'):
            body = endpoint['body']
            content_type = endpoint.get('body_content_type', 'application/json')
            headers['Content-Type'] = content_type

        # ── SSL и редиректы ──
        follow_redirects = endpoint.get('follow_redirects', True)
        ssl_verify = endpoint.get('ssl_verify', True)
        max_redirects = endpoint.get('max_redirects', 5)

        session = requests.Session()
        session.max_redirects = max_redirects

        response = session.request(
            method=method,
            url=url,
            timeout=timeout,
            allow_redirects=follow_redirects,
            headers=headers,
            auth=auth,
            data=body if body else None,
            verify=ssl_verify,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result['latency_ms'] = latency_ms
        result['http_status'] = response.status_code

        # ── Проверка статус-кода ──
        if response.status_code != expected_status:
            result['error_message'] = f"Expected {expected_status}, got {response.status_code}"
            return result

        # ── Проверка тела ответа ──
        body_type = endpoint.get('expected_body_type', 'none')
        expected_body = endpoint.get('expected_body', '')

        if body_type != 'none' and expected_body:
            response_text = response.text
            match = False

            if body_type == 'contains':
                match = expected_body in response_text
            elif body_type == 'exact':
                match = response_text.strip() == expected_body.strip()
            elif body_type == 'regex':
                match = bool(re.search(expected_body, response_text))

            if not match:
                result['error_message'] = f"Body check failed ({body_type}): '{expected_body}'"
                return result

        result['status'] = 'up'

    except requests.exceptions.Timeout:
        result['error_message'] = f"Timeout after {timeout}s"
    except requests.exceptions.SSLError as e:
        result['error_message'] = f"SSL error: {str(e)[:100]}"
    except requests.exceptions.TooManyRedirects:
        result['error_message'] = "Too many redirects"
    except requests.exceptions.ConnectionError:
        result['error_message'] = "Connection error"
    except requests.exceptions.RequestException as e:
        result['error_message'] = f"Request failed: {str(e)[:100]}"

    return result


def check_tcp_endpoint(host, port, timeout=5):
    """
    Проверка TCP порта (для сокетов, баз данных, etc.)
    
    Args:
        host: str (hostname or IP)
        port: int
        timeout: int (секунды)
    
    Returns:
        dict: результат проверки
    """
    start_time = time.time()
    
    result = {
        "status": "down",
        "latency_ms": None,
        "error_message": None
    }
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        
        latency_ms = int((time.time() - start_time) * 1000)
        result['status'] = "up"
        result['latency_ms'] = latency_ms
        
    except socket.timeout:
        result['error_message'] = f"TCP connection timeout after {timeout} seconds"
    except socket.gaierror:
        result['error_message'] = f"DNS resolution failed for {host}"
    except ConnectionRefusedError:
        result['error_message'] = f"Connection refused on port {port}"
    except Exception as e:
        result['error_message'] = f"TCP check failed: {str(e)}"
    
    return result


def check_ping_endpoint(host, timeout=5):
    """
    Проверка через ping (ICMP)
    NOTE: Требует права администратора на некоторых системах
    
    Args:
        host: str (hostname or IP)
        timeout: int (секунды)
    
    Returns:
        dict: результат проверки
    """
    import subprocess
    import platform
    
    start_time = time.time()
    
    result = {
        "status": "down",
        "latency_ms": None,
        "error_message": None
    }
    
    try:
        # Определяем команду ping в зависимости от ОС
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', '-W', str(timeout), host]
        
        # Выполняем ping
        response = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        if response.returncode == 0:
            result['status'] = "up"
            result['latency_ms'] = latency_ms
        else:
            result['error_message'] = "Ping request failed"
            
    except subprocess.TimeoutExpired:
        result['error_message'] = f"Ping timeout after {timeout} seconds"
    except Exception as e:
        result['error_message'] = f"Ping failed: {str(e)}"
    
    return result


def check_endpoint_advanced(endpoint):
    """
    Расширенная проверка с поддержкой разных типов (HTTP, TCP, Ping)
    
    Args:
        endpoint: словарь с данными эндпоинта
            {
                "type": "http" or "tcp" or "ping",
                "url": str (для http),
                "host": str (для tcp/ping),
                "port": int (для tcp),
                ...
            }
    """
    endpoint_type = endpoint.get('type', 'http')
    
    if endpoint_type == 'http':
        return check_endpoint(endpoint)
    elif endpoint_type == 'tcp':
        # Извлекаем host и port из URL или полей
        if 'url' in endpoint:
            parsed = urlparse(endpoint['url'])
            host = parsed.hostname
            port = parsed.port or 80
        else:
            host = endpoint.get('host')
            port = endpoint.get('port', 80)
        
        result = check_tcp_endpoint(host, port, endpoint.get('timeout', 5))
        result["endpoint_id"] = str(endpoint['_id'])
        result["checked_at"] = datetime.utcnow()
        return result
        
    elif endpoint_type == 'ping':
        host = endpoint.get('host') or urlparse(endpoint.get('url', '')).hostname
        result = check_ping_endpoint(host, endpoint.get('timeout', 5))
        result["endpoint_id"] = str(endpoint['_id'])
        result["checked_at"] = datetime.utcnow()
        return result
    
    else:
        return {
            "endpoint_id": str(endpoint['_id']),
            "status": "down",
            "latency_ms": None,
            "error_message": f"Unsupported endpoint type: {endpoint_type}",
            "checked_at": datetime.utcnow()
        }