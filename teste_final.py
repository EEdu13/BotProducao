#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste final do sistema completo
"""

# Dados de teste reais do usuário
texto_teste_usuario = """DATA: HOJE
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

from pre_apontamento import detectar_pre_apontamento, extrair_dados_com_openai, processar_campos_faltantes

print("=== TESTE FINAL SISTEMA COMPLETO ===")
print("Testando com dados reais do usuário...")
print(f"Texto: {texto_teste_usuario[:100]}...")

# 1. Detectar se é pré-apontamento
is_pre_apont = detectar_pre_apontamento(texto_teste_usuario)
print(f"\n1. É pré-apontamento: {is_pre_apont}")

if is_pre_apont:
    # 2. Extrair com OpenAI
    print("\n2. Extraindo com OpenAI...")
    try:
        dados_openai = extrair_dados_com_openai(texto_teste_usuario)
        print(f"OpenAI extraiu: {len([k for k, v in dados_openai.items() if v is not None])} campos")
        
        # 3. Post-processamento
        print("\n3. Executando post-processamento...")
        dados_openai['_texto_original'] = texto_teste_usuario
        boletim_final = processar_campos_faltantes(dados_openai)
        
        # 4. Verificar resultado final
        print(f"\n4. RESULTADO FINAL:")
        campos_importantes = ['lote1', 'insumo1', 'quantidade1', 'area_restante', 'status_campo']
        
        for campo in campos_importantes:
            valor = boletim_final.get(campo)
            status = "✅" if valor is not None else "❌"
            print(f"  {status} {campo}: {valor}")
            
        # Calcular percentual de sucesso
        extraidos = sum(1 for campo in campos_importantes if boletim_final.get(campo) is not None)
        percentual = (extraidos / len(campos_importantes)) * 100
        print(f"\n🎯 SUCESSO: {extraidos}/{len(campos_importantes)} campos ({percentual:.0f}%)")
        
        if percentual == 100:
            print("🚀 SISTEMA 100% FUNCIONAL!")
        else:
            print(f"⚠️ Faltam {len(campos_importantes) - extraidos} campos")
            
    except Exception as e:
        print(f"❌ Erro: {e}")
else:
    print("❌ Texto não foi reconhecido como pré-apontamento")
