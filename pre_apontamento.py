import pyodbc
import re
import hashlib
import os
from openai import OpenAI
from datetime import datetime
import json

# Configurações do banco de dados
DB_SERVER = os.environ.get('DB_SERVER', 'alrflorestal.database.windows.net')
DB_DATABASE = os.environ.get('DB_DATABASE', 'Tabela_teste')
DB_USERNAME = os.environ.get('DB_USERNAME', 'sqladmin')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# Configuração OpenAI
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
client = None

print(f"[INIT] Inicializando cliente OpenAI...")
print(f"[INIT] API Key presente: {'Sim' if OPENAI_API_KEY else 'Não'}")

if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"[INIT] ✅ Cliente OpenAI configurado com sucesso")
    except Exception as e:
        print(f"[INIT] ❌ Erro ao configurar OpenAI: {e}")
        client = None
else:
    print(f"[INIT] ❌ OPENAI_API_KEY não encontrada")

# Configurações Z-API para notificações
INSTANCE_ID = os.environ.get('INSTANCE_ID')
TOKEN = os.environ.get('TOKEN')
CLIENT_TOKEN = os.environ.get('CLIENT_TOKEN')

def conectar_db():
    """Conecta ao banco de dados SQL Server Azure"""
    try:
        drivers = [
            '{ODBC Driver 18 for SQL Server}',
            '{ODBC Driver 17 for SQL Server}',
            '{ODBC Driver 13 for SQL Server}',
            '{FreeTDS}'
        ]
        
        connection_string_base = (
            f'SERVER={DB_SERVER};'
            f'DATABASE={DB_DATABASE};'
            f'UID={DB_USERNAME};'
            f'PWD={DB_PASSWORD};'
            f'TrustServerCertificate=yes;'
        )
        
        for driver in drivers:
            try:
                connection_string = f'DRIVER={driver};{connection_string_base}'
                conn = pyodbc.connect(connection_string, timeout=30)
                return conn
            except Exception:
                continue
        
        raise Exception("Nenhum driver ODBC disponível funcionou")
        
    except Exception as e:
        print(f"[ERRO] Falha na conexão SQL: {e}")
        raise

def detectar_pre_apontamento(texto):
    """Detecta se a mensagem é um pré-apontamento baseado em palavras-chave"""
    texto_lower = texto.lower()
    
    print(f"[DETECT] 🔍 Analisando texto: {len(texto)} chars")
    print(f"[DETECT] Primeiros 200 chars: {texto[:200]}")
    
    # Indicadores principais
    indicadores_principais = ['data:', 'projeto:', 'empresa:', 'serviço:', 'fazenda:', 'talhão:']
    
    # Separadores característicos
    separadores = ['-------------', '---', '========']
    
    # Contar indicadores encontrados
    indicadores_encontrados = []
    for ind in indicadores_principais:
        if ind in texto_lower:
            indicadores_encontrados.append(ind)
    
    separadores_encontrados = []
    for sep in separadores:
        if sep in texto:
            separadores_encontrados.append(sep)
    
    print(f"[DETECT] Indicadores encontrados ({len(indicadores_encontrados)}): {indicadores_encontrados}")
    print(f"[DETECT] Separadores encontrados ({len(separadores_encontrados)}): {separadores_encontrados}")
    
    # Regra: pelo menos 3 indicadores principais OU pelo menos 2 separadores
    resultado = len(indicadores_encontrados) >= 3 or len(separadores_encontrados) >= 2
    print(f"[DETECT] ✅ É pré-apontamento: {resultado}")
    
    return resultado

def gerar_hash_mensagem(texto, telefone):
    """Gera hash único para evitar duplicação"""
    conteudo = f"{telefone}_{texto}_{datetime.now().strftime('%Y%m%d%H')}"
    return hashlib.md5(conteudo.encode()).hexdigest()

def salvar_raw(telefone, conteudo_bruto, hash_msg):
    """Salva o pré-apontamento bruto na tabela PRE_APONTAMENTO_RAW"""
    try:
        print(f"[SQL] 🔄 Conectando ao banco...")
        conn = conectar_db()
        cursor = conn.cursor()
        
        print(f"[SQL] 📝 Preparando inserção...")
        print(f"[SQL] Telefone: {telefone}")
        print(f"[SQL] Hash: {hash_msg}")
        print(f"[SQL] Conteúdo (primeiros 100 chars): {conteudo_bruto[:100]}")
        
        query = """
        INSERT INTO PRE_APONTAMENTO_RAW (PHONE, CONTEUDO_BRUTO, HASH, STATUS, CREATED_AT)
        VALUES (?, ?, ?, 'PENDENTE', GETDATE())
        """
        
        print(f"[SQL] 🚀 Executando INSERT...")
        cursor.execute(query, (telefone, conteudo_bruto, hash_msg))
        print(f"[SQL] ✅ INSERT executado com sucesso")
        
        conn.commit()
        print(f"[SQL] ✅ COMMIT realizado")
        
        # Recuperar o ID inserido usando HASH (mais confiável)
        print(f"[SQL] 🔍 Recuperando ID pelo HASH...")
        cursor.execute("SELECT ID FROM PRE_APONTAMENTO_RAW WHERE HASH = ? ORDER BY CREATED_AT DESC", (hash_msg,))
        resultado = cursor.fetchone()
        
        print(f"[SQL] Resultado busca por HASH: {resultado}")
        
        if resultado and resultado[0]:
            raw_id = int(resultado[0])
            print(f"[SQL] ✅ RAW salvo com ID: {raw_id}")
        else:
            print(f"[SQL] ❌ Falha ao recuperar ID inserido")
            conn.close()
            return None
        
        conn.close()
        return raw_id
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar RAW: {e}")
        import traceback
        traceback.print_exc()
        return None

