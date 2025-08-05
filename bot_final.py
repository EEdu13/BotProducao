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

app = Flask(__name__)

# ================== CONFIG RAILWAY ==================
# Z-API configs - SOMENTE VARIÁVEIS DE AMBIENTE
INSTANCE_ID = os.environ.get('INSTANCE_ID')
TOKEN = os.environ.get('TOKEN')
CLIENT_TOKEN = os.environ.get('CLIENT_TOKEN')

# Database configs - SOMENTE VARIÁVEIS DE AMBIENTE
DB_SERVER = os.environ.get('DB_SERVER', 'alrflorestal.database.windows.net')
DB_DATABASE = os.environ.get('DB_DATABASE', 'Tabela_teste')
DB_USERNAME = os.environ.get('DB_USERNAME', 'sqladmin')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# Debug - mostrar quais variáveis foram carregadas
print("🔍 DEBUG - Variáveis carregadas:")
print(f"INSTANCE_ID: {'✅ OK' if INSTANCE_ID else '❌ VAZIO'}")
print(f"TOKEN: {'✅ OK' if TOKEN else '❌ VAZIO'}")
print(f"CLIENT_TOKEN: {'✅ OK' if CLIENT_TOKEN else '❌ VAZIO'}")
print(f"DB_PASSWORD: {'✅ OK' if DB_PASSWORD else '❌ VAZIO'}")

# Verificação com mensagem mais clara
missing_vars = []
if not INSTANCE_ID: missing_vars.append('INSTANCE_ID')
if not TOKEN: missing_vars.append('TOKEN')
if not CLIENT_TOKEN: missing_vars.append('CLIENT_TOKEN')
if not DB_PASSWORD: missing_vars.append('DB_PASSWORD')

if missing_vars:
    print(f"❌ ERRO: Variáveis de ambiente não encontradas: {missing_vars}")
    print("🔍 Verifique no Railway se estas variáveis estão configuradas")
    raise ValueError(f"Configure as variáveis: {', '.join(missing_vars)}")

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
        # CORRIGIDO: Driver mais compatível para Railway
        drivers = [
            '{ODBC Driver 18 for SQL Server}',  # Mais recente
            '{ODBC Driver 17 for SQL Server}',  # Fallback
            '{ODBC Driver 13 for SQL Server}',  # Mais antigo
            '{FreeTDS}'  # Fallback para Linux
        ]
        
        connection_string_base = (
            f'SERVER={DB_SERVER};'
            f'DATABASE={DB_DATABASE};'
            f'UID={DB_USERNAME};'
            f'PWD={DB_PASSWORD};'
            f'TrustServerCertificate=yes;'  # Para conexões Azure
        )
        
        # Tenta cada driver até conseguir conectar
        for driver in drivers:
            try:
                connection_string = f'DRIVER={driver};{connection_string_base}'
                print(f"🔍 Tentando driver: {driver}")
                conn = pyodbc.connect(connection_string, timeout=30)
                print(f"✅ Conectado com driver: {driver}")
                return conn
            except Exception as e:
                print(f"❌ Falha com driver {driver}: {str(e)[:100]}")
                continue
        
        # Se nenhum driver funcionar
        raise Exception("Nenhum driver ODBC disponível funcionou")
        
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
        print("⚠️ Bot funcionará em modo de emergência (sem autenticação)")
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

def obter_dados_detalhados_hoje(numero_usuario, projeto_especifico=None):
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        data_hoje = datetime.today().strftime('%Y-%m-%d')
        projetos_usuario = obter_projetos_usuario(numero_usuario)
        
        # Se projeto específico foi informado, verificar se usuário tem acesso
        if projeto_especifico:
            if projeto_especifico not in projetos_usuario:
                print(f"[ERRO] Usuário {numero_usuario} não tem acesso ao projeto {projeto_especifico}")
                return []
            projetos_filtro = [projeto_especifico]
        else:
            projetos_filtro = projetos_usuario
            
        if not projetos_filtro:
            return []
            
        placeholders = ','.join(['?' for _ in projetos_filtro])
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
        parametros = [data_hoje] + projetos_filtro
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conn.close()
        
        if projeto_especifico:
            print(f"[INFO] Dados filtrados para projeto {projeto_especifico}: {len(resultados)} registros")
        
        return resultados
    except Exception as e:
        print(f"[ERRO] Falha ao consultar dados hoje: {e}")
        return []

