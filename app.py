import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
import threading

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações
PAG_WEBHOOK_SECRET = os.getenv('PAG_WEBHOOK_SECRET', '')
TT_CLIENT_ID = os.getenv('TT_CLIENT_ID', '')
TT_CLIENT_SECRET = os.getenv('TT_CLIENT_SECRET', '')
TT_EMAIL = os.getenv('TT_EMAIL', '')
TT_PASSWORD = os.getenv('TT_PASSWORD', '')
TT_LOCK_ID = os.getenv('TT_LOCK_ID', '')
TT_API_BASE = os.getenv('TT_API_BASE', 'https://euapi.sciener.com')
OPEN_SECONDS = int(os.getenv('OPEN_SECONDS', '8'))
SIMULATION_MODE = os.getenv('SIMULATION_MODE', 'true').lower() == 'true'

# Cache para token TTLock
token_cache = {
    'access_token': None,
    'expires_at': None
}


def log_message(message):
    """Log rápido"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


def get_ttlock_access_token():
    """Token TTLock com timeout otimizado para Render"""
    if SIMULATION_MODE:
        return "token_simulado_123"

    # Verificar cache
    now = datetime.now()
    if (token_cache['access_token'] and 
        token_cache['expires_at'] and 
        now < token_cache['expires_at']):
        return token_cache['access_token']

    try:
        url = f"{TT_API_BASE}/oauth2/token"
        password_md5 = hashlib.md5(TT_PASSWORD.encode('utf-8')).hexdigest()
        
        data = {
            'client_id': TT_CLIENT_ID,
            'client_secret': TT_CLIENT_SECRET,
            'grant_type': 'password',
            'username': TT_EMAIL,
            'password': password_md5
        }

        # TIMEOUT OTIMIZADO PARA RENDER: 3 segundos
        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            # Cache por 90% do tempo
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            log_message("✅ Token OK")
            return access_token
        
        return None

    except requests.exceptions.Timeout:
        log_message("❌ Timeout token (3s)")
        return None
    except Exception as e:
        log_message(f"❌ Token: {str(e)[:30]}")
        return None


def open_ttlock_fast(lock_id):
    """Abertura rápida com melhor tratamento de erro"""
    if SIMULATION_MODE:
        log_message("🔓 [SIM] ABERTA!")
        return True

    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            log_message("❌ Sem token")
            return False

        url = f"{TT_API_BASE}/v3/lock/unlock"
        data = {
            'clientId': TT_CLIENT_ID,
            'accessToken': access_token,
            'lockId': lock_id,
            'date': int(datetime.now().timestamp() * 1000)
        }

        # TIMEOUT OTIMIZADO PARA RENDER: 4 segundos
        response = requests.post(url, data=data, timeout=4)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message("🔓 FECHADURA ABERTA!")
            return True
        else:
            error_msg = result.get('errmsg', 'Erro desconhecido')
            log_message(f"❌ TTLock: {error_msg}")
            return False

    except requests.exceptions.Timeout:
        log_message("❌ Timeout abertura (4s)")
        return False
    except requests.exceptions.ConnectionError:
        log_message("❌ Conexão falhou")
        return False
    except Exception as e:
        log_message(f"❌ Erro: {str(e)[:30]}")
        return False


def open_lock_async(lock_id):
    """Abertura assíncrona com logs detalhados"""
    def run():
        log_message("🔓 Iniciando abertura...")
        success = open_ttlock_fast(lock_id)
        if success:
            log_message("✅ Fechadura aberta com sucesso!")
        else:
            log_message("❌ Falha na abertura")
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()


@app.route('/', methods=['GET'])
def home():
    """Rota principal"""
    return jsonify({
        'message': 'Sistema PagBank + TTLock OTIMIZADO',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Webhook otimizado para Render"""
    try:
        log_message("📥 PagBank")
        
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/x-www-form-urlencoded' in content_type:
            notification_code = request.form.get('notificationCode')
            notification_type = request.form.get('notificationType')
            
            log_message(f"📄 Code: {notification_code[:15] if notification_code else 'None'}...")
            log_message(f"📄 Type: {notification_type}")
            
            if notification_type == 'transaction' and notification_code:
                log_message("💳 PAGAMENTO APROVADO!")
                
                # ABERTURA ASSÍNCRONA
                open_lock_async(TT_LOCK_ID)
                
                # RESPOSTA IMEDIATA
                return jsonify({'status': 'success', 'message': 'Processing'}), 200
            else:
                log_message("⏸️ Ignorado")
                return jsonify({'status': 'ignored'}), 200
        
        else:
            # Testes manuais JSON
            try:
                webhook_data = json.loads(request.get_data().decode('utf-8'))
            except:
                return jsonify({'error': 'JSON inválido'}), 400
            
            status = webhook_data.get('status', '')
            log_message(f"📄 JSON Status: {status}")
            
            if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
                log_message("💳 TESTE APROVADO!")
                open_lock_async(TT_LOCK_ID)
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'ignored'}), 200
            
    except Exception as e:
        log_message(f"❌ Webhook erro: {str(e)[:50]}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Teste manual"""
    if not SIMULATION_MODE:
        return jsonify({'error': 'Desabilitado no modo real'}), 403
    
    try:
        webhook_data = json.loads(request.get_data().decode('utf-8'))
        status = webhook_data.get('status', '')

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("🧪 TESTE MANUAL")
            open_lock_async(TT_LOCK_ID)
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'ignored'}), 200

    except:
        return jsonify({'error': 'Erro'}), 500


@app.route('/open-now', methods=['POST'])
def open_now():
    """Abertura manual para teste"""
    log_message("🔓 ABERTURA MANUAL SOLICITADA")
    open_lock_async(TT_LOCK_ID)
    return jsonify({'status': 'opening', 'message': 'Comando enviado'}), 200


@app.route('/test-connection', methods=['GET'])
def test_connection():
    """Testar conexão TTLock"""
    log_message("🧪 Testando conexão TTLock...")
    
    if SIMULATION_MODE:
        return jsonify({'status': 'simulation', 'message': 'Modo simulação ativo'})
    
    try:
        # Teste simples de conectividade
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(('euapi.sciener.com', 443))
        sock.close()
        
        if result == 0:
            token = get_ttlock_access_token()
            return jsonify({
                'connection': 'OK',
                'token_obtained': bool(token),
                'cached': bool(token_cache['access_token'])
            })
        else:
            return jsonify({'connection': 'FAILED', 'error': f'Socket error: {result}'})
            
    except Exception as e:
        return jsonify({'connection': 'ERROR', 'error': str(e)})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'mode': 'SIMULAÇÃO' if SIMULATION_MODE else 'REAL',
        'cache': bool(token_cache['access_token']),
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    log_message("🚀 Sistema PagBank + TTLock - OTIMIZADO RENDER")
    log_message(f"🔧 Modo: {'SIMULAÇÃO' if SIMULATION_MODE else 'REAL'}")
    
    # Pré-aquecer cache se não estiver em simulação
    if not SIMULATION_MODE:
        log_message("🔥 Pré-aquecendo cache...")
        token = get_ttlock_access_token()
        if token:
            log_message("✅ Cache aquecido com sucesso")
        else:
            log_message("❌ Falha ao aquecer cache")
    
    port = int(os.getenv('PORT', 10000))  # Porta padrão do Render
    app.run(host='0.0.0.0', port=port, debug=False)
