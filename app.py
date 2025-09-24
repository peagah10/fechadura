import os
import hashlib
import threading
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# =================== CONFIGURAÇÕES OTIMIZADAS PARA PRODUÇÃO ===================
PAG_TOKEN = os.getenv('PAG_TOKEN', '')
TT_CLIENT_ID = os.getenv('TT_CLIENT_ID', '')
TT_CLIENT_SECRET = os.getenv('TT_CLIENT_SECRET', '')
TT_EMAIL = os.getenv('TT_EMAIL', '')
TT_PASSWORD = os.getenv('TT_PASSWORD', '')
TT_LOCK_ID = os.getenv('TT_LOCK_ID', '')
TT_API_BASE = os.getenv('TT_API_BASE', 'https://euapi.sciener.com')
OPEN_SECONDS = int(os.getenv('OPEN_SECONDS', '8'))

# ⚡ MODO PRODUÇÃO APENAS - SEM SIMULAÇÃO
SIMULATION_MODE = False

# Validação obrigatória - FALHA SE CONFIGURAÇÕES AUSENTES
required_configs = ['PAG_TOKEN', 'TT_CLIENT_ID', 'TT_CLIENT_SECRET', 'TT_EMAIL', 'TT_PASSWORD', 'TT_LOCK_ID']
missing_configs = [config for config in required_configs if not os.getenv(config)]
if missing_configs:
    raise ValueError(f"❌ ERRO FATAL: Configurações obrigatórias ausentes: {', '.join(missing_configs)}")

# Cache otimizado para token TTLock
token_cache = {
    'access_token': None,
    'expires_at': None,
    'last_refresh': None
}

# Status da fechadura com métricas de tempo
lock_status = {
    'state': 'fechada',
    'last_payment_time': None,
    'last_open_time': None,
    'response_time_ms': None,
    'message': 'Aguardando pagamento...'
}


def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f"[{timestamp}] {message}")


def get_ttlock_access_token():
    """⚡ Obtém token TTLock com cache otimizado"""
    now = datetime.now()
    
    # Cache hit - retorna imediatamente
    if token_cache['access_token'] and token_cache['expires_at'] and now < token_cache['expires_at']:
        return token_cache['access_token']

    start_time = time.time()
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
        
        # ⚡ Timeout reduzido para 3 segundos
        response = requests.post(url, data=data, timeout=3)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)

        elapsed = int((time.time() - start_time) * 1000)
        
        if access_token:
            # Cache com 90% do tempo de vida
            cache_time = expires_in * 0.9
            token_cache['access_token'] = access_token
            token_cache['expires_at'] = now + timedelta(seconds=cache_time)
            token_cache['last_refresh'] = now
            log_message(f"✅ Token TTLock obtido em {elapsed}ms")
            return access_token
        else:
            log_message(f"❌ Token não encontrado (tempo: {elapsed}ms)")
            return None

    except requests.exceptions.Timeout:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"⏰ TIMEOUT ao obter token TTLock ({elapsed}ms)")
        return None
    except requests.exceptions.RequestException as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro rede token TTLock ({elapsed}ms): {str(e)}")
        return None
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro inesperado token ({elapsed}ms): {str(e)}")
        return None


def close_ttlock(lock_id):
    """⚡ Fecha a fechadura TTLock fisicamente com timeout otimizado"""
    start_time = time.time()
    
    try:
        access_token = get_ttlock_access_token()
        if not access_token:
            log_message("❌ Token indisponível para fechamento")
            return False

        url = f"{TT_API_BASE}/v3/lock/lock"
        data = {
            'clientId': TT_CLIENT_ID,
            'accessToken': access_token,
            'lockId': lock_id,
            'date': int(datetime.now().timestamp() * 1000)
        }

        # ⚡ Timeout reduzido para 4 segundos
        response = requests.post(url, data=data, timeout=4)
        response.raise_for_status()
        result = response.json()

        elapsed = int((time.time() - start_time) * 1000)

        if result.get('errcode') == 0:
            log_message(f"🔒 Fechadura {lock_id} FECHADA em {elapsed}ms!")
            return True
        else:
            error_msg = result.get('errmsg', 'Unknown')
            log_message(f"❌ Erro fechar TTLock ({elapsed}ms): {error_msg}")
            return False

    except requests.exceptions.Timeout:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"⏰ TIMEOUT ao fechar fechadura ({elapsed}ms)")
        return False
    except requests.exceptions.RequestException as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro rede fechar ({elapsed}ms): {str(e)}")
        return False
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro inesperado fechar ({elapsed}ms): {str(e)}")
        return False


