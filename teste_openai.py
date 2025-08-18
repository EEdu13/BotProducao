#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste rápido da extração OpenAI
"""

# Importar a função
import sys
import os
sys.path.append('.')
from pre_apontamento import extrair_dados_com_openai

texto_teste = """DATA: HOJE
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
2508 - 
2509 - 
2510 - 
2308 - 
2108 - 
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
OBS: Dia chuvoso, terreno molhado"""

print("🧪 TESTANDO EXTRAÇÃO OPENAI")
print("=" * 50)

resultado = extrair_dados_com_openai(texto_teste)

if resultado:
    boletim = resultado.get('boletim', {})
    print(f"\n📦 RESULTADO FINAL:")
    print(f"  - lote1: {boletim.get('lote1')}")
    print(f"  - insumo1: {boletim.get('insumo1')}")
    print(f"  - quantidade1: {boletim.get('quantidade1')}")
    print(f"  - area_restante: {boletim.get('area_restante')}")
    print(f"  - status_campo: {boletim.get('status_campo')}")
else:
    print("❌ FALHA NA EXTRAÇÃO")
