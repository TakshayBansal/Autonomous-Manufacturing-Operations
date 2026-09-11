# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts

FROM node:24-alpine AS builder
ARG NEXT_PUBLIC_SHOW_SIMULATION_ACCOUNTS=false
ARG NEXT_PUBLIC_V2_SIMULATION_PASSWORD=Northstar@2026
ARG API_INTERNAL_BASE_URL=http://api:8000
ENV NEXT_PUBLIC_SHOW_SIMULATION_ACCOUNTS=$NEXT_PUBLIC_SHOW_SIMULATION_ACCOUNTS
ENV NEXT_PUBLIC_V2_SIMULATION_PASSWORD=$NEXT_PUBLIC_V2_SIMULATION_PASSWORD
ENV API_INTERNAL_BASE_URL=$API_INTERNAL_BASE_URL
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY apps/web ./apps/web
COPY packages/shared ./packages/shared
RUN npm --workspace apps/web run build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/apps/web/package.json ./apps/web/package.json
COPY --from=builder /app/apps/web/.next ./apps/web/.next
COPY --from=builder /app/apps/web/public ./apps/web/public
EXPOSE 3000
CMD ["npm", "--workspace", "apps/web", "run", "start"]
