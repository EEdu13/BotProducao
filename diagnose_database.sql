-- =========================================
-- DIAGNÓSTICO COMPLETO DO BANCO DE DADOS
-- =========================================

PRINT '🔍 INICIANDO DIAGNÓSTICO...';

-- 1. VERIFICAR TODAS AS TABELAS EXISTENTES
PRINT '';
PRINT '📋 TABELAS EXISTENTES:';
SELECT 
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_NAME LIKE '%APONTAMENTO%' 
   OR TABLE_NAME LIKE '%BOLETIM%' 
   OR TABLE_NAME LIKE '%PREMIO%'
ORDER BY TABLE_NAME;

-- 2. VERIFICAR TODAS AS COLUNAS DE CADA TABELA
PRINT '';
PRINT '📋 ESTRUTURA DAS COLUNAS:';
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME LIKE '%APONTAMENTO%' 
   OR TABLE_NAME LIKE '%BOLETIM%' 
   OR TABLE_NAME LIKE '%PREMIO%'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- 3. VERIFICAR FOREIGN KEYS
PRINT '';
PRINT '🔗 FOREIGN KEYS EXISTENTES:';
SELECT 
    fk.name AS FK_Name,
    tp.name AS Parent_Table,
    cp.name AS Parent_Column,
    tr.name AS Referenced_Table,
    cr.name AS Referenced_Column
FROM sys.foreign_keys fk
INNER JOIN sys.tables tp ON fk.parent_object_id = tp.object_id
INNER JOIN sys.tables tr ON fk.referenced_object_id = tr.object_id
INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
INNER JOIN sys.columns cp ON fkc.parent_column_id = cp.column_id AND fkc.parent_object_id = cp.object_id
INNER JOIN sys.columns cr ON fkc.referenced_column_id = cr.column_id AND fkc.referenced_object_id = cr.object_id
WHERE tp.name LIKE '%APONTAMENTO%' 
   OR tp.name LIKE '%BOLETIM%' 
   OR tp.name LIKE '%PREMIO%'
   OR tr.name LIKE '%APONTAMENTO%' 
   OR tr.name LIKE '%BOLETIM%' 
   OR tr.name LIKE '%PREMIO%';

-- 4. VERIFICAR ÍNDICES
PRINT '';
PRINT '📊 ÍNDICES EXISTENTES:';
SELECT 
    t.name AS Table_Name,
    i.name AS Index_Name,
    i.type_desc AS Index_Type
FROM sys.indexes i
INNER JOIN sys.tables t ON i.object_id = t.object_id
WHERE t.name LIKE '%APONTAMENTO%' 
   OR t.name LIKE '%BOLETIM%' 
   OR t.name LIKE '%PREMIO%'
ORDER BY t.name, i.name;

PRINT '';
PRINT '✅ DIAGNÓSTICO COMPLETO FINALIZADO!';
