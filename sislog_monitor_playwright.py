#!/usr/bin/env python3
"""
sislog_monitor_playwright.py
PoC: tenta usar API endpoint (se fornecido via SISLOG_API_ENDPOINT), senão abre a página com Playwright e extrai linhas da tabela.
Config (env vars):
  SISLOG_URL (default https://sislog.go.gov.br/PanelAquisicao/ListarAquisicoes)
  SISLOG_API_ENDPOINT (opcional) - se conhecido, script usa requests direto
  ROW_SELECTOR (CSS selector para cada linha da lista, default 'table tbody tr')
  TITLE_SELECTOR (relativo à linha) ex: 'td:nth-child(2)'
  LINK_SELECTOR (relativo à linha) ex: 'td:nth-child(1) a'
  DB_PATH (default sislog_seen.db)
  TG_TOKEN, TG_CHAT (para alertas)
"""
import os
import time
import sqlite3
import logging
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SISLOG_URL = os.getenv("SISLOG_URL", "https://sislog.go.gov.br/PanelAquisicao/ListarAquisicoes")
API_ENDPOINT = os.getenv("SISLOG_API_ENDPOINT")  # optional
ROW_SELECTOR = os.getenv("ROW_SELECTOR", "table tbody tr")
TITLE_SELECTOR = os.getenv("TITLE_SELECTOR", "td:nth-child(2)")
LINK_SELECTOR = os.getenv("LINK_SELECTOR", "td:nth-child(1) a")
DB_PATH = os.getenv("DB_PATH", "sislog_seen.db")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        logging.info("Telegram não configurado. Mensagem: %s", text)
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT, "text": text}, timeout=10)
        logging.info("Alerta enviado via Telegram.")
    except Exception as e:
        logging.error("Erro enviando Telegram: %s", e)

def fetch_api_and_process(url):
    logging.info("Chamando endpoint SISLOG API: %s", url)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    # Aqui depende do formato da API; tente extrair itens em data['items'] ou data['content']
    items = data.get("content") or data.get("items") or data
    process_items(items)

def process_items(items):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, link TEXT, ts INTEGER)")
    for it in items:
        # adaptação: depende do formato; tente campos comuns
        item_id = it.get("id") or it.get("codigo") or it.get("numero") or it.get("link") or it.get("url")
        title = it.get("titulo") or it.get("objeto") or it.get("descricao", "")[:300]
        link = it.get("link") or it.get("url") or ""
        if not item_id:
            item_id = title[:200]
        cur = conn.execute("SELECT 1 FROM seen WHERE id=?", (item_id,))
        if not cur.fetchone():
            send_telegram(f"Nova aquisição (SISLOG): {title}\n{link}")
            conn.execute("INSERT INTO seen(id,title,link,ts) VALUES(?,?,?,?)", (item_id, title, link, int(time.time())))
            conn.commit()
    conn.close()

def scrape_with_playwright():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, link TEXT, ts INTEGER)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        logging.info("Abrindo %s", SISLOG_URL)
        page.goto(SISLOG_URL, timeout=60000)
        try:
            page.wait_for_selector(ROW_SELECTOR, timeout=20000)
        except PWTimeout:
            logging.warning("Seletor de linhas não encontrado. Verifique a página e seletores.")
            browser.close()
            conn.close()
            return
        rows = page.query_selector_all(ROW_SELECTOR)
        logging.info("Linhas encontradas: %d", len(rows))
        for r in rows:
            try:
                title_el = r.query_selector(TITLE_SELECTOR)
                link_el = r.query_selector(LINK_SELECTOR)
                title = title_el.inner_text().strip() if title_el else r.inner_text().strip()[:300]
                link = link_el.get_attribute("href") if link_el else ""
                item_id = link or title[:200]
                cur = conn.execute("SELECT 1 FROM seen WHERE id=?", (item_id,))
                if not cur.fetchone():
                    send_telegram(f"Nova aquisição (SISLOG): {title}\n{link}")
                    conn.execute("INSERT INTO seen(id,title,link,ts) VALUES(?,?,?,?)", (item_id, title, link, int(time.time())))
                    conn.commit()
            except Exception as e:
                logging.error("Erro processando linha: %s", e)
        browser.close()
    conn.close()

def main():
    if API_ENDPOINT:
        try:
            fetch_api_and_process(API_ENDPOINT)
            return
        except Exception as e:
            logging.error("Erro chamando API endpoint: %s — fallback para scraping", e)
    scrape_with_playwright()

if __name__ == "__main__":
    main()
