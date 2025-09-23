import os
import hmac
import hashlib
import json
from datetime import datetime
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
TT_API_BASE = os.getenv('TT_API_BASE', 'https://api.ttlock.com')
OPEN_SECONDS = int(os.getenv('OPEN_SECONDS', '8'))
SIMULATION_MODE = os.getenv('SIMULATION_MODE', 'true').lower() == 'true'


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
    """Obtém token de acesso da API TTLock"""
    if SIMULATION_MODE:
        log_message("🔧 [SIMULAÇÃO] Obtendo token de acesso TTLock...")
        return "token_simulado_123"

    try:
        url = f"{TT_API_BASE}/oauth2/token"
        data = {
            'client_id': TT_CLIENT_ID,
            'client_secret': TT_CLIENT_SECRET,
            'grant_type': 'password',
            'username': TT_EMAIL,
            'password': TT_PASSWORD
        }

        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')

        if access_token:
            log_message("✅ Token de acesso TTLock obtido com sucesso")
            return access_token
        else:
            log_message(f"❌ Token não encontrado. Resposta: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao obter token TTLock: {str(e)}")
        return None


def open_ttlock(lock_id, seconds):
    """Abre a fechadura TTLock"""
    if SIMULATION_MODE:
        log_message(f"🔧 [SIMULAÇÃO] Abrindo fechadura {lock_id} por {seconds} segundos...")
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

        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message(f"✅ Fechadura {lock_id} aberta com sucesso")
            return True
        else:
            log_message(f"❌ Erro TTLock: {result}")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao abrir fechadura: {str(e)}")
        return False


@app.route('/', methods=['GET'])
def home():
    """Rota principal - informações do sistema"""
    return jsonify({
        'message': 'Sistema PagBank + TTLock funcionando!',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'endpoints': {
            'health': '/health',
            'webhook': '/webhook/pagamento (POST only)',
            'test': '/test/pagamento (POST only - sem HMAC)'
        },
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Recebe webhooks do PagBank (com verificação HMAC)"""
    try:
        log_message("📥 Webhook recebido do PagBank")
        payload = request.get_data()
        header_signature = request.headers.get('X-Signature', '')

        # Preview do payload
        preview = payload.decode('utf-8')[:200]
        log_message(f"📄 Payload: {preview}{'...' if len(payload) > 200 else ''}")

        # Verifica assinatura
        if not verify_signature(payload, header_signature):
            return jsonify({'error': 'Assinatura inválida'}), 401

        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'JSON inválido'}), 400

        status = webhook_data.get('status', '')
        transaction_id = webhook_data.get('id', 'N/A')
        amount = webhook_data.get('amount', 0)

        log_message(f"💳 Pagamento ID: {transaction_id} | Status: {status} | Valor: R$ {amount/100:.2f}")

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("✅ Pagamento aprovado - abrindo fechadura")
            if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                return jsonify({'status': 'success', 'message': 'Fechadura aberta'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Falha ao abrir fechadura'}), 500
        else:
            return jsonify({'status': 'ignored', 'message': 'Pagamento não aprovado'}), 200

    except Exception as e:
        log_message(f"❌ Erro interno: {str(e)}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Rota de teste sem verificação HMAC"""
    try:
        log_message("🧪 TESTE: Webhook recebido (sem verificação HMAC)")
        payload = request.get_data()
        
        # Preview do payload
        preview = payload.decode('utf-8')[:200]
        log_message(f"📄 TESTE - Payload: {preview}{'...' if len(payload) > 200 else ''}")
        
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'JSON inválido'}), 400

        status = webhook_data.get('status', '')
        transaction_id = webhook_data.get('id', 'N/A')
        amount = webhook_data.get('amount', 0)

        log_message(f"💳 TESTE - Pagamento ID: {transaction_id} | Status: {status} | Valor: R$ {amount/100:.2f}")

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("✅ TESTE - Pagamento aprovado - abrindo fechadura")
            if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                return jsonify({'status': 'success', 'message': 'Fechadura aberta (TESTE)', 'test_mode': True}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Falha ao abrir fechadura (TESTE)', 'test_mode': True}), 500
        else:
            return jsonify({'status': 'ignored', 'message': 'Pagamento não aprovado (TESTE)', 'test_mode': True}), 200

    except Exception as e:
        log_message(f"❌ TESTE - Erro interno: {str(e)}")
        return jsonify({'error': 'Erro interno', 'test_mode': True}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'simulation_mode': SIMULATION_MODE,
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    log_message("🚀 Iniciando sistema PagBank + TTLock")
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
