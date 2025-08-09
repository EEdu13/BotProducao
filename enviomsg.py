# enviomsg.py  — worker de captura de FRETE via TEXTO e ÁUDIO (Z-API)
import os
import re
import time
import pyodbc
import requests
from datetime import datetime
import librosa
import soundfile as sf
import speech_recognition as sr

# =================== CONFIG (mesmas env vars do bot_final.py) ===================
INSTANCE_ID   = os.environ.get('INSTANCE_ID')
TOKEN         = os.environ.get('TOKEN')
CLIENT_TOKEN  = os.environ.get('CLIENT_TOKEN')

DB_SERVER     = os.environ.get('DB_SERVER', 'alrflorestal.database.windows.net')
DB_DATABASE   = os.environ.get('DB_DATABASE', 'Tabela_teste')
DB_USERNAME   = os.environ.get('DB_USERNAME', 'sqladmin')
DB_PASSWORD   = os.environ.get('DB_PASSWORD')

POLL_INTERVAL_SECONDS = int(os.environ.get('POLL_INTERVAL_SECONDS', '8'))
MESSAGES_PER_CHAT     = int(os.environ.get('MESSAGES_PER_CHAT', '10'))

ZAPI_BASE = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}"
HEADERS   = {"Client-Token": CLIENT_TOKEN, "Content-Type": "application/json"}

# =================== DB ===================
def conectar_db():
    drivers = [
        '{ODBC Driver 18 for SQL Server}',
        '{ODBC Driver 17 for SQL Server}',
        '{ODBC Driver 13 for SQL Server}',
        '{FreeTDS}'
    ]
    base = (
        f"SERVER={DB_SERVER};DATABASE={DB_DATABASE};UID={DB_USERNAME};"
        f"PWD={DB_PASSWORD};TrustServerCertificate=yes;"
    )
    for d in drivers:
        try:
            conn = pyodbc.connect(f"DRIVER={d};{base}", timeout=30)
            print(f"[SQL] Conectado com driver {d}")
            return conn
        except Exception as e:
            print(f"[SQL] Falha driver {d}: {str(e)[:140]}")
    raise RuntimeError("Nenhum driver ODBC funcionou.")

def ensure_tables():
    """Garante FRETES_TEMP (igual à que você criou) e FRETES_STATE (estado de leitura)."""
    conn = conectar_db()
    cur = conn.cursor()

    # FRETES_TEMP (idempotente; só cria se não existir)
    cur.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'FRETES_TEMP' AND type = 'U')
    BEGIN
        CREATE TABLE dbo.FRETES_TEMP (
            ID         INT IDENTITY(1,1) PRIMARY KEY,
            TIPO       VARCHAR(50)   NOT NULL,
            PROJETO    VARCHAR(50)   NULL,
            SAIDA      VARCHAR(255)  NOT NULL,
            DESTINO    VARCHAR(255)  NOT NULL,
            KM_INICIAL BIGINT        NOT NULL,
            PHONE      VARCHAR(32)   NULL,
            MESSAGE_ID VARCHAR(128)  NULL,
            RAW_TEXT   NVARCHAR(2000) NULL,
            CREATED_AT DATETIME      NOT NULL DEFAULT GETDATE()
        );
        CREATE INDEX IX_FRETES_MESSAGE ON dbo.FRETES_TEMP(MESSAGE_ID);
    END
    """)

    # FRETES_STATE (controla último message_id por phone)
    cur.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = 'FRETES_STATE' AND type = 'U')
    BEGIN
        CREATE TABLE dbo.FRETES_STATE (
            PHONE           VARCHAR(32) PRIMARY KEY,
            LAST_MESSAGE_ID VARCHAR(128) NULL,
            UPDATED_AT      DATETIME NOT NULL DEFAULT GETDATE()
        );
    END
    """)

    conn.commit()
    conn.close()

def get_last_message_id(phone):
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("SELECT LAST_MESSAGE_ID FROM dbo.FRETES_STATE WHERE PHONE = ?", phone)
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_last_message_id(phone, message_id):
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("""
        MERGE dbo.FRETES_STATE AS T
        USING (SELECT ? AS PHONE, ? AS LAST_MESSAGE_ID) AS S
        ON (T.PHONE = S.PHONE)
        WHEN MATCHED THEN UPDATE SET LAST_MESSAGE_ID = S.LAST_MESSAGE_ID, UPDATED_AT = GETDATE()
        WHEN NOT MATCHED THEN INSERT (PHONE, LAST_MESSAGE_ID) VALUES (S.PHONE, S.LAST_MESSAGE_ID);
    """, (phone, message_id))
    conn.commit()
    conn.close()