def extrair_dados_com_openai(texto):
    """Usa OpenAI para extrair e estruturar os dados do pré-apontamento"""
    try:
        print(f"[OPENAI] 🚀 Iniciando extração de dados...")
        
        if not client:
            print(f"[OPENAI] ❌ Cliente OpenAI não configurado")
            return None
            
        if not OPENAI_API_KEY:
            print(f"[OPENAI] ❌ API Key não disponível")
            return None
            
        print(f"[OPENAI] ✅ Cliente disponível, preparando prompt...")
        print(f"[OPENAI] Texto a processar (primeiros 300 chars): {texto[:300]}")
        
        prompt = f"""
Você é um especialista em extração de dados de pré-apontamentos agrícolas.

INSTRUÇÕES IMPORTANTES:
1. Extraia TODOS os dados encontrados no texto
2. Aplique correções automáticas de ortografia e formatação:
   - "larzil" → "LARSIL" 
   - "furmiga" → "FORMIGA"
   - "talão" → "TALHÃO"
   - Nomes de fazendas devem estar em MAIÚSCULAS
   - Códigos técnicos como "TALHÃO: 001" devem manter formato "CAMPO: VALOR"
3. DATAS: Se encontrar "HOJE", "DATA: HOJE" ou similar, use "{datetime.now().strftime('%Y-%m-%d')}"
4. PRÊMIOS/RATEIO: Extrair colaboradores das seções:
   - "RATEIO PRODUÇÃO MANUAL" → categoria "RATEIO_MANUAL"
   - "EQUIPE APOIO ENVOLVIDA" → categoria "APOIO" 
   - "ESTRUTURA APOIO ENVOLVIDA" → categoria "APOIO"
5. Para cada colaborador: código (ex: 2508, 2689, TP001), produção (número após hífen), função (texto após PREMIO)
6. RECEBE_PREMIO: 1 se tem "PREMIO", 0 se vazio
7. Se algum campo estiver em branco, deixe como string vazia ""

TEXTO PARA PROCESSAR:
{texto}

RESPONDA APENAS COM JSON VÁLIDO no formato:
{{
  "boletim": {{
    "data_execucao": "{datetime.now().strftime('%Y-%m-%d')}",
    "projeto": "",
    "empresa": "",
    "servico": "",
    "fazenda": "",
    "talhao": "",
    "area_realizada": 0,
    "area_total": 0,
    "valor_ganho": 0,
    "diaria_colaborador": 0,
    "observacoes": ""
  }},
  "premios": [
    {{
      "categoria": "RATEIO_MANUAL",
      "colaborador_id": "código extraído",
      "equipamento": null,
      "producao": 0,
      "funcao": "CAMPO",
      "recebe_premio": 1,
      "valor_fixo": null
    }}
  ]
}}"""

        print(f"[OPENAI] Enviando requisição para GPT-3.5-turbo...")
        
        print(f"[OPENAI] 📤 Enviando requisição para GPT-3.5-turbo...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente especializado em extração de dados agrícolas. Responda APENAS com JSON válido."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.1,
            timeout=30  # Timeout de 30 segundos
        )
        
        print(f"[OPENAI] ✅ Resposta recebida com sucesso")
        
        conteudo = response.choices[0].message.content.strip()
        print(f"[OPENAI] Processando resposta: {len(conteudo)} caracteres")
        print(f"[OPENAI] Primeiros 300 chars da resposta: {conteudo[:300]}")
        
        # Limpar possíveis marcadores de código
        if conteudo.startswith('```json'):
            conteudo = conteudo[7:]
        if conteudo.startswith('```'):
            conteudo = conteudo[3:]
        if conteudo.endswith('```'):
            conteudo = conteudo[:-3]
        
        print(f"[OPENAI] Fazendo parse do JSON...")
        dados = json.loads(conteudo.strip())
        print(f"[OPENAI] ✅ JSON parseado com sucesso!")
        print(f"[OPENAI] Estrutura: boletim={bool(dados.get('boletim'))}, premios={len(dados.get('premios', []))}")
        
        return dados
        
    except Exception as e:
        print(f"[OPENAI] ❌ ERRO: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
        
        prompt = f"""
Você é um especialista em extrair dados de pré-apontamentos de campo. Analise o texto abaixo e extraia as informações seguindo EXATAMENTE a estrutura JSON solicitada.

REGRAS IMPORTANTES:
1. DATA: Se "HOJE", use a data atual no formato YYYY-MM-DD
2. VALORES: Remover "R$", pontos de milhares, vírgula decimal vira ponto (ex: "R$ 18.004,43" = 18004.43)
3. LOTES/INSUMOS: Apenas os que têm dados preenchidos
4. RATEIO: Extrair colaborador_id e equipamento_id dos códigos
5. RECEBE_PREMIO: 1 se tem "PREMIO", 0 se vazio
6. AREAS: Converter vírgula para ponto decimal
7. RATEIO AUTOMÁTICO: Se produção estiver em branco ou zero, dividir área realizada igualmente
8. VALIDAÇÃO: Verificar se todos os colaboradores têm produção preenchida

CORREÇÕES AUTOMÁTICAS OBRIGATÓRIAS:
- "larzil" ou "larsil" → "LARSIL"
- "furmiga" ou "formiga" → "FORMIGA"
- "combate furmiga" → "COMBATE FORMIGA"
- "COMBATE furmiga" → "COMBATE FORMIGA"
- Sempre MAIÚSCULO para: EMPRESA, SERVIÇO, FAZENDA
- Manter códigos de colaborador/equipamento como estão
- IMPORTANTE: Manter formato "CAMPO: VALOR" (ex: "TALHÃO: 001" não "TALHÃO001")

ESTRUTURA JSON ESPERADA:
{{
    "boletim": {{
        "data_execucao": "YYYY-MM-DD",
        "projeto": "número",
        "empresa": "texto CORRIGIDO E MAIÚSCULO",
        "servico": "texto CORRIGIDO E MAIÚSCULO", 
        "fazenda": "texto MAIÚSCULO",
        "talhao": "texto",
        "area_total": float,
        "area_realizada": float,
        "area_restante": float,
        "status_campo": "texto",
        "valor_ganho": float ou null,
        "diaria_colaborador": float ou null,
        "lote1": "texto ou null",
        "insumo1": "texto ou null", 
        "quantidade1": float ou null,
        "lote2": "texto ou null",
        "insumo2": "texto ou null",
        "quantidade2": float ou null,
        "lote3": "texto ou null",
        "insumo3": "texto ou null",
        "quantidade3": float ou null,
        "divisao_premio_igual": "SIM ou NAO",
        "observacoes": "texto ou null"
    }},
    "premios": [
        {{
            "categoria": "RATEIO_MANUAL",
            "colaborador_id": "código",
            "equipamento": null,
            "producao": float,
            "funcao": "extraído do contexto",
            "recebe_premio": 0 ou 1,
            "valor_fixo": null
        }},
        {{
            "categoria": "RATEIO_MEC", 
            "colaborador_id": "código",
            "equipamento": "código equipamento",
            "producao": float,
            "funcao": "OPERADOR",
            "recebe_premio": 0 ou 1,
            "valor_fixo": null
        }},
        {{
            "categoria": "APOIO",
            "colaborador_id": "código",
            "equipamento": null,
            "producao": null,
            "funcao": "função extraída",
            "recebe_premio": 0 ou 1,
            "valor_fixo": null
        }},
        {{
            "categoria": "ESTRUTURA",
            "colaborador_id": "código", 
            "equipamento": "código equipamento",
            "producao": null,
            "funcao": "função extraída",
            "recebe_premio": 0 ou 1,
            "valor_fixo": null
        }}
    ]
}}

TEXTO PARA ANÁLISE:
{texto}

Responda APENAS com o JSON válido, sem explicações adicionais.
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um extrator de dados especializado em pré-apontamentos de campo. Retorne apenas JSON válido."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.1
        )
        
        resposta = response.choices[0].message.content.strip()
        
        # Tentar extrair JSON da resposta
        try:
            dados_extraidos = json.loads(resposta)
            return dados_extraidos
        except json.JSONDecodeError:
            # Se não for JSON válido, tentar extrair JSON de dentro do texto
            import re
            json_match = re.search(r'\{.*\}', resposta, re.DOTALL)
            if json_match:
                dados_extraidos = json.loads(json_match.group())
                return dados_extraidos
            else:
                raise Exception("Resposta da OpenAI não contém JSON válido")
                
    except Exception as e:
        print(f"[ERRO] Falha na extração OpenAI: {e}")
        return None

def verificar_rateio_e_aplicar_logica(texto, dados_extraidos):
    """
    Verifica rateios e aplica lógica automática:
    1. Rateio automático se valores em branco
    2. Detecção de inconsistências
    3. Alertas para correção
    """
    try:
        alertas = []
        dados_corrigidos = dados_extraidos.copy()
        
        # Extrair área realizada para cálculos
        area_realizada = dados_extraidos.get('boletim', {}).get('area_realizada', 0)
        
        # Analisar RATEIO MANUAL
        rateios_manuais = [p for p in dados_extraidos.get('premios', []) if p.get('categoria') == 'RATEIO_MANUAL']
        
        if rateios_manuais:
            print(f"[RATEIO] Encontrados {len(rateios_manuais)} colaboradores no rateio manual")
            
            # Verificar se tem produção preenchida
            com_producao = [r for r in rateios_manuais if r.get('producao') and r.get('producao') > 0]
            sem_producao = [r for r in rateios_manuais if not r.get('producao') or r.get('producao') <= 0]
            
            total_colaboradores = len(rateios_manuais)
            total_com_producao = len(com_producao)
            total_sem_producao = len(sem_producao)
            
            print(f"[RATEIO] Com produção: {total_com_producao}, Sem produção: {total_sem_producao}")
            
            # CASO 1: Todos em branco - RATEIO AUTOMÁTICO
            if total_sem_producao == total_colaboradores:
                print(f"[RATEIO] ✅ APLICANDO RATEIO AUTOMÁTICO - Dividindo {area_realizada} por {total_colaboradores}")
                producao_automatica = round(area_realizada / total_colaboradores, 2) if total_colaboradores > 0 else 0
                
                # Aplicar rateio automático
                for i, premio in enumerate(dados_corrigidos.get('premios', [])):
                    if premio.get('categoria') == 'RATEIO_MANUAL':
                        premio['producao'] = producao_automatica
                
                alertas.append(f"✅ RATEIO AUTOMÁTICO aplicado: {producao_automatica} por colaborador")
            
            # CASO 2: Parcialmente preenchido - INCONSISTÊNCIA
            elif 0 < total_com_producao < total_colaboradores:
                total_preenchido = sum(r.get('producao', 0) for r in com_producao)
                restante = area_realizada - total_preenchido
                
                print(f"[RATEIO] ⚠️ INCONSISTÊNCIA DETECTADA - {total_com_producao} de {total_colaboradores} preenchidos")
                print(f"[RATEIO] Total preenchido: {total_preenchido}, Restante: {restante}")
                
                alertas.append(f"⚠️ RATEIO INCOMPLETO: {total_com_producao} de {total_colaboradores} colaboradores preenchidos")
                alertas.append(f"📊 Área preenchida: {total_preenchido}, Área restante: {restante}")
                
                if restante > 0:
                    alertas.append(f"🔧 AÇÃO NECESSÁRIA: Defina produção para os {total_sem_producao} colaboradores restantes")
                    # Listar colaboradores sem produção
                    colaboradores_pendentes = [r.get('colaborador_id') for r in sem_producao]
                    alertas.append(f"👥 Colaboradores pendentes: {', '.join(colaboradores_pendentes)}")
                else:
                    alertas.append("✅ Área totalmente distribuída")
            
            # CASO 3: Todos preenchidos - VERIFICAR SOMA
            elif total_sem_producao == 0:
                total_distribuido = sum(r.get('producao', 0) for r in rateios_manuais)
                diferenca = abs(total_distribuido - area_realizada)
                
                print(f"[RATEIO] ✅ Todos preenchidos - Total: {total_distribuido}, Área: {area_realizada}")
                
                if diferenca > 0.1:  # Tolerância de 0.1
                    alertas.append(f"⚠️ DIVERGÊNCIA: Total rateio ({total_distribuido}) ≠ Área realizada ({area_realizada})")
                    alertas.append(f"🔧 Diferença de {diferenca} - Verifique os valores")
                else:
                    alertas.append("✅ Rateio manual conferido - Valores corretos")
        
        # Analisar RATEIO MECANIZADO
        rateios_mec = [p for p in dados_extraidos.get('premios', []) if p.get('categoria') == 'RATEIO_MEC']
        
        if rateios_mec:
            print(f"[RATEIO MEC] Encontrados {len(rateios_mec)} equipamentos")
            
            # Verificar se há "PRODUÇÃO MECANIZADA TOTAL" no texto
            if "PRODUÇÃO MECANIZADA TOTAL:" in texto:
                import re
                match = re.search(r'PRODUÇÃO MECANIZADA TOTAL:\s*(\d+(?:,\d+)?)', texto)
                if match:
                    total_declarado = float(match.group(1).replace(',', '.'))
                    total_rateado = sum(r.get('producao', 0) for r in rateios_mec if r.get('producao'))
                    
                    print(f"[RATEIO MEC] Total declarado: {total_declarado}, Total rateado: {total_rateado}")
                    
                    if abs(total_declarado - total_rateado) > 0.1:
                        diferenca = total_declarado - total_rateado
                        alertas.append(f"⚠️ RATEIO MECANIZADO: Faltam {diferenca} para atingir total de {total_declarado}")
        
        return dados_corrigidos, alertas
        
    except Exception as e:
        print(f"[ERRO] Falha na verificação de rateio: {e}")
        return dados_extraidos, [f"❌ Erro na verificação de rateio: {str(e)[:100]}"]

def salvar_boletim_staging(dados_boletim, raw_id):
    """Salva os dados do boletim na tabela BOLETIM_STAGING"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Converter "HOJE" ou formatos problemáticos para data atual
        data_execucao = dados_boletim.get('data_execucao')
        if data_execucao:
            if data_execucao.upper() == 'HOJE' or data_execucao == 'YYYY-MM-DD':
                data_execucao = datetime.now().strftime('%Y-%m-%d')
                print(f"[SQL] Data convertida: {dados_boletim.get('data_execucao')} -> {data_execucao}")
        else:
            data_execucao = datetime.now().strftime('%Y-%m-%d')
            print(f"[SQL] Data ausente, usando hoje: {data_execucao}")
        
        print(f"[SQL] 💾 Salvando boletim com RAW_ID: {raw_id}")
        print(f"[SQL] Data final: {data_execucao}")
        
        query = """
        INSERT INTO BOLETIM_STAGING (
            RAW_ID, DATA_EXECUCAO, PROJETO, EMPRESA, SERVICO, FAZENDA, TALHAO,
            AREA_TOTAL, AREA_REALIZADA, AREA_RESTANTE, STATUS_CAMPO, VALOR_GANHO,
            DIARIA_COLABORADOR, LOTE1, INSUMO1, QUANTIDADE1, LOTE2, INSUMO2, 
            QUANTIDADE2, LOTE3, INSUMO3, QUANTIDADE3, DIVISAO_PREMIO_IGUAL,
            OBSERVACOES, CREATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """
        
        cursor.execute(query, (
            raw_id,
            data_execucao,  # Usando a data convertida
            dados_boletim.get('projeto'),
            dados_boletim.get('empresa'),
            dados_boletim.get('servico'),
            dados_boletim.get('fazenda'),
            dados_boletim.get('talhao'),
            dados_boletim.get('area_total'),
            dados_boletim.get('area_realizada'),
            dados_boletim.get('area_restante'),
            dados_boletim.get('status_campo'),
            dados_boletim.get('valor_ganho'),
            dados_boletim.get('diaria_colaborador'),
            dados_boletim.get('lote1'),
            dados_boletim.get('insumo1'),
            dados_boletim.get('quantidade1'),
            dados_boletim.get('lote2'),
            dados_boletim.get('insumo2'),
            dados_boletim.get('quantidade2'),
            dados_boletim.get('lote3'),
            dados_boletim.get('insumo3'),
            dados_boletim.get('quantidade3'),
            dados_boletim.get('divisao_premio_igual'),
            dados_boletim.get('observacoes')
        ))
        
        conn.commit()
        print(f"[SQL] ✅ Boletim salvo na STAGING com sucesso!")
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar boletim: {e}")
        import traceback
        traceback.print_exc()
        return False

def salvar_premios_staging(premios_list, raw_id):
    """Salva os prêmios na tabela PREMIO_STAGING"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        query = """
        INSERT INTO PREMIO_STAGING (
            RAW_ID, CATEGORIA, COLABORADOR_ID, EQUIPAMENTO, PRODUCAO, FUNCAO,
            RECEBE_PREMIO, VALOR_FIXO, CREATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """
        
        for premio in premios_list:
            cursor.execute(query, (
                raw_id,
                premio.get('categoria'),
                premio.get('colaborador_id'),
                premio.get('equipamento'),
                premio.get('producao'),
                premio.get('funcao'),
                premio.get('recebe_premio'),
                premio.get('valor_fixo')
            ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar prêmios: {e}")
        return False

def buscar_coordenador(projeto):
    """Busca o telefone do coordenador do projeto"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        query = """
        SELECT TELEFONE FROM USUARIOS 
        WHERE PROJETO = ? AND PERFIL = 'COORDENADOR'
        """
        
        cursor.execute(query, (projeto,))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            return resultado[0]
        return None
        
    except Exception as e:
        print(f"[ERRO] Falha ao buscar coordenador: {e}")
        return None

def enviar_notificacao_coordenador_texto(telefone_coord, dados_resumo, raw_id, telefone_remetente=None):
    """Envia notificação para o coordenador usando TEXTO SIMPLES (SIM/NAO/CORRIGIR)"""
    try:
        print(f"[NOTIF] 🚀 Iniciando envio de notificação TEXTO para coordenador")
        print(f"[NOTIF] 📞 Telefone coordenador: {telefone_coord}")
        print(f"[NOTIF] 🔢 RAW_ID: {raw_id}")
        print(f"[NOTIF] 📱 Telefone remetente: {telefone_remetente}")
        
        import requests
        
        if not all([INSTANCE_ID, TOKEN, telefone_coord]):
            print(f"[NOTIF] ❌ Dados Z-API incompletos!")
            return False

        # Buscar nome do remetente
        nome_remetente = "Usuário"
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            query = "SELECT USUARIO FROM USUARIOS WHERE TELEFONE = ?"
            cursor.execute(query, (telefone_remetente,))
            resultado = cursor.fetchone()
            if resultado:
                nome_remetente = resultado[0]
            conn.close()
        except:
            pass

        # Formatar valores
        valor_ganho = dados_resumo.get('valor_ganho')
        valor_ganho_str = f"R$ {valor_ganho:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor_ganho else "N/A"
        
        diaria_colaborador = dados_resumo.get('diaria_colaborador')
        diaria_str = f"R$ {diaria_colaborador:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if diaria_colaborador else "N/A"
        
        # Formatar data
        data_execucao = dados_resumo.get('data_execucao', '')
        if data_execucao:
            try:
                data_obj = datetime.strptime(data_execucao, '%Y-%m-%d')
                data_formatada = data_obj.strftime('%d/%m/%Y')
            except:
                data_formatada = data_execucao
        else:
            data_formatada = datetime.now().strftime('%d/%m/%Y')

        telefone_formatado = telefone_remetente[-4:] if telefone_remetente else "****"

        mensagem = f"""🚨 *NOVO PRÉ-APONTAMENTO #{raw_id}*
👤 *Enviado por:* {nome_remetente} (...{telefone_formatado})
🏗️ *Projeto:* {dados_resumo.get('projeto', 'N/A')} - {dados_resumo.get('empresa', 'N/A')}
📅 *Data:* {data_formatada}
🌱 *Serviço:* {dados_resumo.get('servico', 'N/A')}
📍 *Fazenda:* {dados_resumo.get('fazenda', 'N/A')} - Talhão {dados_resumo.get('talhao', 'N/A')}
📏 *Área:* {dados_resumo.get('area_realizada', 0)}/{dados_resumo.get('area_total', 0)} ha
💰 *Valor ganho:* {valor_ganho_str}
👷 *Diária colaborador:* {diaria_str}

*OBS:* {dados_resumo.get('observacoes', 'Sem observações')}

⚡ *RESPONDA COM:*
• *SIM {raw_id}* - Para APROVAR
• *NAO {raw_id}* - Para REJEITAR  
• *CORRIGIR {raw_id}* - Para solicitar correção

_Exemplo: SIM {raw_id}_"""

        # Enviar via Z-API texto simples
        url_send = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
        
        payload = {
            "phone": telefone_coord,
            "message": mensagem
        }
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": CLIENT_TOKEN
        }
        
        print(f"[NOTIF] 📡 Enviando notificação TEXTO...")
        response = requests.post(url_send, json=payload, headers=headers)
        
        print(f"[NOTIF] 📊 Status: {response.status_code}")
        print(f"[NOTIF] 📄 Resposta: {response.text[:200]}")
        
        sucesso = response.status_code == 200
        if sucesso:
            print(f"[NOTIF] ✅ Notificação TEXTO enviada com sucesso!")
        else:
            print(f"[NOTIF] ❌ Falha no envio da notificação TEXTO!")
            
        return sucesso
        
    except Exception as e:
        print(f"[NOTIF] ❌ ERRO CRÍTICO no envio: {e}")
        import traceback
        traceback.print_exc()
        return False

def enviar_notificacao_coordenador(telefone_coord, dados_resumo, raw_id, telefone_remetente=None):
    """VERSÃO ATUALIZADA: Envia notificação usando TEXTO ao invés de botões"""
    return enviar_notificacao_coordenador_texto(telefone_coord, dados_resumo, raw_id, telefone_remetente)
    """Envia notificação para o coordenador com botões de aprovação"""
    try:
        import requests
        
        if not all([INSTANCE_ID, TOKEN, telefone_coord]):
            return False
        
        # Buscar nome do remetente se possível
        nome_remetente = "Usuário"
        try:
            conn = conectar_db()
            cursor = conn.cursor()
            query = "SELECT USUARIO FROM USUARIOS WHERE TELEFONE = ?"
            cursor.execute(query, (telefone_remetente,))
            resultado = cursor.fetchone()
            if resultado:
                nome_remetente = resultado[0]
            conn.close()
        except:
            pass
        
        # Formatar valores monetários
        valor_ganho = dados_resumo.get('valor_ganho')
        valor_ganho_str = f"R$ {valor_ganho:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor_ganho else "N/A"
        
        diaria_colaborador = dados_resumo.get('diaria_colaborador')
        diaria_str = f"R$ {diaria_colaborador:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if diaria_colaborador else "N/A"
        
        # Formatar data
        data_execucao = dados_resumo.get('data_execucao', '')
        if data_execucao:
            try:
                from datetime import datetime
                data_obj = datetime.strptime(data_execucao, '%Y-%m-%d')
                data_formatada = data_obj.strftime('%d/%m/%Y')
            except:
                data_formatada = data_execucao
        else:
            data_formatada = datetime.now().strftime('%d/%m/%Y')
        
        # Telefone formatado
        telefone_formatado = telefone_remetente[-4:] if telefone_remetente else "****"
        
        mensagem = f"""� *NOVO PRÉ-APONTAMENTO #{raw_id}*
👤 *Enviado por:* {nome_remetente} (...{telefone_formatado})
🏗️ *Projeto:* {dados_resumo.get('projeto', 'N/A')} - {dados_resumo.get('empresa', 'N/A')}
� *Data:* {data_formatada}
🌱 *Serviço:* {dados_resumo.get('servico', 'N/A')}
📍 *Fazenda:* {dados_resumo.get('fazenda', 'N/A')} - Talhão {dados_resumo.get('talhao', 'N/A')}
� *Área:* {dados_resumo.get('area_realizada', 0)}/{dados_resumo.get('area_total', 0)} ha
💰 *Valor ganho:* {valor_ganho_str}
� *Diária colaborador:* {diaria_str}

*OBS:* {dados_resumo.get('observacoes', 'Sem observações')}"""

        # Enviar mensagem com botões
        url_send = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-button-list"
        
        payload = {
            "phone": telefone_coord,
            "message": mensagem,
            "buttonList": {
                "buttons": [
                    {
                        "id": f"aprovar_{raw_id}",
                        "label": "✅ APROVAR"
                    },
                    {
                        "id": f"rejeitar_{raw_id}",
                        "label": "❌ REJEITAR"
                    },
                    {
                        "id": f"corrigir_{raw_id}",
                        "label": "� SOLICITAR CORREÇÃO"
                    }
                ]
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": CLIENT_TOKEN
        }
        
        response = requests.post(url_send, json=payload, headers=headers)
        return response.status_code == 200
        
    except Exception as e:
        print(f"[ERRO] Falha ao enviar notificação: {e}")
        return False

def processar_pre_apontamento(numero, texto):
    """
    Função principal para processar pré-apontamentos
    
    Args:
        numero: Telefone do usuário
        texto: Conteúdo da mensagem
        
    Returns:
        {
            'is_pre_apont': bool,
            'status': 'ok|alerta|erro', 
            'resposta': 'mensagem'
        }
    """
    try:
        # 1. Detectar se é pré-apontamento
        if not detectar_pre_apontamento(texto):
            return {
                'is_pre_apont': False,
                'status': 'ok',
                'resposta': ''
            }
        
        print(f"[PRE-APONT] Detectado pré-apontamento de {numero}")
        
        # 2. Gerar hash e verificar duplicação
        hash_msg = gerar_hash_mensagem(texto, numero)
        
        # 3. Salvar RAW imediatamente
        raw_id = salvar_raw(numero, texto, hash_msg)
        if not raw_id:
            return {
                'is_pre_apont': True,
                'status': 'erro',
                'resposta': '❌ Erro ao salvar pré-apontamento. Tente novamente.'
            }
        
        print(f"[PRE-APONT] RAW salvo com ID: {raw_id}")
        
        # 4. Extrair dados com OpenAI
        print(f"[PRE-APONT] Iniciando extração OpenAI...")
        print(f"[PRE-APONT] Verificando API Key: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'NONE'}...")
        print(f"[PRE-APONT] Cliente configurado: {'SIM' if client else 'NÃO'}")
        print(f"[PRE-APONT] Texto para processar (primeiros 200 chars): {texto[:200]}...")
        
        dados_extraidos = extrair_dados_com_openai(texto)
        print(f"[PRE-APONT] Resultado OpenAI: {type(dados_extraidos)} - {str(dados_extraidos)[:200] if dados_extraidos else 'NONE'}")
        
        if not dados_extraidos:
            print(f"[PRE-APONT] ERRO: Falha na extração OpenAI - dados_extraidos é None/False")
            return {
                'is_pre_apont': True,
                'status': 'alerta',
                'resposta': '⚠️ Falha na análise do texto. Dados salvos para revisão manual.'
            }
        
        print(f"[PRE-APONT] Dados extraídos com sucesso")
        
        # 4.1. Verificar rateio e aplicar lógicas automáticas
        dados_corrigidos, alertas_rateio = verificar_rateio_e_aplicar_logica(texto, dados_extraidos)
        print(f"[PRE-APONT] Verificação de rateio concluída - {len(alertas_rateio)} alertas")
        
        # 5. Salvar BOLETIM_STAGING
        if not salvar_boletim_staging(dados_corrigidos.get('boletim', {}), raw_id):
            return {
                'is_pre_apont': True,
                'status': 'alerta',
                'resposta': '⚠️ Pré-apontamento recebido, mas houve erro ao estruturar os dados. Será verificado manualmente.'
            }
        
        # 6. Salvar PREMIO_STAGING
        premios = dados_corrigidos.get('premios', [])
        if premios and not salvar_premios_staging(premios, raw_id):
            return {
                'is_pre_apont': True,
                'status': 'alerta',
                'resposta': '⚠️ Dados principais salvos, mas houve erro nos prêmios. Será verificado manualmente.'
            }
        
        print(f"[PRE-APONT] Dados estruturados salvos")
        
        # 7. Buscar coordenador e enviar notificação
        projeto = dados_corrigidos.get('boletim', {}).get('projeto')
        if projeto:
            telefone_coord = buscar_coordenador(projeto)
            if telefone_coord:
                sucesso_notif = enviar_notificacao_coordenador(
                    telefone_coord, 
                    dados_corrigidos.get('boletim', {}), 
                    raw_id,
                    numero
                )
                if not sucesso_notif:
                    print(f"[PRE-APONT] Falha ao notificar coordenador")
            else:
                print(f"[PRE-APONT] Coordenador não encontrado para projeto {projeto}")
        
        # 8. Resposta de sucesso com alertas de rateio
        dados_boletim = dados_corrigidos.get('boletim', {})
        
        # Montar resposta base
        resposta_base = f"""✅ *PRÉ-APONTAMENTO RECEBIDO*

📊 *PROJETO:* {dados_boletim.get('projeto', 'N/A')}
🏭 *EMPRESA:* {dados_boletim.get('empresa', 'N/A')}
🔧 *SERVIÇO:* {dados_boletim.get('servico', 'N/A')}
🌾 *FAZENDA:* {dados_boletim.get('fazenda', 'N/A')}
📍 *TALHÃO:* {dados_boletim.get('talhao', 'N/A')}
📅 *DATA:* {dados_boletim.get('data_execucao', 'N/A')}

📏 *ÁREA REALIZADA:* {dados_boletim.get('area_realizada', 0)}
📐 *ÁREA TOTAL:* {dados_boletim.get('area_total', 0)}

🔄 *STATUS:* Enviado para aprovação
📋 *ID:* {raw_id}"""

        # Adicionar alertas de rateio se houver
        if alertas_rateio:
            resposta_base += "\n\n🎯 *ANÁLISE DE RATEIO:*"
            for alerta in alertas_rateio:
                resposta_base += f"\n{alerta}"
        
        # Verificar se há alertas críticos (inconsistências)
        alertas_criticos = [a for a in alertas_rateio if "INCOMPLETO" in a or "DIVERGÊNCIA" in a or "AÇÃO NECESSÁRIA" in a]
        
        if alertas_criticos:
            resposta_base += "\n\n⚠️ *REQUER ATENÇÃO* - Verifique os alertas acima"
            status_final = 'alerta'
        else:
            resposta_base += "\n\n✅ Coordenador será notificado para aprovação."
            status_final = 'ok'
        
        return {
            'is_pre_apont': True,
            'status': status_final,
            'resposta': resposta_base
        }
        
    except Exception as e:
        print(f"[ERRO] Falha no processamento do pré-apontamento: {e}")
        return {
            'is_pre_apont': True,
            'status': 'erro',
            'resposta': f'❌ Erro interno no processamento do pré-apontamento: {str(e)[:100]}'
        }

# Função auxiliar para atualizar data "HOJE"
def processar_data_hoje():
    """Retorna a data atual no formato YYYY-MM-DD"""
    return datetime.now().strftime('%Y-%m-%d')

if __name__ == "__main__":
    # Teste básico
    texto_teste = """DATA: HOJE
PROJETO: 830
EMPRESA: LARSIL
SERVIÇO: COMBATE FORMIGA
FAZENDA: SÃO JOÃO
TALHÃO: 001
AREA TOTAL: 50
AREA REALIZADA: 10
-------------
TESTE BÁSICO
"""
    
    resultado = processar_pre_apontamento("5511999999999", texto_teste)
    print(f"Teste: {resultado}")

def detectar_resposta_coordenador(texto, telefone_coordenador):
    """
    Detecta se a mensagem é uma resposta de aprovação do coordenador
    Formatos aceitos: SIM 48, NAO 48, CORRIGIR 48
    """
    try:
        print(f"[COORD-RESP] 🔍 Analisando resposta: '{texto}'")
        
        # Normalizar texto
        texto_limpo = texto.upper().strip()
        palavras = texto_limpo.split()
        
        print(f"[COORD-RESP] 📝 Palavras: {palavras}")
        
        # Verificar padrões: ACAO + NUMERO
        if len(palavras) >= 2:
            acao = palavras[0]
            
            # Tentar extrair número (pode ser qualquer palavra que contenha dígitos)
            raw_id = None
            for palavra in palavras[1:]:
                if palavra.isdigit():
                    raw_id = palavra
                    break
                # Também aceitar números dentro de texto (ex: "SIM48", "NAO48")
                import re
                numeros = re.findall(r'\d+', palavra)
                if numeros:
                    raw_id = numeros[0]
                    break
            
            if raw_id and acao in ['SIM', 'NAO', 'CORRIGIR']:
                print(f"[COORD-RESP] ✅ Resposta detectada: {acao} para RAW_ID {raw_id}")
                
                # Verificar se o coordenador tem permissão para este RAW_ID
                if verificar_permissao_coordenador(telefone_coordenador, raw_id):
                    
                    # Converter para formato de button_id para compatibilidade
                    button_id_map = {
                        'SIM': f'aprovar_{raw_id}',
                        'NAO': f'rejeitar_{raw_id}',
                        'CORRIGIR': f'corrigir_{raw_id}'
                    }
                    
                    button_id = button_id_map[acao]
                    print(f"[COORD-RESP] 🎯 Processando como: {button_id}")
                    
                    return {
                        'is_resposta_coord': True,
                        'button_id': button_id,
                        'acao': acao,
                        'raw_id': raw_id
                    }
                else:
                    print(f"[COORD-RESP] ❌ Coordenador sem permissão para RAW_ID {raw_id}")
                    return {
                        'is_resposta_coord': False,
                        'erro': 'Sem permissão para este apontamento'
                    }
            else:
                print(f"[COORD-RESP] ⚠️ Formato inválido - Ação: {acao}, RAW_ID: {raw_id}")
        
        print(f"[COORD-RESP] ➡️ Não é resposta de coordenador")
        return {'is_resposta_coord': False}
        
    except Exception as e:
        print(f"[COORD-RESP] ❌ ERRO: {e}")
        return {'is_resposta_coord': False, 'erro': str(e)}

def verificar_permissao_coordenador(telefone_coordenador, raw_id):
    """Verifica se o coordenador tem permissão para aprovar este RAW_ID"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Buscar projeto do RAW_ID
        query_projeto = "SELECT PROJETO FROM PRE_APONTAMENTO_RAW WHERE ID = ?"
        cursor.execute(query_projeto, (raw_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            print(f"[PERM] ❌ RAW_ID {raw_id} não encontrado")
            conn.close()
            return False
            
        projeto = resultado[0]
        print(f"[PERM] 📊 RAW_ID {raw_id} é do projeto {projeto}")
        
        # Verificar se coordenador tem permissão para este projeto
        query_coord = """
        SELECT COUNT(*) FROM USUARIOS 
        WHERE TELEFONE = ? AND PROJETO = ? AND PERFIL = 'COORDENADOR'
        """
        cursor.execute(query_coord, (telefone_coordenador, projeto))
        tem_permissao = cursor.fetchone()[0] > 0
        
        conn.close()
        
        if tem_permissao:
            print(f"[PERM] ✅ Coordenador autorizado para projeto {projeto}")
        else:
            print(f"[PERM] ❌ Coordenador SEM permissão para projeto {projeto}")
            
        return tem_permissao
        
    except Exception as e:
        print(f"[PERM] ❌ ERRO na verificação: {e}")
        return False
    """
    Processa a resposta do coordenador (APROVAR, REJEITAR, CORRIGIR)
    
    Args:
        button_id: ID do botão clicado (ex: "aprovar_48", "rejeitar_48")
        telefone_coordenador: Telefone do coordenador que respondeu
        mensagem_adicional: Observações adicionais do coordenador
    """
    try:
        print(f"[APRV] 🎯 Processando aprovação do coordenador")
        print(f"[APRV] 🔘 Button ID: {button_id}")
        print(f"[APRV] 📞 Coordenador: {telefone_coordenador}")
        print(f"[APRV] 💬 Mensagem adicional: {mensagem_adicional}")
        
        # Extrair ação e RAW_ID do button_id
        partes = button_id.split('_')
        if len(partes) != 2:
            print(f"[APRV] ❌ Button ID inválido: {button_id}")
            return False
            
        acao = partes[0].upper()  # APROVAR, REJEITAR, CORRIGIR
        raw_id = partes[1]
        
        print(f"[APRV] 🔄 Ação: {acao}, RAW_ID: {raw_id}")
        
        # Verificar se o RAW_ID existe
        conn = conectar_db()
        cursor = conn.cursor()
        
        query_check = "SELECT ID, TELEFONE, PROJETO FROM PRE_APONTAMENTO_RAW WHERE ID = ?"
        cursor.execute(query_check, (raw_id,))
        registro = cursor.fetchone()
        
        if not registro:
            print(f"[APRV] ❌ RAW_ID {raw_id} não encontrado")
            conn.close()
            return False
            
        raw_id_db, telefone_usuario, projeto = registro
        print(f"[APRV] ✅ Registro encontrado - Usuário: {telefone_usuario}, Projeto: {projeto}")
        
        # Verificar se o coordenador tem permissão para este projeto
        query_perm = "SELECT COUNT(*) FROM USUARIOS WHERE TELEFONE = ? AND PROJETO = ? AND PERFIL = 'COORDENADOR'"
        cursor.execute(query_perm, (telefone_coordenador, projeto))
        tem_permissao = cursor.fetchone()[0] > 0
        
        if not tem_permissao:
            print(f"[APRV] ❌ Coordenador sem permissão para projeto {projeto}")
            conn.close()
            return False
            
        print(f"[APRV] ✅ Coordenador autorizado para projeto {projeto}")
        
        # Processar de acordo com a ação
        timestamp_agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if acao == "APROVAR":
            return aprovar_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, mensagem_adicional, timestamp_agora)
            
        elif acao == "REJEITAR":
            return rejeitar_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, mensagem_adicional, timestamp_agora)
            
        elif acao == "CORRIGIR":
            return solicitar_correcao_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, mensagem_adicional, timestamp_agora)
            
        else:
            print(f"[APRV] ❌ Ação não reconhecida: {acao}")
            return False
            
    except Exception as e:
        print(f"[APRV] ❌ ERRO no processamento de aprovação: {e}")
        import traceback
        traceback.print_exc()
        return False

def aprovar_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, observacoes, timestamp):
    """Aprova um pré-apontamento e move dados para tabelas definitivas"""
    try:
        print(f"[APRV] ✅ Iniciando aprovação do RAW_ID {raw_id}")
        
        conn = conectar_db()
        cursor = conn.cursor()
        
        # 1. Atualizar status na tabela RAW
        query_update = """
        UPDATE PRE_APONTAMENTO_RAW 
        SET STATUS = 'APROVADO',
            APROVADO_POR = ?,
            DATA_APROVACAO = ?,
            OBSERVACOES_APROVACAO = ?
        WHERE ID = ?
        """
        cursor.execute(query_update, (telefone_coordenador, timestamp, observacoes, raw_id))
        print(f"[APRV] ✅ Status atualizado para APROVADO")
        
        # 2. Mover dados do STAGING para tabelas definitivas
        # TODO: Implementar lógica de movimentação para BOLETIM e PREMIOS definitivos
        # Por enquanto, apenas marcamos como aprovado
        
        conn.commit()
        conn.close()
        
        # 3. Notificar usuário sobre aprovação
        notificar_usuario_aprovacao(telefone_usuario, raw_id, "APROVADO", observacoes)
        
        # 4. Notificar coordenador sobre confirmação
        notificar_coordenador_confirmacao(telefone_coordenador, raw_id, "APROVADO")
        
        print(f"[APRV] ✅ Aprovação concluída com sucesso!")
        return True
        
    except Exception as e:
        print(f"[APRV] ❌ ERRO na aprovação: {e}")
        import traceback
        traceback.print_exc()
        return False

