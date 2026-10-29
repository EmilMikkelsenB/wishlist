FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wishlist.py .
ENV WISHLIST_DB=/data/wishlist.db
VOLUME /data
# check every 3h; `docker exec wishlist python wishlist.py add <url>` to manage items
CMD ["sh", "-c", "while true; do python wishlist.py check; sleep 10800; done"]
