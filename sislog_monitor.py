#!/usr/bin/env python3
"""
sislog_monitor.py
Monitor de licitacoes do SISLOG-GO (Goias).

A pagina e renderizada inteiramente no servidor: e HTML estatico, sem API JSON e sem
paginacao (todas as licitacoes aparecem em uma unica tabela). Por isso este script usa
requests + BeautifulSoup e nao precisa mais de Playwright.

Seletores confirmados inspecionando a pagina real (agosto/2026):
  tabela: table.contracts-table
  linhas: table.contracts-table tbody tr
  colunas por linha: [0]=numero da linha, [1]=numero+link, [2]=Seq, [3]=Objeto,
                      [4]=Orgao, [5]=Publicacao, [6]=Modalidade, [7]=Status

Config via variaveis de ambiente:
  SISLOG_URL (default https://sislog.go.gov.br/PanelAquisicao/ListarAquisicoes)
  TG_TOKEN, TG_CHAT (alertas Telegram, opcional)
  DB_PATH (default data/sislog_seen.db)
  ESFERA (default "estadual")
  HTTP_RETRIES (default 3), HTTP_RETRY_BACKOFF (segundos, default 5)

O SISLOG (assim como varios sites de governo) pode responder com falhas
intermitentes quando acessado de IPs de nuvem (ex.: runners do GitHub Actions).
Por isso a busca tenta novamente algumas vezes antes de desistir.
"""
import os
import time
import sqlite3
import logging
import requests
from bs4 import BeautifulSoup

from common import montar_registro, salvar_jsonl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SISLOG_URL = os.getenv("SISLOG_URL", "https://sislog.go.gov.br/PanelAquisicao/ListarAquisicoes")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
DB_PATH = os.getenv("DB_PATH", "data/sislog_seen.db")
ESFERA = os.getenv("ESFERA", "estadual")
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
HTTP_RETRY_BACKOFF = float(os.getenv("HTTP_RETRY_BACKOFF", "5"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MonitorLicitacoesGO/1.0; +https://github.com/joseMarcioRsilva/monitor-licitacoes)"
}


def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        logging.info("Telegram nao configurado (TG_TOKEN/TG_CHAT). Mensagem: %s", text)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT, "text": text}, timeout=10)
        r.raise_for_status()
        logging.info("Alerta enviado via Telegram.")
    except Exception as e:
        logging.error("Erro enviando Telegram: %s", e)


def buscar_html_com_retry():
    ultimo_erro = None
    for tentativa in range(1, HTTP_RETRIES + 1):
        try:
            logging.info("Buscando licitacoes em %s (tentativa %d/%d)", SISLOG_URL, tentativa, HTTP_RETRIES)
            r = requests.get(SISLOG_URL, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            ultimo_erro = e
            logging.warning("Falha na tentativa %d/%d: %s", tentativa, HTTP_RETRIES, e)
            if tentativa < HTTP_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * tentativa)
    raise ultimo_erro


def buscar_licitacoes():
    html = buscar_html_com_retry()
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.select_one("table.contracts-table")
    if not tabela:
        logging.warning("Tabela 'table.contracts-table' nao encontrada. O layout da pagina pode ter mudado.")
        return []

    licitacoes = []
    linhas = tabela.select("tbody tr")
    for linha in linhas:
        colunas = linha.find_all("td")
        if len(colunas) < 8:
            continue
        link_el = colunas[1].find("a")
        numero_contratacao = link_el.get_text(strip=True) if link_el else colunas[1].get_text(strip=True)
        link = link_el.get("href") if link_el else ""
        if link and link.startswith("/"):
            link = "https://sislog.go.gov.br" + link
        objeto = colunas[3].get_text(strip=True)
        orgao = colunas[4].get_text(strip=True)
        publicacao = colunas[5].get_text(strip=True)
        modalidade = colunas[6].get_text(strip=True)
        status = colunas[7].get_text(strip=True)
        item_id = numero_contratacao or f"{objeto[:120]}-{publicacao}"
        licitacoes.append({
            "item_id": item_id,
            "numero_contratacao": numero_contratacao,
            "objeto": objeto,
            "orgao": orgao,
            "publicacao": publicacao,
            "modalidade": modalidade,
            "status": status,
            "link": link,
        })
    logging.info("Encontradas %d licitacoes na pagina.", len(licitacoes))
    return licitacoes


def run_once():
    pasta_db = os.path.dirname(DB_PATH)
    if pasta_db:
        os.makedirs(pasta_db, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, link TEXT, ts INTEGER)")
    licitacoes = buscar_licitacoes()
    for item in licitacoes:
        cur = conn.execute("SELECT 1 FROM seen WHERE id=?", (item["item_id"],))
        if not cur.fetchone():
            logging.info("Nova licitacao encontrada: %s", item["objeto"])
            registro = montar_registro(
                fonte="SISLOG-GO",
                esfera=ESFERA,
                numero_contratacao=item["numero_contratacao"],
                objeto=item["objeto"],
                orgao=item["orgao"],
                modalidade=item["modalidade"],
                status=item["status"],
                data_publicacao=item["publicacao"],
                link=item["link"],
                item_id=item["item_id"],
            )
            salvar_jsonl(registro)
            if registro["relevante"]:
                send_telegram(f"Nova licitacao relevante ({', '.join(registro['categorias'])}): {item['objeto']}\n{item['link']}")
            conn.execute("INSERT INTO seen(id,title,link,ts) VALUES(?,?,?,?)", (item["item_id"], item["objeto"], item["link"], int(time.time())))
            conn.commit()
    conn.close()


if __name__ == "__main__":
    run_once()
