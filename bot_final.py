import pyodbc
import requests
from flask import Flask, request
from datetime import datetime
import re
import time
import os
import librosa
import soundfile as sf
import speech_recognition as sr
from collections import defaultdict
import functools
print = functools.partial(print, flush=True)


app = Flask(__name__)

# ================== CONFIG ==================
# Use variáveis de ambiente para produção (Railway, Heroku etc.)
INSTANCE_ID   = os.environ.get('INSTANCE_ID',   'SUA_INSTANCE_ID')
TOKEN         = os.environ.get('TOKEN',         'SEU_TOKEN')
CLIENT_TOKEN  = os.environ.get('CLIENT_TOKEN',  'SEU_CLIENT_TOKEN')

DB_SERVER     = os.environ.get('DB_SERVER',     'alrflorestal.database.windows.net')
DB_DATABASE   = os.environ.get('DB_DATABASE',   'Tabela_teste')
DB_USERNAME   = os.environ.get('DB_USERNAME',   'sqladmin')
DB_PASSWORD   = os.environ.get('DB_PASSWORD',   'SenhaForte123!')

# ================== CONTROLE ==================
ultimo_comando = {}
numeros_ja_notificados = set()
mensagens_processadas = {}
INTERVALO_MINIMO = 10  # segundos

cache_usuarios = {}

# ================== CONEXÃO SQL ==================
def conectar_db():
    try:
        conn = pyodbc.connect(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={DB_SERVER};'
            f'DATABASE={DB_DATABASE};'
            f'UID={DB_USERNAME};'
            f'PWD={DB_PASSWORD}'
        )
        return conn
    except Exception as e:
        print(f"[ERRO] Falha na conexão SQL: {e}")
        raise

def normalizar_telefone(telefone):
    if not telefone:
        return ""
    return ''.join(c for c in str(telefone) if c.isdigit())

def buscar_usuarios_autorizados():
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        query = """
        SELECT DISTINCT TELEFONE, USUARIO, PROJETO
        FROM USUARIOS WHERE TELEFONE IS NOT NULL AND TELEFONE != ''
        """
        cursor.execute(query)
        resultados = cursor.fetchall()
        conn.close()
        usuarios_data = {}
        for linha in resultados:
            telefone_original = linha[0]
            telefone_normalizado = normalizar_telefone(telefone_original)
            usuario = linha[1]
            projeto = str(linha[2])
            if telefone_normalizado not in usuarios_data:
                usuarios_data[telefone_normalizado] = {
                    'nome': usuario,
                    'projetos': set(),
                    'telefone_original': telefone_original
                }
            usuarios_data[telefone_normalizado]['projetos'].add(projeto)
        for telefone in usuarios_data:
            usuarios_data[telefone]['projetos'] = list(usuarios_data[telefone]['projetos'])
        return usuarios_data
    except Exception as e:
        print(f"[ERRO] Falha ao buscar usuários: {e}")
        return {}

def verificar_autorizacao(numero):
    global cache_usuarios
    cache_usuarios = buscar_usuarios_autorizados()
    numero_normalizado = normalizar_telefone(numero)
    print(f"[DEBUG] Numero recebido: {numero} | Normalizado: {numero_normalizado}")
    print(f"[DEBUG] Telefones autorizados: {list(cache_usuarios.keys())}")
    return numero_normalizado in cache_usuarios

def obter_projetos_usuario(numero):
    numero_normalizado = normalizar_telefone(numero)
    return cache_usuarios.get(numero_normalizado, {}).get('projetos', [])

def obter_nome_usuario(numero):
    numero_normalizado = normalizar_telefone(numero)
    return cache_usuarios.get(numero_normalizado, {}).get('nome', 'Usuário')

def ja_foi_notificado(numero):
    if numero in numeros_ja_notificados:
        return True
    numeros_ja_notificados.add(numero)
    return False

def pode_processar_comando(numero):
    agora = time.time()
    ultima_vez = ultimo_comando.get(numero, 0)
    if agora - ultima_vez >= INTERVALO_MINIMO:
        ultimo_comando[numero] = agora
        print(f"[DEBUG] Comando liberado para {numero}")
        return True
    print(f"[DEBUG] Spam bloqueado para {numero} - Aguarde {int(INTERVALO_MINIMO - (agora - ultima_vez))}s")
    return False

