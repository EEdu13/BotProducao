# Configuração de Variáveis de Ambiente - Railway

## 🚀 Passo a Passo para Deploy

### 1. Acesse o Railway Dashboard
- Entre em [railway.app](https://railway.app)
- Selecione seu projeto "BotProducao"

### 2. Configure as Variáveis de Ambiente
No painel do Railway, vá em **Variables** e adicione:

```bash
# ========== OPENAI API ==========
```bash
OPENAI_API_KEY=sua_chave_openai_aqui
```

# ========== SQL SERVER AZURE ==========
DB_SERVER=alrflorestal.database.windows.net
DB_DATABASE=Tabela_teste
DB_USERNAME=sqladmin
DB_PASSWORD=sua_senha_aqui

# ========== Z-API WHATSAPP ==========
INSTANCE_ID=sua_instancia_aqui
TOKEN=seu_token_aqui
CLIENT_TOKEN=seu_client_token_aqui
```

### 3. Deploy Automático
Após configurar as variáveis:
1. Faça commit das alterações: `git add . && git commit -m "Implementar sistema de pré-apontamento"`
2. Push para o repositório: `git push origin main`
3. O Railway fará deploy automaticamente

### 4. Criar Tabelas no Banco (Se necessário)

Execute estes SQLs no Azure SQL Server:

```sql
-- Tabela para dados brutos
CREATE TABLE PRE_APONTAMENTO_RAW (
    ID int IDENTITY(1,1) PRIMARY KEY,
    PHONE varchar(20),
    CONTEUDO_BRUTO text,
    HASH varchar(32),
    STATUS varchar(20) DEFAULT 'PENDENTE',
    CREATED_AT datetime DEFAULT GETDATE()
);

-- Tabela para boletim estruturado
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
    CREATED_AT datetime DEFAULT GETDATE(),
    FOREIGN KEY (RAW_ID) REFERENCES PRE_APONTAMENTO_RAW(ID)
);

-- Tabela para prêmios estruturados
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
    CREATED_AT datetime DEFAULT GETDATE(),
    FOREIGN KEY (RAW_ID) REFERENCES PRE_APONTAMENTO_RAW(ID)
);

-- Adicionar coluna PERFIL na tabela USUARIOS (se não existir)
-- ALTER TABLE USUARIOS ADD PERFIL varchar(20);

-- Inserir alguns coordenadores de exemplo
-- INSERT INTO USUARIOS (TELEFONE, USUARIO, PROJETO, PERFIL) 
-- VALUES ('5511999999999', 'João Coordenador', '830', 'COORDENADOR');
```

### 5. Teste do Sistema

Após o deploy, envie uma mensagem de teste:

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
-------------
RATEIO PRODUÇÃO MANUAL
2508 - 2
2509 - 2
-------------
DIVISÃO DE PRÊMIO IGUAL: SIM
-------------
OBS: Dia chuvoso, terreno molhado
```

### 6. Monitoramento

Monitore os logs no Railway para verificar:
- ✅ Detecção de pré-apontamentos
- ✅ Processamento com OpenAI
- ✅ Salvamento no banco
- ✅ Notificações para coordenadores

### 7. Verificação no Banco

Consulte as tabelas para confirmar os dados:

```sql
-- Verificar dados brutos
SELECT TOP 10 * FROM PRE_APONTAMENTO_RAW ORDER BY CREATED_AT DESC;

-- Verificar boletins processados
SELECT TOP 10 * FROM BOLETIM_STAGING ORDER BY CREATED_AT DESC;

-- Verificar prêmios
SELECT TOP 10 * FROM PREMIO_STAGING ORDER BY CREATED_AT DESC;
```

## 🎯 Checklist Final

- [ ] Variáveis de ambiente configuradas no Railway
- [ ] Tabelas criadas no Azure SQL Server
- [ ] Deploy realizado com sucesso
- [ ] Teste de mensagem executado
- [ ] Logs verificados
- [ ] Dados salvos no banco confirmados
- [ ] Coordenador recebeu notificação

## 📞 Suporte

Se encontrar problemas:
1. Verifique logs no Railway Dashboard
2. Confirme variáveis de ambiente
3. Teste conexão com banco Azure
4. Verifique status da API OpenAI

## 🎉 Sistema Pronto!

Após completar estes passos, seu sistema de pré-apontamento estará totalmente funcional e integrado ao bot WhatsApp existente.
