# Multi-stage build → node:20-slim runtime running the Next.js `standalone` output.
#
# NEXT_PUBLIC_API_BASE_URL is a build-time ARG, not a runtime env var: Next.js inlines every
# NEXT_PUBLIC_* value into the client JS bundle at `next build` time. lib/api.ts is only ever
# called from "use client" components, so it runs in the user's browser on the host machine —
# it can never resolve the compose network's `backend` DNS name, so this must stay a
# host-reachable URL (http://localhost:8000/v1), not a container-to-container one. Setting it
# via docker-compose's `environment:`/`env_file:` on the frontend *service* would have no
# effect, since that only affects the already-built server process, not the baked bundle.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/v1
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
# Docker sets HOSTNAME to the container ID by default, which its own /etc/hosts resolves to
# the container's actual IP — the standalone server then binds only to that IP, not
# 0.0.0.0/127.0.0.1, so anything connecting via localhost inside the container (healthcheck
# included) gets ECONNREFUSED. Must override explicitly.
ENV HOSTNAME="0.0.0.0"
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
