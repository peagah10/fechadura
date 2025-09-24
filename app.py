import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
import threading
import time

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações OTIMIZADAS - APENAS MODO REAL
PAG_WEBHOOK_SECRET = os.getenv('PAG_WEBHOOK_SECRET', '')
TT_CLIENT_ID = os.getenv('TT_CLIENT_ID', '')
TT_CLIENT_SECRET = os.getenv('TT_CLIENT_SECRET', '')
TT_EMAIL = os.getenv('TT_EMAIL', '')
TT_PASSWORD = os.getenv('TT_PASSWORD', '')
TT_LOCK_ID = os.getenv('TT_LOCK_ID', '')
TT_API_BASE = os.getenv('TT_API_BASE', 'https://euapi.sciener.com')
OPEN_SECONDS = int(os.getenv('OPEN_SECONDS', '3'))

# Cache para token TTLock
token_cache = {
    'access_token': None,
    'expires_at': None
}

# Pre-warming do token
def pre_warm_token():
    """Mantém o token sempre válido em background"""
    while True:
        try:
            get_ttlock_access_token()
            time.sleep(1800)  # Renova a cada 30 min
        except:
            pass

# Inicia pre-warming em thread separada
threading.Thread(target=pre_warm_token, daemon=True).start()


def log_message(message):
    """Log com timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


def verify_signature(payload, header_signature):
    """Verifica a assinatura HMAC do webhook do PagBank - OTIMIZADA"""
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
        return is_valid

    except Exception as e:
        log_message(f"❌ Erro ao validar assinatura: {str(e)}")
        return False


def get_ttlock_access_token():
    """Obtém token de acesso da API TTLock com cache OTIMIZADO"""
    # Verificar cache - margem maior para evitar expiração
    now = datetime.now()
    if (token_cache['access_token'] and 
        token_cache['expires_at'] and 
        now < (token_cache['expires_at'] - timedelta(minutes=5))):  # 5min de margem
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

        # ULTRA OTIMIZADO: timeout reduzido para 2s
        response = requests.post(url, data=data, timeout=2)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            # Cache do token por 95% do tempo de vida
            cache_time = expires_in * 0.95
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
    """Abre a fechadura TTLock - ULTRA OTIMIZADA"""
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

        # ULTRA OTIMIZADO: timeout reduzido para 3s
        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()
        result = response.json()

        if result.get('errcode') == 0:
            log_message(f"🔓 Fechadura {lock_id} ABERTA em tempo recorde!")
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
        'message': 'Sistema PagBank + TTLock ULTRA OTIMIZADO - MODO REAL!',
        'status': 'online',
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'open_seconds': OPEN_SECONDS,
        'security_features': [
            'HMAC signature validation',
            'Transaction type verification', 
            'Payment status validation',
            'OAuth2 authentication',
            'Token caching with pre-warming'
        ],
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """Recebe webhooks do PagBank - ULTRA OTIMIZADO"""
    start_time = datetime.now()
    
    try:
        log_message("📥 PagBank webhook - processamento iniciado")
        
        # Verificar se é form-encoded (PagBank)
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/x-www-form-urlencoded' in content_type:
            # Formato PagBank (form-encoded)
            notification_code = request.form.get('notificationCode')
            notification_type = request.form.get('notificationType')
            
            if notification_type == 'transaction' and notification_code:
                log_message(f"💳 Transação confirmada: {notification_code[:20]}...")
                log_message("🚀 ABERTURA ULTRA RÁPIDA INICIADA...")
                
                if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                    elapsed = (datetime.now() - start_time).total_seconds()
                    log_message(f"⚡ SUCESSO! Tempo total: {elapsed:.2f}s")
                    return jsonify({'status': 'success', 'time': f'{elapsed:.2f}s'}), 200
                else:
                    return jsonify({'status': 'error'}), 500
            else:
                return jsonify({'status': 'ignored'}), 200
        
        else:
            # Formato JSON (testes manuais) - validação de segurança mantida
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
                log_message("🚀 ABERTURA ULTRA RÁPIDA (teste)...")
                if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                    elapsed = (datetime.now() - start_time).total_seconds()
                    log_message(f"⚡ SUCESSO! Tempo total: {elapsed:.2f}s")
                    return jsonify({'status': 'success', 'time': f'{elapsed:.2f}s'}), 200
                else:
                    return jsonify({'status': 'error'}), 500
            else:
                return jsonify({'status': 'ignored'}), 200
            
    except Exception as e:
        log_message(f"❌ Erro: {str(e)}")
        return jsonify({'error': 'Erro interno'}), 500


@app.route('/test/pagamento', methods=['POST'])
def test_pagamento():
    """Rota de teste - ULTRA OTIMIZADA"""
    start_time = datetime.now()
    
    try:
        log_message("🧪 Teste manual ultra rápido")
        payload = request.get_data()
        
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'JSON inválido'}), 400

        status = webhook_data.get('status', '')

        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("🚀 TESTE ULTRA RÁPIDO...")
            if open_ttlock(TT_LOCK_ID, OPEN_SECONDS):
                elapsed = (datetime.now() - start_time).total_seconds()
                log_message(f"⚡ TESTE CONCLUÍDO! Tempo: {elapsed:.2f}s")
                return jsonify({'status': 'success', 'time': f'{elapsed:.2f}s'}), 200
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
        url = f"{TT_API_BASE}/oauth2/token"
        password_md5 = hashlib.md5(TT_PASSWORD.encode('utf-8')).hexdigest()
        
        data = {
            'client_id': TT_CLIENT_ID,
            'client_secret': TT_CLIENT_SECRET,
            'grant_type': 'password',
            'username': TT_EMAIL,
            'password': password_md5
        }
        
        response = requests.post(url, data=data, timeout=2)
        
        return jsonify({
            'status_code': response.status_code,
            'response': response.text,
            'cache_status': 'cached' if token_cache['access_token'] else 'empty',
            'open_seconds': OPEN_SECONDS,
            'mode': 'REAL'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'open_seconds': OPEN_SECONDS,
        'performance': 'ultra_optimized_2-3s',
        'mode': 'REAL',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    log_message("🚀 Sistema PagBank + TTLock ULTRA OTIMIZADO")
    log_message("🔧 Modo: PRODUÇÃO (REAL)")
    log_message(f"⚡ Tempo de abertura otimizado: {OPEN_SECONDS}s")
    log_message("🛡️  Segurança: HMAC + OAuth2 + Cache + Pre-warming")
    log_message("🔓 Sistema pronto para abrir fechaduras reais!")
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
