# Sistema PagBank + TTLock

Sistema simples para integrar pagamentos da Moderninha Smart 2 (PagBank) com fechadura inteligente TTLock.

## Funcionalidades

- Recebe webhooks do PagBank quando um pagamento é processado
- Valida assinatura HMAC para segurança
- Abre fechadura TTLock automaticamente quando pagamento é aprovado
- Logs detalhados de todas as operações
- Modo simulação para testes

## Instalação

1. **Clone ou baixe os arquivos do projeto**

2. **Instale as dependências:**
```bash
pip install -r requirements.txt