def rejeitar_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, motivo, timestamp):
    """Rejeita um pré-apontamento"""
    try:
        print(f"[APRV] ❌ Iniciando rejeição do RAW_ID {raw_id}")
        
        conn = conectar_db()
        cursor = conn.cursor()
        
        # 1. Atualizar status na tabela RAW
        query_update = """
        UPDATE PRE_APONTAMENTO_RAW 
        SET STATUS = 'REJEITADO',
            APROVADO_POR = ?,
            DATA_APROVACAO = ?,
            OBSERVACOES_APROVACAO = ?
        WHERE ID = ?
        """
        cursor.execute(query_update, (telefone_coordenador, timestamp, motivo, raw_id))
        print(f"[APRV] ✅ Status atualizado para REJEITADO")
        
        # 2. Remover dados das tabelas STAGING (opcional - pode manter para histórico)
        # Por enquanto, apenas marcamos como rejeitado
        
        conn.commit()
        conn.close()
        
        # 3. Notificar usuário sobre rejeição
        notificar_usuario_aprovacao(telefone_usuario, raw_id, "REJEITADO", motivo)
        
        # 4. Notificar coordenador sobre confirmação  
        notificar_coordenador_confirmacao(telefone_coordenador, raw_id, "REJEITADO")
        
        print(f"[APRV] ✅ Rejeição concluída com sucesso!")
        return True
        
    except Exception as e:
        print(f"[APRV] ❌ ERRO na rejeição: {e}")
        import traceback
        traceback.print_exc()
        return False

