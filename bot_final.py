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

# Configuração de logging simples
def log_print(*args, **kwargs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}]", *args, **kwargs, flush=True)

print = log_print

app = Flask(__name__)

# ================== CONFIG RAILWAY ==================
# Verificação de variáveis obrigatórias
REQUIRED_ENV_VARS = ['INSTANCE_ID', 'TOKEN', 'CLIENT_TOKEN', 'DB_PASSWORD']

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
if missing_vars:
    print(f"❌ ERRO: Variáveis de ambiente obrigatórias não definidas: {missing_vars}")
    raise ValueError(f"Configure as variáveis: {', '.join(missing_vars)}")

# Z-API configs - SOMENTE VARIÁVEIS DE AMBIENTE
INSTANCE_ID = os.environ.get('INSTANCE_ID')
TOKEN = os.environ.get('TOKEN')
CLIENT_TOKEN = os.environ.get('CLIENT_TOKEN')

# Database configs - SOMENTE VARIÁVEIS DE AMBIENTE
DB_SERVER = os.environ.get('DB_SERVER', 'alrflorestal.database.windows.net')
DB_DATABASE = os.environ.get('DB_DATABASE', 'Tabela_teste')
DB_USERNAME = os.environ.get('DB_USERNAME', 'sqladmin')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

print("🔐 Credenciais carregadas das variáveis de ambiente")
print(f"🌐 Conectando em: {DB_SERVER}")
print(f"📊 Database: {DB_DATABASE}")

# Controle de spam e duplicação - MAIS RIGOROSO
ultimo_comando = {}
numeros_ja_notificados = set()
mensagens_processadas = {}  # Cache para evitar reprocessamento
INTERVALO_MINIMO = 10  # Aumentado para 10 segundos

# Cache para usuários
cache_usuarios = {}

def conectar_db():
    try:
        connection_string = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={DB_SERVER};'
            f'DATABASE={DB_DATABASE};'
            f'UID={DB_USERNAME};'
            f'PWD={DB_PASSWORD}'
        )
        return pyodbc.connect(connection_string)
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
        print(f"[INFO] Usuários carregados: {len(usuarios_data)}")
        print("🔐 Conexão com banco estabelecida com segurança")
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

def obter_dados_detalhados_hoje(numero_usuario):
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        data_hoje = datetime.today().strftime('%Y-%m-%d')
        projetos_usuario = obter_projetos_usuario(numero_usuario)
        if not projetos_usuario:
            return []
        placeholders = ','.join(['?' for _ in projetos_usuario])
        query = f"""
        SELECT 
            NOME_DO_LIDER,
            SERVIÇO,
            MEDIDA,
            MOD,
            PROJETO,
            ISNULL(SUM([PRODUÇÃO]), 0) as total_producao,
            ISNULL(SUM([FATURADO]), 0) as total_faturado
        FROM BOLETIM_DIARIO 
        WHERE DATA_EXECUÇÃO = ? AND PROJETO IN ({placeholders})
        GROUP BY NOME_DO_LIDER, SERVIÇO, MEDIDA, MOD, PROJETO
        ORDER BY PROJETO, NOME_DO_LIDER, SERVIÇO
        """
        parametros = [data_hoje] + projetos_usuario
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conn.close()
        return resultados
    except Exception as e:
        print(f"[ERRO] Falha ao consultar dados hoje: {e}")
        return []

def obter_dados_detalhados_periodo(data_inicio, data_fim, numero_usuario):
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        projetos_usuario = obter_projetos_usuario(numero_usuario)
        if not projetos_usuario:
            return []
        placeholders = ','.join(['?' for _ in projetos_usuario])
        # CORRIGIDO: ENTRE DATAS (INCLUINDO INÍCIO E FIM)
        query = f"""
        SELECT 
            NOME_DO_LIDER,
            SERVIÇO,
            MEDIDA,
            MOD,
            PROJETO,
            ISNULL(SUM([PRODUÇÃO]), 0) as total_producao,
            ISNULL(SUM([FATURADO]), 0) as total_faturado
        FROM BOLETIM_DIARIO 
        WHERE DATA_EXECUÇÃO BETWEEN ? AND ? AND PROJETO IN ({placeholders})
        GROUP BY NOME_DO_LIDER, SERVIÇO, MEDIDA, MOD, PROJETO
        ORDER BY PROJETO, NOME_DO_LIDER, SERVIÇO
        """
        parametros = [data_inicio, data_fim] + projetos_usuario
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conn.close()
        return resultados
    except Exception as e:
        print(f"[ERRO] Falha ao consultar período: {e}")
        return []

