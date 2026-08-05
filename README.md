# Monitor de Licitações — PoC PNCP + SISLOG

Este repositório contém scripts PoC para monitorar licitações em:
- PNCP (API pública) — pncp_monitor.py
- SISLOG (Goiás) — sislog_monitor_playwright.py (Playwright scraping com fallback para endpoint)

Pré-requisitos
- Python 3.9+ (recomendo 3.11)
- Para Playwright: navegadores instalados (`python -m playwright install --with-deps`) ou use o Dockerfile que já instala.
- Variáveis de ambiente (exemplos):
  - TG_TOKEN, TG_CHAT — para enviar alertas via Telegram
  - PNCP_START_DATE, PNCP_END_DATE — período para consulta PNCP (YYYY-MM-DD)
  - SISLOG_API_ENDPOINT — (opcional) endpoint JSON conhecido do SISLOG, se existir
  - ROW_SELECTOR, TITLE_SELECTOR, LINK_SELECTOR — seletores CSS para ajustar extração em SISLOG

Como rodar localmente
1. Crie um virtualenv e instale dependências:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Instale browsers do Playwright:
   python -m playwright install --with-deps

3. Defina variáveis de ambiente e rode:
   export TG_TOKEN="..."
   export TG_CHAT="..."
   export PNCP_START_DATE="2026-08-01"
   export PNCP_END_DATE="2026-08-05"
   python pncp_monitor.py

Para SISLOG:
   export TG_TOKEN="..."
   export TG_CHAT="..."
   python sislog_monitor_playwright.py

Observações e próximos passos
- Ajuste seletores do SISLOG com DevTools: abra a página, encontre o seletor CSS que representa a linha e as colunas.
- Prefira endpoints JSON/XHR identificados no DevTools; chamá-los diretamente é mais robusto e rápido.
- Use deduplicação por ID estável (numero do edital/código) e hashing do conteúdo se necessário.
- Respeite robots.txt, termos de uso e limite de requisições (rate limit).
- Para produção: migre do SQLite para PostgreSQL, use MeiliSearch/OpenSearch para indexar texto, e orquestre com Prefect/Airflow ou serverless.

Legal / Ético
- Verifique robots.txt (ex.: https://pncp.gov.br/robots.txt) e os termos do portal.
- Não faça scraping agressivo — delays e backoff são obrigatórios.
- Evite armazenar desnecessariamente dados pessoais sensíveis (LGPD).
- - Verifique robots.txt (ex.: https://pncp.gov.br/robots.txt) e os termos do portal.
  - - Não faça scraping agressivo — delays e backoff são obrigatórios.
    - - Evite armazenar desnecessariamente dados pessoais sensíveis (LGPD).
