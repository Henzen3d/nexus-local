# Usa uma imagem oficial e enxuta do Python 3.11
FROM python:3.11-slim

# Define variáveis de ambiente para otimizar o Python no Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala dependências do sistema necessárias para o python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências primeiro (aproveita o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código para dentro do subdiretório "backend/" — preserva a estrutura
# de pacote que o main.py espera (from backend.database import ..., etc.)
COPY . ./backend/

# Expõe a porta interna do container
EXPOSE 8000

# Comando para rodar o FastAPI em modo produção.
# --forwarded-allow-ips="*": sem isso o uvicorn só confia em X-Forwarded-* vindos
# de 127.0.0.1 e, como o nginx fala com o backend pela rede Docker, o IP real e o
# esquema (https) eram ignorados. É seguro porque a porta 8000 NÃO é publicada no
# host — o único caminho até o backend é o proxy nginx dentro da rede nexus_net.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]