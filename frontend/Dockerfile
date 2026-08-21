# ---- Stage 1: reproducible frontend build ----
FROM node:22.14-alpine AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Stage 2: static non-development runtime ----
FROM nginx:1.27.4-alpine
# The official nginx image's master starts with the image's configured user and
# serves workers as nginx; no Node/npm toolchain or source is shipped here.
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
