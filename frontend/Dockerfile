# Stage 0, "build-stage", based on Bun, to build and compile the frontend
FROM oven/bun:1 AS build-stage

WORKDIR /app

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN for attempt in 1 2 3; do \
      bun ci && exit 0; \
      if [ "$attempt" -eq 3 ]; then exit 1; fi; \
      bun pm cache rm || true; \
      rm -rf /app/node_modules /app/frontend/node_modules; \
      sleep 3; \
    done

COPY ./frontend /app/frontend
ARG VITE_API_URL
ARG VITE_APP_VERSION
ARG VITE_MAP_IMAGE_CDN_BASE_URL

RUN bun run build


# Stage 1, based on Nginx, to have only the compiled app, ready for production with Nginx
FROM nginx:1

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ./frontend/nginx-backend-not-found.conf /etc/nginx/extra-conf.d/backend-not-found.conf
