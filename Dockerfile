
FROM python:3.9-slim


WORKDIR /app


RUN apt-get update && apt-get install -y ffmpeg --no-install-recommends && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .


EXPOSE 7860
EXPOSE 8080


CMD ["python", "app.py"]
