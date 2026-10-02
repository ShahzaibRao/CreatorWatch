# License server image (for the k3s deploy later).
FROM python:3.12-slim
WORKDIR /srv/license-server
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV HOST=0.0.0.0 PORT=5001 LICENSE_DB=/data/licenses.db
VOLUME ["/data"]
EXPOSE 5001
CMD ["python", "app.py"]
