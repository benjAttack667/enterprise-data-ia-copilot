FROM node:22-alpine AS dependencies

WORKDIR /app
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
COPY docker/certs/ /tmp/copilot-certificates/
COPY frontend/package.json frontend/package-lock.json ./
RUN for certificate in /tmp/copilot-certificates/*.crt; do \
      if [ -f "$certificate" ]; then cat "$certificate" >> /etc/ssl/certs/ca-certificates.crt; fi; \
    done \
    && npm ci

FROM node:22-alpine AS builder

WORKDIR /app
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=dependencies /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY frontend/ ./
RUN npm run build

FROM node:22-alpine AS runner

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app
RUN chown node:node /app

COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))"]

CMD ["node", "server.js"]
