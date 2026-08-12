#!/usr/bin/env python3
"""
common.py
Funcoes compartilhadas entre os monitores (PNCP e SISLOG-GO):
- padronizacao dos registros de licitacao em um formato unico
- classificacao por categoria (municipal/estadual/federal) usando config/categorias.json
- gravacao em arquivo JSON Lines (data/novas_licitacoes.jsonl) para integracao futura com N8N

Esse arquivo existe para que ambos os monitores produzam o mesmo formato de dado,
facilitando consumir tudo depois em uma automacao no N8N, sem tratar PNCP e SISLOG
de formas diferentes.
"""
import json
import os
from datetime import datetime, timezone

CATEGORIAS_PATH = os.getenv("CATEGORIAS_PATH", "config/categorias.json")
JSONL_PATH = os.getenv("NOVAS_LICITACOES_PATH", "data/novas_licitacoes.jsonl")


def carregar_categorias(path=CATEGORIAS_PATH):
    """Carrega o arquivo de categorias/palavras-chave. Retorna {} se o arquivo nao existir."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def classificar(texto, categorias):
    """Retorna a lista de categorias cujas keywords aparecem no texto."""
    if not texto:
        return []
    texto_lower = texto.lower()
    matches = []
    for nome_categoria, dados in categorias.items():
        keywords = dados.get("keywords", [])
        for kw in keywords:
            if kw.lower() in texto_lower:
                matches.append(nome_categoria)
                break
    return matches


def montar_registro(fonte, esfera, numero_contratacao, objeto, orgao, modalidade,
                     status, data_publicacao, link, item_id):
    """Monta um registro padronizado de licitacao, ja classificado por categoria."""
    categorias = carregar_categorias()
    matches = classificar(objeto, categorias)
    return {
        "id": item_id,
        "fonte": fonte,
        "esfera": esfera,
        "numero_contratacao": numero_contratacao,
        "objeto": objeto,
        "orgao": orgao,
        "modalidade": modalidade,
        "status": status,
        "data_publicacao": data_publicacao,
        "link": link,
        "categorias": matches,
        "relevante": len(matches) > 0,
        "coletado_em": datetime.now(timezone.utc).isoformat(),
    }


def salvar_jsonl(registro, path=JSONL_PATH):
    """Acrescenta um registro (dict) como uma linha JSON no arquivo de saida."""
    pasta = os.path.dirname(path)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
