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
from pre_apontamento import processar_pre_apontamento

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
    print(f"⚠️ AVISO: Variáveis de ambiente não encontradas: {missing_vars}")
    print("🔍 Algumas funcionalidades podem não funcionar corretamente")
    print("💡 No Railway, verifique se estas variáveis estão configuradas")
else:
    print("🔐 Credenciais carregadas das variáveis de ambiente")

print(f"🌐 Conectando em: {DB_SERVER}")
print(f"📊 Database: {DB_DATABASE}")

# Controle de spam e duplicação - MAIS RIGOROSO
ultimo_comando = {}
numeros_ja_notificados = set()
mensagens_processadas = {}  # Cache para evitar reprocessamento

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
    """Controle rigoroso de spam por usuário - AUMENTADO para 15 segundos"""
    agora = time.time()
    ultima_vez = ultimo_comando.get(numero, 0)
    INTERVALO_MINIMO_NOVO = 15  # AUMENTADO de 10 para 15 segundos
    
    if agora - ultima_vez >= INTERVALO_MINIMO_NOVO:
        ultimo_comando[numero] = agora
        print(f"[DEBUG] ✅ Comando liberado para {numero}")
        return True
    else:
        tempo_restante = int(INTERVALO_MINIMO_NOVO - (agora - ultima_vez))
        print(f"[DEBUG] ❌ SPAM BLOQUEADO para {numero} - Aguarde {tempo_restante}s")
        return False

def gerar_hash_mensagem(dados, numero):
    """Gera hash único mais específico para cada mensagem SEM timestamp para evitar duplicação"""
    import hashlib
    
    if "audio" in dados:
        audio_url = dados["audio"].get("audioUrl", "")
        # REMOVIDO timestamp para evitar hashes diferentes da mesma mensagem
        conteudo = f"AUDIO_{numero}_{audio_url}"
    elif "text" in dados:
        texto = dados["text"].get("message", "")
        # REMOVIDO timestamp para evitar hashes diferentes da mesma mensagem
        conteudo = f"TEXT_{numero}_{texto}"
    else:
        conteudo = f"OTHER_{numero}"
    
    hash_final = hashlib.md5(conteudo.encode()).hexdigest()
    print(f"[DEBUG] Hash gerado: {hash_final[:8]} para {numero}")
    return hash_final

def ja_processou_mensagem(hash_mensagem):
    """Verifica se a mensagem já foi processada - Cache de 300 segundos (5 minutos)"""
    agora = time.time()
    
    # Limpar mensagens antigas (mais de 300 segundos - 5 minutos)
    hashes_removidos = []
    for hash_msg, timestamp in list(mensagens_processadas.items()):
        if agora - timestamp > 300:  # AUMENTADO de 60 para 300 segundos
            del mensagens_processadas[hash_msg]
            hashes_removidos.append(hash_msg[:8])
    
    if hashes_removidos:
        print(f"[DEBUG] Cache limpo: {len(hashes_removidos)} hashes removidos")
    
    # Verificar se já processou
    if hash_mensagem in mensagens_processadas:
        print(f"[DEBUG] ❌ MENSAGEM JÁ PROCESSADA: {hash_mensagem[:8]} - IGNORANDO!")
        return True
    
    # Marcar como processada
    mensagens_processadas[hash_mensagem] = agora
    print(f"[DEBUG] ✅ Hash registrado: {hash_mensagem[:8]}")
    return False

# ========== NOVA FUNÇÃO: VERIFICAR SE É MENSAGEM DE FRETE ==========
def eh_mensagem_frete(dados):
    """Verifica se a mensagem contém 'frete' - para ser ignorada pelo bot de produção"""
    
    # Verificar texto direto
    if "text" in dados and isinstance(dados["text"], dict):
        texto = dados["text"].get("message", "").lower()
        if "frete" in texto:
            print(f"[DEBUG] 🚚 MENSAGEM DE FRETE DETECTADA (TEXTO): ignorando")
            return True
    
    # Verificar áudio (precisaria transcrever, mas vamos usar uma heurística)
    if "audio" in dados:
        # Por performance, vamos assumir que se tem áudio E o usuário já mandou frete recentemente,
        # pode ser áudio de frete. Alternativamente, você pode transcrever aqui se necessário.
        print(f"[DEBUG] 🎤 ÁUDIO DETECTADO - Verificando se é frete...")
        
        # OPCIONAL: Você pode transcrever o áudio aqui para verificar se contém "frete"
        # Por agora, vamos deixar passar para não interferir no fluxo
        
    return False

