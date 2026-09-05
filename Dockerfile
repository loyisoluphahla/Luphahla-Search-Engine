FROM python:3.11  # Changed from 'slim' – this has gcc pre-installed
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/startup.sh
CMD ["/app/startup.sh"]
