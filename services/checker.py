import requests
import socket
import time
from datetime import datetime
from urllib.parse import urlparse

def check_endpoint(endpoint):
    """
    Проверяет доступность эндпоинта
    
    Args:
        endpoint: словарь с данными эндпоинта из MongoDB
            {
                "_id": ObjectId,
                "name": str,
                "url": str,
                "method": str (GET, POST, etc.),
                "expected_status": int,
                "timeout": int (секунды),
                "interval": int,
                "active": bool
            }
    
    Returns:
        dict: результат проверки
            {
                "endpoint_id": str,
                "status": str ("up" или "down"),
                "latency_ms": int or None,
                "http_status": int or None,
                "error_message": str or None,
                "checked_at": datetime
            }
    """
    
    start_time = time.time()
    endpoint_id = str(endpoint['_id'])
    url = endpoint['url']
    method = endpoint.get('method', 'GET').upper()
    expected_status = endpoint.get('expected_status', 200)
    timeout = endpoint.get('timeout', 5)
    
    result = {
        "endpoint_id": endpoint_id,
        "status": "down",  # по умолчанию down
        "latency_ms": None,
        "http_status": None,
        "error_message": None,
        "checked_at": datetime.utcnow()
    }
    
    try:
        # Выполняем HTTP запрос
        response = requests.request(
            method=method,
            url=url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                'User-Agent': 'Beacon-Monitor/1.0'
            }
        )
        
        # Вычисляем latency
        latency_ms = int((time.time() - start_time) * 1000)
        result['latency_ms'] = latency_ms
        result['http_status'] = response.status_code
        
        # Проверяем статус ответа
        if response.status_code == expected_status:
            result['status'] = "up"
        else:
            result['error_message'] = f"Expected status {expected_status}, got {response.status_code}"
            
    except requests.exceptions.Timeout:
        result['error_message'] = f"Connection timeout after {timeout} seconds"
        
    except requests.exceptions.ConnectionError:
        result['error_message'] = "Connection error (DNS failure, refused connection, etc.)"
        
    except requests.exceptions.TooManyRedirects:
        result['error_message'] = "Too many redirects"
        
    except requests.exceptions.RequestException as e:
        result['error_message'] = f"Request failed: {str(e)}"
        
    except Exception as e:
        result['error_message'] = f"Unexpected error: {str(e)}"
    
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