def open_ttlock(lock_id, seconds):
    """⚡ Abre a fechadura TTLock com velocidade otimizada"""
    global lock_status
    start_time = time.time()

    try:
        # ⚡ Token já deve estar em cache para máxima velocidade
        access_token = get_ttlock_access_token()
        if not access_token:
            log_message("❌ FALHA CRÍTICA: Token indisponível para abertura")
            lock_status['message'] = 'Erro: Token indisponível ❌'
            return False

        url = f"{TT_API_BASE}/v3/lock/unlock"
        data = {
            'clientId': TT_CLIENT_ID,
            'accessToken': access_token,
            'lockId': lock_id,
            'date': int(datetime.now().timestamp() * 1000)
        }

        # ⚡ Timeout de apenas 4 segundos para máxima velocidade
        response = requests.post(url, data=data, timeout=4)
        response.raise_for_status()
        result = response.json()

        elapsed = int((time.time() - start_time) * 1000)
        open_time = datetime.now()

        if result.get('errcode') == 0:
            log_message(f"🔓 FECHADURA ABERTA EM {elapsed}ms! Lock {lock_id}")
            lock_status.update({
                'state': 'aberta',
                'last_payment_time': open_time.isoformat(),
                'last_open_time': open_time.isoformat(),
                'response_time_ms': elapsed,
                'message': f"✅ ABERTA em {elapsed}ms - Fecha em {seconds}s 🔓"
            })
            
            # ⚡ Agendar fechamento automático otimizado
            def fechar_automatico():
                time.sleep(seconds)  # Usa sleep direto para maior precisão
                close_start = time.time()
                
                if close_ttlock(lock_id):
                    close_elapsed = int((time.time() - close_start) * 1000)
                    lock_status.update({
                        'state': 'fechada',
                        'message': f'🔒 Fechada automaticamente em {close_elapsed}ms'
                    })
                    log_message(f"🔒 Auto-fechamento em {close_elapsed}ms após {seconds}s")
                else:
                    lock_status['message'] = 'Erro no fechamento automático ❌'
                    log_message(f"❌ FALHA no fechamento automático da fechadura {lock_id}")
            
            threading.Thread(target=fechar_automatico, daemon=True).start()
            return True
        else:
            error_msg = result.get('errmsg', 'Erro desconhecido')
            log_message(f"❌ Erro TTLock ({elapsed}ms): {error_msg}")
            lock_status.update({
                'response_time_ms': elapsed,
                'message': f'Erro abertura ({elapsed}ms): {error_msg} ❌'
            })
            return False

    except requests.exceptions.Timeout:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"⏰ TIMEOUT CRÍTICO abertura ({elapsed}ms)")
        lock_status.update({
            'response_time_ms': elapsed,
            'message': f'TIMEOUT abertura ({elapsed}ms) ❌'
        })
        return False
    except requests.exceptions.RequestException as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro rede abertura ({elapsed}ms): {str(e)}")
        lock_status.update({
            'response_time_ms': elapsed,
            'message': f'Erro rede ({elapsed}ms): {str(e)} ❌'
        })
        return False
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro crítico abertura ({elapsed}ms): {str(e)}")
        lock_status.update({
            'response_time_ms': elapsed,
            'message': f'Erro crítico ({elapsed}ms) ❌'
        })
        return False