def obter_colaboradores_por_classe(projetos):
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        placeholders = ','.join(['?' for _ in projetos])
        query = f"""
        SELECT 
            PROJETO,
            CLASSE,
            COUNT(*) as quantidade
        FROM COLABORADORES
        WHERE PROJETO IN ({placeholders})
          AND (CLASSE IS NOT NULL AND CLASSE NOT IN ('ADM', 'COF'))
        GROUP BY PROJETO, CLASSE
        ORDER BY PROJETO, CLASSE
        """
        cursor.execute(query, projetos)
        resultados = cursor.fetchall()
        conn.close()
        por_classe = {}
        for projeto, classe, qtd in resultados:
            if projeto not in por_classe:
                por_classe[projeto] = {}
            por_classe[projeto][classe] = qtd
        return por_classe
    except Exception as e:
        print(f"[ERRO] Falha ao buscar classes: {e}")
        return {}

# NOVA FUNÇÃO: Buscar supervisores por faturamento
def obter_supervisores_por_faturamento(projetos_usuario, data_inicio=None, data_fim=None):
    """Busca ranking de supervisores por faturamento"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        if not projetos_usuario:
            return []
            
        placeholders = ','.join(['?' for _ in projetos_usuario])
        
        if data_inicio and data_fim:
            # Para período específico
            query = f"""
            SELECT 
                SUPERVISOR,
                ISNULL(SUM([FATURADO]), 0) as total_faturado
            FROM BOLETIM_DIARIO 
            WHERE DATA_EXECUÇÃO BETWEEN ? AND ? 
              AND PROJETO IN ({placeholders})
              AND SUPERVISOR IS NOT NULL 
              AND SUPERVISOR != ''
            GROUP BY SUPERVISOR
            ORDER BY total_faturado DESC
            """
            parametros = [data_inicio, data_fim] + projetos_usuario
        else:
            # Para hoje
            data_hoje = datetime.today().strftime('%Y-%m-%d')
            query = f"""
            SELECT 
                SUPERVISOR,
                ISNULL(SUM([FATURADO]), 0) as total_faturado
            FROM BOLETIM_DIARIO 
            WHERE DATA_EXECUÇÃO = ? 
              AND PROJETO IN ({placeholders})
              AND SUPERVISOR IS NOT NULL 
              AND SUPERVISOR != ''
            GROUP BY SUPERVISOR
            ORDER BY total_faturado DESC
            """
            parametros = [data_hoje] + projetos_usuario
            
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conn.close()
        
        print(f"[DEBUG] Encontrados {len(resultados)} supervisores com faturamento")
        for supervisor, faturado in resultados[:5]:  # Log dos primeiros 5
            print(f"[DEBUG] Supervisor: {supervisor} - Faturado: R$ {faturado:,.2f}")
            
        return [(supervisor, faturado) for supervisor, faturado in resultados if faturado > 0]
        
    except Exception as e:
        print(f"[ERRO] Falha ao buscar supervisores: {e}")
        import traceback
        traceback.print_exc()
        return []

def agrupar_dados_completo(dados):
    if not dados:
        return {}, {}, {}, {}
    resumo_projetos = {}
    projetos_modalidade = {}
    lideres_detalhado = {}
    lideres_por_projeto = {}
    servicos_por_projeto = defaultdict(lambda: defaultdict(lambda: {'producao': 0, 'faturado': 0, 'medida': ''}))
    
    for linha in dados:
        nome_lider = linha[0] or "Sem Líder"
        servico = linha[1] or "Sem Serviço"
        medida = linha[2] or "Un"
        modalidade_original = linha[3] or "N/A"
        projeto = str(linha[4])
        producao = round(linha[5] or 0, 2)
        faturado = round(linha[6] or 0, 2)
        
        # NORMALIZAR MODALIDADE - Padronizar maiúsculas/minúsculas
        modalidade = normalizar_modalidade(modalidade_original)
        
        if projeto not in resumo_projetos:
            resumo_projetos[projeto] = {'producao': 0, 'faturado': 0}
        resumo_projetos[projeto]['producao'] += producao
        resumo_projetos[projeto]['faturado'] += faturado
        if projeto not in lideres_por_projeto:
            lideres_por_projeto[projeto] = set()
        lideres_por_projeto[projeto].add(nome_lider)
        if projeto not in projetos_modalidade:
            projetos_modalidade[projeto] = {}
        if modalidade not in projetos_modalidade[projeto]:
            projetos_modalidade[projeto][modalidade] = {'producao': 0, 'faturado': 0}
        projetos_modalidade[projeto][modalidade]['producao'] += producao
        projetos_modalidade[projeto][modalidade]['faturado'] += faturado
        chave_lider = f"{projeto}_{nome_lider}"
        if chave_lider not in lideres_detalhado:
            lideres_detalhado[chave_lider] = {
                'nome': nome_lider,
                'projeto': projeto,
                'servicos': {}
            }
        if servico not in lideres_detalhado[chave_lider]['servicos']:
            lideres_detalhado[chave_lider]['servicos'][servico] = {
                'producao': 0, 
                'faturado': 0, 
                'medida': medida
            }
        lideres_detalhado[chave_lider]['servicos'][servico]['producao'] += producao
        lideres_detalhado[chave_lider]['servicos'][servico]['faturado'] += faturado
        servicos_por_projeto[projeto][servico]['producao'] += producao
        servicos_por_projeto[projeto][servico]['faturado'] += faturado
        servicos_por_projeto[projeto][servico]['medida'] = medida
    for projeto in lideres_por_projeto:
        resumo_projetos[projeto]['total_lideres'] = len(lideres_por_projeto[projeto])
    return resumo_projetos, projetos_modalidade, lideres_detalhado, servicos_por_projeto

def normalizar_modalidade(modalidade):
    """Normaliza modalidades para agrupar variações de maiúscula/minúscula"""
    if not modalidade:
        return "N/A"
    
    modalidade_limpa = modalidade.strip()
    
    # Dicionário de normalização
    normalizacao = {
        'mec': 'Mec',
        'MEC': 'Mec', 
        'mecânica': 'Mec',
        'mecanica': 'Mec',
        'man': 'Man',
        'MAN': 'Man',
        'manual': 'Man',
        'apo': 'Apo',
        'APO': 'Apo',
        'apoio': 'Apo',
        'dro': 'Dro',
        'DRO': 'Dro',
        'drone': 'Dro'
    }
    
    # Verificar se existe uma normalização específica
    modalidade_lower = modalidade_limpa.lower()
    if modalidade_lower in normalizacao:
        return normalizacao[modalidade_lower]
    
    # Se não encontrar, capitalizar primeira letra
    return modalidade_limpa.capitalize()

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_numero(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def emoji_mod(mod):
    # Removido - não usar mais emojis para padronizar
    return ""

# FUNÇÃO MODIFICADA: Adicionado ranking de supervisores e melhor formatação visual
def formatar_resumo_geral(dados, numero_usuario, titulo_data, data_inicio=None, data_fim=None):
    resumo_projetos, projetos_modalidade, _, _ = agrupar_dados_completo(dados)
    nome_usuario = obter_nome_usuario(numero_usuario)
    projetos_usuario = obter_projetos_usuario(numero_usuario)
    classes_info = obter_colaboradores_por_classe(projetos_usuario)

    texto = f"📊 {titulo_data}\n\n"
    texto += f"🎯 RESUMO GERAL - {nome_usuario}\n\n"
    total_faturado = sum(proj['faturado'] for proj in resumo_projetos.values())
    texto += f"💰 Faturado Total: {formatar_moeda(total_faturado)}\n"

    # Modalidades TOTAIS (sem emojis para padronizar)
    modalidades_totais = defaultdict(lambda: {'producao': 0, 'faturado': 0})
    for projeto, mods in projetos_modalidade.items():
        for mod, dados_mod in mods.items():
            modalidades_totais[mod]['producao'] += dados_mod['producao']
            modalidades_totais[mod]['faturado'] += dados_mod['faturado']

    for mod, tot in modalidades_totais.items():
        texto += f"{mod}: {formatar_numero(tot['producao'])} | {formatar_moeda(tot['faturado'])}\n"

    texto += f"---------------------------------------------\n"

    # Colaboradores (total geral)
    total_colabs = sum(sum(cl.values()) for cl in classes_info.values())
    texto += f"👤Colaboradores: {total_colabs}\n"
    # Por classe
    todas_classes = defaultdict(int)
    for classes in classes_info.values():
        for classe, qtd in classes.items():
            todas_classes[classe] += qtd
    for classe, qtd in todas_classes.items():
        texto += f"👤 {classe}: {qtd}\n"

    texto += f"---------------------------------------------\n"

    # RANKING DE SUPERVISORES POR FATURAMENTO
    supervisores_ranking = obter_supervisores_por_faturamento(projetos_usuario, data_inicio, data_fim)
    if supervisores_ranking:
        texto += f"🏆 RANKING FATURAMENTO POR SUPERVISOR\n"
        posicao = 1
        for supervisor, faturado in supervisores_ranking:
            if posicao == 1:
                emoji_pos = "🥇"
            elif posicao == 2:
                emoji_pos = "🥈"
            elif posicao == 3:
                emoji_pos = "🥉"
            else:
                emoji_pos = f"{posicao}º"
            
            texto += f"{emoji_pos} {supervisor} - {formatar_moeda(faturado)}\n"
            posicao += 1
    else:
        print(f"[DEBUG] Nenhum supervisor encontrado para ranking")

    texto += f"-----------------------------------------------\n"

    # RANKING DE PROJETOS POR FATURAMENTO
    if resumo_projetos:
        texto += f"🏆 RANKING FATURAMENTO POR PROJETO\n"
        # Ordenar projetos por faturamento (decrescente)
        projetos_ordenados = sorted(
            resumo_projetos.items(), 
            key=lambda x: x[1]['faturado'], 
            reverse=True
        )
        
        posicao = 1
        for projeto, dados_proj in projetos_ordenados:
            if dados_proj['faturado'] > 0:  # Só mostra projetos com faturamento
                if posicao == 1:
                    emoji_pos = "🥇"
                elif posicao == 2:
                    emoji_pos = "🥈"
                elif posicao == 3:
                    emoji_pos = "🥉"
                else:
                    emoji_pos = f"{posicao}º"
                
                texto += f"{emoji_pos} {projeto} - {formatar_moeda(dados_proj['faturado'])}\n"
                posicao += 1

    texto += f"--------------------------------------------\n"

    # NOVO: MODALIDADES POR PROJETO
    texto += f"📊 MODALIDADES POR PROJETO\n\n"
    
    # Ordenar projetos por faturamento (mesmo ordem do ranking)
    projetos_ordenados = sorted(
        projetos_modalidade.items(), 
        key=lambda x: sum(mod['faturado'] for mod in x[1].values()), 
        reverse=True
    )
    
    for projeto, modalidades in projetos_ordenados:
        # Só mostra projetos com faturamento
        total_projeto = sum(mod['faturado'] for mod in modalidades.values())
        if total_projeto > 0:
            texto += f"PROJETO {projeto}\n"
            
            # Ordenar modalidades por faturamento
            modalidades_ordenadas = sorted(
                modalidades.items(),
                key=lambda x: x[1]['faturado'],
                reverse=True
            )
            
            for modalidade, dados in modalidades_ordenadas:
                if dados['faturado'] > 0:
                    texto += f"{modalidade}: {formatar_numero(dados['producao'])} | {formatar_moeda(dados['faturado'])}\n"
            
            texto += f"--------------------------------------\n"

    return texto.strip()

def formatar_resumo_detalhado(dados, numero_usuario, titulo_data):
    resumo_projetos, projetos_modalidade, lideres_detalhado, servicos_por_projeto = agrupar_dados_completo(dados)
    nome_usuario = obter_nome_usuario(numero_usuario)
    texto = f"📊 {titulo_data}\n\n"
    texto += f"🎯 RESUMO DETALHADO - {nome_usuario}\n\n"

    projetos_processados = {}
    for chave_lider, dados_lider in lideres_detalhado.items():
        projeto = dados_lider['projeto']
        nome_lider = dados_lider['nome']
        if projeto not in projetos_processados:
            projetos_processados[projeto] = []
            texto += f"🏗 PROJETO {projeto} - RESUMO POR LÍDER\n"
        texto += f"👷 {nome_lider}\n"
        texto += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        total_lider_producao = 0
        total_lider_faturado = 0
        total_lider_medida = ""
        for servico, dados_servico in dados_lider['servicos'].items():
            producao = dados_servico['producao']
            faturado = dados_servico['faturado'] 
            medida = dados_servico['medida']
            total_lider_producao += producao
            total_lider_faturado += faturado
            total_lider_medida = medida
            texto += f"{servico}\n"
            texto += f"📊 Produção: {formatar_numero(producao)} {medida}\n"
            texto += f"💰 Faturado: {formatar_moeda(faturado)}\n"
            texto += "_____________________\n"
        texto += f"🏆 TOTAL {nome_lider}:\n"
        texto += f"📊 Produção: {formatar_numero(total_lider_producao)} {total_lider_medida}\n"
        texto += f"💰 Faturado: {formatar_moeda(total_lider_faturado)}\n"
        texto += f"═══════════════════════════════════\n\n"

    # AGRUPADO POR SERVIÇO (novo formato)
    texto += f"***AGRUPADO POR SERVIÇO***\n"
    for projeto, servicos in servicos_por_projeto.items():
        texto += f"PROJETO {projeto}\n"
        for servico, dados in servicos.items():
            prod = formatar_numero(dados['producao'])
            fat = formatar_moeda(dados['faturado'])
            medida = dados['medida']
            texto += f"{servico}\n"
            texto += f"📊 Produção: {prod} {medida}\n"
            texto += f"💰 Faturado: {fat}\n"
            texto += "_____________________\n"
        texto += "\n"
    return texto.strip()

def baixar_e_converter_audio(url_audio):
    try:
        headers = {"Client-Token": CLIENT_TOKEN}
        resposta = requests.get(url_audio, headers=headers, timeout=30)
        if resposta.status_code == 200:
            nome_arquivo = f"temp_audio_{int(time.time())}"
            caminho_ogg = f"{nome_arquivo}.ogg"
            with open(caminho_ogg, 'wb') as f:
                f.write(resposta.content)
            time.sleep(1)
            try:
                audio_data, sample_rate = librosa.load(caminho_ogg, sr=16000)
                caminho_wav = f"{nome_arquivo}.wav"
                sf.write(caminho_wav, audio_data, sample_rate)
                try:
                    os.remove(caminho_ogg)
                except:
                    pass
                return caminho_wav
            except Exception as e:
                print(f"[ERRO] Erro na conversão: {e}")
                return None
        else:
            return None
    except Exception as e:
        print(f"[ERRO] Erro no download: {e}")
        return None

def transcrever_com_speech_recognition(caminho_audio):
    try:
        if not os.path.exists(caminho_audio):
            return None
        try:
            r = sr.Recognizer()
            with sr.AudioFile(caminho_audio) as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.record(source)
            texto = r.recognize_google(audio, language="pt-BR")
            return texto.strip()
        except Exception as e:
            print(f"[ERRO] Erro no reconhecimento: {e}")
            return None
    except Exception as e:
        print(f"[ERRO] Erro geral na transcrição: {e}")
        return None
    finally:
        try:
            if os.path.exists(caminho_audio):
                os.remove(caminho_audio)
        except:
            pass

def processar_comando_audio(texto):
    texto = texto.lower().strip()
    
    # CORRIGIDO: Regex mais flexível para períodos
    padrao_periodo = r'(\d{1,2})\s*(?:a|até|de)\s*(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_periodo = re.search(padrao_periodo, texto)
    
    if match_periodo:
        dia_inicio = match_periodo.group(1).zfill(2)
        dia_fim = match_periodo.group(2).zfill(2)
        mes_nome = match_periodo.group(3).lower()
        
        # Mapeamento de meses
        meses = {
            'janeiro': '01', 'jan': '01',
            'fevereiro': '02', 'fev': '02', 
            'março': '03', 'mar': '03',
            'abril': '04', 'abr': '04',
            'maio': '05', 'mai': '05',
            'junho': '06', 'jun': '06',
            'julho': '07', 'jul': '07',
            'agosto': '08', 'ago': '08',
            'setembro': '09', 'set': '09',
            'outubro': '10', 'out': '10',
            'novembro': '11', 'nov': '11',
            'dezembro': '12', 'dez': '12'
        }
        
        mes = meses.get(mes_nome, '07')  # Default julho
        ano = str(datetime.now().year)
        
        data_inicio = f"{dia_inicio}/{mes}/{ano}"
        data_fim = f"{dia_fim}/{mes}/{ano}"
        
        return "periodo", f"{data_inicio} A {data_fim}"
    
    # Padrão original para datas numéricas
    padrao_data = r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?'
    match_data = re.search(padrao_data, texto)
    if match_data:
        dia = match_data.group(1).zfill(2)
        mes = match_data.group(2).zfill(2)
        ano = match_data.group(3) if match_data.group(3) else str(datetime.now().year)
        data_br = f"{dia}/{mes}/{ano}"
        periodo = f"{data_br} A {data_br}"
        return "periodo", periodo
    
    # Padrão antigo para um dia específico (mantido para compatibilidade)
    padrao_mes_extenso = r'(\d{1,2})\s*de\s*(julho|jul)'
    match_mes = re.search(padrao_mes_extenso, texto)
    if match_mes:
        dia = match_mes.group(1).zfill(2)
        mes = "07"
        ano = str(datetime.now().year)
        data_br = f"{dia}/{mes}/{ano}"
        periodo = f"{data_br} A {data_br}"
        return "periodo", periodo
    
    if any(palavra in texto for palavra in ["produção", "producao", "produzido"]):
        return "producao_hoje", None
    elif any(palavra in texto for palavra in ["faturado", "faturamento"]):
        return "faturado_hoje", None
    elif any(palavra in texto for palavra in ["oi", "olá", "menu"]):
        return "menu", None
    else:
        return "nao_reconhecido", None

def processar_periodo(texto):
    padrao = r'(\d{1,2}/\d{1,2}/\d{4})\s*[Aa]\s*(\d{1,2}/\d{1,2}/\d{4})'
    match = re.search(padrao, texto)
    if match:
        try:
            data_inicio_str = match.group(1)
            data_fim_str = match.group(2)
            data_inicio = datetime.strptime(data_inicio_str, '%d/%m/%Y').strftime('%Y-%m-%d')
            data_fim = datetime.strptime(data_fim_str, '%d/%m/%Y').strftime('%Y-%m-%d')
            return data_inicio, data_fim
        except ValueError:
            return None, None
    return None, None

def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {"Content-Type": "application/json", "Client-Token": CLIENT_TOKEN}
    
    try:
        resposta = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"[DEBUG] Mensagem enviada - Status: {resposta.status_code}")
        return resposta
    except Exception as e:
        print(f"[ERRO] Erro ao enviar mensagem: {e}")
        return None

def enviar_mensagem_nao_autorizado(numero):
    if ja_foi_notificado(numero):
        return
    mensagem = """🚫 *ACESSO NEGADO*
