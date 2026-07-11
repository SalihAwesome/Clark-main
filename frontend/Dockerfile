# ============================================================================
#  Clark Frontend — Next.js 14 (App Router) production build
#  Multi-stage: deps → builder → runner
# ============================================================================

# ---- deps: install dependencies ----
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- builder: compile the app ----
FROM node:20-alpine AS builder
ARG BACKEND_URL=http://localhost:8008
ENV BACKEND_URL=$BACKEND_URL
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN mkdir -p /app/public && npm run build

# ---- runner: serve the compiled app ----
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Pass through BACKEND_URL so the standalone server knows where the backend lives
ARG BACKEND_URL=http://localhost:8008
ENV BACKEND_URL=$BACKEND_URL

# Create a non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Copy standalone output (requires output: "standalone" in next.config.js)
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
