FROM python:3.13-slim
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-lock.txt
COPY . .
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
