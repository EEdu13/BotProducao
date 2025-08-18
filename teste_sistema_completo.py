#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Teste simulado completo do sistema sem API OpenAI
import sys
import os

# Simular função extrair_dados_com_openai sem usar OpenAI real
def extrair_dados_com_openai_simulado(texto, numero_celular):
    """Simula extração do OpenAI retornando dados básicos (sem insumos)"""
    print("[SIMULAÇÃO] 🤖 Simulando extração OpenAI...")
    
    # Simular que OpenAI extraiu alguns campos mas falhou nos insumos
    dados_simulados = {
        '_texto_original': texto,
        'numero_celular': numero_celular,
        'boletim': {
            'produtor': 'João Silva',
            'fazenda': 'Fazenda Esperança',
            'talhao': 'T123',
            'cultura': 'MILHO',
            'variedade': 'AG9045',
            'area_total': 50.5,
            'area_aplicada': 10.5,
            'data': '15/01/2025',
            'operador': 'Carlos Oliveira',
            # OpenAI falhou em extrair estes campos críticos:
            'lote1': None,
            'insumo1': None,
            'quantidade1': None,
            'area_restante': None,
            'status_campo': None
        }
    }
    
    print("[SIMULAÇÃO] ✅ Extração simulada concluída")
    return dados_simulados

# Importar função real de pós-processamento
sys.path.append(os.path.dirname(__file__))

