FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt && \
    pip install -r requirements.txt --no-cache-dir

COPY . .
RUN pip install -e . --no-deps --no-cache-dir

CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8080"]