# ========== NOVA FUNÇÃO: SALVAR FRETE NO BANCO ==========
def salvar_frete_no_banco(dados_frete, numero, texto_original=""):
    """Salva dados de frete na tabela FRETES_TEMP (tabela já existe)"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Inserir frete diretamente (tabela já existe)
        cursor.execute("""
        INSERT INTO dbo.FRETES_TEMP 
            (TIPO, PROJETO, SAIDA, DESTINO, KM_INICIAL, PHONE, RAW_TEXT)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            dados_frete["TIPO"],
            dados_frete.get("PROJETO"),
            dados_frete["SAIDA"], 
            dados_frete["DESTINO"],
            dados_frete["KM_INICIAL"],
            numero,
            texto_original
        ))
        
        conn.commit()
        conn.close()
        print(f"[DEBUG] ✅ FRETE SALVO NO BANCO: {dados_frete}")
        return True
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar frete: {e}")
        return False

# ========== NOVA FUNÇÃO: PROCESSAR COMANDO DE FRETE ==========
def processar_frete_texto(texto):
    """Extrai dados de frete do texto usando regex"""
    import re
    
    # Regex para capturar frete com projeto opcional
    padrao_frete = re.compile(
        r"\bfrete\b(?:\s*(?P<projeto>\d{2,6}))?.*?"
        r"(?:\bda\b|\bdo\b|\bdas\b|\bdos\b|\bde\b)\s+(?P<origem>[^,.;\n]+?)\s+"
        r"(?:\bpara\b|\bpra\b|\b->\b)\s+(?P<destino>[^,.;\n]+?)"
        r".*?(?:\bkm\b|\bkm\s*inicial\b|\bquilometragem\b|\bkm\s*é\b|\bkilometro\b).*?(?P<km>\d{1,7})",
        flags=re.IGNORECASE | re.UNICODE
    )
    
    # Regex flexível (sem "km" explícito, assume número grande é KM)
    padrao_frete_flex = re.compile(
        r"\bfrete\b(?:\s*(?P<projeto>\d{2,6}))?.*?"
        r"(?:\bda\b|\bdo\b|\bdas\b|\bdos\b|\bde\b)\s+(?P<origem>[^,.;\n]+?)\s+"
        r"(?:\bpara\b|\bpra\b|\b->\b)\s+(?P<destino>[^,.;\n]+?)"
        r".*?(?P<km>\d{4,7})\b",
        flags=re.IGNORECASE | re.UNICODE
    )
    
    def normalizar_local(s):
        s = " ".join(s.strip().split())
        return " ".join(p.capitalize() for p in s.split(" "))
    
    texto_limpo = " ".join(texto.split())
    match = padrao_frete.search(texto_limpo) or padrao_frete_flex.search(texto_limpo)
    
    if not match:
        return None
        
    projeto = match.group("projeto") if match.group("projeto") else None
    origem = normalizar_local(match.group("origem"))
    destino = normalizar_local(match.group("destino"))
    km = int(match.group("km"))
    
    return {
        "TIPO": "FRETE",
        "PROJETO": projeto,
        "SAIDA": origem,
        "DESTINO": destino,
        "KM_INICIAL": km
    }

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

