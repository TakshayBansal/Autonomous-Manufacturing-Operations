FROM python:3.12-alpine
WORKDIR /app
COPY server.py index.html app.js styles.css extras.css ./
EXPOSE 3100
CMD ["python", "server.py"]
