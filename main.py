import os
from cryptography.exceptions import InvalidTag
from auth import cadastrar, login
from blockchain import criar_bloco, validar_chain
from storage import carregar_chain, salvar_chain
from crypto import decifrar_aes_gcm

chave_sessao = None
usuario_atual = None

def menu():
    logado = f" (logado: {usuario_atual})" if usuario_atual else ""
    print(f"\n=== Mini Blockchain{logado} ===")
    print("1. Cadastrar usuário")
    print("2. Login")
    print("3. Adicionar bloco")
    print("4. Ler blockchain")
    print("5. Sair")
    return input("Opção: ").strip()

def main():
    global chave_sessao, usuario_atual

    os.makedirs("data", exist_ok=True)

    while True:
        opcao = menu()

        if opcao == "1":
            username = input("Username: ").strip()
            senha = input("Senha: ").strip()
            try:
                cadastrar(username, senha)
                print("Cadastro realizado com sucesso!")
            except ValueError as e:
                print(f"Erro: {e}")

        elif opcao == "2":
            username = input("Username: ").strip()
            senha = input("Senha: ").strip()
            codigo_totp = input("Código TOTP: ").strip()
            resultado_chave, resultado_user = login(username, senha, codigo_totp)
            if resultado_chave is None:
                print("Usuário ou senha inválidos.")
            else:
                chave_sessao = resultado_chave
                usuario_atual = resultado_user
                print(f"Login realizado! Bem-vindo, {usuario_atual}.")

        elif opcao == "3":
            if chave_sessao is None:
                print("É necessário estar logado.")
                continue
            dados = input("Dados do bloco: ").strip()
            chain = carregar_chain()
            bloco = criar_bloco(dados, usuario_atual, chave_sessao, chain)
            chain.append(bloco)
            salvar_chain(chain)
            print("Bloco adicionado com sucesso!")

        elif opcao == "4":
            if chave_sessao is None:
                print("É necessário estar logado.")
                continue
            chain = carregar_chain()
            if not chain:
                print("Blockchain vazia.")
                continue
            valida, idx = validar_chain(chain)
            if not valida:
                print(f"\n[ALERTA: cadeia corrompida no bloco {idx}!]")
            for i, bloco in enumerate(chain):
                print(f"\n--- Bloco {i} ---")
                print(f"  Owner    : {bloco['owner']}")
                if bloco["owner"] == usuario_atual:
                    try:
                        iv = bytes.fromhex(bloco["iv"])
                        ct = bytes.fromhex(bloco["ciphertext"])
                        dados = decifrar_aes_gcm(chave_sessao, iv, ct)
                        print(f"  Dados    : {dados}")
                    except InvalidTag:
                        print("  [ALERTA: bloco adulterado!]")
                else:
                    print("  [bloco de outro usuário — cifrado]")

        elif opcao == "5":
            print("Saindo...")
            break

        else:
            print("Opção inválida.")

if __name__ == "__main__":
    main()
