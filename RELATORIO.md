# Relatório de Estudos — Mini Blockchain

Material de apoio para apresentação. Cobre arquitetura, conceitos criptográficos, fluxos e decisões de projeto.

---

## 1. Visão geral

Sistema de "blockchain de bolso" em Python que demonstra três pilares de segurança aplicada:

- **Confidencialidade** — só o dono lê o conteúdo do bloco.
- **Integridade** — adulteração de qualquer bloco é detectada.
- **Autenticação forte** — login exige senha **e** segundo fator (TOTP).

Cada usuário pode adicionar blocos cifrados em uma cadeia compartilhada; ao ler, vê seus próprios em claro e os dos outros como "[bloco de outro usuário — cifrado]".

---

## 2. Arquitetura

```
Mini_Blockchain/
├── main.py         # menu de texto e fluxo principal
├── auth.py         # cadastro, login e 2FA
├── crypto.py       # primitivas: PBKDF2, AES-GCM
├── blockchain.py   # blocos, encadeamento, validação
├── storage.py      # leitura/escrita de JSON
└── data/
    ├── users.json  # cadastro (salt, IVs, TOTP cifrado, chave de sessão cifrada)
    └── chain.json  # blocos da cadeia
```

**Dependências de módulo:**

```
crypto.py   (base — não depende de ninguém)
   ↑
auth.py ────┴──── blockchain.py
   ↑               ↑
storage.py ←──── main.py
```

---

## 3. Conceitos criptográficos

### 3.1 PBKDF2 — Password-Based Key Derivation Function

Transforma senha humana fraca em chave criptográfica de 32 bytes.

- **Algoritmo:** PBKDF2 com HMAC-SHA256.
- **Iterações:** 600.000 (recomendação OWASP 2023).
- **Salt:** 16 bytes aleatórios, único por usuário.

**Por que iterar muito?** Pra forçar lentidão em ataques de força bruta. Se um atacante roubar `users.json`, cada tentativa de senha custa ~600k operações de hash.

**Por que salt?** Sem salt, dois usuários com senha igual gerariam a mesma chave; e atacantes pré-computariam tabelas de hash (rainbow tables). Salt aleatório por usuário neutraliza isso.

**No código:** `crypto.py → derivar_chave()`.

---

### 3.2 AES-GCM — Cifragem autenticada

Algoritmo simétrico que cifra **e** autentica em uma operação só.

- **AES** = bloco simétrico de 128 bits, chave de 256 bits no projeto.
- **GCM** = modo de operação que adiciona **tag de autenticação** (16 bytes).

**Saídas de `cifrar_aes_gcm`:** `(IV, ciphertext)` — a tag fica embutida nos últimos 16 bytes do `ciphertext`.

**Detecção de adulteração:** se um bit do ciphertext (ou do IV) for alterado, `decrypt` lança `InvalidTag` automaticamente. O sistema não distingue "chave errada" de "ciphertext mexido" — ambos dão `InvalidTag` (e tem que ser assim, por segurança).

**No código:** `crypto.py → cifrar_aes_gcm()`, `decifrar_aes_gcm()`.

---

### 3.3 IV — Initialization Vector

Valor aleatório de 12 bytes gerado a cada chamada de cifragem.

**Por que existe?** Sem IV, a mesma mensagem cifrada com a mesma chave produziria sempre o mesmo ciphertext. Isso vazaria informação (atacante saberia quando duas mensagens são iguais sem decifrá-las).

**Regras críticas:**
- Aleatório (`os.urandom(12)`).
- **Único por (chave, mensagem)** — nunca reutilizar com a mesma chave.
- **Pode ser público.** É salvo em claro junto com o ciphertext.
- Tamanho fixo (12 bytes para AES-GCM).

**No projeto há vários IVs:** um pro segredo TOTP (`iv_totp`), um pra chave de sessão (`iv_sessao`), e um por bloco da chain (`iv` em cada bloco).

---

### 3.4 SHA-256 — Hash criptográfico

Função que pega entrada de tamanho qualquer e devolve 32 bytes (64 caracteres hex).

