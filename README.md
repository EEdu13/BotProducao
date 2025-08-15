# 🤖 Bot de Pré-Apontamento WhatsApp

Sistema inteligente de pré-apontamento agrícola com integração WhatsApp, OpenAI e SQL Server Azure.

## 🚀 Funcionalidades

- ✅ **Extração Inteligente**: OpenAI GPT-3.5-turbo extrai dados automaticamente
- ✅ **Pós-Processamento**: Sistema de backup para garantir 100% de extração
- ✅ **Integração WhatsApp**: Webhook Z-API para comunicação
- ✅ **Banco SQL Azure**: Armazenamento em três tabelas especializadas
- ✅ **Notificações**: Sistema de aprovação para coordenadores
- ✅ **Cálculos Automáticos**: Rateio, área restante, status de campo
- ✅ **Timezone Brasília**: Datas e horários no fuso brasileiro

## 📋 Campos Extraídos

### Dados Principais
- Produtor, Fazenda, Talhão
- Cultura, Variedade
- Data, Operador

### Áreas e Aplicação
- Área Total, Área Aplicada, Área Restante
- Status do Campo (PARCIAL/FINALIZADO)

### Insumos (até 2)
- Lote1/Lote2
- Insumo1/Insumo2  
- Quantidade1/Quantidade2

## 🛠️ Configuração Rápida

### 1. Executar Setup Automático
```bash
python setup.py
```

### 2. Configuração Manual

#### Instalar Dependências
```bash
pip install -r requirements.txt
```

#### Configurar Variáveis de Ambiente
Copie `.env.example` para `.env` e configure:

```env
# OpenAI API Key
OPENAI_API_KEY=sk-your-key-here

# Banco de Dados Azure
DB_PASSWORD=your-password-here

# Z-API WhatsApp
ZAPI_TOKEN=your-token-here
ZAPI_INSTANCE=your-instance-here

# Coordenadores
COORDENADORES=5511999999999,5511888888888
```

## 📱 Formato de Mensagem

Envie mensagens WhatsApp no formato:

```
PRODUTOR: João Silva
FAZENDA: Fazenda Esperança
TALHAO: T123
CULTURA: MILHO
VARIEDADE: AG9045
AREA TOTAL: 50.5
AREA APLICADA: 10.5
LOTE1: 1508AB
INSUMO1: MIREX
QUANTIDADE1: 15,59
DATA: 15/01/2025
OPERADOR: Carlos Oliveira
```

## 🗄️ Estrutura do Banco

### PRE_APONTAMENTO_RAW
Dados brutos recebidos via webhook.

### BOLETIM_STAGING  
Dados estruturados após extração OpenAI.

### PREMIO_STAGING
Dados finais após aprovação do coordenador.

## 🔧 Arquitetura

```
WhatsApp → Z-API → Webhook → OpenAI → Pós-Proc → SQL Azure
                                ↓
                        Notificação Coordenador
```

## 🧪 Testes

### Teste Completo do Sistema
```bash
python teste_sistema_completo.py
```

### Teste Específico de Insumos
```bash
python teste_insumos.py
```

## 📊 Logs e Debug

O sistema gera logs detalhados com marcadores:
- `[INIT]` - Inicialização
- `[DETECT]` - Detecção de mensagens
- `[OPENAI]` - Extração OpenAI
- `[POS-PROC]` - Pós-processamento
- `[SQL]` - Operações de banco
- `[ZAPI]` - Notificações WhatsApp

## 🚀 Deploy

### Railway (Recomendado)
1. Conecte o repositório ao Railway
2. Configure as variáveis de ambiente
3. Deploy automático

### Heroku
```bash
git push heroku main
```

### Configuração de Variáveis
Todas as configurações são via variáveis de ambiente - sem hardcode de credenciais.

## 🔒 Segurança

- ✅ Credenciais em variáveis de ambiente
- ✅ Arquivo `.env` no `.gitignore`
- ✅ Conexões SSL/TLS
- ✅ Validação de entrada

## 🤝 Suporte

Para problemas ou dúvidas:
1. Verifique os logs de debug
2. Execute `python teste_sistema_completo.py`
3. Confirme configuração das variáveis de ambiente

## 📈 Status do Projeto

- ✅ **Sistema Base**: 100% funcional
- ✅ **Extração OpenAI**: Implementado com fallback
- ✅ **Pós-Processamento**: Garantia de 100% extração
- ✅ **Integração WhatsApp**: Funcionando
- ✅ **Banco SQL**: Três tabelas operacionais
- ✅ **Deploy**: Railway compatível

## 🏗️ Arquivos Principais

- `bot_final.py` - Webhook principal e roteamento
- `pre_apontamento.py` - Core do sistema (1700+ linhas)
- `setup.py` - Script de configuração automática
- `teste_sistema_completo.py` - Simulação completa
- `requirements.txt` - Dependências Python
- `.env.example` - Template de configuração
