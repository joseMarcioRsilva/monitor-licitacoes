FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exemplo: rodar pncp monitor; ajuste conforme necessidade
CMD ["python", "pncp_monitor.py"]