def obter_dados_detalhados_periodo(data_inicio, data_fim, numero_usuario, projeto_especifico=None):
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        projetos_usuario = obter_projetos_usuario(numero_usuario)
        
        # Se projeto específico foi informado, verificar se usuário tem acesso
        if projeto_especifico:
            if projeto_especifico not in projetos_usuario:
                print(f"[ERRO] Usuário {numero_usuario} não tem acesso ao projeto {projeto_especifico}")
                return []
            projetos_filtro = [projeto_especifico]
        else:
            projetos_filtro = projetos_usuario
            
        if not projetos_filtro:
            return []
            
        placeholders = ','.join(['?' for _ in projetos_filtro])
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
        parametros = [data_inicio, data_fim] + projetos_filtro
        cursor.execute(query, parametros)
        resultados = cursor.fetchall()
        conn.close()
        
        if projeto_especifico:
            print(f"[INFO] Dados filtrados para projeto {projeto_especifico} no período: {len(resultados)} registros")
            
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

def obter_supervisores_por_faturamento(projetos_usuario, data_inicio=None, data_fim=None):
    """Busca ranking de supervisores por faturamento"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        if not projetos_usuario:
            return []
            
        placeholders = ','.join(['?' for _ in projetos_usuario])
        
        if data_inicio and data_fim:
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
        
        return [(supervisor, faturado) for supervisor, faturado in resultados if faturado > 0]
        
    except Exception as e:
        print(f"[ERRO] Falha ao buscar supervisores: {e}")
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
    if not modalidade:
        return "N/A"
    
    modalidade_limpa = modalidade.strip()
    
    normalizacao = {
        'mec': 'Mec', 'MEC': 'Mec', 'mecânica': 'Mec', 'mecanica': 'Mec',
        'man': 'Man', 'MAN': 'Man', 'manual': 'Man',
        'apo': 'Apo', 'APO': 'Apo', 'apoio': 'Apo',
        'dro': 'Dro', 'DRO': 'Dro', 'drone': 'Dro'
    }
    
    modalidade_lower = modalidade_limpa.lower()
    if modalidade_lower in normalizacao:
        return normalizacao[modalidade_lower]
    
    return modalidade_limpa.capitalize()

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_numero(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_resumo_geral(dados, numero_usuario, titulo_data, data_inicio=None, data_fim=None):
    resumo_projetos, projetos_modalidade, _, _ = agrupar_dados_completo(dados)
    nome_usuario = obter_nome_usuario(numero_usuario)
    projetos_usuario = obter_projetos_usuario(numero_usuario)
    classes_info = obter_colaboradores_por_classe(projetos_usuario)

    texto = f"📊 {titulo_data}\n\n"
    texto += f"🎯 RESUMO GERAL - {nome_usuario}\n\n"
    total_faturado = sum(proj['faturado'] for proj in resumo_projetos.values())
    texto += f"💰 Faturado Total: {formatar_moeda(total_faturado)}\n"

    modalidades_totais = defaultdict(lambda: {'producao': 0, 'faturado': 0})
    for projeto, mods in projetos_modalidade.items():
        for mod, dados_mod in mods.items():
            modalidades_totais[mod]['producao'] += dados_mod['producao']
            modalidades_totais[mod]['faturado'] += dados_mod['faturado']

    for mod, tot in modalidades_totais.items():
        texto += f"{mod}: {formatar_numero(tot['producao'])} | {formatar_moeda(tot['faturado'])}\n"

    texto += f"---------------------------------------------\n"

    total_colabs = sum(sum(cl.values()) for cl in classes_info.values())
    texto += f"👤Colaboradores: {total_colabs}\n"
    todas_classes = defaultdict(int)
    for classes in classes_info.values():
        for classe, qtd in classes.items():
            todas_classes[classe] += qtd
    for classe, qtd in todas_classes.items():
        texto += f"👤 {classe}: {qtd}\n"

    texto += f"---------------------------------------------\n"

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

    texto += f"-----------------------------------------------\n"

    if resumo_projetos:
        texto += f"🏆 RANKING FATURAMENTO POR PROJETO\n"
        projetos_ordenados = sorted(
            resumo_projetos.items(), 
            key=lambda x: x[1]['faturado'], 
            reverse=True
        )
        
        posicao = 1
        for projeto, dados_proj in projetos_ordenados:
            if dados_proj['faturado'] > 0:
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
    
    # Padrão para projeto específico com data numérica
    padrao_projeto_numerico = r'(?:produção|producao|faturamento)\s+projeto\s+(\d+)\s+(\d{1,2})[/](\d{1,2})(?:[/](\d{4}))?\s*(?:a|até)\s*(\d{1,2})[/](\d{1,2})(?:[/](\d{4}))?'
    match_projeto_numerico = re.search(padrao_projeto_numerico, texto)
    
    if match_projeto_numerico:
        projeto = match_projeto_numerico.group(1)
        dia_inicio = match_projeto_numerico.group(2).zfill(2)
        mes_inicio = match_projeto_numerico.group(3).zfill(2)
        ano_inicio = match_projeto_numerico.group(4) if match_projeto_numerico.group(4) else str(datetime.now().year)
        dia_fim = match_projeto_numerico.group(5).zfill(2)
        mes_fim = match_projeto_numerico.group(6).zfill(2)
        ano_fim = match_projeto_numerico.group(7) if match_projeto_numerico.group(7) else str(datetime.now().year)
        
        data_inicio = f"{dia_inicio}/{mes_inicio}/{ano_inicio}"
        data_fim = f"{dia_fim}/{mes_fim}/{ano_fim}"
        
        return "projeto_periodo", f"{projeto}|{data_inicio} A {data_fim}"
    
    # Padrão para projeto específico com período
    padrao_projeto_periodo = r'(?:produção|producao|faturamento)\s+projeto\s+(\d+)\s+(?:dia\s+)?(\d{1,2})\s*(?:a|até|de)\s*(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_projeto_periodo = re.search(padrao_projeto_periodo, texto)
    
    if match_projeto_periodo:
        projeto = match_projeto_periodo.group(1)
        dia_inicio = match_projeto_periodo.group(2).zfill(2)
        dia_fim = match_projeto_periodo.group(3).zfill(2)
        mes_nome = match_projeto_periodo.group(4).lower()
        
        meses = {
            'janeiro': '01', 'jan': '01', 'fevereiro': '02', 'fev': '02', 
            'março': '03', 'mar': '03', 'abril': '04', 'abr': '04',
            'maio': '05', 'mai': '05', 'junho': '06', 'jun': '06',
            'julho': '07', 'jul': '07', 'agosto': '08', 'ago': '08',
            'setembro': '09', 'set': '09', 'outubro': '10', 'out': '10',
            'novembro': '11', 'nov': '11', 'dezembro': '12', 'dez': '12'
        }
        
        mes = meses.get(mes_nome, '07')
        ano = str(datetime.now().year)
        
        data_inicio = f"{dia_inicio}/{mes}/{ano}"
        data_fim = f"{dia_fim}/{mes}/{ano}"
        
        return "projeto_periodo", f"{projeto}|{data_inicio} A {data_fim}"
    
    # Padrão para projeto específico hoje
    padrao_projeto_hoje = r'(?:produção|producao|faturamento)\s+projeto\s+(\d+)\s+(?:do\s+dia|hoje)'
    match_projeto_hoje = re.search(padrao_projeto_hoje, texto)
    
    if match_projeto_hoje:
        projeto = match_projeto_hoje.group(1)
        return "projeto_hoje", projeto
    
    # Padrão para projeto específico em data específica
    padrao_projeto_data = r'(?:produção|producao|faturamento)\s+projeto\s+(\d+)\s+(?:dia\s+)?(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_projeto_data = re.search(padrao_projeto_data, texto)
    
    if match_projeto_data:
        projeto = match_projeto_data.group(1)
        dia = match_projeto_data.group(2).zfill(2)
        mes_nome = match_projeto_data.group(3).lower()
        
        meses = {
            'janeiro': '01', 'jan': '01', 'fevereiro': '02', 'fev': '02', 
            'março': '03', 'mar': '03', 'abril': '04', 'abr': '04',
            'maio': '05', 'mai': '05', 'junho': '06', 'jun': '06',
            'julho': '07', 'jul': '07', 'agosto': '08', 'ago': '08',
            'setembro': '09', 'set': '09', 'outubro': '10', 'out': '10',
            'novembro': '11', 'nov': '11', 'dezembro': '12', 'dez': '12'
        }
        
        mes = meses.get(mes_nome, '07')
        ano = str(datetime.now().year)
        data_br = f"{dia}/{mes}/{ano}"
        
        return "projeto_periodo", f"{projeto}|{data_br} A {data_br}"
    
    # Padrão para "do dia" com data específica (TODOS OS PROJETOS)
    padrao_dia_especifico = r'(?:produção|producao|faturamento)\s+do\s+dia\s+(\d{1,2})[/](\d{1,2})(?:[/](\d{4}))?'
    match_dia_especifico = re.search(padrao_dia_especifico, texto)
    
    if match_dia_especifico:
        dia = match_dia_especifico.group(1).zfill(2)
        mes = match_dia_especifico.group(2).zfill(2)
        ano = match_dia_especifico.group(3) if match_dia_especifico.group(3) else str(datetime.now().year)
        data_br = f"{dia}/{mes}/{ano}"
        periodo = f"{data_br} A {data_br}"
        return "periodo", periodo
    
    # Padrões originais (sem projeto específico)
    padrao_periodo = r'(\d{1,2})\s*(?:a|até|de)\s*(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_periodo = re.search(padrao_periodo, texto)
    
    if match_periodo:
        dia_inicio = match_periodo.group(1).zfill(2)
        dia_fim = match_periodo.group(2).zfill(2)
        mes_nome = match_periodo.group(3).lower()
        
        meses = {
            'janeiro': '01', 'jan': '01', 'fevereiro': '02', 'fev': '02', 
            'março': '03', 'mar': '03', 'abril': '04', 'abr': '04',
            'maio': '05', 'mai': '05', 'junho': '06', 'jun': '06',
            'julho': '07', 'jul': '07', 'agosto': '08', 'ago': '08',
            'setembro': '09', 'set': '09', 'outubro': '10', 'out': '10',
            'novembro': '11', 'nov': '11', 'dezembro': '12', 'dez': '12'
        }
        
        mes = meses.get(mes_nome, '07')
        ano = str(datetime.now().year)
        
        data_inicio = f"{dia_inicio}/{mes}/{ano}"
        data_fim = f"{dia_fim}/{mes}/{ano}"
        
        return "periodo", f"{data_inicio} A {data_fim}"
    
    # Padrão original para datas numéricas (TODOS OS PROJETOS)
    padrao_data = r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\s*(?:a|até)\s*(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?'
    match_data = re.search(padrao_data, texto)
    if match_data:
        dia_inicio = match_data.group(1).zfill(2)
        mes_inicio = match_data.group(2).zfill(2)
        ano_inicio = match_data.group(3) if match_data.group(3) else str(datetime.now().year)
        dia_fim = match_data.group(4).zfill(2)
        mes_fim = match_data.group(5).zfill(2)
        ano_fim = match_data.group(6) if match_data.group(6) else str(datetime.now().year)
        
        data_inicio = f"{dia_inicio}/{mes_inicio}/{ano_inicio}"
        data_fim = f"{dia_fim}/{mes_fim}/{ano_fim}"
        periodo = f"{data_inicio} A {data_fim}"
        return "periodo", periodo
    
    # Padrão para data única numérica (TODOS OS PROJETOS)
    padrao_data_unica = r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?'
    match_data_unica = re.search(padrao_data_unica, texto)
    if match_data_unica:
        dia = match_data_unica.group(1).zfill(2)
        mes = match_data_unica.group(2).zfill(2)
        ano = match_data_unica.group(3) if match_data_unica.group(3) else str(datetime.now().year)
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

🎤 *COMANDOS GERAIS (todos os projetos):*
• "produção do dia" → hoje
• "produção do dia 01/08" → data específica
• "produção de 01/08 a 03/08" → período

🎯 *COMANDOS POR PROJETO ESPECÍFICO:*
• "produção projeto 202 do dia" → projeto hoje
• "produção projeto 202 01/08 a 03/08" → projeto período
• "faturamento projeto 150 dia 15 de agosto"
"""
    return enviar_mensagem(numero, menu_texto)

