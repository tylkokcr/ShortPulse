# ShortPulse web UI.
#
# Three stages so the runtime image carries neither the source nor the
# build toolchain: node_modules here is ~500MB, and Next's standalone
# output bundles only what the server actually imports.

FROM node:26-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci


FROM node:26-alpine AS build
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

# Which identity providers the sign-in screen offers. Comma separated,
# empty by default: a provider only works once it has been given a client
# id and secret in the Supabase dashboard, and a button for one that
# hasn't been is a dead end on the first screen a stranger sees. The
# hosted deployment turns them on one at a time as their paperwork clears.
ARG NEXT_PUBLIC_OAUTH_PROVIDERS

# Who runs this install — printed on the terms and privacy pages, which
# have to name a controller and a contact to be worth anything. Left
# unset, those pages say the operator hasn't published them rather than
# showing somebody else's company, which is the right answer for a
# self-hosted install that isn't selling to anyone.
ARG NEXT_PUBLIC_OPERATOR_NAME
ARG NEXT_PUBLIC_OPERATOR_ADDRESS
ARG NEXT_PUBLIC_OPERATOR_EMAIL
ARG NEXT_PUBLIC_OPERATOR_TAX_ID
ARG NEXT_PUBLIC_OPERATOR_COUNTRY
ARG NEXT_PUBLIC_OPERATOR_DATA_REGION

ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY \
    NEXT_PUBLIC_WS_ORIGIN=$NEXT_PUBLIC_WS_ORIGIN \
    NEXT_PUBLIC_OAUTH_PROVIDERS=$NEXT_PUBLIC_OAUTH_PROVIDERS \
    NEXT_PUBLIC_OPERATOR_NAME=$NEXT_PUBLIC_OPERATOR_NAME \
    NEXT_PUBLIC_OPERATOR_ADDRESS=$NEXT_PUBLIC_OPERATOR_ADDRESS \
    NEXT_PUBLIC_OPERATOR_EMAIL=$NEXT_PUBLIC_OPERATOR_EMAIL \
    NEXT_PUBLIC_OPERATOR_TAX_ID=$NEXT_PUBLIC_OPERATOR_TAX_ID \
    NEXT_PUBLIC_OPERATOR_COUNTRY=$NEXT_PUBLIC_OPERATOR_COUNTRY \
    NEXT_PUBLIC_OPERATOR_DATA_REGION=$NEXT_PUBLIC_OPERATOR_DATA_REGION \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build


FROM node:26-alpine AS runtime
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
