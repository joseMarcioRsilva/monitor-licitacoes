#!/usr/bin/env python3
"""
pncp_monitor.py
PoC: consulta a API pública do PNCP, armazena IDs vistos em SQLite e notifica via Telegram.
Rode periodicamente (cron, GitHub Actions, VPS).
Config via env vars:
  PNCP_START_DATE, PNCP_END_DATE (YYYY-MM-DD)
  PNCP_PAGE_SIZE (default 50)
  TG_TOKEN, TG_CHAT (para alertas)
  DB_PATH (default pncp_seen.db)
"""
import os
import time
import requests
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE = os.getenv("PNCP_API_BASE", "https://pncp.gov.br/api/pncp/v1/consultas/licitacoes")
START_DATE = os.getenv("PNCP_START_DATE")  # ex: "2026-08-01"
END_DATE = os.getenv("PNCP_END_DATE")      # ex: "2026-08-05"
PAGE_SIZE = int(os.getenv("PNCP_PAGE_SIZE", "50"))
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
DB_PATH = os.getenv("DB_PATH", "pncp_seen.db")

def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        logging.info("Telegram não configurado (TG_TOKEN/TG_CHAT). Mensagem: %s", text)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT, "text": text}, timeout=10)
        r.raise_for_status()
        logging.info("Alerta enviado via Telegram.")
    except Exception as e:
        logging.error("Erro enviando Telegram: %s", e)

def fetch_page(start_date, end_date, page=0, size=50):
    params = {
        "dataPublicacaoInicio": start_date,
        "dataPublicacaoFim": end_date,
        "page": page,
        "size": size
    }
    logging.debug("GET %s %s", BASE, params)
    r = requests.get(BASE, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def run_once():
    if not (START_DATE and END_DATE):
        logging.error("Defina PNCP_START_DATE e PNCP_END_DATE no ambiente.")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, link TEXT, ts INTEGER)")
    page = 0
    while True:
        try:
            data = fetch_page(START_DATE, END_DATE, page=page, size=PAGE_SIZE)
        except Exception as e:
            logging.error("Erro ao consultar PNCP: %s", e)
            break
        content = data.get("content", [])
        total_pages = data.get("totalPages", None)
        logging.info("Página %d - %d itens", page, len(content))
        for item in content:
            # campos podem variar conforme API; adapt if needed
            item_id = item.get("id") or item.get("numeroEdital") or item.get("codigo") or item.get("link")
            title = item.get("titulo") or item.get("objeto") or item.get("descricao", "")[:300]
            link = item.get("link") or item.get("documento") or ""
            if not item_id:
                # fallback: combine título+data
                item_id = f"{title[:120]}-{item.get('dataPublicacao','')}"
            cur = conn.execute("SELECT 1 FROM seen WHERE id=?", (item_id,))
            if not cur.fetchone():
                text = f"Nova licitação: {title}\n{link}"
                logging.info("Encontrado novo item: %s", title)
                send_telegram(text)
                conn.execute("INSERT INTO seen(id,title,link,ts) VALUES(?,?,?,?)", (item_id, title, link, int(time.time())))
                conn.commit()
        # paginação: se totalPages disponível
        if total_pages is not None:
            if page + 1 >= total_pages:
                break
        else:
            # se não houver totalPages, tentar flag 'last' ou sair quando content vazio
            if not content:
                break
        page += 1
        time.sleep(0.2)
    conn.close()

if __name__ == "__main__":
    run_once()