Você não tem autorização para usar este sistema.
Este bot é exclusivo para usuários autorizados do sistema de produção.
Para solicitar acesso, entre em contato com o administrador.
⚠️ *Nota:* Esta é a única notificação que você receberá."""
    enviar_mensagem(numero, mensagem)

def enviar_menu(numero):
    nome_usuario = obter_nome_usuario(numero)
    projetos = obter_projetos_usuario(numero)
    menu_texto = f"""🏢 *SISTEMA DE PRODUÇÃO*
👤 *Usuário:* {nome_usuario}
🏗️ *Seus projetos:* {', '.join(projetos) if projetos else 'Nenhum'}
Escolha uma opção digitando o número:
*1* - 📊 PRODUÇÃO HOJE
*2* - 💰 FATURADO HOJE
*3* - 📅 SELECIONAR PERÍODO
🎤 *COMANDOS POR VOZ:*
• "produção do dia"
• "produção do dia 30 de julho"
• "produção de 10 a 15 de julho"
"""
    return enviar_mensagem(numero, menu_texto)

# ================== HEALTH CHECK ENDPOINT ==================
@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificação de saúde do serviço"""
    try:
        # Testa conexão com banco
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'cache_users': len(cache_usuarios),
            'processed_messages': len(mensagens_processadas)
        }, 200
    except Exception as e:
        print(f"[ERRO] Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }, 500

@app.route('/', methods=['GET'])
def home():
    """Endpoint raiz"""
    return {
        'name': 'Bot WhatsApp Sistema de Produção',
        'status': 'running',
        'version': '2.0 Railway',
        'timestamp': datetime.now().isoformat(),
        'endpoints': ['/webhook', '/health']
    }, 200

# ================== WEBHOOK PRINCIPAL ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        dados = request.json
        numero = dados.get("phone")
        
        print(f"\n[DEBUG] ========== WEBHOOK RECEBIDO ==========")
        print(f"[DEBUG] Número: {numero}")
        print(f"[DEBUG] Tipo: {'AUDIO' if 'audio' in dados else 'TEXTO'}")
        
        # PRIMEIRO: Verificação de autorização
        if not verificar_autorizacao(numero):
            print(f"[DEBUG] Usuário não autorizado: {numero}")
            enviar_mensagem_nao_autorizado(numero)
            return '', 200
        
        # SEGUNDO: Controle de spam RIGOROSO - PRIMEIRA BARREIRA
        if not pode_processar_comando(numero):
            print(f"[DEBUG] ❌ SPAM BLOQUEADO para {numero}")
            return '', 200
        
        # TERCEIRO: Gerar hash único
        hash_mensagem = gerar_hash_mensagem(dados, numero)
        
        # QUARTO: Verificar duplicação - SEGUNDA BARREIRA
        if ja_processou_mensagem(hash_mensagem):
            print(f"[DEBUG] ❌ MENSAGEM DUPLICADA: {hash_mensagem[:8]}")
            return '', 200
        
        print(f"[DEBUG] ✅ PROCESSANDO: {hash_mensagem[:8]}")
        
        # PROCESSAMENTO DE ÁUDIO
        if "audio" in dados:
            print(f"[DEBUG] Iniciando processamento de ÁUDIO")
            url_audio = dados["audio"].get("audioUrl")
            if not url_audio:
                print(f"[DEBUG] URL de áudio não encontrada")
                return '', 200
                
            caminho_wav = baixar_e_converter_audio(url_audio)
            if not caminho_wav:
                print(f"[DEBUG] Falha na conversão do áudio")
                return '', 200
                
            texto_transcrito = transcrever_com_speech_recognition(caminho_wav)
            if not texto_transcrito:
                print(f"[DEBUG] Falha na transcrição")
                return '', 200
                
            print(f"[DEBUG] Áudio transcrito: '{texto_transcrito}'")
            comando, parametro = processar_comando_audio(texto_transcrito)
            
            if comando == "producao_hoje":
                print(f"[DEBUG] Executando comando: PRODUÇÃO HOJE")
                dados_prod = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_prod, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_prod, numero, f"PRODUÇÃO {data_hoje}")
                
                print(f"[DEBUG] Enviando mensagem 1/2 - RESUMO")
                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                time.sleep(4)
                print(f"[DEBUG] Enviando mensagem 2/2 - DETALHADO")
                enviar_mensagem(numero, detalhado)
                
            elif comando == "periodo" and parametro:
                print(f"[DEBUG] Executando comando: PERÍODO - {parametro}")
                data_inicio, data_fim = processar_periodo(parametro)
                if data_inicio and data_fim:
                    dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                    data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                    data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                    resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                    detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                    
                    print(f"[DEBUG] Enviando mensagem 1/2 - RESUMO PERÍODO")
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                    time.sleep(4)
                    print(f"[DEBUG] Enviando mensagem 2/2 - DETALHADO PERÍODO")
                    enviar_mensagem(numero, detalhado)
                else:
                    print(f"[DEBUG] Erro no processamento da data")
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Não consegui entender a data informada.")
            else:
                print(f"[DEBUG] Comando não reconhecido: {comando}")
                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Não reconheci o comando. Envie novamente ou digite *menu*.")
        
        # PROCESSAMENTO DE TEXTO
        elif "text" in dados:
            mensagem = dados["text"]["message"].lower().strip()
            
            # FILTRO: Ignorar mensagens de trial ou muito longas
            if ("trial" in mensagem and "favor desconsiderar" in mensagem) or len(mensagem) > 500:
                print(f"[DEBUG] Mensagem de trial/spam ignorada")
                return '', 200
            
            print(f"[DEBUG] Processando TEXTO: '{mensagem[:50]}...'")
            
            if mensagem in ["oi", "menu"]:
                print(f"[DEBUG] Enviando MENU")
                enviar_menu(numero)
                
            elif mensagem == "1":
                print(f"[DEBUG] Executando opção 1 - PRODUÇÃO HOJE")
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                print(f"[DEBUG] Enviando mensagem 1/2 - RESUMO")
                enviar_mensagem(numero, resumo)
                time.sleep(4)
                print(f"[DEBUG] Enviando mensagem 2/2 - DETALHADO")
                enviar_mensagem(numero, detalhado)
                
            elif mensagem == "produção" or mensagem == "producao":
                print(f"[DEBUG] Comando texto: PRODUÇÃO")
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                print(f"[DEBUG] Enviando mensagem 1/2 - RESUMO")
                enviar_mensagem(numero, resumo)
                time.sleep(4)
                print(f"[DEBUG] Enviando mensagem 2/2 - DETALHADO")
                enviar_mensagem(numero, detalhado)
                
            else:
                comando, parametro = processar_comando_audio(mensagem)
                if comando == "periodo" and parametro:
                    print(f"[DEBUG] Comando texto PERÍODO: {parametro}")
                    data_inicio, data_fim = processar_periodo(parametro)
                    if data_inicio and data_fim:
                        dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                        data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                        data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                        resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                        detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                        
                        print(f"[DEBUG] Enviando mensagem 1/2 - RESUMO PERÍODO")
                        enviar_mensagem(numero, resumo)
                        time.sleep(4)
                        print(f"[DEBUG] Enviando mensagem 2/2 - DETALHADO PERÍODO")
                        enviar_mensagem(numero, detalhado)
                    else:
                        enviar_mensagem(numero, "❌ Não consegui entender a data informada.")
                else:
                    print(f"[DEBUG] Comando não reconhecido")
                    enviar_mensagem(numero, "❓ Não reconheci o comando. Digite *menu* para ver as opções.")
        
        print(f"[DEBUG] ✅ PROCESSAMENTO CONCLUÍDO: {hash_mensagem[:8]}")
        print(f"[DEBUG] ========================================\n")
        return '', 200
        
    except Exception as e:
        print(f"[ERRO] Erro crítico no webhook: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

# ================== INICIALIZAÇÃO ==================
# Inicialização para Gunicorn (fora do if __name__)
try:
    print("🔧 Inicializando para Gunicorn...")
    cache_usuarios = buscar_usuarios_autorizados()
    print("✅ Inicialização do Gunicorn concluída")
except Exception as e:
    print(f"❌ Erro na inicialização: {e}")

if __name__ == '__main__':
    print("🤖 Bot Completo - Texto + Áudio iniciando...")
    print("🎤 Reconhecimento de voz: Google Speech Recognition")
    print("📊 Sistema: Produção com Controle por Usuário")
    print("🔐 Usuários carregados dinamicamente da tabela USUARIOS")
    print("🏆 NOVO: Ranking de projetos por faturamento")
    print("🏆 NOVO: Ranking de supervisores por faturamento")
    print("📅 CORRIGIDO: Processamento de períodos por voz")
    print("🚀 RAILWAY: Configurado para deploy em produção")
    
    # Carrega cache inicial de usuários
    cache_usuarios = buscar_usuarios_autorizados()
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Servidor iniciando na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)