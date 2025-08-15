# Sistema de Pré-Apontamento WhatsApp Bot

## 📋 Visão Geral

Sistema completo de pré-apontamento de campo integrado ao bot WhatsApp, com processamento inteligente via OpenAI e aprovação por coordenadores.

## 🚀 Funcionalidades Implementadas

### ✅ Detecção Automática
- Identifica mensagens de pré-apontamento baseado em palavras-chave
- Procura por: `DATA:`, `PROJETO:`, `EMPRESA:`, `SERVIÇO:`, `FAZENDA:`, `TALHÃO:`
- Detecta separadores: `-------------`, `---`, `========`

### ✅ Processamento com IA
- Extração estruturada de dados usando OpenAI GPT-3.5-turbo
- Normalização automática de valores monetários
- Conversão de "HOJE" para data atual
- Separação de dados em boletim e prêmios

### ✅ Armazenamento Estruturado
- **PRE_APONTAMENTO_RAW**: Dados brutos + hash anti-duplicação
- **BOLETIM_STAGING**: Dados principais estruturados
- **PREMIO_STAGING**: Rateios e prêmios por categoria

### ✅ Sistema de Aprovação
- Busca automática do coordenador do projeto
- Notificação com botões de aprovação/rejeição
- Rastreamento por ID único

## 📁 Arquivos Criados/Modificados

### `pre_apontamento.py`
Módulo principal com todas as funcionalidades:
```python
from pre_apontamento import processar_pre_apontamento

resultado = processar_pre_apontamento(numero, texto)
# Returns: {'is_pre_apont': bool, 'status': str, 'resposta': str}
```

### `bot_final.py` (Modificado)
Integração no webhook principal:
```python
# Verificação de pré-apontamento antes do processamento normal
resultado_pre_apont = processar_pre_apontamento(numero, mensagem_original)
if resultado_pre_apont['is_pre_apont']:
    enviar_mensagem(numero, resultado_pre_apont['resposta'])
    return '', 200
```

### `requirements.txt` (Atualizado)
```
openai>=1.0.0  # Adicionado para processamento IA
```

### `runtime.txt` (Atualizado)
```
python-3.12.8  # Versão atualizada conforme solicitado
```

### `teste_pre_apontamento.py`
Script de testes e demonstração

## 🗄️ Estrutura do Banco de Dados

### PRE_APONTAMENTO_RAW
```sql
CREATE TABLE PRE_APONTAMENTO_RAW (
    ID int IDENTITY(1,1) PRIMARY KEY,
    PHONE varchar(20),
    CONTEUDO_BRUTO text,
    HASH varchar(32),
    STATUS varchar(20),
    CREATED_AT datetime
);
```

### BOLETIM_STAGING
```sql
CREATE TABLE BOLETIM_STAGING (
    ID int IDENTITY(1,1) PRIMARY KEY,
    RAW_ID int,
    DATA_EXECUCAO date,
    PROJETO varchar(10),
    EMPRESA varchar(100),
    SERVICO varchar(100),
    FAZENDA varchar(100),
    TALHAO varchar(20),
    AREA_TOTAL float,
    AREA_REALIZADA float,
    AREA_RESTANTE float,
    STATUS_CAMPO varchar(50),
    VALOR_GANHO float,
    DIARIA_COLABORADOR float,
    LOTE1 varchar(50),
    INSUMO1 varchar(50),
    QUANTIDADE1 float,
    LOTE2 varchar(50),
    INSUMO2 varchar(50),
    QUANTIDADE2 float,
    LOTE3 varchar(50),
    INSUMO3 varchar(50),
    QUANTIDADE3 float,
    DIVISAO_PREMIO_IGUAL varchar(10),
    OBSERVACOES text,
    CREATED_AT datetime
);
```

### PREMIO_STAGING
```sql
CREATE TABLE PREMIO_STAGING (
    ID int IDENTITY(1,1) PRIMARY KEY,
    RAW_ID int,
    CATEGORIA varchar(20), -- 'RATEIO_MANUAL', 'RATEIO_MEC', 'APOIO', 'ESTRUTURA'
    COLABORADOR_ID varchar(10),
    EQUIPAMENTO varchar(10),
    PRODUCAO float,
    FUNCAO varchar(50),
    RECEBE_PREMIO int, -- 1 se tem "PREMIO", 0 se vazio
    VALOR_FIXO float,
    CREATED_AT datetime
);
```

## ⚙️ Variáveis de Ambiente

### Obrigatórias
```bash
```python
# Configuração OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sua_chave_aqui')
```

# Banco SQL Azure
DB_SERVER=alrflorestal.database.windows.net
DB_DATABASE=Tabela_teste
DB_USERNAME=sqladmin
DB_PASSWORD=sua_senha

# Z-API WhatsApp
INSTANCE_ID=sua_instancia
TOKEN=seu_token
CLIENT_TOKEN=seu_client_token
```

## 📱 Exemplo de Uso

