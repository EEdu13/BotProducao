#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para truncar (limpar) todas as tabelas do sistema de pré-apontamento
CUIDADO: Este script apaga TODOS os dados das 3 tabelas!
"""

import pyodbc
import os
from datetime import datetime

def conectar_sql():
    """Conecta ao SQL Server Azure"""
    try:
        connection_string = os.getenv('DATABASE_URL_SQLSERVER')
        if not connection_string:
            raise ValueError("DATABASE_URL_SQLSERVER não encontrada nas variáveis de ambiente")
        
        print(f"[SQL] 🔌 Conectando ao banco...")
        conn = pyodbc.connect(connection_string, timeout=30)
        print(f"[SQL] ✅ Conectado com sucesso!")
        return conn
        
    except Exception as e:
        print(f"[SQL] ❌ ERRO na conexão: {e}")
        return None

def truncar_tabelas():
    """Trunca todas as 3 tabelas do sistema"""
    
    conn = conectar_sql()
    if not conn:
        print("❌ Não foi possível conectar ao banco!")
        return False
    
    try:
        cursor = conn.cursor()
        
        print("\n🚨 ATENÇÃO: Este script irá APAGAR TODOS OS DADOS das tabelas!")
        print("📋 Tabelas que serão limpas:")
        print("  1. PRE_APONTAMENTO_RAW")
        print("  2. BOLETIM_STAGING") 
        print("  3. PREMIO_STAGING")
        
        # Confirmar antes de executar
        confirmacao = input("\n⚠️  Digite 'CONFIRMO' para prosseguir (qualquer outra coisa cancela): ")
        
        if confirmacao.upper() != "CONFIRMO":
            print("❌ Operação cancelada pelo usuário")
            return False
        
        print(f"\n🔄 Iniciando limpeza às {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
        # 1. Truncar PREMIO_STAGING (tem FK para BOLETIM_STAGING)
        print("🧹 Limpando PREMIO_STAGING...")
        cursor.execute("DELETE FROM PREMIO_STAGING")
        linhas_premio = cursor.rowcount
        print(f"  ✅ {linhas_premio} registros removidos")
        
        # 2. Truncar BOLETIM_STAGING (tem FK para PRE_APONTAMENTO_RAW)
        print("🧹 Limpando BOLETIM_STAGING...")
        cursor.execute("DELETE FROM BOLETIM_STAGING")
        linhas_boletim = cursor.rowcount
        print(f"  ✅ {linhas_boletim} registros removidos")
        
        # 3. Truncar PRE_APONTAMENTO_RAW (tabela principal)
        print("🧹 Limpando PRE_APONTAMENTO_RAW...")
        cursor.execute("DELETE FROM PRE_APONTAMENTO_RAW")
        linhas_raw = cursor.rowcount
        print(f"  ✅ {linhas_raw} registros removidos")
        
        # Resetar contadores de identidade se necessário
        print("🔄 Resetando contadores de ID...")
        try:
            cursor.execute("DBCC CHECKIDENT ('PRE_APONTAMENTO_RAW', RESEED, 0)")
            cursor.execute("DBCC CHECKIDENT ('BOLETIM_STAGING', RESEED, 0)")
            cursor.execute("DBCC CHECKIDENT ('PREMIO_STAGING', RESEED, 0)")
            print("  ✅ Contadores resetados")
        except Exception as e:
            print(f"  ⚠️  Aviso: Não foi possível resetar contadores: {e}")
        
        # Commit das alterações
        conn.commit()
        
        print(f"\n🎉 LIMPEZA CONCLUÍDA COM SUCESSO!")
        print(f"📊 Resumo:")
        print(f"  - PRE_APONTAMENTO_RAW: {linhas_raw} registros removidos")
        print(f"  - BOLETIM_STAGING: {linhas_boletim} registros removidos")
        print(f"  - PREMIO_STAGING: {linhas_premio} registros removidos")
        print(f"  - Total: {linhas_raw + linhas_boletim + linhas_premio} registros removidos")
        print(f"\n✨ Sistema pronto para novos testes!")
        
        return True
        
    except Exception as e:
        print(f"❌ ERRO durante a limpeza: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()
        print("🔌 Conexão fechada")

def verificar_tabelas_vazias():
    """Verifica se as tabelas estão realmente vazias após a limpeza"""
    
    conn = conectar_sql()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        print("\n🔍 Verificando se as tabelas estão vazias...")
        
        # Contar registros em cada tabela
        cursor.execute("SELECT COUNT(*) FROM PRE_APONTAMENTO_RAW")
        count_raw = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM BOLETIM_STAGING")
        count_boletim = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM PREMIO_STAGING")
        count_premio = cursor.fetchone()[0]
        
        print(f"📊 Status das tabelas:")
        print(f"  - PRE_APONTAMENTO_RAW: {count_raw} registros")
        print(f"  - BOLETIM_STAGING: {count_boletim} registros")
        print(f"  - PREMIO_STAGING: {count_premio} registros")
        
        if count_raw == 0 and count_boletim == 0 and count_premio == 0:
            print("✅ Todas as tabelas estão vazias!")
            return True
        else:
            print("⚠️  Algumas tabelas ainda têm dados")
            return False
            
    except Exception as e:
        print(f"❌ ERRO na verificação: {e}")
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🧹 SCRIPT DE LIMPEZA DO SISTEMA DE PRÉ-APONTAMENTO")
    print("=" * 60)
    
    # Executar limpeza
    sucesso = truncar_tabelas()
    
    if sucesso:
        # Verificar se realmente limpou
        verificar_tabelas_vazias()
    
    print("\n" + "=" * 60)
    print("🏁 Script finalizado")
    print("=" * 60)