**Propriedades usadas:**
- **Determinística** — mesma entrada → mesma saída sempre.
- **Sensível a 1 bit** — alterar um bit da entrada muda completamente a saída ("efeito avalanche").
- **Resistente a colisões** — inviável encontrar duas entradas com o mesmo hash.

**No código:** `blockchain.py → hash_bloco()` calcula SHA-256 dos campos públicos do bloco para amarrar a cadeia.

---

### 3.5 Encadeamento por hash

Cada bloco guarda o hash do bloco anterior em `hash_prev`. Isso forma a cadeia.

```
[B0] ──hash(B0)──→ [B1] ──hash(B1)──→ [B2] ──hash(B2)──→ [B3]
hash_prev:         hash_prev:          hash_prev:         hash_prev:
"000...000"        hash(B0)            hash(B1)           hash(B2)
```

**Garantia de integridade:** alterar qualquer bloco muda seu hash → invalida o `hash_prev` do bloco seguinte → `validar_chain` detecta e retorna o índice do bloco corrompido.

**Bloco gênese (B0):** primeiro da cadeia, recebe `hash_prev = "0" * 64` (convenção herdada do Bitcoin).

**No código:** `blockchain.py → hash_bloco()`, `validar_chain()`.

---

### 3.6 TOTP — Time-based One-Time Password

Segundo fator de autenticação. Gera código de 6 dígitos a partir de:

```
SEGREDO (32 chars, fixo) + HORA ATUAL (janelas de 30s) → CÓDIGO (6 dígitos)
```

**No cadastro:** `pyotp.random_base32()` gera o segredo, exibido **uma vez** ao usuário (que adiciona no Google Authenticator). O segredo é cifrado com a chave derivada da senha e salvo.

**No login:** o segredo é decifrado, e `pyotp.TOTP(secret).verify(codigo)` confirma se o código de 6 dígitos digitado bate com o esperado para a hora atual.

**Por que é seguro?**
- Senha vazada não basta — precisa também do segredo TOTP no celular.
- Código vazado também não basta — vira lixo em 30s.
- Funciona offline (só precisa do relógio).

---

### 3.7 Key Wrapping — Envelopamento de chave

Técnica para tornar a chave de sessão **persistente entre sessões** sem armazená-la em claro.

**Sem key wrapping (versão inicial do projeto):**
```
login → chave_sessao = os.urandom(32)   ← nova a cada login
```
Resultado: blocos antigos ficam ilegíveis após logout (chave perdida).

**Com key wrapping (versão final):**
```
cadastro:
  chave_mestre = derivar_chave(senha, salt)   ← reproduzível
  chave_sessao = os.urandom(32)               ← gerada UMA vez
  chave_sessao_cifrada = cifrar(chave_mestre, chave_sessao)
  salva chave_sessao_cifrada no users.json

login:
  chave_mestre = derivar_chave(senha, salt)
  chave_sessao = decifrar(chave_mestre, chave_sessao_cifrada)
  ← sempre a mesma chave_sessao!
```

**Por que duas chaves?**
- A **chave mestre** (derivada da senha) precisa ser **reproduzível** — sai de senha + salt.
- A **chave de sessão** precisa ser **forte** (32 bytes verdadeiramente aleatórios) e **fácil de trocar** se necessário.
- Trocar a senha re-cifra só a chave de sessão, não todos os blocos.

---

## 4. Módulos em detalhe

### 4.1 `crypto.py`

| Função | Entrada | Saída | Papel |
|---|---|---|---|
| `derivar_chave(senha, salt)` | str + bytes | bytes (32) | PBKDF2 600k iterações |
| `cifrar_aes_gcm(chave, dados)` | bytes + str | (iv, ciphertext) | AES-GCM com IV aleatório |
| `decifrar_aes_gcm(chave, iv, ct)` | bytes + bytes + bytes | str | inverso, lança `InvalidTag` se adulterado |

### 4.2 `storage.py`

I/O simples sobre dois arquivos JSON. Sem criptografia. Funções: `carregar_usuarios`, `salvar_usuarios`, `carregar_chain`, `salvar_chain`.

