#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste simulando dados do OpenAI + Post-processamento
"""

# Simular dados que o OpenAI retornaria (alguns campos faltando)
dados_simulados_openai = {
    'data': 'HOJE',
    'projeto': '830',
    'empresa': 'LARSIL',
    'servico': 'COMBATE FORMIGA',
    'fazenda': 'SÃO JOÃO',
    'talhao': '001',
    'area_total': 50.0,
    'area_realizada': 10.0,
    # Insumos que OpenAI não conseguiu extrair:
    'lote1': None,
    'insumo1': None,
    'quantidade1': None,
    # Campos que OpenAI não conseguiu calcular:
    'area_restante': None,
    'status_campo': None,
    # Texto original para post-processamento:
    '_texto_original': """DATA: HOJE
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
TESTE FINAL"""
}

# Simular a função de post-processamento
import re

def testar_pos_processamento(dados):
    """Testar post-processamento manual"""
    print("=== SIMULAÇÃO POST-PROCESSAMENTO ===")
    print("Dados antes do pós-processamento:")
    
    # Mostrar campos importantes antes
    campos = ['lote1', 'insumo1', 'quantidade1', 'area_restante', 'status_campo']
    for campo in campos:
        print(f"  {campo}: {dados.get(campo)}")
    
    texto_original = dados.get('_texto_original', '')
    
    # 1. AREA RESTANTE (cálculo)
    area_total = dados.get('area_total')
    area_realizada = dados.get('area_realizada')
    
    if area_total and area_realizada and dados.get('area_restante') is None:
        area_restante = area_total - area_realizada
        dados['area_restante'] = area_restante
        print(f"\n[POS-PROC] 📏 Área restante calculada: {area_restante}")
    
    # 2. STATUS CAMPO (inferência)
    if dados.get('status_campo') is None:
        area_restante = dados.get('area_restante')
        if area_restante is not None and area_restante > 0:
            status_campo = "PARCIAL"
        elif area_restante is not None and area_restante <= 0:
            status_campo = "CONCLUÍDO"
        else:
            status_campo = "INICIADO"
        
        dados['status_campo'] = status_campo
        print(f"[POS-PROC] 📊 Status campo inferido: {status_campo}")
    
    # 3. INSUMOS (extração manual)
    if dados.get('lote1') is None and dados.get('insumo1') is None:
        print(f"[POS-PROC] 📦 Extraindo insumos do texto bruto...")
        
        # LOTE1
        lote1_match = re.search(r'LOTE1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if lote1_match:
            dados['lote1'] = lote1_match.group(1).strip()
            print(f"[POS-PROC] 📦 LOTE1 extraído: {dados['lote1']}")
        
        # INSUMO1
        insumo1_match = re.search(r'INSUMO1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if insumo1_match:
            dados['insumo1'] = insumo1_match.group(1).strip()
            print(f"[POS-PROC] 📦 INSUMO1 extraído: {dados['insumo1']}")
        
        # QUANTIDADE1
        quantidade1_match = re.search(r'QUANTIDADE1:\s*([^\n\r]+)', texto_original, re.IGNORECASE)
        if quantidade1_match:
            quantidade_str = quantidade1_match.group(1).strip().replace(',', '.')
            try:
                dados['quantidade1'] = float(quantidade_str)
                print(f"[POS-PROC] 📦 QUANTIDADE1 extraída: {dados['quantidade1']}")
            except ValueError:
                print(f"[POS-PROC] ⚠️ Erro ao converter quantidade1: {quantidade_str}")
    
    print(f"\nDados após pós-processamento:")
    for campo in campos:
        valor = dados.get(campo)
        status = "✅" if valor is not None else "❌"
        print(f"  {status} {campo}: {valor}")
    
    # Calcular sucesso
    extraidos = sum(1 for campo in campos if dados.get(campo) is not None)
    percentual = (extraidos / len(campos)) * 100
    print(f"\n🎯 RESULTADO: {extraidos}/{len(campos)} campos ({percentual:.0f}%)")
    
    if percentual == 100:
        print("🚀 SISTEMA 100% FUNCIONAL!")
        print("✅ TODOS OS INSUMOS FORAM EXTRAÍDOS!")
    
    return dados

if __name__ == "__main__":
    resultado = testar_pos_processamento(dados_simulados_openai)