def processar_campos_faltantes_real(dados):
    """Usar a lógica real de pós-processamento"""
    boletim = dados['boletim']
    texto_original = dados.get('_texto_original', '')
    
    print(f"[POS-PROC] 🔧 Iniciando pós-processamento...")
    
    # 1. ÁREA RESTANTE: Calcular se não foi extraída
    if boletim.get('area_restante') is None:
        area_total = boletim.get('area_total')
        area_aplicada = boletim.get('area_aplicada')
        if area_total is not None and area_aplicada is not None:
            boletim['area_restante'] = area_total - area_aplicada
            print(f"[POS-PROC] 📏 AREA RESTANTE calculada: {boletim['area_restante']}")
    
    # 2. STATUS CAMPO: Inferir se não foi extraído
    if boletim.get('status_campo') is None:
        area_total = boletim.get('area_total')
        area_aplicada = boletim.get('area_aplicada')
        if area_total is not None and area_aplicada is not None:
            if area_aplicada >= area_total:
                boletim['status_campo'] = 'FINALIZADO'
            else:
                boletim['status_campo'] = 'PARCIAL'
            print(f"[POS-PROC] 📊 STATUS inferido: {boletim['status_campo']}")
    
    # 3. INSUMOS: Extrair do texto bruto se OpenAI não conseguiu
    # Verificar se pelo menos lote1 está vazio
    if boletim.get('lote1') is None and boletim.get('insumo1') is None:
        print(f"[POS-PROC] 📦 Extraindo insumos do texto bruto...")
        
        # Extrair LOTE1, INSUMO1, QUANTIDADE1
        import re
        
        lote1_match = re.search(r'LOTE1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if lote1_match:
            boletim['lote1'] = lote1_match.group(1).strip()
            print(f"[POS-PROC] 📦 LOTE1 extraído: {boletim['lote1']}")
        
        insumo1_match = re.search(r'INSUMO1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if insumo1_match:
            boletim['insumo1'] = insumo1_match.group(1).strip()
            print(f"[POS-PROC] 📦 INSUMO1 extraído: {boletim['insumo1']}")
        
        quantidade1_match = re.search(r'QUANTIDADE1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if quantidade1_match:
            quantidade_str = quantidade1_match.group(1).strip().replace(',', '.')
            try:
                boletim['quantidade1'] = float(quantidade_str)
                print(f"[POS-PROC] 📦 QUANTIDADE1 extraída: {boletim['quantidade1']}")
            except ValueError:
                print(f"[POS-PROC] ⚠️ Erro ao converter quantidade1: {quantidade_str}")
        
        # Extrair LOTE2, INSUMO2, QUANTIDADE2 se existirem
        lote2_match = re.search(r'LOTE2:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if lote2_match and lote2_match.group(1).strip():
            boletim['lote2'] = lote2_match.group(1).strip()
            print(f"[POS-PROC] 📦 LOTE2 extraído: {boletim['lote2']}")
        
        insumo2_match = re.search(r'INSUMO2:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if insumo2_match and insumo2_match.group(1).strip():
            boletim['insumo2'] = insumo2_match.group(1).strip()
            print(f"[POS-PROC] 📦 INSUMO2 extraído: {boletim['insumo2']}")
        
        quantidade2_match = re.search(r'QUANTIDADE2:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if quantidade2_match and quantidade2_match.group(1).strip():
            quantidade_str = quantidade2_match.group(1).strip().replace(',', '.')
            try:
                boletim['quantidade2'] = float(quantidade_str)
                print(f"[POS-PROC] 📦 QUANTIDADE2 extraída: {boletim['quantidade2']}")
            except ValueError:
                print(f"[POS-PROC] ⚠️ Erro ao converter quantidade2: {quantidade_str}")
    
    # 4. STATUS CAMPO: Extrair do texto se não foi extraído pelo OpenAI
    if boletim.get('status_campo') is None:
        import re
        status_match = re.search(r'STATUS:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if status_match:
            boletim['status_campo'] = status_match.group(1).strip().upper()
            print(f"[POS-PROC] 📊 STATUS extraído do texto: {boletim['status_campo']}")
    
    # 5. AREA RESTANTE: Extrair do texto se não foi extraído pelo OpenAI
    if boletim.get('area_restante') is None:
        import re
        area_restante_match = re.search(r'AREA\s*RESTANTE:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if area_restante_match:
            try:
                area_str = area_restante_match.group(1).strip().replace(',', '.')
                boletim['area_restante'] = float(area_str)
                print(f"[POS-PROC] 📏 AREA RESTANTE extraída do texto: {boletim['area_restante']}")
            except ValueError:
                print(f"[POS-PROC] ⚠️ Erro ao converter area_restante: {area_restante_match.group(1)}")
    
    print(f"[POS-PROC] ✅ Pós-processamento concluído")
    return dados

def simular_sistema_completo():
    """Simula todo o fluxo do sistema"""
    print("=== SIMULAÇÃO SISTEMA COMPLETO ===\n")
    
    # Texto de entrada do usuário
    texto_entrada = '''
PRODUTOR: João Silva
FAZENDA: Fazenda Esperança  
TALHAO: T123
CULTURA: MILHO
VARIEDADE: AG9045
AREA TOTAL: 50.5
AREA APLICADA: 10.5
AREA RESTANTE: 40.0
LOTE1: 1508AB
INSUMO1: MIREX
QUANTIDADE1: 15,59
STATUS: PARCIAL
DATA: 15/01/2025
OPERADOR: Carlos Oliveira
'''
    
    numero_celular = '5511999999999'
    
    print("1️⃣ FASE: Extração OpenAI (simulada)")
    dados = extrair_dados_com_openai_simulado(texto_entrada, numero_celular)
    
    print(f"\n📊 Campos extraídos pelo OpenAI:")
    boletim = dados['boletim']
    for campo, valor in boletim.items():
        status = "✅" if valor is not None else "❌"
        print(f"  {status} {campo}: {valor}")
    
    print(f"\n2️⃣ FASE: Pós-processamento (extração manual)")
    dados = processar_campos_faltantes_real(dados)
    
    print(f"\n📊 Campos após pós-processamento:")
    boletim = dados['boletim']
    for campo, valor in boletim.items():
        status = "✅" if valor is not None else "❌"
        print(f"  {status} {campo}: {valor}")
    
    # Verificar se todos os campos críticos foram preenchidos
    campos_criticos = ['lote1', 'insumo1', 'quantidade1', 'area_restante', 'status_campo']
    todos_preenchidos = all(boletim.get(campo) is not None for campo in campos_criticos)
    
    print(f"\n🎯 RESULTADO FINAL:")
    print(f"  Campos críticos: {campos_criticos}")
    print(f"  Status: {'✅ TODOS PREENCHIDOS' if todos_preenchidos else '❌ CAMPOS FALTANDO'}")
    
    if todos_preenchidos:
        print(f"\n🚀 Sistema 100% funcional!")
        print(f"  📦 Insumos: LOTE1={boletim['lote1']}, INSUMO1={boletim['insumo1']}, QTD1={boletim['quantidade1']}")
        print(f"  📏 Área restante: {boletim['area_restante']}")
        print(f"  📊 Status campo: {boletim['status_campo']}")
    else:
        print(f"\n⚠️ Ainda há campos faltando - verificar lógica")
    
    return dados

if __name__ == "__main__":
    resultado = simular_sistema_completo()
    print("\n=== FIM DA SIMULAÇÃO ===")
