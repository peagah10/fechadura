import os
import hashlib
import threading
import xml.etree.ElementTree as ET
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

# Validação de configurações obrigatórias
required_configs = ['PAG_EMAIL', 'PAG_TOKEN', 'TT_CLIENT_ID', 'TT_CLIENT_SECRET', 'TT_EMAIL', 'TT_PASSWORD', 'TT_LOCK_ID']
missing_configs = [config for config in required_configs if not os.getenv(config)]
if missing_configs and not SIMULATION_MODE:
    raise ValueError(f"Configurações obrigatórias ausentes: {', '.join(missing_configs)}")

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
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        if access_token:
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            log_message("✅ Token TTLock obtido com sucesso")
            return access_token
        else:
            log_message("❌ Token não encontrado na resposta")
            return None

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao obter token TTLock: {str(e)}")
        return None
    except Exception as e:
        log_message(f"❌ Erro inesperado ao obter token: {str(e)}")
        return None


def close_ttlock(lock_id):
    """Fecha a fechadura TTLock fisicamente"""
    if SIMULATION_MODE:
        log_message(f"🔒 [SIM] Fechadura {lock_id} fechada!")
        return True

    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            return False

        url = f"{TT_API_BASE}/v3/lock/lock"
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
            log_message(f"🔒 Fechadura {lock_id} FECHADA!")
            return True
        else:
            log_message(f"❌ Erro ao fechar TTLock: {result.get('errmsg', 'Unknown')}")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao fechar fechadura: {str(e)}")
        return False
    except Exception as e:
        log_message(f"❌ Erro inesperado ao fechar: {str(e)}")
        return False


def open_ttlock(lock_id, seconds):
    """Abre a fechadura TTLock e atualiza status"""
    global lock_status

    if SIMULATION_MODE:
        log_message(f"🔓 [SIM] Fechadura {lock_id} aberta por {seconds}s!")
        lock_status['state'] = 'aberta'
        lock_status['last_payment_time'] = datetime.now().isoformat()
        lock_status['message'] = f"Pagamento confirmado ✅ Fechadura aberta {seconds}s 🔓"
        
        # Agendar fechamento em modo simulação
        def fechar_simulacao():
            threading.Event().wait(seconds)
            lock_status['state'] = 'fechada'
            lock_status['message'] = 'Fechadura fechada automaticamente 🔒'
            log_message(f"🔒 [SIM] Fechadura {lock_id} fechada automaticamente.")
        
        threading.Thread(target=fechar_simulacao, daemon=True).start()
        return True

    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            log_message("❌ Não foi possível obter token para abrir fechadura")
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
            log_message(f"🔓 Fechadura {lock_id} ABERTA com sucesso!")
            lock_status['state'] = 'aberta'
            lock_status['last_payment_time'] = datetime.now().isoformat()
            lock_status['message'] = f"Pagamento confirmado ✅ Fechadura aberta {seconds}s 🔓"
            
            # Agendar fechamento automático
            def fechar_automatico():
                threading.Event().wait(seconds)
                if close_ttlock(lock_id):
                    lock_status['state'] = 'fechada'
                    lock_status['message'] = 'Fechadura fechada automaticamente 🔒'
                    log_message(f"🔒 Fechadura {lock_id} fechada automaticamente após {seconds}s.")
                else:
                    lock_status['message'] = 'Erro ao fechar automaticamente ❌'
                    log_message(f"❌ Erro ao fechar automaticamente fechadura {lock_id}")
            
            threading.Thread(target=fechar_automatico, daemon=True).start()
            return True
        else:
            error_msg = result.get('errmsg', 'Erro desconhecido')
            log_message(f"❌ Erro TTLock: {error_msg}")
            lock_status['message'] = f'Erro ao abrir fechadura: {error_msg} ❌'
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro de rede ao abrir fechadura: {str(e)}")
        lock_status['message'] = f'Erro de rede: {str(e)} ❌'
        return False
    except Exception as e:
        log_message(f"❌ Erro inesperado ao abrir fechadura: {str(e)}")
        lock_status['message'] = f'Erro inesperado: {str(e)} ❌'
        return False


def parse_pagseguro_xml(xml_content):
    """Parse da resposta XML do PagSeguro"""
    try:
        root = ET.fromstring(xml_content)
        
        # Extrai informações relevantes
        status = root.find('status')
        reference = root.find('reference')
        
        return {
            'status': int(status.text) if status is not None else 0,
            'reference': reference.text if reference is not None else 'N/A'
        }
    except ET.ParseError as e:
        log_message(f"❌ Erro ao fazer parse do XML: {str(e)}")
        return None
    except Exception as e:
        log_message(f"❌ Erro inesperado no parse XML: {str(e)}")
        return None


