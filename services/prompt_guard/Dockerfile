FROM python:3.11-slim

WORKDIR /app
# torch bản CPU (nhẹ hơn nhiều so với bản CUDA mặc định)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1" \
 && pip install --no-cache-dir "transformers==4.46.3" "sentencepiece==0.2.0" "protobuf==5.28.3" \
    "huggingface_hub==0.26.2" "fastapi==0.115.5" "uvicorn==0.32.1"

COPY app.py .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
