FROM python:3.11-slim

# Dependencias de sistema necessarias para navegadores Playwright
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget gnupg unzip libnss3 libatk1.0-0 libcups2 libxss1 libasound2 libx11-xcb1 libxcomposite1 libxrandr2 libgbm1 libgtk-3-0 libpangocairo-1.0-0 libpango-1.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala browsers do Playwright
RUN python -m playwright install --with-deps

COPY . .

# Exemplo: rodar pncp monitor; ajuste conforme necessidade
CMD ["python", "pncp_monitor.py"]
