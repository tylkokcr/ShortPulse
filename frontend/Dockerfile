# ShortPulse web UI.
#
# Three stages so the runtime image carries neither the source nor the
# build toolchain: node_modules here is ~500MB, and Next's standalone
# output bundles only what the server actually imports.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci


FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are compiled into the client bundle, so they have to
# be present at build time rather than injected when the container starts.
# Both are optional: without Supabase the app runs in its self-hosted
# shape, with no accounts and no billing.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_WS_ORIGIN
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY \
    NEXT_PUBLIC_WS_ORIGIN=$NEXT_PUBLIC_WS_ORIGIN \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build


FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Where this server proxies /api to. Read at request time, so it can point
# at a container name without being baked into the client bundle.
ENV BACKEND_ORIGIN=http://api:8000

COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

RUN addgroup -g 10001 -S web && adduser -u 10001 -S web -G web && chown -R web:web /app
USER web

EXPOSE 3000
CMD ["node", "server.js"]
