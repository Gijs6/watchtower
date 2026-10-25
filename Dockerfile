FROM python:3.15

WORKDIR /app
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt
COPY . .
ENV HOME=/tmp
USER 1000:1000
CMD ["gunicorn", "--bind", "0.0.0.0:4000", "app:app"]