def formatar_resumo_geral(dados, numero_usuario, titulo_data, data_inicio=None, data_fim=None, projeto_especifico=None):
    resumo_projetos, projetos_modalidade, _, _ = agrupar_dados_completo(dados)
    nome_usuario = obter_nome_usuario(numero_usuario)
    
    # Se projeto específico, usar só ele, senão usar todos os projetos do usuário
    if projeto_especifico:
        projetos_para_busca = [projeto_especifico]
    else:
        projetos_para_busca = obter_projetos_usuario(numero_usuario)
    
    classes_info = obter_colaboradores_por_classe(projetos_para_busca)

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

    # CORRIGIDO: Usar projetos filtrados para supervisores
    supervisores_ranking = obter_supervisores_por_faturamento(projetos_para_busca, data_inicio, data_fim)
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

    # AGRUPADO POR SERVIÇO - CORRIGIDO: Só projetos dos dados filtrados
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
    
    # NOVO PADRÃO CORRIGIDO: "produção do projeto X do dia Y a Z de mês"
    padrao_projeto_periodo_completo = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(?:do\s+)?dia\s+(\d{1,2})\s*(?:a|até)\s*(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_projeto_periodo_completo = re.search(padrao_projeto_periodo_completo, texto)
    
    if match_projeto_periodo_completo:
        projeto = match_projeto_periodo_completo.group(1)
        dia_inicio = match_projeto_periodo_completo.group(2).zfill(2)
        dia_fim = match_projeto_periodo_completo.group(3).zfill(2)
        mes_nome = match_projeto_periodo_completo.group(4).lower()
        
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
        
        print(f"[DEBUG] ✅ PROJETO PERÍODO DETECTADO: Projeto {projeto}, {data_inicio} a {data_fim}")
        return "projeto_periodo", f"{projeto}|{data_inicio} A {data_fim}"
    
    # PADRÃO CORRIGIDO: "produção do projeto X dia Y de mês" (data única)
    padrao_projeto_data_unica = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(?:do\s+)?dia\s+(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
    match_projeto_data_unica = re.search(padrao_projeto_data_unica, texto)
    
    if match_projeto_data_unica:
        projeto = match_projeto_data_unica.group(1)
        dia = match_projeto_data_unica.group(2).zfill(2)
        mes_nome = match_projeto_data_unica.group(3).lower()
        
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
        
        print(f"[DEBUG] ✅ PROJETO DATA ÚNICA DETECTADO: Projeto {projeto}, {data_br}")
        return "projeto_periodo", f"{projeto}|{data_br} A {data_br}"
    
    # NOVO: Padrão para projeto específico com data numérica SIMPLES
    padrao_projeto_data_simples = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(\d{1,2})[/](\d{1,2})(?:[/](\d{4}))?'
    match_projeto_data_simples = re.search(padrao_projeto_data_simples, texto)
    
    if match_projeto_data_simples:
        projeto = match_projeto_data_simples.group(1)
        dia = match_projeto_data_simples.group(2).zfill(2)
        mes = match_projeto_data_simples.group(3).zfill(2)
        ano = match_projeto_data_simples.group(4) if match_projeto_data_simples.group(4) else str(datetime.now().year)
        
        data_br = f"{dia}/{mes}/{ano}"
        
        print(f"[DEBUG] ✅ PROJETO DATA NUMÉRICA DETECTADO: Projeto {projeto}, {data_br}")
        return "projeto_periodo", f"{projeto}|{data_br} A {data_br}"
    
    # Padrão para projeto específico com data numérica (PERÍODO)
    padrao_projeto_numerico = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\s*(?:a|até)\s*(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?'
    match_projeto_numerico = re.search(padrao_projeto_numerico, texto)
    
    if match_projeto_numerico:
        projeto = match_projeto_numerico.group(1)
        dia_inicio = match_projeto_numerico.group(2).zfill(2)
        mes_inicio = match_projeto_numerico.group(3).zfill(2)
        ano_inicio = match_projeto_numerico.group(4) if match_projeto_numerico.group(4) else str(datetime.now().year)
        dia_fim = match_projeto_numerico.group(5).zfill(2)
        mes_fim = match_projeto_numerico.group(6).zfill(2)
        ano_fim = match_projeto_numerico.group(7) if match_projeto_numerico.group(7) else ano_inicio
        
        data_inicio = f"{dia_inicio}/{mes_inicio}/{ano_inicio}"
        data_fim = f"{dia_fim}/{mes_fim}/{ano_fim}"
        
        try:
            data_inicio_dt = datetime.strptime(data_inicio, '%d/%m/%Y')
            data_fim_dt = datetime.strptime(data_fim, '%d/%m/%Y')
            if data_fim_dt < data_inicio_dt:
                return "invalido", "Data final anterior à data inicial"
        except ValueError:
            return "invalido", "Formato de data inválido"
        
        return "projeto_periodo", f"{projeto}|{data_inicio} A {data_fim}"
    
    # Padrão para projeto específico com período
    padrao_projeto_periodo = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(?:dia\s+)?(\d{1,2})\s*(?:a|até|de)\s*(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
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
    padrao_projeto_hoje = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(?:do\s+dia|hoje)'
    match_projeto_hoje = re.search(padrao_projeto_hoje, texto)
    
    if match_projeto_hoje:
        projeto = match_projeto_hoje.group(1)
        return "projeto_hoje", projeto
    
    # Padrão para projeto específico em data específica
    padrao_projeto_data = r'(?:produção|producao|faturamento)\s+(?:do\s+)?projeto\s+(\d+)\s+(?:dia\s+)?(\d{1,2})\s*de\s*(julho|jul|janeiro|jan|fevereiro|fev|março|mar|abril|abr|maio|mai|junho|jun|agosto|ago|setembro|set|outubro|out|novembro|nov|dezembro|dez)'
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
            data_inicio_dt = datetime.strptime(data_inicio_str, '%d/%m/%Y')
            data_fim_dt = datetime.strptime(data_fim_str, '%d/%m/%Y')
            
            if data_fim_dt < data_inicio_dt:
                print(f"[ERRO] Data final ({data_fim_str}) anterior à data inicial ({data_inicio_str})")
                return None, None
                
            data_inicio = data_inicio_dt.strftime('%Y-%m-%d')
            data_fim = data_fim_dt.strftime('%Y-%m-%d')
            return data_inicio, data_fim
        except ValueError as e:
            print(f"[ERRO] Erro ao processar datas: {e}")
            return None, None
    print(f"[DEBUG] Período não reconhecido: {texto}")
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

def enviar_resposta_completa(numero, resumo, detalhado, texto_transcrito=None):
    """Envia resposta completa com controle para evitar duplicação"""
    try:
        if texto_transcrito:
            mensagem_inicial = f"🎤 Ouvi: \"{texto_transcrito}\"\n\n{resumo}"
        else:
            mensagem_inicial = resumo
            
        # Enviar mensagem inicial
        resposta1 = enviar_mensagem(numero, mensagem_inicial)
        if not resposta1 or resposta1.status_code != 200:
            print(f"[ERRO] Falha ao enviar primeira mensagem para {numero}")
            return False
            
        # Aguardar antes de enviar a segunda
        time.sleep(5)  # AUMENTADO de 4 para 5 segundos
        
        # Enviar detalhado
        resposta2 = enviar_mensagem(numero, detalhado)
        if not resposta2 or resposta2.status_code != 200:
            print(f"[ERRO] Falha ao enviar segunda mensagem para {numero}")
            return False
            
        print(f"[DEBUG] ✅ Resposta completa enviada para {numero}")
        return True
        
    except Exception as e:
        print(f"[ERRO] Erro ao enviar resposta completa: {e}")
        return False

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

🚚 *COMANDOS DE FRETE:*
• "frete da [origem] para [destino] km [número]"
• "frete 150 da São João para São Pedro km 50324"
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
        'name': 'Bot WhatsApp Sistema de Produção + Frete + Pré-Apontamento',
        'status': 'running',
        'version': '2.2 Railway - Sistema Completo',
        'timestamp': datetime.now().isoformat(),
        'endpoints': ['/webhook', '/webhook_pre_apont', '/webhook_aprovacao', '/health'],
        'features': ['Produção', 'Frete', 'Áudio STT', 'Pré-Apontamento', 'Aprovação Coordenador']
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
        
        # ========== NOVA VERIFICAÇÃO: IGNORAR FRETES ==========
        if eh_mensagem_frete(dados):
            print(f"[DEBUG] 🚚 MENSAGEM DE FRETE - IGNORADA pelo bot de produção")
            return '', 200
        
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
        
        # ========== PROCESSAMENTO DE FRETE (TEXTO E ÁUDIO) ==========
        texto_para_frete = ""
        
        # Verificar se é texto
        if "text" in dados:
            texto_original = dados["text"].get("message", "").strip()
            if "frete" in texto_original.lower():
                print(f"[DEBUG] 🚚 Processando FRETE via TEXTO")
                dados_frete = processar_frete_texto(texto_original)
                if dados_frete:
                    if salvar_frete_no_banco(dados_frete, numero, texto_original):
                        resposta_frete = f"""✅ *FRETE REGISTRADO*
🚚 Tipo: {dados_frete['TIPO']}
🏗️ Projeto: {dados_frete.get('PROJETO') or 'N/A'}
📍 Saída: {dados_frete['SAIDA']}
🎯 Destino: {dados_frete['DESTINO']}
📏 KM Inicial: {dados_frete['KM_INICIAL']}"""
                        enviar_mensagem(numero, resposta_frete)
                    else:
                        enviar_mensagem(numero, "❌ Erro ao salvar frete. Tente novamente.")
                else:
                    enviar_mensagem(numero, "❌ Não consegui entender o frete. Use o formato: 'frete da [origem] para [destino] km [número]'")
                return '', 200
        
        # Verificar se é áudio que pode conter frete
        elif "audio" in dados:
            print(f"[DEBUG] 🎤 Processando ÁUDIO - verificando se é frete")
            url_audio = dados["audio"].get("audioUrl")
            if url_audio:
                caminho_wav = baixar_e_converter_audio(url_audio)
                if caminho_wav:
                    texto_transcrito = transcrever_com_speech_recognition(caminho_wav)
                    if texto_transcrito:
                        print(f"[DEBUG] Áudio transcrito: '{texto_transcrito}'")
                        
                        # Verificar se contém "frete"
                        if "frete" in texto_transcrito.lower():
                            print(f"[DEBUG] 🚚 FRETE detectado no áudio")
                            dados_frete = processar_frete_texto(texto_transcrito)
                            if dados_frete:
                                if salvar_frete_no_banco(dados_frete, numero, texto_transcrito):
                                    resposta_frete = f"""✅ *FRETE REGISTRADO (ÁUDIO)*
🎤 Ouvi: "{texto_transcrito}"
🚚 Tipo: {dados_frete['TIPO']}
🏗️ Projeto: {dados_frete.get('PROJETO') or 'N/A'}
📍 Saída: {dados_frete['SAIDA']}
🎯 Destino: {dados_frete['DESTINO']}
📏 KM Inicial: {dados_frete['KM_INICIAL']}"""
                                    enviar_mensagem(numero, resposta_frete)
                                else:
                                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n❌ Erro ao salvar frete.")
                            else:
                                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_transcrito}\"\n❌ Não identifiquei um frete válido.")
                            return '', 200
                        else:
                            # Não é frete, continuar com processamento normal de produção
                            texto_para_frete = texto_transcrito
        
        # ========== PROCESSAMENTO DE PRODUÇÃO (AUDIO) ==========
        if "audio" in dados and not texto_para_frete:
            print(f"[DEBUG] Iniciando processamento de ÁUDIO para PRODUÇÃO")
            url_audio = dados["audio"].get("audioUrl")
            if not url_audio:
                return '', 200
                
            caminho_wav = baixar_e_converter_audio(url_audio)
            if not caminho_wav:
                return '', 200
                
            texto_transcrito = transcrever_com_speech_recognition(caminho_wav)
            if not texto_transcrito:
                return '', 200
            
            texto_para_frete = texto_transcrito
        
        # Se temos texto transcrito do áudio, usar ele
        if texto_para_frete:
            print(f"[DEBUG] Áudio transcrito: '{texto_para_frete}'")
            comando, parametro = processar_comando_audio(texto_para_frete)
            
            if comando == "producao_hoje":
                dados_prod = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_prod, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_prod, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_resposta_completa(numero, resumo, detalhado, texto_para_frete)
                
            elif comando == "projeto_hoje" and parametro:
                projeto_id = parametro
                dados_prod = obter_dados_detalhados_hoje(numero, projeto_id)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                
                if dados_prod:
                    resumo = formatar_resumo_geral(dados_prod, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}", None, None, projeto_id)
                    detalhado = formatar_resumo_detalhado(dados_prod, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}")
                    
                    enviar_resposta_completa(numero, resumo, detalhado, texto_para_frete)
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_para_frete}\"\n\n❌ Nenhum dado encontrado para o projeto {projeto_id} hoje, ou você não tem acesso a este projeto.")
                
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
                        resumo = formatar_resumo_geral(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim, projeto_id)
                        detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}")
                        
                        enviar_resposta_completa(numero, resumo, detalhado, texto_para_frete)
                    else:
                        enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_para_frete}\"\n\n❌ Nenhum dado encontrado para o projeto {projeto_id} no período {data_inicio_br} a {data_fim_br}, ou você não tem acesso a este projeto.")
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_para_frete}\"\n\n❌ Não consegui entender o período informado. Use o formato DD/MM/YYYY a DD/MM/YYYY.")
                
            elif comando == "periodo" and parametro:
                data_inicio, data_fim = processar_periodo(parametro)
                if data_inicio and data_fim:
                    dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                    data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                    data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                    resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                    detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                    
                    enviar_resposta_completa(numero, resumo, detalhado, texto_para_frete)
                else:
                    enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_para_frete}\"\n\n❌ Não consegui entender a data informada.")
            else:
                enviar_mensagem(numero, f"🎤 Ouvi: \"{texto_para_frete}\"\n\n❌ Não reconheci o comando. Envie novamente ou digite *menu*.")
                
        # ========== PROCESSAMENTO DE TEXTO ==========
        elif "text" in dados:
            mensagem = dados["text"]["message"].lower().strip()
            mensagem_original = dados["text"]["message"].strip()  # Manter original para pré-apontamento
            
            if ("trial" in mensagem and "favor desconsiderar" in mensagem) or len(mensagem) > 500:
                return '', 200
            
            print(f"[DEBUG] Processando TEXTO: '{mensagem[:50]}...'")
            
            # ========== VERIFICAÇÃO DE PRÉ-APONTAMENTO ==========
            print(f"[DEBUG] 🔍 Verificando se é pré-apontamento...")
            resultado_pre_apont = processar_pre_apontamento(numero, mensagem_original)
            print(f"[DEBUG] 📊 Resultado pré-apont: {resultado_pre_apont}")
            
            if resultado_pre_apont['is_pre_apont']:
                print(f"[DEBUG] 📋 PRÉ-APONTAMENTO detectado")
                enviar_mensagem(numero, resultado_pre_apont['resposta'])
                return '', 200
            else:
                print(f"[DEBUG] ➡️ Não é pré-apontamento, continuando...")
            
            if mensagem in ["oi", "menu"]:
                enviar_menu(numero)
                
            elif mensagem == "1":
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_resposta_completa(numero, resumo, detalhado)
                
            elif mensagem == "produção" or mensagem == "producao":
                dados_detalhados = obter_dados_detalhados_hoje(numero)
                data_hoje = datetime.today().strftime('%d/%m/%Y')
                resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}", None, None)
                detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO {data_hoje}")
                
                enviar_resposta_completa(numero, resumo, detalhado)
                
            else:
                comando, parametro = processar_comando_audio(mensagem)
                
                if comando == "projeto_hoje" and parametro:
                    projeto_id = parametro
                    dados_detalhados = obter_dados_detalhados_hoje(numero, projeto_id)
                    data_hoje = datetime.today().strftime('%d/%m/%Y')
                    
                    if dados_detalhados:
                        resumo = formatar_resumo_geral(dados_detalhados, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}", None, None, projeto_id)
                        detalhado = formatar_resumo_detalhado(dados_detalhados, numero, f"PRODUÇÃO PROJETO {projeto_id} - {data_hoje}")
                        
                        enviar_resposta_completa(numero, resumo, detalhado)
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
                            resumo = formatar_resumo_geral(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim, projeto_id)
                            detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PROJETO {projeto_id} - PERÍODO {data_inicio_br} a {data_fim_br}")
                            
                            enviar_resposta_completa(numero, resumo, detalhado)
                        else:
                            enviar_mensagem(numero, f"❌ Nenhum dado encontrado para o projeto {projeto_id} no período {data_inicio_br} a {data_fim_br}, ou você não tem acesso a este projeto.")
                    else:
                        enviar_mensagem(numero, f"❌ Não consegui entender o período informado. Use o formato DD/MM/YYYY a DD/MM/YYYY.")
                        
                elif comando == "periodo" and parametro:
                    data_inicio, data_fim = processar_periodo(parametro)
                    if data_inicio and data_fim:
                        dados_periodo = obter_dados_detalhados_periodo(data_inicio, data_fim, numero)
                        data_inicio_br = datetime.strptime(data_inicio, '%Y-%m-%d').strftime('%d/%m/%Y')
                        data_fim_br = datetime.strptime(data_fim, '%Y-%m-%d').strftime('%d/%m/%Y')
                        resumo = formatar_resumo_geral(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}", data_inicio, data_fim)
                        detalhado = formatar_resumo_detalhado(dados_periodo, numero, f"PERÍODO {data_inicio_br} a {data_fim_br}")
                        
                        enviar_resposta_completa(numero, resumo, detalhado)
                    else:
                        enviar_mensagem(numero, f"❌ Não consegui entender o período informado. Use o formato DD/MM/YYYY a DD/MM/YYYY.")
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

