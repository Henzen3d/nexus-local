# Estágio 1: Instala as dependências e faz o build do React/Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

ARG VITE_API_URL
ARG VITE_WS_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# Estágio 2: Serve os arquivos estáticos com o Nginx (super leve)
FROM nginx:alpine
# Remove a página padrão do Nginx
RUN rm -rf /usr/share/nginx/html/*
# Copia os arquivos compilados do Vite (pasta dist) do Estágio 1
COPY --from=builder /app/dist /usr/share/nginx/html
# Copia a sua configuração customizada de rotas
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expõe a porta interna do container
EXPOSE 80

# Comando para manter o Nginx rodando
CMD ["nginx", "-g", "daemon off;"]