def gerar_hash_mensagem(dados, numero):
    import hashlib
    timestamp_atual = str(int(time.time()))
    if "audio" in dados:
        audio_url = dados["audio"].get("audioUrl", "")
        conteudo = f"AUDIO_{numero}_{audio_url}_{timestamp_atual}"
    elif "text" in dados:
        texto = dados["text"].get("message", "")
        conteudo = f"TEXT_{numero}_{texto}_{timestamp_atual}"
    else:
        conteudo = f"OTHER_{numero}_{timestamp_atual}"
    hash_final = hashlib.md5(conteudo.encode()).hexdigest()
    print(f"[DEBUG] Hash gerado: {hash_final[:8]} para {numero}")
    return hash_final

def ja_processou_mensagem(hash_mensagem):
    agora = time.time()
    hashes_removidos = []
    for hash_msg, timestamp in list(mensagens_processadas.items()):
        if agora - timestamp > 60:
            del mensagens_processadas[hash_msg]
            hashes_removidos.append(hash_msg[:8])
    if hash_mensagem in mensagens_processadas:
        print(f"[DEBUG] Hash duplicado encontrado: {hash_mensagem[:8]}")
        return True
    mensagens_processadas[hash_mensagem] = agora
    print(f"[DEBUG] Hash registrado: {hash_mensagem[:8]}")
    return False

# ================== MENSAGENS E MENU ==================
def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {"Content-Type": "application/json", "Client-Token": CLIENT_TOKEN}
    resposta = requests.post(url, json=payload, headers=headers)
    print(f"[DEBUG] Mensagem enviada para {numero} - Status: {resposta.status_code}")
    return resposta

def enviar_mensagem_nao_autorizado(numero):
    if ja_foi_notificado(numero):
        return
    mensagem = (
        "🚫 *ACESSO NEGADO*\n"
        "Você não tem autorização para usar este sistema.\n"
        "Este bot é exclusivo para usuários autorizados do sistema de produção.\n"
        "Para solicitar acesso, entre em contato com o administrador.\n"
        "⚠️ *Nota:* Esta é a única notificação que você receberá."
    )
    enviar_mensagem(numero, mensagem)

def enviar_menu(numero):
    nome_usuario = obter_nome_usuario(numero)
    projetos = obter_projetos_usuario(numero)
    menu_texto = (
        f"🏢 *SISTEMA DE PRODUÇÃO*\n"
        f"👤 *Usuário:* {nome_usuario}\n"
        f"🏗️ *Seus projetos:* {', '.join(projetos) if projetos else 'Nenhum'}\n"
        f"Escolha uma opção digitando o número:\n"
        f"*1* - 📊 PRODUÇÃO HOJE\n"
        f"*2* - 💰 FATURADO HOJE\n"
        f"*3* - 📅 SELECIONAR PERÍODO\n"
        f"🎤 *COMANDOS POR VOZ:*\n"
        f"• \"produção do dia\"\n"
        f"• \"produção do dia 30 de julho\"\n"
        f"• \"produção de 10 a 15 de julho\"\n"
    )
    return enviar_mensagem(numero, menu_texto)

# ================== WEBHOOK ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        print("\n=== CHEGOU NO WEBHOOK ===")
        dados = request.json
        numero = dados.get("phone")
        print(f"[DEBUG] Número recebido: {numero}")

        # 1. AUTORIZAÇÃO
        if not verificar_autorizacao(numero):
            print(f"[DEBUG] Usuário não autorizado: {numero}")
            enviar_mensagem_nao_autorizado(numero)
            return '', 200

        # 2. CONTROLE DE SPAM
        if not pode_processar_comando(numero):
            return '', 200

        # 3. HASH DUPLICAÇÃO
        hash_mensagem = gerar_hash_mensagem(dados, numero)
        if ja_processou_mensagem(hash_mensagem):
            return '', 200

        # 4. TEXTO OU ÁUDIO?
        if "text" in dados:
            mensagem = dados["text"]["message"].lower().strip()
            print(f"[DEBUG] Texto recebido: {mensagem}")
            if mensagem in ["oi", "menu"]:
                enviar_menu(numero)
            else:
                # Expanda aqui seus comandos...
                enviar_mensagem(numero, "⚠️ Digite *menu* para ver as opções.")
        elif "audio" in dados:
            enviar_mensagem(numero, "🎤 Áudio recebido. (Transcrição não implementada aqui!)")
        else:
            enviar_mensagem(numero, "⚠️ Mensagem não reconhecida.")
        return '', 200
    except Exception as e:
        print(f"[ERRO] Erro no webhook: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

# ================== MAIN ==================
if __name__ == '__main__':
    print("🤖 Bot Completo - Texto + Áudio iniciando...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