### Mensagem de Pré-Apontamento
```
DATA: HOJE
PROJETO: 830
EMPRESA: LARSIL
SERVIÇO: COMBATE FORMIGA
FAZENDA: SÃO JOÃO
TALHÃO: 001
AREA TOTAL: 50
AREA REALIZADA: 10
AREA RESTANTE: 40
STATUS: ABERTO
VALOR GANHO: R$ 18.004,43
DIÁRIA COLABORADOR: R$ 1.500,36
-------------
LOTE1: 1508AB
INSUMO1: MIREX
QUANTIDADE1: 15,59
LOTE2:
INSUMO2:
QUANTIDADE2:
LOTE3:
INSUMO3:
QUANTIDADE3:
-------------
RATEIO PRODUÇÃO MANUAL
2508 - 2
2509 - 2
2510 - 2
2308 - 2
2108 - 2
-------------
RATEIO PRODUÇÃO MECANIZADA
PRODUÇÃO MECANIZADA TOTAL: 15
TPP005 - 2508 - 
TPP006 - 2509 - 5
-------------
DIVISÃO DE PRÊMIO IGUAL: SIM
-------------
EQUIPE APOIO ENVOLVIDA
2689 - PREMIO - VIVEIRO
2608 - 
2609 - 
-------------
ESTRUTURA APOIO ENVOLVIDA
TP001 - 0528 - PREMIO - MOTORISTA
TP009 -
-------------
OBS: Dia chuvoso, terreno molhado
```

### Resposta do Bot
```
✅ PRÉ-APONTAMENTO RECEBIDO

📊 PROJETO: 830
🏭 EMPRESA: LARSIL
🔧 SERVIÇO: COMBATE FORMIGA
🌾 FAZENDA: SÃO JOÃO
📍 TALHÃO: 001
📅 DATA: 2025-08-14

📏 ÁREA REALIZADA: 10
📐 ÁREA TOTAL: 50

🔄 STATUS: Enviado para aprovação
📋 ID: 123

✅ Coordenador será notificado para aprovação.
```

### Notificação para Coordenador
```
🚨 NOVO PRÉ-APONTAMENTO

📊 PROJETO: 830
🏭 EMPRESA: LARSIL
🔧 SERVIÇO: COMBATE FORMIGA
🌾 FAZENDA: SÃO JOÃO
📍 TALHÃO: 001
📅 DATA: 2025-08-14

📏 ÁREA REALIZADA: 10
📐 ÁREA TOTAL: 50

⚠️ AGUARDANDO APROVAÇÃO

[✅ APROVAR] [❌ REJEITAR] [👁️ VER DETALHES]
```

## 🔄 Fluxo Completo

1. **Recepção**: Usuário envia mensagem estruturada
2. **Detecção**: Sistema identifica pré-apontamento
3. **Salvamento RAW**: Dados brutos salvos imediatamente
4. **Processamento IA**: OpenAI extrai e estrutura dados
5. **Salvamento Staging**: Dados estruturados nas tabelas
6. **Busca Coordenador**: Identifica responsável pelo projeto
7. **Notificação**: Envia para coordenador com botões
8. **Resposta**: Confirma recebimento para usuário

## 🧪 Testes

Execute o arquivo de teste:
```bash
python teste_pre_apontamento.py
```

## 📋 Regras de Negócio Implementadas

### ✅ Detecção
- Pelo menos 3 indicadores principais OU 2 separadores
- Indicadores: `DATA:`, `PROJETO:`, `EMPRESA:`, `SERVIÇO:`, `FAZENDA:`, `TALHÃO:`
- Separadores: `-------------`, `---`, `========`

### ✅ Normalização
- "HOJE" → data atual (YYYY-MM-DD)
- "R$ 18.004,43" → 18004.43
- Vírgulas decimais → pontos

### ✅ Categorização de Prêmios
- `RATEIO_MANUAL`: Rateio de produção manual
- `RATEIO_MEC`: Rateio de produção mecanizada
- `APOIO`: Equipe de apoio envolvida
- `ESTRUTURA`: Estrutura de apoio envolvida

### ✅ Sistema de Prêmios
- `RECEBE_PREMIO`: 1 se contém "PREMIO", 0 se vazio
- Campos opcionais: VALOR_GANHO e DIARIA_COLABORADOR

## 🚀 Deploy

O sistema está pronto para deploy no Railway:

1. Todas as variáveis de ambiente configuradas
2. Dependências atualizadas no `requirements.txt`
3. Runtime atualizado para Python 3.12.8
4. Integração completa com bot existente

## 🔧 Manutenção

### Logs
- Logs detalhados em cada etapa do processamento
- Hash único para controle de duplicação
- Status de processamento rastreável

### Monitoramento
- Verificação de conexão com banco
- Validação de resposta da OpenAI
- Controle de falhas e fallbacks

### Escalabilidade
- Sistema modular e independente
- Pode ser facilmente expandido
- Compatible com múltiplos projetos
