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
PAG_TOKEN = os.getenv('PAG_TOKEN', '')  # Token do PagBank
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
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


def verify_payment_with_pagbank(notification_code):
    """VERIFICA SE PAGAMENTO FOI REALMENTE APROVADO"""
    if SIMULATION_MODE:
        log_message("🔧 [SIM] Pagamento aprovado (simulação)")
        return True
    
    if not PAG_TOKEN:
        log_message("❌ PAG_TOKEN não configurado")
        return False
    
    try:
        # API do PagBank para consultar transação
        url = f"https://api.pagseguro.com/notifications/{notification_code}"
        headers = {
            'Authorization': f'Bearer {PAG_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        log_message(f"🔍 Consultando pagamento: {notification_code[:15]}...")
        
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        payment_data = response.json()
        
        # Verificar status do pagamento
        status = payment_data.get('status', '').lower()
        amount = payment_data.get('amount', 0)
        payment_id = payment_data.get('id', 'N/A')
        
        log_message(f"💳 ID: {payment_id} | Status: {status} | Valor: R$ {amount/100:.2f}")
        
        # SÓ APROVADOS
        approved_statuses = ['paid', 'approved', 'autorizado', 'capturado', 'available']
        
        if status in approved_statuses:
            log_message(f"✅ PAGAMENTO CONFIRMADO: {status.upper()}")
            return True
        else:
            log_message(f"❌ PAGAMENTO NÃO APROVADO: {status.upper()}")
            return False
            
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao consultar PagBank: {str(e)}")
        return False
    except Exception as e:
        log_message(f"❌ Erro verificação: {str(e)}")
        return False


def get_ttlock_access_token():
    """Token TTLock com cache"""
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

        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            return access_token
        
        return None

    except Exception as e:
        log_message(f"❌ Token TTLock: {str(e)[:30]}")
        return None


def open_ttlock_secure(lock_id):
    """Abertura SEGURA da fechadura"""
    if SIMULATION_MODE:
        log_message("🔓 [SIM] Fechadura aberta!")
        return True

    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            log_message("❌ Sem token TTLock")
            return False

        url = f"{TT_API_BASE}/v3/lock/unlock"
        data = {
            'clientId': TT_CLIENT_ID,
            'accessToken': access_token,
            'lockId': lock_id,
            'date': int(datetime.now().timestamp() * 1000)
        }

        response = requests.post(url, data=data, timeout=4)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message("🔓 FECHADURA ABERTA COM SEGURANÇA!")
            return True
        else:
            error_msg = result.get('errmsg', 'Erro desconhecido')
            log_message(f"❌ TTLock: {error_msg}")
            return False

    except Exception as e:
        log_message(f"❌ Erro abertura: {str(e)[:30]}")
        return False


def process_payment_securely(notification_code):
    """Processa pagamento com VERIFICAÇÃO DE SEGURANÇA"""
    def run():
        log_message("🔒 VERIFICANDO PAGAMENTO...")
        
        # ETAPA 1: Verificar se pagamento foi aprovado
        if verify_payment_with_pagbank(notification_code):
            log_message("🔓 Abrindo fechadura (pagamento confirmado)...")
            
            # ETAPA 2: Só agora abrir fechadura
            success = open_ttlock_secure(TT_LOCK_ID)
            
            if success:
                log_message("✅ PROCESSO COMPLETO: Pagamento + Abertura")
            else:
                log_message("❌ Pagamento OK, mas falha na abertura")
        else:
            log_message("🚫 FECHADURA NÃO ABERTA: Pagamento não confirmado")
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()


@app.route('/', methods=['GET'])
def home():
    """Rota principal"""
    return jsonify({
        'message': 'Sistema PagBank + TTLock SEGURO',
        'status': 'online',
        'simulation_mode': SIMULATION_MODE,
        'security': 'Só abre com pagamento confirmado',
        'lock_id': TT_LOCK_ID,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Webhook SEGURO - verifica pagamento antes de abrir"""
    try:
        log_message("📥 Webhook PagBank recebido")
        
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/x-www-form-urlencoded' in content_type:
            notification_code = request.form.get('notificationCode')
            notification_type = request.form.get('notificationType')
            
            log_message(f"📄 Type: {notification_type}")
            log_message(f"📄 Code: {notification_code[:20] if notification_code else 'None'}...")
            
            if notification_type == 'transaction' and notification_code:
                log_message("🔒 INICIANDO VERIFICAÇÃO SEGURA...")
                
                # PROCESSAMENTO SEGURO
                process_payment_securely(notification_code)
                
                # Resposta imediata
                return jsonify({
                    'status': 'received', 
                    'message': 'Verificando pagamento...'
                }), 200
            else:
                log_message("⏸️ Notificação ignorada")
                return jsonify({'status': 'ignored'}), 200
        
        else:
            # Testes manuais JSON (só em simulação)
            if not SIMULATION_MODE:
                return jsonify({'error': 'Formato não suportado em produção'}), 400
                
            try:
                webhook_data = json.loads(request.get_data().decode('utf-8'))
            except:
                return jsonify({'error': 'JSON inválido'}), 400
            
            status = webhook_data.get('status', '')
            
            if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
                log_message("🧪 TESTE: Simulando pagamento aprovado")
                process_payment_securely('TEST_CODE')
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'ignored'}), 200
            
    except Exception as e:
        log_message(f"❌ Erro webhook: {str(e)[:50]}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Teste manual SEGURO"""
    if not SIMULATION_MODE:
        return jsonify({'error': 'Testes desabilitados em produção'}), 403
    
    try:
        webhook_data = json.loads(request.get_data().decode('utf-8'))
        status = webhook_data.get('status', '')

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("🧪 TESTE MANUAL SEGURO")
            process_payment_securely('MANUAL_TEST')
            return jsonify({'status': 'testing'}), 200
        else:
            return jsonify({'status': 'ignored'}), 200

    except:
        return jsonify({'error': 'Erro'}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'mode': 'SIMULAÇÃO' if SIMULATION_MODE else 'PRODUÇÃO SEGURA',
        'security': 'Verificação de pagamento ativa',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    log_message("🚀 Sistema SEGURO PagBank + TTLock")
    log_message("🔒 SEGURANÇA: Só abre com pagamento confirmado")
    log_message(f"🔧 Modo: {'SIMULAÇÃO' if SIMULATION_MODE else 'PRODUÇÃO'}")
    
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
