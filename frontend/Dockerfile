# syntax=docker/dockerfile:1

# ---- build stage ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite env vars are baked in at build time. Point this at the backend's
# public URL (e.g. https://duster-api.example.azurecontainerapps.io/api);
# left unset, the app falls back to the same-origin "/api" (see
# src/constants/appConfig.js), which is what you want if nginx below proxies
# /api to the backend instead.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---- serve stage ----
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