@app.route('/webhook_pre_apont', methods=['POST'])
@app.route('/webhook_pre_apont', methods=['POST'])
def webhook_pre_apontamento_dedicado():
    """Webhook dedicado APENAS para pré-apontamento"""
    try:
        dados = request.json
        print(f"[PRE-BOT] ========== WEBHOOK PRÉ-APONTAMENTO ==========")
        print(f"[PRE-BOT] Número: {dados.get('phone')}")
        print(f"[PRE-BOT] Tipo: {dados.get('type', 'UNKNOWN')}")
        
        # 🚨 VERIFICAÇÃO CRÍTICA: Ignorar mensagens do próprio bot
        if dados.get('fromMe', False):
            print(f"[PRE-BOT] ⏭️ Ignorando mensagem do próprio bot (fromMe=True)")
            return "OK"
        
        # 🚨 VERIFICAÇÃO ADICIONAL: Ignorar mensagens da API
        if dados.get('fromApi', False):
            print(f"[PRE-BOT] ⏭️ Ignorando mensagem da API (fromApi=True)")
            return "OK"
        
        # Log completo dos dados para debug
        print(f"[PRE-BOT] 🔍 Dados completos: {dados}")
        
        numero = dados.get("phone")
        tipo_mensagem = dados.get("type")
        
        # Verificar se tem mensagem de texto (várias possibilidades)
        mensagem_original = None
        button_response = None
        
        # 1. VERIFICAR SE É CLIQUE EM BOTÃO (PRIORIDADE)
        if tipo_mensagem == "ButtonResponse":
            button_response = dados.get("buttonResponse", {})
            print(f"[PRE-BOT] 🔘 ButtonResponse detectado: {button_response}")
            
        elif tipo_mensagem == "InteractiveResponse":
            interactive = dados.get("interactiveResponse", {})
            button_response = interactive.get("buttonReply", {})
            print(f"[PRE-BOT] 🔘 InteractiveResponse detectado: {button_response}")
            
        elif dados.get("selectedButtonId"):  # Formato alternativo
            button_response = {
                "id": dados.get("selectedButtonId"),
                "title": dados.get("selectedButtonTitle", "")
            }
            print(f"[PRE-BOT] 🔘 SelectedButton detectado: {button_response}")
        
        # 2. SE FOR BOTÃO DE APROVAÇÃO, PROCESSAR
        if button_response and button_response.get("id"):
            button_id = button_response.get("id")
            button_title = button_response.get("title", "")
            
            print(f"[PRE-BOT] 🎯 Botão clicado: {button_id} - {button_title}")
            
            # Verificar se é botão de aprovação
            if any(button_id.startswith(prefix) for prefix in ["aprovar_", "rejeitar_", "corrigir_"]):
                print(f"[PRE-BOT] ✅ Processando aprovação de coordenador...")
                
                from pre_apontamento import processar_aprovacao_coordenador
                
                resultado = processar_aprovacao_coordenador(
                    button_id=button_id,
                    telefone_coordenador=numero,
                    mensagem_adicional=""
                )
                
                if resultado:
                    print(f"[PRE-BOT] ✅ Aprovação processada!")
                    resposta = "✅ Sua resposta foi processada com sucesso!"
                else:
                    print(f"[PRE-BOT] ❌ Erro na aprovação")
                    resposta = "❌ Erro ao processar sua resposta. Tente novamente."
                
                enviar_mensagem(numero, resposta)
                return '', 200
        
        # 3. SE NÃO FOR BOTÃO, PROCESSAR COMO MENSAGEM DE TEXTO
        if tipo_mensagem == "text" and dados.get("text", {}).get("message"):
            mensagem_original = dados["text"]["message"].strip()
        elif tipo_mensagem == "ReceivedCallback" and dados.get("text", {}).get("message"):
            mensagem_original = dados["text"]["message"].strip()
        elif dados.get("message"):  # Fallback
            mensagem_original = str(dados.get("message")).strip()

        if mensagem_original:
            print(f"[PRE-BOT] 📝 Mensagem: '{mensagem_original[:100]}...'")
            
            # 🆕 PRIMEIRO: Verificar se é resposta de coordenador (SIM/NAO/CORRIGIR)
            from pre_apontamento import detectar_resposta_coordenador
            
            resposta_coord = detectar_resposta_coordenador(mensagem_original, numero)
            
            if resposta_coord['is_resposta_coord']:
                print(f"[PRE-BOT] ✅ RESPOSTA DE COORDENADOR detectada!")
                print(f"[PRE-BOT] 🎯 Ação: {resposta_coord.get('acao')} para RAW_ID {resposta_coord.get('raw_id')}")
                
                from pre_apontamento import processar_aprovacao_coordenador
                
                resultado = processar_aprovacao_coordenador(
                    button_id=resposta_coord['button_id'],
                    telefone_coordenador=numero,
                    mensagem_adicional=""
                )
                
                if resultado:
                    print(f"[PRE-BOT] ✅ Aprovação processada!")
                    resposta = "✅ Sua resposta foi processada com sucesso!"
                else:
                    print(f"[PRE-BOT] ❌ Erro na aprovação")
                    resposta = "❌ Erro ao processar sua resposta. Tente novamente."
                
                enviar_mensagem(numero, resposta)
                return '', 200
            
            # Se não for resposta de coordenador, processar como pré-apontamento normal
            print(f"[PRE-BOT] 🔍 Processando como pré-apontamento...")
            
            resultado_pre_apont = processar_pre_apontamento(numero, mensagem_original)
            
            print(f"[PRE-BOT] 📊 Resultado: {resultado_pre_apont}")
            
            if resultado_pre_apont['is_pre_apont']:
                print(f"[PRE-BOT] ✅ PRÉ-APONTAMENTO detectado!")
                enviar_mensagem(numero, resultado_pre_apont['resposta'])
                print(f"[PRE-BOT] 📤 Resposta enviada")
            else:
                print(f"[PRE-BOT] ➡️ Não é pré-apontamento")
        else:
            print(f"[PRE-BOT] ⚠️ Sem mensagem de texto para processar")
        
        return '', 200
        
    except Exception as e:
        print(f"[PRE-BOT] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

@app.route('/webhook_aprovacao', methods=['POST'])
def webhook_aprovacao_coordenador():
    """Webhook para processar aprovações de coordenadores (botões)"""
    try:
        dados = request.json
        print(f"[APRV-BOT] ========== WEBHOOK APROVAÇÃO ==========")
        print(f"[APRV-BOT] 📦 Dados recebidos: {dados}")
        
        # 🚨 VERIFICAÇÃO: Ignorar mensagens do próprio bot
        if dados.get('fromMe', False):
            print(f"[APRV-BOT] ⏭️ Ignorando mensagem do próprio bot")
            return "OK"
        
        numero = dados.get("phone")
        tipo_mensagem = dados.get("type")
        
        print(f"[APRV-BOT] 📞 Número: {numero}")
        print(f"[APRV-BOT] 🔄 Tipo: {tipo_mensagem}")
        
        # Verificar se é um clique em botão
        button_response = None
        mensagem_adicional = ""
        
        # Diferentes formatos de resposta de botão no Z-API
        if tipo_mensagem == "ButtonResponse":
            button_response = dados.get("buttonResponse", {})
            print(f"[APRV-BOT] 🔘 ButtonResponse detectado: {button_response}")
            
        elif tipo_mensagem == "InteractiveResponse":
            interactive = dados.get("interactiveResponse", {})
            button_response = interactive.get("buttonReply", {})
            print(f"[APRV-BOT] 🔘 InteractiveResponse detectado: {button_response}")
            
        elif dados.get("selectedButtonId"):  # Formato alternativo
            button_response = {
                "id": dados.get("selectedButtonId"),
                "title": dados.get("selectedButtonTitle", "")
            }
            print(f"[APRV-BOT] 🔘 SelectedButton detectado: {button_response}")
        
        if button_response and button_response.get("id"):
            button_id = button_response.get("id")
            button_title = button_response.get("title", "")
            
            print(f"[APRV-BOT] 🎯 Processando botão: {button_id} - {button_title}")
            
            # Verificar se é um botão de aprovação (prefixos: aprovar_, rejeitar_, corrigir_)
            if any(button_id.startswith(prefix) for prefix in ["aprovar_", "rejeitar_", "corrigir_"]):
                print(f"[APRV-BOT] ✅ Botão de aprovação identificado!")
                
                # Verificar se há mensagem adicional do coordenador
                if tipo_mensagem == "text" and dados.get("text", {}).get("message"):
                    mensagem_adicional = dados["text"]["message"].strip()
                elif dados.get("message"):
                    mensagem_adicional = str(dados.get("message", "")).strip()
                
                # Processar aprovação
                from pre_apontamento import processar_aprovacao_coordenador
                
                resultado = processar_aprovacao_coordenador(
                    button_id=button_id,
                    telefone_coordenador=numero,
                    mensagem_adicional=mensagem_adicional
                )
                
                if resultado:
                    print(f"[APRV-BOT] ✅ Aprovação processada com sucesso!")
                    resposta = "✅ Sua resposta foi processada com sucesso!"
                else:
                    print(f"[APRV-BOT] ❌ Erro ao processar aprovação")
                    resposta = "❌ Erro ao processar sua resposta. Tente novamente."
                
                # Enviar confirmação
                enviar_mensagem(numero, resposta)
                
            else:
                print(f"[APRV-BOT] ⚠️ Botão não relacionado a aprovação: {button_id}")
        else:
            print(f"[APRV-BOT] ⚠️ Não é um clique em botão válido")
        
        return '', 200
        
    except Exception as e:
        print(f"[APRV-BOT] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

if __name__ == '__main__':
    print("🤖 Bot Integrado - Produção + Frete (Texto + Áudio) iniciando...")
    print("🎤 Reconhecimento de voz: Google Speech Recognition")
    print("📊 Sistema: Produção com Controle por Usuário")
    print("🚚 Sistema: Fretes com captura por texto e áudio")
    print("🔐 Usuários carregados dinamicamente da tabela USUARIOS")
    print("🏆 NOVO: Ranking de projetos por faturamento")
    print("🏆 NOVO: Ranking de supervisores por faturamento")
    print("📅 CORRIGIDO: Processamento de períodos por voz")
    print("🎯 NOVO: Filtros por projeto específico")
    print("🚚 INTEGRADO: Processamento de fretes via texto e áudio")
    print("🚀 RAILWAY: Configurado para deploy em produção")
    print("✅ CORRIGIDO: Sistema anti-duplicação e controle de spam")
    
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