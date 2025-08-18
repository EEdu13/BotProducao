#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de configuração inicial para o Bot de Pré-Apontamento WhatsApp
Este script ajuda a configurar as credenciais e testar o sistema
"""

import os
import shutil

def criar_arquivo_env():
    """Cria arquivo .env baseado no .env.example"""
    print("🔧 CONFIGURAÇÃO INICIAL DO BOT DE PRÉ-APONTAMENTO")
    print("=" * 50)
    
    # Verificar se .env já existe
    if os.path.exists('.env'):
        resposta = input("📁 Arquivo .env já existe. Deseja sobrescrever? (s/n): ")
        if resposta.lower() != 's':
            print("❌ Configuração cancelada.")
            return False
    
    # Copiar do exemplo
    if os.path.exists('.env.example'):
        shutil.copy('.env.example', '.env')
        print("✅ Arquivo .env criado a partir do exemplo")
    else:
        print("❌ Arquivo .env.example não encontrado!")
        return False
    
    print("\n📝 Configure as seguintes variáveis no arquivo .env:")
    print("   1. OPENAI_API_KEY - Sua chave da API OpenAI")
    print("   2. DB_PASSWORD - Senha do banco de dados Azure")
    print("   3. ZAPI_TOKEN - Token da Z-API WhatsApp")
    print("   4. ZAPI_INSTANCE - Instância da Z-API WhatsApp")
    print("   5. COORDENADORES - Números dos coordenadores")
    
    print(f"\n📂 Edite o arquivo: {os.path.abspath('.env')}")
    print("⚠️  IMPORTANTE: Não compartilhe este arquivo (.env) no Git!")
    
    return True

def instalar_dependencias():
    """Instala as dependências Python"""
    print("\n📦 INSTALAÇÃO DE DEPENDÊNCIAS")
    print("=" * 30)
    
    import subprocess
    import sys
    
    try:
        print("🔄 Instalando dependências...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Dependências instaladas com sucesso!")
            return True
        else:
            print(f"❌ Erro na instalação: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Erro ao instalar dependências: {e}")
        return False

def testar_configuracao():
    """Testa se as configurações estão funcionando"""
    print("\n🧪 TESTE DE CONFIGURAÇÃO")
    print("=" * 25)
    
    try:
        # Carregar .env
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("✅ Arquivo .env carregado")
        except ImportError:
            print("⚠️  python-dotenv não encontrado")
        
        # Verificar OpenAI
        openai_key = os.environ.get('OPENAI_API_KEY')
        if openai_key and openai_key != 'your_openai_api_key_here':
            print("✅ OPENAI_API_KEY configurada")
        else:
            print("❌ OPENAI_API_KEY não configurada ou usando valor padrão")
        
        # Verificar banco
        db_password = os.environ.get('DB_PASSWORD')
        if db_password and db_password != 'your_database_password_here':
            print("✅ DB_PASSWORD configurada")
        else:
            print("❌ DB_PASSWORD não configurada ou usando valor padrão")
        
        # Verificar Z-API
        zapi_token = os.environ.get('ZAPI_TOKEN')
        if zapi_token and zapi_token != 'your_zapi_token_here':
            print("✅ ZAPI_TOKEN configurada")
        else:
            print("❌ ZAPI_TOKEN não configurada ou usando valor padrão")
        
        print("\n📋 RESUMO DA CONFIGURAÇÃO:")
        print(f"   🔑 OpenAI: {'✅' if openai_key and openai_key != 'your_openai_api_key_here' else '❌'}")
        print(f"   🗄️  Banco: {'✅' if db_password and db_password != 'your_database_password_here' else '❌'}")
        print(f"   📱 Z-API: {'✅' if zapi_token and zapi_token != 'your_zapi_token_here' else '❌'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        return False

def executar_teste_sistema():
    """Executa teste completo do sistema"""
    print("\n🚀 TESTE DO SISTEMA COMPLETO")
    print("=" * 30)
    
    try:
        import subprocess
        import sys
        
        print("🔄 Executando teste simulado...")
        result = subprocess.run([
            sys.executable, "teste_sistema_completo.py"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Teste do sistema executado com sucesso!")
            print("\n📊 SAÍDA DO TESTE:")
            print("-" * 20)
            print(result.stdout)
            return True
        else:
            print(f"❌ Erro no teste: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao executar teste: {e}")
        return False

def main():
    """Função principal do script de configuração"""
    print("🤖 BOT DE PRÉ-APONTAMENTO WHATSAPP")
    print("   Sistema inteligente com OpenAI + SQL Server")
    print("=" * 50)
    
    # Verificar se estamos no diretório correto
    arquivos_necessarios = ['pre_apontamento.py', 'bot_final.py', 'requirements.txt']
    for arquivo in arquivos_necessarios:
        if not os.path.exists(arquivo):
            print(f"❌ Arquivo {arquivo} não encontrado!")
            print("   Execute este script no diretório do projeto.")
            return
    
    print("✅ Arquivos do projeto encontrados")
    
    # Menu de opções
    while True:
        print("\n📋 OPÇÕES DE CONFIGURAÇÃO:")
        print("   1. 📁 Criar arquivo .env")
        print("   2. 📦 Instalar dependências")
        print("   3. 🧪 Testar configuração")
        print("   4. 🚀 Executar teste do sistema")
        print("   5. 🔄 Executar tudo")
        print("   0. ❌ Sair")
        
        opcao = input("\n🔢 Escolha uma opção (0-5): ").strip()
        
        if opcao == '1':
            criar_arquivo_env()
        elif opcao == '2':
            instalar_dependencias()
        elif opcao == '3':
            testar_configuracao()
        elif opcao == '4':
            executar_teste_sistema()
        elif opcao == '5':
            print("\n🔄 EXECUTANDO CONFIGURAÇÃO COMPLETA...")
            sucesso = True
            sucesso &= criar_arquivo_env()
            sucesso &= instalar_dependencias()
            sucesso &= testar_configuracao()
            sucesso &= executar_teste_sistema()
            
            if sucesso:
                print("\n🎉 CONFIGURAÇÃO COMPLETA!")
                print("   ✅ Sistema pronto para uso")
                print("   📝 Lembre-se de configurar as credenciais no .env")
            else:
                print("\n⚠️  Configuração concluída com alguns erros")
                print("   📝 Verifique as mensagens acima e configure manualmente")
        elif opcao == '0':
            print("\n👋 Configuração finalizada!")
            break
        else:
            print("❌ Opção inválida!")

if __name__ == "__main__":
    main()
