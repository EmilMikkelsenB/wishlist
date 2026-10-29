# wishlist

Self-hosted price-drop tracker. Checks product pages every 3h and sends an [ntfy](https://ntfy.sh) push when a price changes.

## Install (Docker)
    wget https://github.com/EmilMikkelsenB/wishlist/releases/latest/download/wishlist.tar.gz
    tar xzf wishlist.tar.gz && cd wishlist
    cp .env.example .env && nano .env      # set NTFY_TOPIC to a long random string
    docker compose up -d --build

## Use
    docker exec wishlist python wishlist.py add <url> --name "Thing" [--selector "css"]
    docker exec wishlist python wishlist.py list
    docker exec wishlist python wishlist.py remove <id>

Without Docker: `pip install -r requirements.txt`, then run `wishlist.py check` from cron.