# ================== HEALTH CHECK ENDPOINT ==================
@app.route('/health', methods=['GET'])
def health_check():
    try:
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
        
        # Verificação de autorização
        if not verificar_autorizacao(numero):
            print(f"[DEBUG] Usuário não autorizado: {numero}")
            enviar_mensagem_nao_autorizado(numero)
            return '', 200
        
        # Controle de spam
        if not pode_processar_comando(numero):
            print(f"[DEBUG] ❌ SPAM BLOQUEADO para {numero}")
            return '', 200
        
        # Gerar hash único
        hash_mensagem = gerar_hash_mensagem(dados, numero)
        
        # Verificar duplicação
        if ja_processou_mensagem(hash_mensagem):
            print(f"[DEBUG] ❌ MENSAGEM DUPLICADA: {hash_mensagem[:8]}")
            return '', 200
        
        print(f"[DEBUG] ✅ PROCESSANDO: {hash_mensagem[:8]}")
        
        # PROCESSAMENTO DE ÁUDIO
        if "audio" in dados:
            print(f"[DEBUG] Iniciando processamento de ÁUDIO")
            url_audio = dados["audio"].get("audioUrl")
            if not url_audio:
                return '', 200
                
            caminho_wav = baixar_e_converter_audio(url_audio)
            if not caminho_wav:
                return '', 200
                
            texto_transcrito = transcrever_com_speech_recognition(caminho_wav)
            if not texto_transcrito:
                return '', 200
                
            print(f"[DEBUG] Áudio transcrito: '{texto_transcrito}'")
            comando, parametro = processar_comando_audio(texto_transcrito)
            
            if comando == "producao_hoje":
                dados_prod = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_prod, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_prod, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                time.sleep(4)
                enviar_mensagem(numero, detalhado)
                
            elif comando == "projeto_hoje" and parametro:
                projeto_id = parametro
                dados_prod = obter_dados_detalhados_hoje(numero, projeto_id)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                
                if dados_prod:
                    resumo = formatar_resumo_geral(dados_prod, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}", None, None)
                    detalhado = formatar_resumo_detalhado(dados_prod, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}")
                    
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                    time.sleep(4)
                    enviar_mensagem(numero, detalhado)
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Nenhum dado encontrado para o projeto {projeto_id} hoje, ou você não tem acesso a este projeto.")
                
            elif comando == "projeto_periodo" and parametro:
                partes = parametro.split("|")
                projeto_id = partes[0]
                periodo_str = partes[1]
                
                data_inicio, data_fim = processar_periodo(periodo_str)
                
                if data_inicio and data_fim:
                    dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero, projeto_id)
                    data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                    data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                    
                    if dados_periodo:
                        resumo = formatar_resumo_geral(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                        detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}")
                        
                        enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                        time.sleep(4)
                        enviar_mensagem(numero, detalhado)
                    else:
                        enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Nenhum dado encontrado para o projeto {projeto_id} no período informado.")
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Não consegui entender a data informada.")
                
            elif comando == "periodo" and parametro:
                data_inicio, data_fim = processar_periodo(parametro)
                if data_inicio and data_fim:
                    dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                    data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                    data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                    resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                    detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                    
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}")
                    time.sleep(4)
                    enviar_mensagem(numero, detalhado)
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Não consegui entender a data informada.")
            else:
                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n\n❌ Não reconheci o comando. Envie novamente ou digite *menu*.")
        
        # PROCESSAMENTO DE TEXTO
        elif "text" in dados:
            mensagem = dados["text"]["message"].lower().strip()
            
            if ("trial" in mensagem and "favor desconsiderar" in mensagem) or len(mensagem) > 500:
                return '', 200
            
            print(f"[DEBUG] Processando TEXTO: '{mensagem[:50]}...'")
            
            if mensagem in ["oi", "menu"]:
                enviar_menu(numero)
                
            elif mensagem == "1":
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_mensagem(numero, resumo)
                time.sleep(4)
                enviar_mensagem(numero, detalhado)
                
            elif mensagem == "produção" or mensagem == "producao":
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_mensagem(numero, resumo)
                time.sleep(4)
                enviar_mensagem(numero, detalhado)
                
            else:
                comando, parametro = processar_comando_audio(mensagem)
                
                if comando == "projeto_hoje" and parametro:
                    projeto_id = parametro
                    dados_detalhados = obter_dados_detalhados_hoje(numero, projeto_id)
                    data_hoje = datetime.today().strftime('%d/%m/%Y')
                    
                    if dados_detalhados:
                        resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}", None, None)
                        detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}")
                        
                        enviar_mensagem(numero, resumo)
                        time.sleep(4)
                        enviar_mensagem(numero, detalhado)
                    else:
                        enviar_mensagem(numero, f"❌ Nenhum dado encontrado para o projeto {projeto_id} hoje, ou você não tem acesso a este projeto.")
                        
                elif comando == "projeto_periodo" and parametro:
                    partes = parametro.split("|")
                    projeto_id = partes[0]
                    periodo_str = partes[1]
                    
                    data_inicio, data_fim = processar_periodo(periodo_str)
                    
                    if data_inicio and data_fim:
                        dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero, projeto_id)
                        data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                        data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                        
                        if dados_periodo:
                            resumo = formatar_resumo_geral(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                            detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}")
                            
                            enviar_mensagem(numero, resumo)
                            time.sleep(4)
                            enviar_mensagem(numero, detalhado)
                        else:
                            enviar_mensagem(numero, f"❌ Nenhum dado encontrado para o projeto {projeto_id} no período informado.")
                    else:
                        enviar_mensagem(numero, "❌ Não consegui entender a data informada.")
                        
                elif comando == "periodo" and parametro:
                    data_inicio, data_fim = processar_periodo(parametro)
                    if data_inicio and data_fim:
                        dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                        data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                        data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                        resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                        detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                        
                        enviar_mensagem(numero, resumo)
                        time.sleep(4)
                        enviar_mensagem(numero, detalhado)
                    else:
                        enviar_mensagem(numero, "❌ Não consegui entender a data informada.")
                else:
                    enviar_mensagem(numero, "❓ Não reconheci o comando. Digite *menu* para ver as opções.")
        
        print(f"[DEBUG] ✅ PROCESSAMENTO CONCLUÍDO: {hash_mensagem[:8]}")
        return '', 200
        
    except Exception as e:
        print(f"[ERRO] Erro crítico no webhook: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

# ================== INICIALIZAÇÃO ==================
try:
    print("🔧 Inicializando para Gunicorn...")
    print("🔍 Testando conexão com banco de dados...")
    cache_usuarios = buscar_usuarios_autorizados()
    if cache_usuarios:
        print("✅ Inicialização do Gunicorn concluída")
        print(f"👥 {len(cache_usuarios)} usuários autorizados carregados")
    else:
        print("⚠️ Nenhum usuário carregado - verificar conexão DB")
except Exception as e:
    print(f"❌ Erro na inicialização: {e}")
    print("🔄 Bot continuará tentando conectar...")

if __name__ == '__main__':
    print("🤖 Bot Completo - Texto + Áudio iniciando...")
    print("🎤 Reconhecimento de voz: Google Speech Recognition")
    print("📊 Sistema: Produção com Controle por Usuário")
    print("🔐 Usuários carregados dinamicamente da tabela USUARIOS")
    print("🏆 NOVO: Ranking de projetos por faturamento")
    print("🏆 NOVO: Ranking de supervisores por faturamento")
    print("📅 CORRIGIDO: Processamento de períodos por voz")
    print("🎯 NOVO: Filtros por projeto específico")
    print("🚀 RAILWAY: Configurado para deploy em produção")
    
    try:
        print("🔍 Testando conexão inicial com banco...")
        cache_usuarios = buscar_usuarios_autorizados()
        if cache_usuarios:
            print(f"👥 {len(cache_usuarios)} usuários carregados com sucesso")
        else:
            print("⚠️ Aguardando conexão com banco de dados...")
    except Exception as e:
        print(f"❌ Erro na conexão inicial: {e}")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Servidor iniciando na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)