#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot dedicado APENAS para pré-apontamento
Sem interferência do sistema principal
"""

from flask import Flask, request
import sys
import os

# Adicionar imports necessários
from pre_apontamento import processar_pre_apontamento
import requests

app = Flask(__name__)

# Configurações Z-API
INSTANCE_ID = os.environ.get('INSTANCE_ID')
TOKEN = os.environ.get('TOKEN')
CLIENT_TOKEN = os.environ.get('CLIENT_TOKEN')

def enviar_mensagem(telefone, mensagem):
    """Envia mensagem via Z-API"""
    try:
        if not all([INSTANCE_ID, TOKEN, CLIENT_TOKEN]):
            print("[ERRO] Credenciais Z-API não configuradas")
            return False
            
        url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
        
        payload = {
            "phone": telefone,
            "message": mensagem
        }
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": CLIENT_TOKEN
        }
        
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code == 200
        
    except Exception as e:
        print(f"[ERRO] Falha ao enviar mensagem: {e}")
        return False

@app.route('/webhook_pre_apont', methods=['POST'])
def webhook_pre_apontamento():
    """Webhook dedicado APENAS para pré-apontamento"""
    try:
        dados = request.json
        print(f"[PRE-BOT] ========== WEBHOOK PRÉ-APONTAMENTO ==========")
        print(f"[PRE-BOT] Número: {dados.get('phone')}")
        print(f"[PRE-BOT] Tipo: {dados.get('type', 'UNKNOWN')}")
        
        numero = dados.get("phone")
        
        # Apenas processar se for mensagem de texto
        if dados.get("type") == "text" and dados.get("text", {}).get("message"):
            mensagem_original = dados["text"]["message"].strip()
            
            print(f"[PRE-BOT] 📝 Mensagem: '{mensagem_original[:100]}...'")
            print(f"[PRE-BOT] 🔍 Processando com pré-apontamento...")
            
            resultado_pre_apont = processar_pre_apontamento(numero, mensagem_original)
            
            print(f"[PRE-BOT] 📊 Resultado: {resultado_pre_apont}")
            
            if resultado_pre_apont['is_pre_apont']:
                print(f"[PRE-BOT] ✅ PRÉ-APONTAMENTO detectado!")
                enviar_mensagem(numero, resultado_pre_apont['resposta'])
                print(f"[PRE-BOT] 📤 Resposta enviada")
            else:
                print(f"[PRE-BOT] ➡️ Não é pré-apontamento")
        
        return '', 200
        
    except Exception as e:
        print(f"[PRE-BOT] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

@app.route('/test_pre_apont', methods=['GET'])
def test_pre_apontamento():
    """Endpoint de teste"""
    return {
        'status': 'ok',
        'message': 'Bot pré-apontamento funcionando',
        'endpoints': {
            'webhook': '/webhook_pre_apont',
            'test': '/test_pre_apont'
        }
    }

if __name__ == '__main__':
    print("🚀 INICIANDO BOT PRÉ-APONTAMENTO DEDICADO")
    print("📡 Endpoint: /webhook_pre_apont")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=False)
