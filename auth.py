import pyotp, os
from cryptography.exceptions import InvalidTag
from crypto import derivar_chave, cifrar_aes_gcm, decifrar_aes_gcm
from storage import carregar_usuarios, salvar_usuarios

def cadastrar(username, senha):
    usuarios = carregar_usuarios()
    if username in usuarios:
        raise ValueError("Usuário já existe.")

    salt = os.urandom(16)
    chave = derivar_chave(senha, salt)

    totp_secret = pyotp.random_base32()
    iv_totp, totp_cifrado = cifrar_aes_gcm(chave, totp_secret)

    chave_sessao = os.urandom(32)
    iv_sessao, chave_sessao_cifrada = cifrar_aes_gcm(chave, chave_sessao.hex())

    usuarios[username] = {
        "salt": salt.hex(),
        "iv_totp": iv_totp.hex(),
        "totp_cifrado": totp_cifrado.hex(),
        "iv_sessao": iv_sessao.hex(),
        "chave_sessao_cifrada": chave_sessao_cifrada.hex()
    }
    salvar_usuarios(usuarios)
    print(f"\nSeu segredo TOTP (configure no app autenticador): {totp_secret}\n")


def login(username, senha, codigo_totp):
    usuarios = carregar_usuarios()

    if username not in usuarios:
        return None, None

    dados = usuarios[username]

    try:
        chave = derivar_chave(senha, bytes.fromhex(dados["salt"]))
        totp_secret = decifrar_aes_gcm(
            chave,
            bytes.fromhex(dados["iv_totp"]),
            bytes.fromhex(dados["totp_cifrado"])
        )
    except (InvalidTag, KeyError, ValueError):
        return None, None

    if not pyotp.TOTP(totp_secret).verify(codigo_totp):
        return None, None

    try:
        chave_sessao_hex = decifrar_aes_gcm(
            chave,
            bytes.fromhex(dados["iv_sessao"]),
            bytes.fromhex(dados["chave_sessao_cifrada"])
        )
        chave_sessao = bytes.fromhex(chave_sessao_hex)
    except (InvalidTag, KeyError, ValueError):
        return None, None

    return chave_sessao, username