### 4.3 `auth.py`

**`cadastrar(username, senha)`** — produz no `users.json`:

```json
{
  "username": {
    "salt": "...",                    # 16 bytes hex
    "iv_totp": "...",                 # IV do segredo TOTP
    "totp_cifrado": "...",            # TOTP cifrado com chave mestre
    "iv_sessao": "...",               # IV da chave de sessão
    "chave_sessao_cifrada": "..."     # chave de sessão cifrada com chave mestre
  }
}
```

**`login(username, senha, codigo_totp)`** — retorna `(chave_sessao, username)` ou `(None, None)`:

1. Carrega registro do usuário (se não existe → erro genérico).
2. Deriva `chave_mestre = derivar_chave(senha, salt)`.
3. Decifra `totp_secret` com a chave mestre. Falha → senha errada → erro genérico.
4. Verifica `pyotp.TOTP(totp_secret).verify(codigo_totp)`. Falha → erro genérico.
5. Decifra `chave_sessao` com a chave mestre.
6. Retorna a chave de sessão (mesma a cada login).

**Erro genérico:** todas as falhas retornam a mesma mensagem ("Usuário ou senha inválidos") para evitar **enumeração de usuários**.

### 4.4 `blockchain.py`

**`hash_bloco(bloco)`** — `json.dumps(campos_públicos, sort_keys=True) → SHA-256 → hex`. Ordenação alfabética garante hash determinístico.

**`criar_bloco(dados, owner, chave_sessao, chain)`** — monta dict com:
- `owner`, `timestamp`, `hash_prev`, `iv`, `ciphertext`.
- `hash_prev` = hash do último bloco (ou 64 zeros se gênese).
- Cifra os dados com a chave de sessão.

**`validar_chain(chain)`** — percorre i = 1..n, recalcula `hash_bloco(chain[i-1])` e compara com `chain[i]["hash_prev"]`. Retorna `(True, -1)` ou `(False, índice_corrompido)`.

### 4.5 `main.py`

Menu com 5 opções; mantém `chave_sessao` e `usuario_atual` em variáveis globais (RAM).

| Opção | Requer login? | Ação |
|---|---|---|
| 1. Cadastrar | não | `auth.cadastrar()` + salva users |
| 2. Login | não | `auth.login()` → guarda `chave_sessao` em RAM |
| 3. Adicionar bloco | sim | `criar_bloco()` + salva chain |
| 4. Ler blockchain | sim | `validar_chain()` + decifra blocos próprios; alheios mostra "[cifrado]" |
| 5. Sair | não | encerra |

Na leitura: `try/except InvalidTag` distingue bloco íntegro de bloco adulterado.

---

## 5. Fluxos completos

### 5.1 Cadastro

```
1. usuário digita username + senha
2. salt = os.urandom(16)
3. chave_mestre = PBKDF2(senha, salt, 600k)
4. totp_secret = random_base32()
5. iv_totp, totp_cif = AES-GCM(chave_mestre, totp_secret)
6. chave_sessao = os.urandom(32)
7. iv_sessao, chave_sessao_cif = AES-GCM(chave_mestre, chave_sessao.hex())
8. salva {salt, iv_totp, totp_cif, iv_sessao, chave_sessao_cif} em users.json
9. exibe totp_secret (uma vez) → usuário configura no app autenticador
```

### 5.2 Login

```
1. usuário digita username + senha + código TOTP
2. carrega registro do usuário
3. chave_mestre = PBKDF2(senha, salt, 600k)
4. totp_secret = AES-GCM-decrypt(chave_mestre, iv_totp, totp_cif)
   ↳ InvalidTag se senha errada → erro genérico
5. pyotp.TOTP(totp_secret).verify(codigo)
   ↳ False → erro genérico
6. chave_sessao = AES-GCM-decrypt(chave_mestre, iv_sessao, chave_sessao_cif)
7. retorna (chave_sessao, username) → main.py guarda em RAM
```

### 5.3 Adicionar bloco

