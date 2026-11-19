FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY . .
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY render-nginx-config.sh /usr/local/bin/render-nginx-config.sh
RUN chmod +x /usr/local/bin/render-nginx-config.sh \
    && rm -f /etc/nginx/conf.d/default.conf

ENV PORT=8080 \
    CORE_UPSTREAM=http://core:8000 \
    INGEST_UPSTREAM=http://ingest:8000

EXPOSE 8080
CMD ["sh", "-c", "render-nginx-config.sh /etc/nginx/templates/default.conf.template /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
