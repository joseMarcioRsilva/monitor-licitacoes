#!/usr/bin/env python3
"""
pncp_monitor.py
PoC: consulta a API publica do PNCP, armazena IDs vistos em SQLite, classifica cada
licitacao por categoria (municipal/estadual/federal) usando config/categorias.json e
notifica via Telegram quando relevante. Rode periodicamente (cron, GitHub Actions, VPS).

Endpoint: /api/consulta/v1/contratacoes/publicacao (o antigo /api/pncp/v1/consultas/licitacoes
foi descontinuado pelo PNCP e retorna 404). Esse endpoint exige o parametro
codigoModalidadeContratacao, entao o monitor consulta uma lista de modalidades (env
PNCP_MODALIDADES) e junta os resultados.

Config via env vars:
  PNCP_START_DATE, PNCP_END_DATE (YYYY-MM-DD) — opcional; se nao definidas, usa uma
    janela movel automatica (hoje - PNCP_LOOKBACK_DAYS ate hoje), assim o monitor
    continua avancando sozinho sem precisar editar secrets a cada execucao.
  PNCP_LOOKBACK_DAYS (default 3)
  PNCP_PAGE_SIZE (default 50, minimo aceito pela API e 10)
  PNCP_MODALIDADES (default "6,8" — Pregao Eletronico e Dispensa de Licitacao, que
    cobrem a grande maioria das compras de material/equipamento. Para ampliar,
    inclua tambem 4 e 5 = Concorrencia Eletronica/Presencial, 7 = Pregao Presencial,
    9 = Inexigibilidade — cada modalidade a mais custa varias dezenas de paginas
    extras por execucao, entao va testando aos poucos)
  HTTP_RETRIES (default 3), HTTP_RETRY_BACKOFF (segundos, default 5) — a API do PNCP
    e instavel e pode responder devagar ou com 504; o monitor tenta novamente antes
    de desistir dessa pagina.
  TG_TOKEN, TG_CHAT (para alertas)
  DB_PATH (default data/pncp_seen.db)

Filtro "em curso": itens cujo prazo de envio de proposta (dataEncerramentoProposta)
ja passou sao ignorados (nao vao para o JSONL nem geram alerta) — sem isso o arquivo
enchia de licitacoes antigas que ja nao da mais tempo de participar. Quando a API
nao informa esse prazo, o item e mantido (nao da pra saber se encerrou ou nao).
"""
import os
import time
import requests
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from common import montar_registro, salvar_jsonl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE = os.getenv("PNCP_API_BASE", "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao")
PAGE_SIZE = max(10, int(os.getenv("PNCP_PAGE_SIZE", "50")))
LOOKBACK_DAYS = int(os.getenv("PNCP_LOOKBACK_DAYS", "3"))
MODALIDADES = [m.strip() for m in os.getenv("PNCP_MODALIDADES", "6,8").split(",") if m.strip()]
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
HTTP_RETRY_BACKOFF = float(os.getenv("HTTP_RETRY_BACKOFF", "5"))
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
DB_PATH = os.getenv("DB_PATH", "data/pncp_seen.db")

ESFERA_MAP = {"F": "federal", "E": "estadual", "M": "municipal", "D": "distrital"}


def janela_padrao():
    """Janela movel: hoje - LOOKBACK_DAYS ate hoje, usada quando PNCP_START_DATE/END_DATE nao sao definidas."""
    hoje = datetime.now(timezone.utc).date()
    inicio = hoje - timedelta(days=LOOKBACK_DAYS)
    return inicio.strftime("%Y-%m-%d"), hoje.strftime("%Y-%m-%d")


_start_env = os.getenv("PNCP_START_DATE")
_end_env = os.getenv("PNCP_END_DATE")
if _start_env and _end_env:
    START_DATE, END_DATE = _start_env, _end_env
else:
    START_DATE, END_DATE = janela_padrao()


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


