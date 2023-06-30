FROM python:3.8

WORKDIR /app

COPY . ./

RUN apt-get update && apt-get install -y ffmpeg

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

ENV PYTHONPATH /app

CMD ["python3", "app/main.py" ]