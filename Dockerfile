FROM python:3.10

RUN apt-get update && \
    apt-get install -y gcc g++ unixodbc-dev unixodbc curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "bot_final.py"]