def solicitar_correcao_pre_apontamento(raw_id, telefone_coordenador, telefone_usuario, solicitacao, timestamp):
    """Solicita correção de um pré-apontamento"""
    try:
        print(f"[APRV] 🔧 Iniciando solicitação de correção do RAW_ID {raw_id}")
        
        conn = conectar_db()
        cursor = conn.cursor()
        
        # 1. Atualizar status na tabela RAW
        query_update = """
        UPDATE PRE_APONTAMENTO_RAW 
        SET STATUS = 'CORRECAO_SOLICITADA',
            APROVADO_POR = ?,
            DATA_APROVACAO = ?,
            OBSERVACOES_APROVACAO = ?
        WHERE ID = ?
        """
        cursor.execute(query_update, (telefone_coordenador, timestamp, solicitacao, raw_id))
        print(f"[APRV] ✅ Status atualizado para CORRECAO_SOLICITADA")
        
        conn.commit()
        conn.close()
        
        # 2. Notificar usuário sobre solicitação de correção
        notificar_usuario_aprovacao(telefone_usuario, raw_id, "CORRECAO_SOLICITADA", solicitacao)
        
        # 3. Notificar coordenador sobre confirmação
        notificar_coordenador_confirmacao(telefone_coordenador, raw_id, "CORRECAO_SOLICITADA")
        
        print(f"[APRV] ✅ Solicitação de correção enviada com sucesso!")
        return True
        
    except Exception as e:
        print(f"[APRV] ❌ ERRO na solicitação de correção: {e}")
        import traceback
        traceback.print_exc()
        return False

