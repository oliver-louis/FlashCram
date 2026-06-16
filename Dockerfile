FROM node:22-alpine AS assets

WORKDIR /app
COPY package.json ./
RUN npm install
COPY static_src ./static_src
RUN mkdir -p static/css static/vendor \
    && npm run build:css \
    && cp node_modules/htmx.org/dist/htmx.min.js static/vendor/htmx.min.js \
    && cp node_modules/alpinejs/dist/cdn.min.js static/vendor/alpine.min.js

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=assets /app/static/css/app.css ./static/css/app.css
COPY --from=assets /app/static/vendor/htmx.min.js ./static/vendor/htmx.min.js
COPY --from=assets /app/static/vendor/alpine.min.js ./static/vendor/alpine.min.js
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p /data /app/staticfiles \
    && chown -R app:app /app /data

USER app

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "flashcram.wsgi:application", "--bind", "0.0.0.0:8000"]