```
1. dados = input do usuário
2. chain = carregar_chain()
3. hash_prev = hash_bloco(chain[-1]) ou "000...000"
4. iv, ciphertext = AES-GCM(chave_sessao, dados)
5. bloco = {owner, timestamp, hash_prev, iv, ciphertext}
6. chain.append(bloco) + salvar_chain(chain)
```

### 5.4 Ler blockchain

```
1. chain = carregar_chain()
2. valida, idx = validar_chain(chain)
3. para cada bloco i:
   - se bloco["owner"] == usuario_atual:
       try: dados = AES-GCM-decrypt(chave_sessao, iv, ct) → exibe
       except InvalidTag: "[ALERTA: bloco adulterado!]"
   - senão: "[bloco de outro usuário — cifrado]"
4. se !valida: "[ALERTA: cadeia corrompida no bloco {idx}]"
```

---

## 6. Propriedades de segurança garantidas

| Propriedade | Como é garantida |
|---|---|
| **Confidencialidade dos dados** | AES-GCM com chave de sessão de 32 bytes |
| **Integridade dos dados** | Tag GCM (lança InvalidTag em adulteração) |
| **Integridade da cadeia** | Encadeamento de hashes SHA-256 |
| **Autenticação 2FA** | Senha (PBKDF2) + TOTP (RFC 6238) |
| **Resistência a brute-force** | 600k iterações PBKDF2 + salt único |
| **Resistência a rainbow tables** | Salt aleatório por usuário |
| **Resistência a enumeração** | Mensagem de erro genérica em login |
| **Senha nunca em claro** | Só salt + TOTP cifrado no disco |
| **Chave de sessão nunca em claro** | Cifrada com chave mestre (key wrapping) |
| **Isolamento entre usuários** | Cada um tem sua chave; não decifra blocos alheios |

---

## 7. Limitações conhecidas

1. **Sem proof-of-work** — qualquer um com acesso ao `chain.json` pode reescrever a cadeia inteira (recalculando todos os hashes). Em uma blockchain real, isso é caro de propósito.
2. **Sem rede / consenso** — uma única máquina, um único arquivo. Sem distribuição.
3. **Sem rate limiting no login** — atacante pode tentar senhas indefinidamente (mas PBKDF2 já impõe custo).
4. **Sem rotação de chave** — trocar senha exigiria re-derivar a chave mestre e re-cifrar `chave_sessao_cif` e `totp_cif` (não implementado).
5. **TOTP sem janela de tolerância** — relógio dessincronizado (mais de 30s) faz login falhar.

---

## 8. Pontos para destacar na apresentação

1. **"Senha nunca toca o disco."** Só o salt fica em claro; o resto é derivado dele e da senha do usuário no momento do login.
2. **"Tag GCM = integridade automática."** Sem ela, precisaríamos de HMAC separado para cada bloco.
3. **"IV pode ser público, chave nunca."** Ponto que costuma confundir e diferencia muita gente.
4. **"Erro genérico = anti-enumeração."** Decisão consciente de UX em prol de segurança.
5. **"Key wrapping resolve o trade-off** entre derivar chave da senha (ruim porque trocar senha mataria os dados) e gerar chave aleatória (ruim porque some entre sessões)."
6. **"600k iterações = OWASP 2023."** Não é número arbitrário.

---

## 9. Glossário rápido

| Termo | Significado |
|---|---|
| **AEAD** | Authenticated Encryption with Associated Data |
| **GCM** | Galois/Counter Mode — modo AES com tag de autenticação |
| **IV** | Initialization Vector — valor aleatório por cifragem |
| **KDF** | Key Derivation Function — função que deriva chaves de senhas |
| **PBKDF2** | Password-Based KDF v2 — KDF padrão da indústria |
| **TOTP** | Time-based One-Time Password (RFC 6238) |
| **Salt** | Bytes aleatórios concatenados à senha antes do hash |
| **Tag** | 16 bytes de autenticação anexados ao ciphertext em GCM |
| **Key Wrapping** | Cifrar uma chave com outra para armazenamento seguro |
| **Hash chain** | Estrutura onde cada item carrega o hash do anterior |
| **Bloco gênese** | Primeiro bloco da cadeia; tem `hash_prev` zerado |
