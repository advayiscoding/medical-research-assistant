# Frontend image. Three stages: install deps, build the standalone bundle, then
# a minimal runner that ships only the standalone output + static assets.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so the
# backend URL the browser will call must be provided here. It defaults to the
# host-mapped backend port used by docker-compose.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
# node:20-slim already ships a non-root "node" user at UID 1000 — reuse it
# rather than creating a duplicate.

# Standalone output bundles a minimal server + only the node_modules it needs.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER node
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
