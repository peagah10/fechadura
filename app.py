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
    """Token TTLock ULTRA RÁPIDO"""
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

        # ULTRA RÁPIDO: timeout 1 segundo!
        response = requests.post(url, data=data, timeout=1)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            # Cache por 95% do tempo
            cache_time = expires_in * 0.95
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            return access_token
        
        return None

    except:
        return None


def open_ttlock_fast(lock_id):
    """Abertura ULTRA RÁPIDA"""
    if SIMULATION_MODE:
        log_message("🔓 [SIM] ABERTA!")
        return True

    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            return False

        url = f"{TT_API_BASE}/v3/lock/unlock"
        data = {
            'clientId': TT_CLIENT_ID,
            'accessToken': access_token,
            'lockId': lock_id,
            'date': int(datetime.now().timestamp() * 1000)
        }

        # ULTRA RÁPIDO: timeout 1.5 segundos!
        response = requests.post(url, data=data, timeout=1.5)
        result = response.json()

        if result.get('errcode') == 0:
            log_message("🔓 ABERTA!")
            return True
        else:
            log_message(f"❌ {result.get('errmsg', 'Erro')}")
            return False

    except Exception as e:
        log_message(f"❌ {str(e)[:50]}")
        return False


def open_lock_async(lock_id):
    """Abre fechadura em thread separada - NÃO BLOQUEIA"""
    def run():
        open_ttlock_fast(lock_id)
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()


@app.route('/', methods=['GET'])
def home():
    """Rota principal"""
    return jsonify({
        'message': 'Sistema ULTRA RÁPIDO!',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache': 'cached' if token_cache['access_token'] else 'empty'
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Webhook ULTRA RÁPIDO - não espera TTLock"""
    try:
        log_message("📥 PagBank")
        
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/x-www-form-urlencoded' in content_type:
            notification_code = request.form.get('notificationCode')
            notification_type = request.form.get('notificationType')
            
            if notification_type == 'transaction' and notification_code:
                log_message("💳 APROVADO")
                
                # ABERTURA ASSÍNCRONA - NÃO ESPERA!
                open_lock_async(TT_LOCK_ID)
                
                # RESPOSTA IMEDIATA
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'ignored'}), 200
        
        else:
            # Testes manuais JSON
            try:
                webhook_data = json.loads(request.get_data().decode('utf-8'))
            except:
                return jsonify({'error': 'JSON inválido'}), 400
            
            status = webhook_data.get('status', '')
            
            if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
                log_message("💳 TESTE APROVADO")
                
                # ABERTURA ASSÍNCRONA
                open_lock_async(TT_LOCK_ID)
                
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'ignored'}), 200
            
    except Exception as e:
        log_message(f"❌ {str(e)[:50]}")
        return jsonify({'error': 'Erro'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Teste ULTRA RÁPIDO"""
    if not SIMULATION_MODE:
        return jsonify({'error': 'Desabilitado no modo real'}), 403
    
    try:
        webhook_data = json.loads(request.get_data().decode('utf-8'))
        status = webhook_data.get('status', '')

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("🧪 TESTE")
            open_lock_async(TT_LOCK_ID)
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'ignored'}), 200

    except:
        return jsonify({'error': 'Erro'}), 500


@app.route('/warm-cache', methods=['GET'])
def warm_cache():
    """Pré-aquece o cache do token"""
    token = get_ttlock_access_token()
    return jsonify({
        'cache_warmed': bool(token),
        'cached': bool(token_cache['access_token'])
    })


@app.route('/open-now', methods=['POST'])
def open_now():
    """Abertura manual IMEDIATA"""
    log_message("🔓 ABERTURA MANUAL")
    open_lock_async(TT_LOCK_ID)
    return jsonify({'status': 'opening'}), 200


@app.route('/debug/ttlock', methods=['GET'])
def debug_ttlock():
    """Debug TTLock"""
    if SIMULATION_MODE:
        return jsonify({'status': 'simulation_mode'})
    
    token = get_ttlock_access_token()
    return jsonify({
        'token_obtained': bool(token),
        'cached': bool(token_cache['access_token'])
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'mode': 'SIM' if SIMULATION_MODE else 'REAL',
        'cache': bool(token_cache['access_token'])
    })


if __name__ == '__main__':
    log_message("🚀 SISTEMA ULTRA RÁPIDO")
    
    # Pré-aquecer cache na inicialização
    if not SIMULATION_MODE:
        log_message("🔥 Pré-aquecendo cache...")
        get_ttlock_access_token()
    
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
