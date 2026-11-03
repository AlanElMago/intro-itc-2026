FROM python:3.13-alpine

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser -D python
COPY . .
RUN chown -R python:python /app

USER python

CMD ["python", "main.py"]
