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
TT_LOCK_ID = os.getenv('TT_LOCK_ID', '')
TT_API_BASE = os.getenv('TT_API_BASE', 'https://euopen.sciener.com')
OPEN_SECONDS = int(os.getenv('OPEN_SECONDS', '8'))
SIMULATION_MODE = os.getenv('SIMULATION_MODE', 'true').lower() == 'true'


def log_message(message):
    """Log com timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


def verify_signature(payload, header_signature):
    """
    Verifica a assinatura HMAC do webhook do PagBank
    """
    if not PAG_WEBHOOK_SECRET:
        log_message("⚠️  AVISO: PAG_WEBHOOK_SECRET não configurado - "
                    "pulando validação")
        return True

    if not header_signature:
        log_message("❌ Header X-Signature não encontrado")
        return False

    try:
        # Remove o prefixo 'sha256=' se existir
        if header_signature.startswith('sha256='):
            header_signature = header_signature[7:]

        # Calcula a assinatura esperada
        expected_signature = hmac.new(
            PAG_WEBHOOK_SECRET.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Compara as assinaturas
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
    """
    Obtém token de acesso da API TTLock
    """
    if SIMULATION_MODE:
        log_message("🔧 [SIMULAÇÃO] Obtendo token de acesso TTLock...")
        return "token_simulado_123"

    try:
        url = f"{TT_API_BASE}/oauth2/token"
        data = {
            'client_id': TT_CLIENT_ID,
            'client_secret': TT_CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }

        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()

        token_data = response.json()
        access_token = token_data.get('access_token')

        if access_token:
            log_message("✅ Token de acesso TTLock obtido com sucesso")
            return access_token
        else:
            log_message("❌ Token de acesso não encontrado na "
                        "resposta da TTLock")
            return None

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao obter token TTLock: {str(e)}")
        return None


def open_ttlock(lock_id, seconds):
    """
    Abre a fechadura TTLock por X segundos
    """
    if SIMULATION_MODE:
        log_message(f"🔧 [SIMULAÇÃO] Abrindo fechadura {lock_id} por "
                    f"{seconds} segundos...")
        return True

    try:
        # Obtém token de acesso
        access_token = get_ttlock_access_token()
        if not access_token:
            return False

        # Chama API para abrir fechadura
        url = f"{TT_API_BASE}/v3/lock/unlock"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        data = {
            'lockId': lock_id,
            'unlockTime': seconds * 1000  # TTLock usa milissegundos
        }

        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()

        result = response.json()

        if result.get('errcode') == 0:
            log_message(f"✅ Fechadura {lock_id} aberta por {seconds} "
                        "segundos")
            return True
        else:
            log_message(f"❌ Erro da TTLock: "
                        f"{result.get('errmsg', 'Erro desconhecido')}")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Erro ao abrir fechadura: {str(e)}")
        return False


@app.route('/webhook/pagamento', methods=['POST'])
def webhook_pagamento():
    """
    Endpoint que recebe webhooks do PagBank
    """
    try:
        log_message("📥 Webhook recebido do PagBank")

        # Obtém dados da requisição
        payload = request.get_data()
        header_signature = request.headers.get('X-Signature', '')

        # Log do payload (apenas primeiros 200 caracteres por segurança)
        payload_preview = payload.decode('utf-8')[:200] + (
            '...' if len(payload) > 200 else '')
        log_message(f"📄 Payload: {payload_preview}")

        # Verifica assinatura
        if not verify_signature(payload, header_signature):
            log_message("❌ Webhook rejeitado - assinatura inválida")
            return jsonify({'error': 'Assinatura inválida'}), 401

        # Parse do JSON
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            log_message(f"❌ Erro ao fazer parse do JSON: {str(e)}")
            return jsonify({'error': 'JSON inválido'}), 400

        # Extrai informações do pagamento
        status = webhook_data.get('status', '')
        transaction_id = webhook_data.get('id', 'N/A')
        amount = webhook_data.get('amount', 0)

        log_message(f"💳 Pagamento ID: {transaction_id}")
        log_message(f"💰 Valor: R$ {amount/100:.2f}" if amount else
                    "💰 Valor: N/A")
        log_message(f"📊 Status: {status}")

        # Verifica se pagamento foi aprovado
        if status.lower() in ['paid', 'approved', 'autorizado', 'capturado']:
            log_message("✅ Pagamento aprovado - iniciando abertura da "
                        "fechadura")

            # Abre a fechadura
            success = open_ttlock(TT_LOCK_ID, OPEN_SECONDS)

            if success:
                log_message("🚪 Fechadura aberta com sucesso!")
                return jsonify({
                    'status': 'success',
                    'message': 'Fechadura aberta',
                    'transaction_id': transaction_id
                }), 200
            else:
                log_message("❌ Falha ao abrir fechadura")
                return jsonify({
                    'status': 'error',
                    'message': 'Falha ao abrir fechadura',
                    'transaction_id': transaction_id
                }), 500

        else:
            log_message(f"⏳ Pagamento não aprovado (status: {status}) - "
                        "fechadura não será aberta")
            return jsonify({
                'status': 'ignored',
                'message': 'Pagamento não aprovado',
                'transaction_id': transaction_id
            }), 200

    except Exception as e:
        log_message(f"❌ Erro interno: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check
    """
    return jsonify({
        'status': 'ok',
        'simulation_mode': SIMULATION_MODE,
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def home():
    """
    Página inicial com informações do sistema
    """
    return jsonify({
        'message': 'Sistema PagBank + TTLock ativo',
        'endpoints': {
            'webhook': '/webhook/pagamento',
            'health': '/health'
        },
        'simulation_mode': SIMULATION_MODE
    }), 200


# Para Vercel, exportamos o app diretamente
# Verifica configurações essenciais na inicialização
if not SIMULATION_MODE:
    if not TT_CLIENT_ID or not TT_CLIENT_SECRET:
        print("⚠️  AVISO: Credenciais TTLock não configuradas")
    if not TT_LOCK_ID:
        print("⚠️  AVISO: ID da fechadura não configurado")

if not PAG_WEBHOOK_SECRET:
    print("⚠️  AVISO: Secret do webhook PagBank não configurado")