# =================== Z-API ===================
def z_get_chats(page=1, page_size=200):
    url = f"{ZAPI_BASE}/chats?page={page}&pageSize={page_size}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"[Z-API] Erro chats: {r.status_code} {r.text[:200]}")
        return []
    data = r.json()
    return data if isinstance(data, list) else []

def z_get_chat_messages(phone, amount=10, last_message_id=None):
    url = f"{ZAPI_BASE}/chat-messages/{phone}?amount={amount}"
    if last_message_id:
        url += f"&lastMessageId={last_message_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"[Z-API] Erro msgs({phone}): {r.status_code} {r.text[:200]}")
        return []
    data = r.json()
    return data if isinstance(data, list) else []

def z_send_text(phone, text):
    url = f"{ZAPI_BASE}/send-text"
    payload = {"phone": phone, "message": text}
    r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    return r.status_code == 200

# =================== ÁUDIO (download, conversão, STT) ===================
def baixar_e_converter_audio(url_audio):
    """Baixa áudio da Z-API e converte para WAV (16k) com librosa."""
    try:
        resp = requests.get(url_audio, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"[AUDIO] Falha download: {resp.status_code}")
            return None
        ts = int(time.time() * 1000)
        ogg_path = f"/tmp/frete_{ts}.ogg"
        wav_path = f"/tmp/frete_{ts}.wav"
        with open(ogg_path, "wb") as f:
            f.write(resp.content)
        # converte
        audio_data, sample_rate = librosa.load(ogg_path, sr=16000)
        sf.write(wav_path, audio_data, sample_rate)
        try:
            os.remove(ogg_path)
        except:
            pass
        return wav_path
    except Exception as e:
        print(f"[AUDIO] Erro conversão: {e}")
        return None

def transcrever_audio(caminho_wav):
    """Transcreve com Google Speech Recognition (pt-BR)."""
    try:
        r = sr.Recognizer()
        with sr.AudioFile(caminho_wav) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.record(source)
        texto = r.recognize_google(audio, language="pt-BR")
        return texto.strip()
    except Exception as e:
        print(f"[AUDIO] Erro STT: {e}")
        return None
    finally:
        try:
            if os.path.exists(caminho_wav):
                os.remove(caminho_wav)
        except:
            pass

# =================== Parser de FRETE (texto/voz) ===================
RE_FRETE = re.compile(
    r"\bfrete\b(?:\s*(?P<projeto>\d{2,6}))?.*?"
    r"(?:\bda\b|\bdo\b|\bdas\b|\bdos\b|\bde\b)\s+(?P<origem>[^,.;\n]+?)\s+"
    r"(?:\bpara\b|\bpra\b|\b->\b)\s+(?P<destino>[^,.;\n]+?)"
    r".*?(?:\bkm\b|\bkm\s*inicial\b|\bquilometragem\b|\bkm\s*é\b|\bkilometro\b).*?(?P<km>\d{1,7})",
    flags=re.IGNORECASE | re.UNICODE
)

RE_FRETE_FLEX = re.compile(
    r"\bfrete\b(?:\s*(?P<projeto>\d{2,6}))?.*?"
    r"(?:\bda\b|\bdo\b|\bdas\b|\bdos\b|\bde\b)\s+(?P<origem>[^,.;\n]+?)\s+"
    r"(?:\bpara\b|\bpra\b|\b->\b)\s+(?P<destino>[^,.;\n]+?)"
    r".*?(?P<km>\d{4,7})\b",
    flags=re.IGNORECASE | re.UNICODE
)

def normalize_place(s: str) -> str:
    s = " ".join(s.strip().split())
    return " ".join(p.capitalize() for p in s.split(" "))

def parse_frete(text):
    if not text:
        return None
    t = " ".join(text.split())
    m = RE_FRETE.search(t) or RE_FRETE_FLEX.search(t)
    if not m:
        return None
    projeto = m.group("projeto") if m.group("projeto") else None
    origem  = normalize_place(m.group("origem"))
    destino = normalize_place(m.group("destino"))
    km      = int(m.group("km"))
    return {
        "TIPO": "FRETE",
        "PROJETO": projeto,
        "SAIDA": origem,
        "DESTINO": destino,
        "KM_INICIAL": km
    }

