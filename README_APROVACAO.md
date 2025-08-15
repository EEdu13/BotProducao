# 🔘 Sistema de Aprovação de Coordenadores

## 📋 Fluxo Completo de Aprovação

### 1. 📤 **Envio pelo Usuário**
- Usuário envia pré-apontamento via WhatsApp
- Sistema processa com OpenAI e salva no banco
- Status inicial: `PENDENTE`

### 2. 📞 **Notificação do Coordenador**
- Sistema busca coordenador do projeto na tabela `USUARIOS`
- Envia mensagem com botões de ação:
  - ✅ **APROVAR** - Libera o apontamento
  - ❌ **REJEITAR** - Recusa o apontamento  
  - 🔧 **CORRIGIR** - Solicita correções

### 3. 🎯 **Processamento da Resposta**
Coordenador clica em um dos botões:

#### ✅ **APROVAÇÃO**
- Status atualizado para `APROVADO`
- Dados movidos para tabelas definitivas
- Usuário notificado sobre aprovação
- Coordenador recebe confirmação

#### ❌ **REJEIÇÃO**
- Status atualizado para `REJEITADO`
- Motivo da rejeição registrado
- Usuário notificado sobre rejeição
- Dados mantidos para histórico

#### 🔧 **CORREÇÃO**
- Status atualizado para `CORRECAO_SOLICITADA`
- Solicitação de correção enviada ao usuário
- Usuário pode enviar novo apontamento

## 🔗 Endpoints do Sistema

### `/webhook_pre_apont` - Processamento Principal
- Recebe mensagens de usuários
- Processa pré-apontamentos
- Envia notificações para coordenadores
- **Também processa cliques em botões** (integrado)

### `/webhook_aprovacao` - Endpoint Dedicado (Opcional)
- Endpoint específico só para aprovações
- Pode ser usado como backup ou separação

## 📊 Estrutura do Banco de Dados

### Tabela `PRE_APONTAMENTO_RAW`
```sql
- ID (PK)
- TELEFONE
- PROJETO  
- STATUS ('PENDENTE', 'APROVADO', 'REJEITADO', 'CORRECAO_SOLICITADA')
- APROVADO_POR
- DATA_APROVACAO
- OBSERVACOES_APROVACAO
```

### Permissões de Coordenador
```sql
SELECT * FROM USUARIOS 
WHERE PERFIL = 'COORDENADOR' AND PROJETO = ?
```

## 🎯 Formatos de Button Response

O sistema suporta múltiplos formatos do Z-API:

### 1. ButtonResponse
```json
{
  "type": "ButtonResponse",
  "buttonResponse": {
    "id": "aprovar_48",
    "title": "✅ APROVAR"
  }
}
```

### 2. InteractiveResponse  
```json
{
  "type": "InteractiveResponse",
  "interactiveResponse": {
    "buttonReply": {
      "id": "rejeitar_48", 
      "title": "❌ REJEITAR"
    }
  }
}
```

### 3. SelectedButton (Alternativo)
```json
{
  "selectedButtonId": "corrigir_48",
  "selectedButtonTitle": "🔧 SOLICITAR CORREÇÃO"
}
```

## 🔄 Estados do Pré-Apontamento

```
USUÁRIO ENVIA
     ↓
  PENDENTE ←─────────┐
     ↓              │
COORDENADOR AVALIA   │
     ↓              │
┌─ APROVADO         │
├─ REJEITADO        │
└─ CORRECAO_SOLICITADA
     ↓              │
 USUÁRIO CORRIGE ───┘
```

## 🚀 Próximas Funcionalidades

1. **🔄 Reenvio Automático** - Coordenador não responde em X horas
2. **📊 Dashboard** - Visualização de aprovações pendentes  
3. **👥 Múltiplos Coordenadores** - Escalonamento por hierarquia
4. **📱 Notificações Push** - Alertas em tempo real
5. **📈 Analytics** - Métricas de aprovação

## 🛠️ Configuração Z-API

Para funcionar, configure no Railway:
- `INSTANCE_ID` - ID da instância Z-API
- `TOKEN` - Token da instância  
- `CLIENT_TOKEN` - Token de cliente

## 🔍 Debug e Logs

Todos os logs são prefixados para fácil identificação:
- `[APRV]` - Sistema de aprovação
- `[NOTIF]` - Notificações
- `[ZAPI]` - Envios Z-API
- `[PRE-BOT]` - Webhook principal

## ✅ Sistema Testado e Funcional

- ✅ Processamento de pré-apontamentos
- ✅ Notificações com botões
- ✅ Detecção de cliques em botões
- ✅ Fluxo completo de aprovação
- ✅ Notificações de confirmação
- ✅ Logs detalhados para debug