def verificar_transacao_pagbank(notification_code):
    """Consulta a transação no PagBank para confirmar pagamento"""
    if not notification_code:
        log_message("❌ Código de notificação não fornecido")
        return False
        
    # URL atualizada da API PagSeguro
    url = f"https://ws.pagseguro.uol.com.br/v3/transactions/notifications/{notification_code}"
    
    try:
        params = {
            'email': PAG_EMAIL,
            'token': PAG_TOKEN
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # Parse da resposta XML
        transaction_data = parse_pagseguro_xml(response.text)
        
        if transaction_data:
            status = transaction_data['status']
            reference = transaction_data['reference']
            log_message(f"🔎 Transação {reference} com status {status}")
            
            # Status 3 = Paga, Status 4 = Disponível
            return status in [3, 4]
        else:
            log_message("❌ Não foi possível fazer parse da resposta")
            return False
            
    except requests.exceptions.Timeout:
        log_message("❌ Timeout ao verificar transação PagBank")
        return False
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro de rede ao verificar transação: {str(e)}")
        return False
    except Exception as e:
        log_message(f"❌ Erro inesperado ao verificar transação: {str(e)}")
        return False


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    log_message("📥 Webhook PagBank recebido")
    
    try:
        content_type = request.headers.get('Content-Type', '')

        if 'application/x-www-form-urlencoded' in content_type:
            notification_type = request.form.get('notificationType')
            notification_code = request.form.get('notificationCode')

            log_message(f"📋 Tipo: {notification_type}, Código: {notification_code}")

            if notification_type == 'transaction' and notification_code:
                if verificar_transacao_pagbank(notification_code):
                    log_message("✅ Pagamento confirmado! Iniciando abertura da fechadura...")
                    # Executa em thread separada para não bloquear resposta do webhook
                    threading.Thread(
                        target=open_ttlock, 
                        args=(TT_LOCK_ID, OPEN_SECONDS),
                        daemon=True
                    ).start()
                else:
                    log_message("⚠️ Pagamento não confirmado. Fechadura permanecerá fechada.")
            else:
                log_message("⚠️ Dados de notificação inválidos ou incompletos")
                
        return ('OK', 200)
        
    except Exception as e:
        log_message(f"❌ Erro no webhook: {str(e)}")
        return ('ERROR', 500)


@app.route('/status', methods=['GET'])
def status():
    """Rota para consultar o status da fechadura"""
    try:
        return jsonify({
            **lock_status,
            'timestamp': datetime.now().isoformat(),
            'simulation_mode': SIMULATION_MODE
        })
    except Exception as e:
        log_message(f"❌ Erro na rota status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/manual/open', methods=['POST'])
def manual_open():
    """Rota para abertura manual (teste)"""
    try:
        seconds = int(request.json.get('seconds', OPEN_SECONDS))
        success = open_ttlock(TT_LOCK_ID, seconds)
        return jsonify({
            'success': success,
            'message': 'Abertura iniciada' if success else 'Falha na abertura',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        log_message(f"❌ Erro na abertura manual: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'Sistema PagBank + TTLock',
        'status': 'online',
        'version': '2.0.0',
        'simulation_mode': SIMULATION_MODE,
        'lock_id': TT_LOCK_ID,
        'cache_status': 'cached' if token_cache['access_token'] else 'empty',
        'lock_status': lock_status,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        # Verifica conectividade básica
        health_status = {
            'status': 'healthy',
            'simulation_mode': SIMULATION_MODE,
            'lock_id': TT_LOCK_ID,
            'cache_status': 'cached' if token_cache['access_token'] else 'empty',
            'timestamp': datetime.now().isoformat()
        }
        
        # Em modo real, testa conectividade com TTLock
        if not SIMULATION_MODE:
            token = get_ttlock_access_token()
            health_status['ttlock_connectivity'] = 'ok' if token else 'error'
        
        return jsonify(health_status)
        
    except Exception as e:
        log_message(f"❌ Erro no health check: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


if __name__ == '__main__':
    try:
        log_message("🚀 Iniciando Sistema PagBank + TTLock v2.0.0")
        log_message(f"🔧 Modo: {'SIMULAÇÃO' if SIMULATION_MODE else 'PRODUÇÃO'}")
        
        # Teste inicial de conectividade
        if not SIMULATION_MODE:
            log_message("🔗 Testando conectividade com TTLock...")
            initial_token = get_ttlock_access_token()
            if initial_token:
                log_message("✅ Conectividade TTLock OK")
            else:
                log_message("⚠️ Problema na conectividade TTLock - verifique configurações")
        
        port = int(os.getenv('PORT', 5000))
        log_message(f"🌐 Servidor rodando na porta {port}")
        app.run(host='0.0.0.0', port=port, debug=False)
        
    except Exception as e:
        log_message(f"💥 Erro fatal ao iniciar aplicação: {str(e)}")
        raise