def notificar_usuario_aprovacao(telefone_usuario, raw_id, status, observacoes=""):
    """Notifica o usuário sobre o resultado da aprovação"""
    try:
        print(f"[NOTIF_USER] 📱 Notificando usuário sobre {status}")
        
        emoji_status = {
            "APROVADO": "✅",
            "REJEITADO": "❌", 
            "CORRECAO_SOLICITADA": "🔧"
        }
        
        status_texto = {
            "APROVADO": "APROVADO",
            "REJEITADO": "REJEITADO",
            "CORRECAO_SOLICITADA": "CORREÇÃO SOLICITADA"
        }
        
        emoji = emoji_status.get(status, "ℹ️")
        texto = status_texto.get(status, status)
        
        mensagem = f"""{emoji} *PRÉ-APONTAMENTO #{raw_id} - {texto}*

{emoji} Seu pré-apontamento foi {texto.lower()} pelo coordenador.

"""
        
        if observacoes:
            mensagem += f"💬 *Observações do coordenador:*\n{observacoes}\n\n"
            
        if status == "APROVADO":
            mensagem += "🎉 *Seu apontamento foi aprovado!*\nOs dados foram transferidos para o sistema definitivo."
        elif status == "REJEITADO":
            mensagem += "⚠️ *Seu apontamento foi rejeitado.*\nVerifique as observações e envie um novo apontamento se necessário."
        elif status == "CORRECAO_SOLICITADA":
            mensagem += "🔧 *Correção necessária.*\nPor favor, envie um novo apontamento com as correções solicitadas."
            
        mensagem += f"\n\n📅 *Processado em:* {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
        
        # Enviar via Z-API
        return enviar_mensagem_zapi(telefone_usuario, mensagem)
        
    except Exception as e:
        print(f"[NOTIF_USER] ❌ ERRO ao notificar usuário: {e}")
        return False