def fetch_page(start_date, end_date, modalidade, page=1, size=PAGE_SIZE):
    params = {
        "dataInicial": start_date.replace("-", ""),
        "dataFinal": end_date.replace("-", ""),
        "codigoModalidadeContratacao": modalidade,
        "pagina": page,
        "tamanhoPagina": size,
    }
    ultimo_erro = None
    for tentativa in range(1, HTTP_RETRIES + 1):
        try:
            r = requests.get(BASE, params=params, timeout=45)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            ultimo_erro = e
            logging.warning(
                "Falha ao consultar PNCP (modalidade %s, pagina %s, tentativa %d/%d): %s",
                modalidade, page, tentativa, HTTP_RETRIES, e,
            )
            if tentativa < HTTP_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * tentativa)
    raise ultimo_erro


def montar_link(item):
    orgao = item.get("orgaoEntidade") or {}
    cnpj = orgao.get("cnpj")
    ano = item.get("anoCompra")
    seq = item.get("sequencialCompra")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
    return item.get("linkSistemaOrigem") or ""


def proposta_ainda_aberta(data_encerramento_proposta):
    """True se ainda da tempo de enviar proposta (prazo nao informado conta como aberto,
    ja que nem toda modalidade/contratacao preenche esse campo)."""
    if not data_encerramento_proposta:
        return True
    try:
        prazo = datetime.fromisoformat(data_encerramento_proposta)
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return prazo >= datetime.now(timezone.utc)
    except ValueError:
        return True


def run_once():
    logging.info("Consultando PNCP no periodo %s a %s (modalidades: %s)", START_DATE, END_DATE, ", ".join(MODALIDADES))
    pasta_db = os.path.dirname(DB_PATH)
    if pasta_db:
        os.makedirs(pasta_db, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, link TEXT, ts INTEGER)")

    for modalidade in MODALIDADES:
        page = 1
        while True:
            try:
                data = fetch_page(START_DATE, END_DATE, modalidade, page=page, size=PAGE_SIZE)
            except Exception as e:
                logging.error("Erro ao consultar PNCP (modalidade %s, pagina %s): %s", modalidade, page, e)
                break
            content = data.get("data", [])
            total_paginas = data.get("totalPaginas", None)
            logging.info("Modalidade %s - pagina %d - %d itens", modalidade, page, len(content))
            for item in content:
                orgao_entidade = item.get("orgaoEntidade") or {}
                item_id = item.get("numeroControlePNCP")
                title = item.get("objetoCompra", "")
                link = montar_link(item)
                orgao = orgao_entidade.get("razaoSocial", "")
                modalidade_nome = item.get("modalidadeNome", "")
                status = item.get("situacaoCompraNome", "")
                data_publicacao = item.get("dataPublicacaoPncp", "")
                data_encerramento = item.get("dataEncerramentoProposta", "")
                esfera = ESFERA_MAP.get(orgao_entidade.get("esferaId"), "a-detectar")
                if not item_id:
                    item_id = f"{title[:120]}-{data_publicacao}"
                cur = conn.execute("SELECT 1 FROM seen WHERE id=?", (item_id,))
                if not cur.fetchone():
                    if not proposta_ainda_aberta(data_encerramento):
                        logging.info("Ignorado (prazo de proposta encerrado em %s): %s", data_encerramento, title)
                    else:
                        logging.info("Encontrado novo item: %s", title)
                        registro = montar_registro(
                            fonte="PNCP",
                            esfera=esfera,
                            numero_contratacao=item.get("numeroCompra", ""),
                            objeto=title,
                            orgao=orgao,
                            modalidade=modalidade_nome,
                            status=status,
                            data_publicacao=data_publicacao,
                            link=link,
                            item_id=item_id,
                        )
                        salvar_jsonl(registro)
                        if registro["relevante"]:
                            send_telegram(f"Nova licitacao relevante ({', '.join(registro['categorias'])}): {title}\n{link}")
                    conn.execute("INSERT INTO seen(id,title,link,ts) VALUES(?,?,?,?)", (item_id, title, link, int(time.time())))
                    conn.commit()
            if total_paginas is not None:
                if page >= total_paginas:
                    break
            else:
                if not content:
                    break
            page += 1
            time.sleep(0.5)
    conn.close()


if __name__ == "__main__":
    run_once()
