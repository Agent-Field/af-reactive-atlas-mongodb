FROM python:3.12-slim

WORKDIR /app

COPY reactive-atlas/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agentfield/sdk/python/ /tmp/sdk/
RUN pip install --no-cache-dir /tmp/sdk/ && rm -rf /tmp/sdk/

COPY reactive-atlas/ .

CMD ["python", "main.py"]
