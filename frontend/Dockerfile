# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1


FROM base AS deps
COPY package.json package-lock.json* ./
# `npm ci` needs a lockfile; the fallback only fires before the first install
# has been committed.
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi


# --- dev: source bind-mounted over /app, node_modules kept from the image ---
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]


FROM deps AS builder
COPY . .
RUN npm run build


# --- runner: standalone server, no node_modules, non-root -------------------
FROM base AS runner
ENV NODE_ENV=production
RUN addgroup -g 10001 -S app && adduser -u 10001 -S app -G app

COPY --from=builder /app/public ./public
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static

USER app
EXPOSE 3000
CMD ["node", "server.js"]
