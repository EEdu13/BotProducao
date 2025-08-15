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
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)

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
    
    # Indicadores principais
    indicadores_principais = ['data:', 'projeto:', 'empresa:', 'serviço:', 'fazenda:', 'talhão:']
    
    # Separadores característicos
    separadores = ['-------------', '---', '========']
    
    # Contar indicadores encontrados
    indicadores_encontrados = sum(1 for ind in indicadores_principais if ind in texto_lower)
    separadores_encontrados = sum(1 for sep in separadores if sep in texto)
    
    # Regra: pelo menos 3 indicadores principais OU pelo menos 2 separadores
    return indicadores_encontrados >= 3 or separadores_encontrados >= 2

def gerar_hash_mensagem(texto, telefone):
    """Gera hash único para evitar duplicação"""
    conteudo = f"{telefone}_{texto}_{datetime.now().strftime('%Y%m%d%H')}"
    return hashlib.md5(conteudo.encode()).hexdigest()

def salvar_raw(telefone, conteudo_bruto, hash_msg):
    """Salva o pré-apontamento bruto na tabela PRE_APONTAMENTO_RAW"""
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        query = """
        INSERT INTO PRE_APONTAMENTO_RAW (PHONE, CONTEUDO_BRUTO, HASH, STATUS, CREATED_AT)
        VALUES (?, ?, ?, 'PENDENTE', GETDATE())
        """
        
        cursor.execute(query, (telefone, conteudo_bruto, hash_msg))
        conn.commit()
        
        # Recuperar o ID inserido
        cursor.execute("SELECT SCOPE_IDENTITY()")
        raw_id = cursor.fetchone()[0]
        
        conn.close()
        return int(raw_id)
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar RAW: {e}")
        return None

def extrair_dados_com_openai(texto):
    """Usa OpenAI para extrair e estruturar os dados do pré-apontamento"""
    try:
        if not client:
            raise Exception("OpenAI client não configurado")
        
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
            dados_boletim.get('data_execucao'),
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
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar boletim: {e}")
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

def enviar_notificacao_coordenador(telefone_coord, dados_resumo, raw_id, telefone_remetente=None):
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
        dados_extraidos = extrair_dados_com_openai(texto)
        if not dados_extraidos:
            return {
                'is_pre_apont': True,
                'status': 'alerta',
                'resposta': '⚠️ Pré-apontamento recebido, mas houve dificuldade na extração automática. Será analisado manualmente.'
            }
        
        print(f"[PRE-APONT] Dados extraídos com OpenAI")
        
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
