# Imagen para Railway (o cualquier host con Docker).
# La BD no viaja en git: se regenera aquí con el ETL a partir de los .txt crudos
# comprimidos en deploy/raw/ (los prepara deploy/pack_raw.py; se suben con `railway up`).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY etl ./etl
COPY web ./web
COPY deploy/raw ./deploy/raw

# Descomprime los crudos, genera data/hospital.db y borra los crudos de la imagen
RUN mkdir -p DATOS data \
 && for f in deploy/raw/*.txt.gz; do gunzip -c "$f" > "DATOS/$(basename "$f" .gz)"; done \
 && python etl/build_db.py --raw DATOS --out data/hospital.db \
 && rm -rf DATOS deploy

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
