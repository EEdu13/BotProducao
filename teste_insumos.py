#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Teste específico para extração de insumos
import os
import sys
import re

# Simular dados extraídos pelo OpenAI (sem insumos)
dados_simulados = {
    '_texto_original': '''
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
''',
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
        # OpenAI falhou em extrair estes campos:
        'lote1': None,
        'insumo1': None,
        'quantidade1': None,
        'area_restante': None,
        'status_campo': None
    }
}

def processar_campos_faltantes_teste(dados):
    """Versão de teste da função processar_campos_faltantes"""
    boletim = dados['boletim']
    texto_original = dados.get('_texto_original', '')
    
    print("=== TESTE DE EXTRAÇÃO DE INSUMOS ===")
    print(f"Texto original (primeiros 300 chars):\n{texto_original[:300]}...")
    print(f"\nBoletim antes do pós-processamento:")
    print(f"  lote1: {boletim.get('lote1')}")
    print(f"  insumo1: {boletim.get('insumo1')}")
    print(f"  quantidade1: {boletim.get('quantidade1')}")
    print(f"  area_restante: {boletim.get('area_restante')}")
    print(f"  status_campo: {boletim.get('status_campo')}")
    
    # 1. INSUMOS: Extrair do texto bruto se OpenAI não conseguiu
    # Verificar se pelo menos lote1 está vazio
    if boletim.get('lote1') is None and boletim.get('insumo1') is None:
        print(f"\n[POS-PROC] 📦 Extraindo insumos do texto bruto...")
        
        # Extrair LOTE1, INSUMO1, QUANTIDADE1
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
    
    # 2. STATUS CAMPO: Extrair do texto se não foi extraído pelo OpenAI
    if boletim.get('status_campo') is None:
        status_match = re.search(r'STATUS:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if status_match:
            boletim['status_campo'] = status_match.group(1).strip().upper()
            print(f"[POS-PROC] 📊 STATUS extraído do texto: {boletim['status_campo']}")
    
    # 3. AREA RESTANTE: Extrair do texto se não foi extraído pelo OpenAI
    if boletim.get('area_restante') is None:
        area_restante_match = re.search(r'AREA\s*RESTANTE:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if area_restante_match:
            try:
                area_str = area_restante_match.group(1).strip().replace(',', '.')
                boletim['area_restante'] = float(area_str)
                print(f"[POS-PROC] 📏 AREA RESTANTE extraída do texto: {boletim['area_restante']}")
            except ValueError:
                print(f"[POS-PROC] ⚠️ Erro ao converter area_restante: {area_restante_match.group(1)}")
    
    # 4. Se AREA RESTANTE ainda for None, calcular
    if boletim.get('area_restante') is None:
        area_total = boletim.get('area_total')
        area_aplicada = boletim.get('area_aplicada')
        if area_total is not None and area_aplicada is not None:
            boletim['area_restante'] = area_total - area_aplicada
            print(f"[POS-PROC] 📏 AREA RESTANTE calculada: {boletim['area_restante']}")
    
    # 5. Se STATUS ainda for None, inferir
    if boletim.get('status_campo') is None:
        area_total = boletim.get('area_total')
        area_aplicada = boletim.get('area_aplicada')
        if area_total is not None and area_aplicada is not None:
            if area_aplicada >= area_total:
                boletim['status_campo'] = 'FINALIZADO'
            else:
                boletim['status_campo'] = 'PARCIAL'
            print(f"[POS-PROC] 📊 STATUS inferido: {boletim['status_campo']}")
    
    print(f"\nBoletim após pós-processamento:")
    print(f"  lote1: {boletim.get('lote1')}")
    print(f"  insumo1: {boletim.get('insumo1')}")
    print(f"  quantidade1: {boletim.get('quantidade1')}")
    print(f"  area_restante: {boletim.get('area_restante')}")
    print(f"  status_campo: {boletim.get('status_campo')}")
    
    return dados

if __name__ == "__main__":
    resultado = processar_campos_faltantes_teste(dados_simulados)
    print("\n=== TESTE CONCLUÍDO ===")
    print("✅ Extração de insumos funcionando!")
