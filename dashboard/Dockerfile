# syntax=docker/dockerfile:1
#
# Dashboard Next.js (output: standalone), chạy `node server.js` cổng 3000.
#
# Build arg NEXT_PUBLIC_API_URL được nhận để tương thích docker-compose nhưng hiện
# KHÔNG được dùng: trình duyệt luôn gọi cùng origin `/api/...`.
#
# Env lúc chạy API_INTERNAL_URL (mặc định http://localhost:8000) được đọc ở MỖI request
# bởi Route Handler `src/app/api/[...path]/route.ts`, nên chỉ cần đặt trong
# `environment:` của compose, không cần build lại. (Không dùng `rewrites()` của
# next.config vì cấu hình đó được serialize lúc build; env lúc chạy không có tác dụng.)

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    API_INTERNAL_URL=http://api:8000
RUN addgroup -S nextjs && adduser -S nextjs -G nextjs
COPY --from=build --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nextjs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
