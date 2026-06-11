# Single image: FastAPI (internal :8000) + Streamlit (public :$PORT).
FROM python:3.12-slim

WORKDIR /app

# system deps for pandas/duckdb wheels are bundled; none extra needed on slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit talks to the API on localhost inside the container
ENV DOCQA_API=http://localhost:8000
ENV PORT=8501

RUN chmod +x start.sh
EXPOSE 8501
CMD ["./start.sh"]
