# Monitor de Licitacoes — PNCP + SISLOG (com base para automacao N8N)

Este repositorio contem scripts para monitorar licitacoes publicas em duas fontes:
- PNCP (API publica, abrange licitacoes federais/estaduais/municipais) — pncp_monitor.py
- SISLOG (Goias, estadual) — sislog_monitor.py (HTML estatico via requests + BeautifulSoup, sem necessidade de Playwright)

## Arquitetura

Os dois monitores usam um modulo compartilhado, common.py, que padroniza cada licitacao encontrada em um registro unico com estes campos: id, fonte, esfera, numero_contratacao, objeto, orgao, modalidade, status, data_publicacao, link, categorias, relevante e coletado_em.

Cada novo registro e classificado automaticamente por categoria (municipal, estadual, federal) usando as palavras-chave definidas em config/categorias.json, e e gravado em data/novas_licitacoes.jsonl (um objeto JSON por linha). Esse arquivo JSON Lines e o ponto de integracao pensado para o N8N: cada linha e uma licitacao pronta para ser lida, filtrada (ex.: so as com relevante true) e roteada para o proximo passo do seu fluxo (planilha, CRM, WhatsApp, etc.).

Alertas via Telegram continuam sendo enviados, mas agora somente quando a licitacao bate com alguma categoria configurada.

## Estrutura de arquivos

- pncp_monitor.py — monitora a API do PNCP
- sislog_monitor.py — monitora o SISLOG-GO (tabela HTML estatica, seletor confirmado: table.contracts-table)
- common.py — funcoes compartilhadas (padronizacao, categorizacao, gravacao em JSONL)
- config/categorias.json — palavras-chave por esfera (municipal/estadual/federal) — edite conforme as diretrizes da sua empresa
- data/novas_licitacoes.jsonl — saida padronizada, gerada automaticamente na primeira execucao
- requirements.txt, Dockerfile, .github/workflows/monitor.yml — dependencias, container e agendamento

## Configurando as categorias

Edite config/categorias.json e substitua os valores de exemplo pelas palavras-chave reais que identificam licitacoes que sua empresa consegue atender, separadas por esfera (municipal, estadual, federal). Uma licitacao e marcada como relevante se o campo objeto contiver qualquer uma das palavras-chave (comparacao sem diferenciar maiusculas/minusculas).

## Pre-requisitos

- Python 3.9+ (recomendo 3.11)
- pip install -r requirements.txt (requests e beautifulsoup4 — Playwright nao e mais necessario)

## Como rodar localmente

1. Crie um virtualenv e instale dependencias:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Ajuste config/categorias.json com suas palavras-chave.

3. Defina variaveis de ambiente e rode o PNCP:
   export TG_TOKEN="..."
   export TG_CHAT="..."
   export PNCP_START_DATE="2026-08-01"
   export PNCP_END_DATE="2026-08-05"
   python pncp_monitor.py

4. Rode o SISLOG:
   export TG_TOKEN="..."
   export TG_CHAT="..."
   python sislog_monitor.py

5. Confira o resultado em data/novas_licitacoes.jsonl — esse arquivo e o que sera consumido pelo N8N.

## Variaveis de ambiente

- TG_TOKEN, TG_CHAT — credenciais do bot do Telegram para alertas
- PNCP_START_DATE, PNCP_END_DATE — periodo de consulta no PNCP (YYYY-MM-DD)
- PNCP_PAGE_SIZE — tamanho de pagina da API do PNCP (default 50)
- SISLOG_URL — URL da listagem do SISLOG (default ja configurado)
- ESFERA — esfera padrao atribuida aos registros do SISLOG (default estadual)
- DB_PATH — caminho do SQLite usado para deduplicacao (padrao diferente por script)
- CATEGORIAS_PATH — caminho do arquivo de categorias (default config/categorias.json)
- NOVAS_LICITACOES_PATH — caminho do arquivo JSONL de saida (default data/novas_licitacoes.jsonl)

## Proximos passos sugeridos

- Testar os dois scripts localmente e validar a classificacao por categoria com casos reais.
- Cadastrar os secrets no GitHub (Settings, Secrets and variables, Actions) para o workflow agendado funcionar: TG_TOKEN, TG_CHAT, PNCP_START_DATE, PNCP_END_DATE.
- No N8N, criar um fluxo que leia data/novas_licitacoes.jsonl (ou, futuramente, receba os dados via webhook) e direcione as licitacoes relevantes para o proximo passo do seu processo.
- Para producao: migrar do SQLite para PostgreSQL e considerar MeiliSearch ou OpenSearch se o volume crescer muito.

## Legal e etico

- Verifique o robots.txt de cada portal (ex.: pncp.gov.br/robots.txt) e os respectivos termos de uso.
- Nao faca scraping agressivo — respeite atrasos e limites de requisicao.
- Evite armazenar dados pessoais sensiveis sem necessidade (LGPD).
