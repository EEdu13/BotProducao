-- =========================================
-- SCRIPT DE CORREÇÃO DEFINITIVO DO BANCO - V2
-- Estrutura compatível com o código Python
-- =========================================

-- 1. DROPAR TABELAS INCORRETAS (SE EXISTIREM) - ORDEM CORRETA
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

PRINT 'Tabelas removidas com sucesso!';

-- 2. CRIAR PRE_APONTAMENTO_RAW
PRINT 'Criando PRE_APONTAMENTO_RAW...';
CREATE TABLE [dbo].[PRE_APONTAMENTO_RAW](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [telefone] [varchar](20) NOT NULL,
    [texto_original] [nvarchar](max) NOT NULL,
    [data_hora] [datetime] NOT NULL DEFAULT (GETDATE()),
    CONSTRAINT [PK_PRE_APONTAMENTO_RAW] PRIMARY KEY CLUSTERED ([id])
);
PRINT 'PRE_APONTAMENTO_RAW criada!';

-- 3. CRIAR BOLETIM_STAGING
PRINT 'Criando BOLETIM_STAGING...';
CREATE TABLE [dbo].[BOLETIM_STAGING](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [raw_id] [int] NOT NULL,
    [data_execucao] [date] NULL,
    [projeto] [varchar](100) NULL,
    [empresa] [varchar](100) NULL,
    [servico] [varchar](200) NULL,
    [fazenda] [varchar](100) NULL,
    [talhao] [varchar](50) NULL,
    [area_total] [decimal](10, 2) NULL,
    [area_realizada] [decimal](10, 2) NULL,
    [area_restante] [decimal](10, 2) NULL,
    [status_campo] [varchar](50) NULL,
    [valor_ganho] [decimal](10, 2) NULL,
    [diaria_colaborador] [decimal](10, 2) NULL,
    [lote1] [varchar](50) NULL,
    [insumo1] [varchar](100) NULL,
    [quantidade1] [decimal](10, 2) NULL,
    [lote2] [varchar](50) NULL,
    [insumo2] [varchar](100) NULL,
    [quantidade2] [decimal](10, 2) NULL,
    [data_cadastro] [datetime] NOT NULL DEFAULT (GETDATE()),
    CONSTRAINT [PK_BOLETIM_STAGING] PRIMARY KEY CLUSTERED ([id])
);
PRINT 'BOLETIM_STAGING criada!';

-- 4. CRIAR PREMIO_STAGING
PRINT 'Criando PREMIO_STAGING...';
CREATE TABLE [dbo].[PREMIO_STAGING](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [raw_id] [int] NOT NULL,
    [categoria] [varchar](50) NULL,
    [colaborador_id] [varchar](50) NULL,
    [equipamento] [varchar](100) NULL,
    [funcao] [varchar](100) NULL,
    [producao] [decimal](10, 2) NULL,
    [recebe_premio] [bit] NULL DEFAULT (0),
    [data_cadastro] [datetime] NOT NULL DEFAULT (GETDATE()),
    CONSTRAINT [PK_PREMIO_STAGING] PRIMARY KEY CLUSTERED ([id])
);
PRINT 'PREMIO_STAGING criada!';

-- 5. ADICIONAR FOREIGN KEYS
PRINT 'Adicionando Foreign Keys...';
ALTER TABLE [dbo].[BOLETIM_STAGING]
    ADD CONSTRAINT FK_BOLETIM_RAW FOREIGN KEY ([raw_id]) 
        REFERENCES [dbo].[PRE_APONTAMENTO_RAW]([id]);

ALTER TABLE [dbo].[PREMIO_STAGING]
    ADD CONSTRAINT FK_PREMIO_RAW FOREIGN KEY ([raw_id]) 
        REFERENCES [dbo].[PRE_APONTAMENTO_RAW]([id]);
PRINT 'Foreign Keys criadas!';

-- 6. CRIAR ÍNDICES PARA PERFORMANCE
PRINT 'Criando índices...';
CREATE INDEX IX_BOLETIM_RAW_ID ON [dbo].[BOLETIM_STAGING]([raw_id]);
CREATE INDEX IX_BOLETIM_DATA ON [dbo].[BOLETIM_STAGING]([data_execucao]);
CREATE INDEX IX_BOLETIM_PROJETO ON [dbo].[BOLETIM_STAGING]([projeto]);

CREATE INDEX IX_PREMIO_RAW_ID ON [dbo].[PREMIO_STAGING]([raw_id]);
CREATE INDEX IX_PREMIO_COLABORADOR ON [dbo].[PREMIO_STAGING]([colaborador_id]);

CREATE INDEX IX_RAW_TELEFONE ON [dbo].[PRE_APONTAMENTO_RAW]([telefone]);
CREATE INDEX IX_RAW_DATA ON [dbo].[PRE_APONTAMENTO_RAW]([data_hora]);
PRINT 'Índices criados!';

-- 7. INSERIR DADO DE TESTE PARA VALIDAR
PRINT 'Inserindo dados de teste...';
INSERT INTO [dbo].[PRE_APONTAMENTO_RAW] ([telefone], [texto_original])
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
BANCO CORRIGIDO');
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

PRINT '✅ BANCO CORRIGIDO COM ESTRUTURA COMPATÍVEL!';
PRINT '🚀 Bot deve funcionar normalmente agora!';