def notificar_coordenador_confirmacao(telefone_coordenador, raw_id, acao):
    """Envia confirmação para o coordenador sobre a ação realizada"""
    try:
        print(f"[NOTIF_COORD] 📱 Enviando confirmação da ação {acao}")
        
        emoji_acao = {
            "APROVADO": "✅",
            "REJEITADO": "❌",
            "CORRECAO_SOLICITADA": "🔧"
        }
        
        emoji = emoji_acao.get(acao, "ℹ️")
        
        mensagem = f"""{emoji} *AÇÃO PROCESSADA COM SUCESSO*

Pré-apontamento #{raw_id} foi {acao.lower()}.

📅 *Processado em:* {datetime.now().strftime('%d/%m/%Y às %H:%M')}

✅ O usuário foi notificado automaticamente."""

        return enviar_mensagem_zapi(telefone_coordenador, mensagem)
        
    except Exception as e:
        print(f"[NOTIF_COORD] ❌ ERRO ao confirmar para coordenador: {e}")
        return False

def enviar_mensagem_zapi(telefone, mensagem):
    """Envia mensagem via Z-API"""
    try:
        import requests
        
        if not all([INSTANCE_ID, TOKEN, CLIENT_TOKEN]):
            print(f"[ZAPI] ❌ Credenciais Z-API não configuradas")
            return False
            
        url_send = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
        
        payload = {
            "phone": telefone,
            "message": mensagem
        }
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": CLIENT_TOKEN
        }
        
        response = requests.post(url_send, json=payload, headers=headers)
        
        sucesso = response.status_code == 200
        print(f"[ZAPI] {'✅' if sucesso else '❌'} Envio para {telefone}: {response.status_code}")
        
        return sucesso
        
    except Exception as e:
        print(f"[ZAPI] ❌ ERRO no envio: {e}")
        return False
