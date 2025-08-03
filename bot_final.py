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

# Controle de spam e duplicação - MAIS RIGOROSO
ultimo_comando = {}
numeros_ja_notificados = set()
mensagens_processadas = {}  # Cache para evitar reprocessamento
INTERVALO_MINIMO = 10  # Aumentado para 10 segundos

app = Flask(__name__)

# Z-API configs - USANDO VARIÁVEIS DE AMBIENTE
INSTANCE_ID = os.environ.get('INSTANCE_ID')
TOKEN = os.environ.get('TOKEN')
CLIENT_TOKEN = os.environ.get('CLIENT_TOKEN')

# Cache para usuários
cache_usuarios = {}

def conectar_db():
    # USANDO VARIÁVEIS DE AMBIENTE PARA SEGURANÇA
    server = os.environ.get('DB_SERVER')
    database = os.environ.get('DB_DATABASE')
    username = os.environ.get('DB_USERNAME')
    password = os.environ.get('DB_PASSWORD')
    
    if not all([server, database, username, password]):
        raise Exception("Variáveis de ambiente do banco não configuradas")
    
    return pyodbc.connect(
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password}'
    )

def normalizar_telefone(telefone):
    if not telefone:
        return ""
    return ''.join(c for c in str(telefone) if c.isdigit())

def buscar_usuarios_autorizados():
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        query = """
        SELECT DISTINCT 
            TELEFONE,
            USUARIO,
            PROJETO
        FROM USUARIOS 
        WHERE TELEFONE IS NOT NULL AND TELEFONE != ''
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
    if numero_normalizado in cache_usuarios:
        return True
    else:
        return False

def obter_projetos_usuario(numero):
    numero_normalizado = normalizar_telefone(numero)
    if numero_normalizado in cache_usuarios:
        return cache_usuarios[numero_normalizado]['projetos']
    return []

def obter_nome_usuario(numero):
    numero_normalizado = normalizar_telefone(numero)
    if numero_normalizado in cache_usuarios:
        return cache_usuarios[numero_normalizado]['nome']
    return "Usuário"

def ja_foi_notificado(numero):
    if numero in numeros_ja_notificados:
        return True
    else:
        numeros_ja_notificados.add(numero)
        return False

def pode_processar_comando(numero):
    """Controle rigoroso de spam por usuário"""
    agora = time.time()
    ultima_vez = ultimo_comando.get(numero, 0)
    if agora - ultima_vez >= INTERVALO_MINIMO:
        ultimo_comando[numero] = agora
        print(f"[DEBUG] Comando liberado para {numero}")
        return True
    else:
        tempo_restante = int(INTERVALO_MINIMO - (agora - ultima_vez))
        print(f"[DEBUG] Spam bloqueado para {numero} - Aguarde {tempo_restante}s")
        return False

def gerar_hash_mensagem(dados, numero):
    """Gera hash único mais específico para cada mensagem"""
    import hashlib
    timestamp_atual = str(int(time.time()))
    
    if "audio" in dados:
        # Para áudio: usar URL + número + timestamp do sistema
        audio_url = dados["audio"].get("audioUrl", "")
        conteudo = f"AUDIO_{numero}_{audio_url}_{timestamp_atual}"
    elif "text" in dados:
        # Para texto: usar mensagem + número + timestamp do sistema
        texto = dados["text"].get("message", "")
        conteudo = f"TEXT_{numero}_{texto}_{timestamp_atual}"
    else:
        conteudo = f"OTHER_{numero}_{timestamp_atual}"
    
    hash_final = hashlib.md5(conteudo.encode()).hexdigest()
    print(f"[DEBUG] Hash gerado: {hash_final[:8]} para {numero}")
    return hash_final

def ja_processou_mensagem(hash_mensagem):
    """Verifica se a mensagem já foi processada - Cache de 60 segundos"""
    agora = time.time()
    
    # Limpar mensagens antigas (mais de 60 segundos)
    hashes_removidos = []
    for hash_msg, timestamp in list(mensagens_processadas.items()):
        if agora - timestamp > 60:
            del mensagens_processadas[hash_msg]
            hashes_removidos.append(hash_msg[:8])
    
    if hashes_removidos:
        print(f"[DEBUG] Cache limpo: {len(hashes_removidos)} hashes removidos")
    
    # Verificar se já processou
    if hash_mensagem in mensagens_processadas:
        print(f"[DEBUG] Hash duplicado encontrado: {hash_mensagem[:8]}")
        return True
    
    # Marcar como processada
    mensagens_processadas[hash_mensagem] = agora
    print(f"[DEBUG] Hash registrado: {hash_mensagem[:8]}")
    return False

# ... DEMAIS FUNÇÕES (sem alterações) ...
# (mantive todas as funções seguintes como estavam no seu último código)

# Cole o restante do seu código normalmente aqui (todas as funções,
# formatações, processamento de comandos, rotas Flask, etc).

# No final, mantenha o main:
if __name__ == '__main__':
    print("🤖 Bot Completo - Texto + Áudio iniciando...")
    print("🎤 Reconhecimento de voz: Google Speech Recognition")
    print("📊 Sistema: Produção com Controle por Usuário")
    print("🔐 Usuários carregados dinamicamente da tabela USUARIOS")
    print("🏆 NOVO: Ranking de projetos por faturamento")
    print("🏆 NOVO: Ranking de supervisores por faturamento")
    print("📅 CORRIGIDO: Processamento de períodos por voz")
    print("🔒 SEGURO: Usando variáveis de ambiente")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
