-- =========================================
-- CORREÇÃO COM ESTRUTURA ORIGINAL - V3
-- Baseado na estrutura que funcionava antes
-- =========================================

-- 1. DROPAR TABELAS (ORDEM CORRETA)
PRINT 'Removendo constraints...';
IF EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_PREMIO_RAW')
    ALTER TABLE [dbo].[PREMIO_STAGING] DROP CONSTRAINT FK_PREMIO_RAW;

IF EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_BOLETIM_RAW')
    ALTER TABLE [dbo].[BOLETIM_STAGING] DROP CONSTRAINT FK_BOLETIM_RAW;

PRINT 'Removendo tabelas...';
IF OBJECT_ID('dbo.PREMIO_STAGING', 'U') IS NOT NULL
    DROP TABLE [dbo].[PREMIO_STAGING];

IF OBJECT_ID('dbo.BOLETIM_STAGING', 'U') IS NOT NULL
    DROP TABLE [dbo].[BOLETIM_STAGING];

IF OBJECT_ID('dbo.PRE_APONTAMENTO_RAW', 'U') IS NOT NULL
    DROP TABLE [dbo].[PRE_APONTAMENTO_RAW];

PRINT 'Tabelas removidas!';

-- 2. CRIAR PRE_APONTAMENTO_RAW (ESTRUTURA ORIGINAL)
PRINT 'Criando PRE_APONTAMENTO_RAW...';
CREATE TABLE [dbo].[PRE_APONTAMENTO_RAW](
    [ID] [int] IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [PHONE] [varchar](20) NOT NULL,              -- ⚠️ PHONE (como o erro indica)
    [CONTEUDO_BRUTO] [nvarchar](max) NOT NULL,   -- ⚠️ CONTEUDO_BRUTO (como o erro indica)
    [HASH] [varchar](50) NULL,                   -- ⚠️ HASH (não HASH_MSG!)
    [STATUS] [varchar](20) NULL DEFAULT 'PENDENTE', -- ⚠️ STATUS que estava faltando!
    [CREATED_AT] [datetime] NOT NULL DEFAULT (GETDATE())
);
PRINT 'PRE_APONTAMENTO_RAW criada!';

-- 3. CRIAR BOLETIM_STAGING (ESTRUTURA ORIGINAL)
PRINT 'Criando BOLETIM_STAGING...';
CREATE TABLE [dbo].[BOLETIM_STAGING](
    [ID] [int] IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [RAW_ID] [int] NOT NULL,
    [DATA_EXECUCAO] [date] NULL,
    [PROJETO] [varchar](10) NULL,                -- ⚠️ varchar(10) original
    [EMPRESA] [varchar](100) NULL,
    [SERVICO] [varchar](100) NULL,               -- ⚠️ varchar(100) original
    [FAZENDA] [varchar](100) NULL,
    [TALHAO] [varchar](20) NULL,                 -- ⚠️ varchar(20) original
    [AREA_TOTAL] [float] NULL,                   -- ⚠️ float original
    [AREA_REALIZADA] [float] NULL,               -- ⚠️ float original
    [AREA_RESTANTE] [float] NULL,                -- ⚠️ float original
    [STATUS_CAMPO] [varchar](50) NULL,
    [VALOR_GANHO] [float] NULL,                  -- ⚠️ float original
    [DIARIA_COLABORADOR] [float] NULL,           -- ⚠️ float original
    [LOTE1] [varchar](50) NULL,
    [INSUMO1] [varchar](50) NULL,                -- ⚠️ varchar(50) original
    [QUANTIDADE1] [float] NULL,                  -- ⚠️ float original
    [LOTE2] [varchar](50) NULL,
    [INSUMO2] [varchar](50) NULL,                -- ⚠️ varchar(50) original
    [QUANTIDADE2] [float] NULL,                  -- ⚠️ float original
    [LOTE3] [varchar](50) NULL,                  -- ⚠️ LOTE3 que estava faltando!
    [INSUMO3] [varchar](50) NULL,                -- ⚠️ INSUMO3 que estava faltando!
    [QUANTIDADE3] [float] NULL,                  -- ⚠️ QUANTIDADE3 que estava faltando!
    [DIVISAO_PREMIO_IGUAL] [varchar](10) NULL,   -- ⚠️ DIVISAO_PREMIO_IGUAL que estava faltando!
    [OBSERVACOES] [nvarchar](max) NULL,          -- ⚠️ OBSERVACOES que estava faltando!
    [CREATED_AT] [datetime] NOT NULL DEFAULT (GETDATE())
);
PRINT 'BOLETIM_STAGING criada!';

