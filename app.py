import os
import hashlib
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações
PAG_EMAIL = os.getenv('PAG_EMAIL', '')
PAG_TOKEN = os.getenv('PAG_TOKEN', '')
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

# Status da fechadura
lock_status = {
    'state': 'fechada',
    'last_payment_time': None,
    'message': 'Aguardando pagamento...'
}


def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


def get_ttlock_access_token():
    if SIMULATION_MODE:
        return "token_simulado_123"

    now = datetime.now()
    if token_cache['access_token'] and token_cache['expires_at'] and now < token_cache['expires_at']:
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
        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            log_message("✅ Token TTLock obtido (cached)")
            return access_token
        else:
            log_message("❌ Token não encontrado")
            return None

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro token TTLock: {str(e)}")
        return None


def open_ttlock(lock_id, seconds):
    """Abre a fechadura TTLock e atualiza status"""
    global lock_status

    if SIMULATION_MODE:
        log_message(f"🔓 [SIM] Fechadura {lock_id} aberta por {seconds}s!")
        lock_status['state'] = 'aberta'
        lock_status['last_payment_time'] = datetime.now().isoformat()
        lock_status['message'] = f"Pagamento confirmado ✅ Fechadura aberta {seconds}s 🔓"
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

        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message(f"🔓 Fechadura {lock_id} ABERTA!")
            lock_status['state'] = 'aberta'
            lock_status['last_payment_time'] = datetime.now().isoformat()
            lock_status['message'] = f"Pagamento confirmado ✅ Fechadura aberta {seconds}s 🔓"
            return True
        else:
            log_message(f"❌ Erro TTLock: {result.get('errmsg', 'Unknown')}")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro abertura: {str(e)}")
        return False
    finally:
        # Fecha automaticamente após OPEN_SECONDS
        def fechar():
            global lock_status
            threading.Event().wait(seconds)
            lock_status['state'] = 'fechada'
            lock_status['message'] = 'Fechadura fechada 🔒'
            log_message(f"🔒 Fechadura {lock_id} fechada automaticamente.")

        threading.Thread(target=fechar).start()


def verificar_transacao_pagbank(notification_code):
    """Consulta a transação no PagBank para confirmar pagamento"""
    url = f"https://ws.pagseguro.uol.com.br/v3/transactions/notifications/{notification_code}?email={PAG_EMAIL}&token={PAG_TOKEN}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        status = int(data.get("status", 0))
        reference = data.get("reference", "N/A")
        log_message(f"🔎 Transação {reference} com status {status}")
        return status in [3, 4]
    except Exception as e:
        log_message(f"❌ Erro ao verificar transação: {str(e)}")
        return False


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    log_message("📥 PagBank webhook recebido")
    content_type = request.headers.get('Content-Type', '')

    if 'application/x-www-form-urlencoded' in content_type:
        notification_type = request.form.get('notificationType')
        notification_code = request.form.get('notificationCode')

        if notification_type == 'transaction' and notification_code:
            if verificar_transacao_pagbank(notification_code):
                log_message("✅ Pagamento confirmado! Abrindo fechadura...")
                threading.Thread(target=open_ttlock, args=(TT_LOCK_ID, OPEN_SECONDS)).start()
            else:
                log_message("⚠️ Pagamento não confirmado. Fechadura NÃO será aberta.")
        return ('', 200)

    return ('', 200)


@app.route('/status', methods=['GET'])
def status():
    """Rota para a maquininha consultar o status da fechadura"""
    return jsonify(lock_status)


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'Sistema PagBank + TTLock funcionando!',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    log_message("🚀 Sistema PagBank + TTLock SEGURO")
    log_message(f"🔧 Modo: {'SIMULAÇÃO' if SIMULATION_MODE else 'REAL'}")
    get_ttlock_access_token()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