def parse_pagseguro_xml(xml_content):
    """⚡ Parse XML PagSeguro otimizado"""
    try:
        root = ET.fromstring(xml_content)
        
        # Busca direta por elementos necessários
        status_element = root.find('status')
        reference_element = root.find('reference')
        
        return {
            'status': int(status_element.text) if status_element is not None else 0,
            'reference': reference_element.text if reference_element is not None else 'N/A'
        }
    except ET.ParseError as e:
        log_message(f"❌ XML inválido: {str(e)}")
        return None
    except (ValueError, AttributeError) as e:
        log_message(f"❌ Dados XML inválidos: {str(e)}")
        return None


def verificar_transacao_pagbank(notification_code):
    """⚡ Verificação PagBank otimizada para velocidade máxima"""
    if not notification_code:
        log_message("❌ Notification code vazio")
        return False
        
    start_time = time.time()
    url = f"https://ws.pagseguro.uol.com.br/v3/transactions/notifications/{notification_code}"
    
    try:
        params = {
            'token': PAG_TOKEN
        }
        
        # ⚡ Timeout agressivo de 5 segundos para não atrasar
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        elapsed = int((time.time() - start_time) * 1000)
        
        # Parse otimizado da resposta XML
        transaction_data = parse_pagseguro_xml(response.text)
        
        if transaction_data:
            status = transaction_data['status']
            reference = transaction_data['reference']
            log_message(f"🔎 Transação {reference} status {status} ({elapsed}ms)")
            
            # Status 3 = Paga, Status 4 = Disponível (liberação imediata)
            is_paid = status in [3, 4]
            log_message(f"💰 Pagamento {'CONFIRMADO' if is_paid else 'PENDENTE'} ({elapsed}ms)")
            return is_paid
        else:
            log_message(f"❌ Parse XML falhou ({elapsed}ms)")
            return False
            
    except requests.exceptions.Timeout:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"⏰ TIMEOUT verificação PagBank ({elapsed}ms)")
        return False
    except requests.exceptions.RequestException as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro rede PagBank ({elapsed}ms): {str(e)}")
        return False
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        log_message(f"❌ Erro crítico verificação ({elapsed}ms): {str(e)}")
        return False


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """⚡ Webhook otimizado para resposta instantânea"""
    webhook_start = time.time()
    log_message("📥 WEBHOOK PagBank recebido")
    
    try:
        content_type = request.headers.get('Content-Type', '')

        if 'application/x-www-form-urlencoded' in content_type:
            notification_type = request.form.get('notificationType')
            notification_code = request.form.get('notificationCode')

            log_message(f"📋 Tipo: {notification_type}, Código: {notification_code}")

            if notification_type == 'transaction' and notification_code:
                # ⚡ Inicia verificação imediatamente em thread separada
                def processar_pagamento():
                    process_start = time.time()
                    if verificar_transacao_pagbank(notification_code):
                        log_message("✅ PAGAMENTO CONFIRMADO! Abrindo fechadura AGORA...")
                        open_ttlock(TT_LOCK_ID, OPEN_SECONDS)
                    else:
                        log_message("⚠️ Pagamento não confirmado - fechadura permanece fechada")
                    
                    total_time = int((time.time() - process_start) * 1000)
                    log_message(f"⚡ Processamento total: {total_time}ms")

                # Executa processamento sem bloquear resposta do webhook
                threading.Thread(target=processar_pagamento, daemon=True).start()
            else:
                log_message("⚠️ Dados webhook inválidos")
        
        webhook_elapsed = int((time.time() - webhook_start) * 1000)
        log_message(f"📤 Webhook respondido em {webhook_elapsed}ms")
        return ('OK', 200)
        
    except Exception as e:
        webhook_elapsed = int((time.time() - webhook_start) * 1000)
        log_message(f"❌ ERRO WEBHOOK ({webhook_elapsed}ms): {str(e)}")
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