-- 4. CRIAR PREMIO_STAGING (ESTRUTURA ORIGINAL)
PRINT 'Criando PREMIO_STAGING...';
CREATE TABLE [dbo].[PREMIO_STAGING](
    [ID] [int] IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [RAW_ID] [int] NOT NULL,
    [CATEGORIA] [varchar](20) NULL,              -- ⚠️ varchar(20) original
    [COLABORADOR_ID] [varchar](10) NULL,         -- ⚠️ varchar(10) original
    [EQUIPAMENTO] [varchar](10) NULL,            -- ⚠️ varchar(10) original
    [PRODUCAO] [float] NULL,                     -- ⚠️ float original
    [FUNCAO] [varchar](50) NULL,
    [RECEBE_PREMIO] [int] NULL,                  -- ⚠️ int original (não bit)
    [VALOR_FIXO] [float] NULL,                   -- ⚠️ VALOR_FIXO que estava faltando!
    [CREATED_AT] [datetime] NOT NULL DEFAULT (GETDATE())
);
PRINT 'PREMIO_STAGING criada!';

-- 5. ADICIONAR FOREIGN KEYS
PRINT 'Adicionando Foreign Keys...';
ALTER TABLE [dbo].[BOLETIM_STAGING]
    ADD CONSTRAINT FK_BOLETIM_RAW FOREIGN KEY ([RAW_ID]) 
        REFERENCES [dbo].[PRE_APONTAMENTO_RAW]([ID]);

ALTER TABLE [dbo].[PREMIO_STAGING]
    ADD CONSTRAINT FK_PREMIO_RAW FOREIGN KEY ([RAW_ID]) 
        REFERENCES [dbo].[PRE_APONTAMENTO_RAW]([ID]);
PRINT 'Foreign Keys criadas!';

-- 6. CRIAR ÍNDICES PARA PERFORMANCE
PRINT 'Criando índices...';
CREATE INDEX IX_BOLETIM_RAW_ID ON [dbo].[BOLETIM_STAGING]([RAW_ID]);
CREATE INDEX IX_BOLETIM_DATA ON [dbo].[BOLETIM_STAGING]([DATA_EXECUCAO]);
CREATE INDEX IX_BOLETIM_PROJETO ON [dbo].[BOLETIM_STAGING]([PROJETO]);

CREATE INDEX IX_PREMIO_RAW_ID ON [dbo].[PREMIO_STAGING]([RAW_ID]);
CREATE INDEX IX_PREMIO_COLABORADOR ON [dbo].[PREMIO_STAGING]([COLABORADOR_ID]);

CREATE INDEX IX_RAW_PHONE ON [dbo].[PRE_APONTAMENTO_RAW]([PHONE]);
CREATE INDEX IX_RAW_DATA ON [dbo].[PRE_APONTAMENTO_RAW]([CREATED_AT]);
CREATE INDEX IX_RAW_HASH ON [dbo].[PRE_APONTAMENTO_RAW]([HASH]);
CREATE INDEX IX_RAW_STATUS ON [dbo].[PRE_APONTAMENTO_RAW]([STATUS]);
PRINT 'Índices criados!';

-- 7. INSERIR DADO DE TESTE PARA VALIDAR
PRINT 'Inserindo dados de teste...';
INSERT INTO [dbo].[PRE_APONTAMENTO_RAW] ([PHONE], [CONTEUDO_BRUTO], [HASH], [STATUS])
VALUES ('5511999999999', 'DATA: HOJE
PROJETO: 830
EMPRESA: LARSIL
SERVIÇO: COMBATE FORMIGA
FAZENDA: SÃO JOÃO
TALHÃO: 001
AREA TOTAL: 50
AREA REALIZADA: 10
LOTE1: 1508AB
INSUMO1: MIREX
QUANTIDADE1: 15,59
AREA RESTANTE: 40
STATUS: PARCIAL
-------------
BANCO ORIGINAL RESTAURADO', 'test_hash_123', 'PROCESSADO');
PRINT 'Dados de teste inseridos!';

-- 8. VERIFICAR SE ESTÁ FUNCIONANDO
PRINT 'Verificando tabelas criadas...';
SELECT 'PRE_APONTAMENTO_RAW' as Tabela, COUNT(*) as Registros FROM [dbo].[PRE_APONTAMENTO_RAW]
UNION ALL
SELECT 'BOLETIM_STAGING' as Tabela, COUNT(*) as Registros FROM [dbo].[BOLETIM_STAGING]
UNION ALL
SELECT 'PREMIO_STAGING' as Tabela, COUNT(*) as Registros FROM [dbo].[PREMIO_STAGING];

-- 9. MOSTRAR ESTRUTURA DAS TABELAS
PRINT 'Mostrando estrutura das tabelas...';
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME IN ('PRE_APONTAMENTO_RAW', 'BOLETIM_STAGING', 'PREMIO_STAGING')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

PRINT '✅ BANCO ORIGINAL RESTAURADO!';
PRINT '🚀 Estrutura exata que funcionava antes!';
PRINT '📋 PRINCIPAIS MUDANÇAS:';
PRINT '   - PHONE (não telefone)';
PRINT '   - CONTEUDO_BRUTO (não texto_original)';
PRINT '   - HASH (não HASH_MSG)';
PRINT '   - CREATED_AT (não data_hora/data_cadastro)';
PRINT '   - Tipos FLOAT (não decimal)';
PRINT '   - Colunas LOTE3/INSUMO3/QUANTIDADE3 restauradas';
PRINT '   - VALOR_FIXO restaurado';
PRINT '   - Tamanhos originais dos varchar';