# =================== Persistência ===================
def salvar_frete(reg, phone, message_id, raw_text):
    conn = conectar_db()
    cur = conn.cursor()
    # evita duplicar pelo MESSAGE_ID
    cur.execute("""
        IF NOT EXISTS (SELECT 1 FROM dbo.FRETES_TEMP WHERE MESSAGE_ID = ?)
        INSERT INTO dbo.FRETES_TEMP
            (TIPO, PROJETO, SAIDA, DESTINO, KM_INICIAL, PHONE, MESSAGE_ID, RAW_TEXT)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_id,
        reg["TIPO"], reg["PROJETO"], reg["SAIDA"], reg["DESTINO"], reg["KM_INICIAL"],
        phone, message_id, raw_text
    ))
    conn.commit()
    conn.close()

# =================== Loop principal ===================
def processar():
    ensure_tables()
    print("🚚 enviomsg.py (texto+áudio) rodando…")
    while True:
        try:
            chats = z_get_chats(page=1, page_size=200)
            for ch in chats:
                phone = str(ch.get("phone") or "").strip()
                if not phone.isdigit():
                    continue

                last_id = get_last_message_id(phone)
                msgs = z_get_chat_messages(phone, amount=MESSAGES_PER_CHAT, last_message_id=last_id)

                # ordena por timestamp crescente (se houver)
                def keymsg(m):
                    ts = m.get("timestamp")
                    return int(ts) if isinstance(ts, (int, float)) else 0
                msgs = sorted(msgs, key=keymsg)

                new_last_id = last_id
                for msg in msgs:
                    mid = msg.get("id")
                    if msg.get("fromMe") is True:
                        new_last_id = mid or new_last_id
                        continue

                    texto_original = ""
                    # 1) Texto puro
                    if isinstance(msg.get("text"), dict):
                        texto_original = (msg["text"].get("message") or "").strip()
                    elif isinstance(msg.get("text"), str):
                        texto_original = msg["text"].strip()

                    # 2) Áudio? Estrutura comum: msg["audio"]["audioUrl"]
                    audio_url = None
                    if isinstance(msg.get("audio"), dict):
                        audio_url = msg["audio"].get("audioUrl")

                    # alguns provedores usam "media"/"audioMessage"; tentamos cobrir:
                    if not audio_url and isinstance(msg.get("media"), dict):
                        if msg["media"].get("type") == "audio":
                            audio_url = msg["media"].get("url")

                    # Processar TEXTO
                    if texto_original:
                        parsed = parse_frete(texto_original)
                        if parsed:
                            salvar_frete(parsed, phone, mid, texto_original)
                            z_send_text(phone,
                                "✅ Frete registrado (TEXTO):\n"
                                f"• Projeto: {parsed['PROJETO'] or '-'}\n"
                                f"• Saída: {parsed['SAIDA']}\n"
                                f"• Destino: {parsed['DESTINO']}\n"
                                f"• KM inicial: {parsed['KM_INICIAL']}"
                            )
                            print(f"[OK] FRETE/TEXTO salvo {phone} | {parsed}")

                    # Processar ÁUDIO
                    if audio_url:
                        wav = baixar_e_converter_audio(audio_url)
                        if wav:
                            transcrito = transcrever_audio(wav)
                            if transcrito:
                                parsed = parse_frete(transcrito)
                                if parsed:
                                    salvar_frete(parsed, phone, mid, transcrito)
                                    z_send_text(phone,
                                        "✅ Frete registrado (ÁUDIO):\n"
                                        f"• Texto: \"{transcrito}\"\n"
                                        f"• Projeto: {parsed['PROJETO'] or '-'}\n"
                                        f"• Saída: {parsed['SAIDA']}\n"
                                        f"• Destino: {parsed['DESTINO']}\n"
                                        f"• KM inicial: {parsed['KM_INICIAL']}"
                                    )
                                    print(f"[OK] FRETE/AUDIO salvo {phone} | {parsed}")
                                else:
                                    z_send_text(phone, f"🎤 Ouvi: \"{transcrito}\" \n❌ Não identifiquei um frete válido.")
                            else:
                                z_send_text(phone, "❌ Não consegui transcrever seu áudio. Tente falar novamente, citando origem, destino e KM.")

                    new_last_id = mid or new_last_id

                if new_last_id and new_last_id != last_id:
                    set_last_message_id(phone, new_last_id)

        except Exception as e:
            print(f"[LOOP] Erro: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    missing = [k for k, v in {
        "INSTANCE_ID": INSTANCE_ID, "TOKEN": TOKEN, "CLIENT_TOKEN": CLIENT_TOKEN,
        "DB_PASSWORD": DB_PASSWORD
    }.items() if not v]
    if missing:
        raise SystemExit(f"Variáveis ausentes: {', '.join(missing)}")
    processar()
