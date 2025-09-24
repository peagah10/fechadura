import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

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
    """Log com timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


def verify_signature(payload, header_signature):
    """Verifica a assinatura HMAC do webhook do PagBank"""
    if not PAG_WEBHOOK_SECRET:
        log_message("⚠️  AVISO: PAG_WEBHOOK_SECRET não configurado - pulando validação")
        return True

    if not header_signature:
        log_message("❌ Header X-Signature não encontrado")
        return False

    try:
        if header_signature.startswith('sha256='):
            header_signature = header_signature[7:]

        expected_signature = hmac.new(
            PAG_WEBHOOK_SECRET.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, header_signature)

        if is_valid:
            log_message("✅ Assinatura do webhook validada com sucesso")
        else:
            log_message("❌ Assinatura do webhook inválida")

        return is_valid

    except Exception as e:
        log_message(f"❌ Erro ao validar assinatura: {str(e)}")
        return False


def get_ttlock_access_token():
    """Obtém token de acesso da API TTLock com cache"""
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
        
        # Criptografar senha em MD5
        password_md5 = hashlib.md5(TT_PASSWORD.encode('utf-8')).hexdigest()
        
        data = {
            'client_id': TT_CLIENT_ID,
            'client_secret': TT_CLIENT_SECRET,
            'grant_type': 'password',
            'username': TT_EMAIL,
            'password': password_md5
        }

        # REDUZIDO: timeout de 10s para 3s
        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            # Cache do token por 90% do tempo de vida
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            
            log_message("✅ Token TTLock obtido (cached)")
            return access_token
        else:
            log_message(f"❌ Token não encontrado")
            return None

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro token TTLock: {str(e)}")
        return None


def open_ttlock(lock_id, seconds):
    """Abre a fechadura TTLock - OTIMIZADA"""
    if SIMULATION_MODE:
        log_message(f"🔓 [SIM] Fechadura {lock_id} aberta!")
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

        # REDUZIDO: timeout de 10s para 5s
        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message(f"🔓 Fechadura {lock_id} ABERTA!")
            return True
        else:
            log_message(f"❌ Erro TTLock: {result.get('errmsg', 'Unknown')}")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro abertura: {str(e)}")
        return False


@app.route('/', methods=['GET'])
def home():
    """Rota principal - informações do sistema"""
    return jsonify({
        'message': 'Sistema PagBank + TTLock funcionando!',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Recebe webhooks do PagBank - OTIMIZADO"""
    try:
        log_message("📥 PagBank webhook")
        
        # Verificar se é form-encoded (PagBank)
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/x-www-form-urlencoded' in content_type:
            # Formato PagBank (form-encoded)
            notification_code = request.form.get('notificationCode')
            notification_type = request.form.get('notificationType')
            
            if notification_type == 'transaction' and notification_code:
                log_message(f"💳 Transação: {notification_code[:20]}...")
                log_message("🔓 ABRINDO FECHADURA...")
                
                if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                    return jsonify({'status': 'success'}), 200
                else:
                    return jsonify({'status': 'error'}), 500
            else:
                return jsonify({'status': 'ignored'}), 200
        
        else:
            # Formato JSON (testes manuais)
            payload = request.get_data()
            header_signature = request.headers.get('X-Signature', '')
            
            if not verify_signature(payload, header_signature):
                return jsonify({'error': 'Assinatura inválida'}), 401
            
            try:
                webhook_data = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                return jsonify({'error': 'JSON inválido'}), 400
            
            status = webhook_data.get('status', '')
            
            if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
                log_message("🔓 ABRINDO FECHADURA (teste)...")
                if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                    return jsonify({'status': 'success'}), 200
                else:
                    return jsonify({'status': 'error'}), 500
            else:
                return jsonify({'status': 'ignored'}), 200
            
    except Exception as e:
        log_message(f"❌ Erro: {str(e)}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Rota de teste - OTIMIZADA"""
    if not SIMULATION_MODE:
        return jsonify({'error': 'Rota de teste desabilitada no modo real'}), 403
    
    try:
        log_message("🧪 Teste manual")
        payload = request.get_data()
        
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'JSON inválido'}), 400

        status = webhook_data.get('status', '')

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("🔓 ABRINDO (teste)...")
            if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'error'}), 500
        else:
            return jsonify({'status': 'ignored'}), 200

    except Exception as e:
        log_message(f"❌ Erro teste: {str(e)}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/debug/ttlock', methods=['GET'])
def debug_ttlock():
    """Rota para debug da autenticação TTLock"""
    try:
        if SIMULATION_MODE:
            return jsonify({
                'status': 'simulation_mode',
                'message': 'Modo simulação ativo',
                'simulation_mode': True,
                'lock_id': TT_LOCK_ID
            })
        
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
        
        return jsonify({
            'status_code': response.status_code,
            'response': response.text,
            'cache_status': 'cached' if token_cache['access_token'] else 'empty',
            'simulation_mode': SIMULATION_MODE
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})


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
    log_message("🚀 Sistema PagBank + TTLock OTIMIZADO")
    log_message(f"🔧 Modo: {'SIMULAÇÃO' if SIMULATION_MODE else 'REAL'}")
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
