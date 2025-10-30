#!/bin/bash

#########################################################
# Binance Futures Bot - Автоматическая установка на VPS
# GitHub: https://github.com/tsygulevsergey-pixel/BinanceFuturesBot
#########################################################

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 УСТАНОВКА BINANCE FUTURES BOT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Функция для логирования
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    log_error "Запустите скрипт от имени root: sudo bash setup_vps.sh"
    exit 1
fi

# Установка директории
INSTALL_DIR="/root/BinanceFuturesBot"

log_info "Обновление системы..."
apt update && apt upgrade -y

log_info "Установка необходимых пакетов..."
apt install -y python3 python3-pip git redis-server postgresql postgresql-contrib curl

log_info "Клонирование репозитория..."
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Директория $INSTALL_DIR уже существует. Обновление..."
    cd "$INSTALL_DIR"
    git pull
else
    git clone https://github.com/tsygulevsergey-pixel/BinanceFuturesBot.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

log_info "Создание requirements.txt..."
cat > requirements.txt <<EOF
python-binance==1.0.19
python-telegram-bot==20.7
python-dotenv==1.0.0
redis==5.0.1
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
pandas==2.1.4
numpy==1.26.2
aiohttp==3.9.1
websockets==12.0
asyncpg==0.29.0
python-socks==2.4.3
pytz==2023.3
EOF

log_info "Установка Python зависимостей..."
pip3 install -r requirements.txt

log_info "Создание директории для логов..."
mkdir -p "$INSTALL_DIR/bot/logs"

log_info "Настройка PostgreSQL..."
systemctl start postgresql
systemctl enable postgresql

# Создание пользователя и базы данных PostgreSQL
sudo -u postgres psql -c "DROP DATABASE IF EXISTS binance_bot;" 2>/dev/null || true
sudo -u postgres psql -c "DROP USER IF EXISTS bot_user;" 2>/dev/null || true
sudo -u postgres psql -c "CREATE USER bot_user WITH PASSWORD 'bot_password_2024';"
sudo -u postgres psql -c "CREATE DATABASE binance_bot OWNER bot_user;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE binance_bot TO bot_user;"

log_info "Настройка Redis..."
systemctl start redis-server
systemctl enable redis-server

log_info "Создание .env файла..."
cat > "$INSTALL_DIR/.env" <<EOF
# Binance API
BINANCE_API_KEY=YOUR_BINANCE_API_KEY
BINANCE_API_SECRET=YOUR_BINANCE_API_SECRET

# Telegram
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

# Database
DATABASE_URL=postgresql://bot_user:bot_password_2024@localhost/binance_bot

# Proxy (уже настроен в коде)
# PROXY_HOST=23.27.184.165
# PROXY_PORT=5766

# Trading Settings (уже в config.py)
# USE_DYNAMIC_LARGE_TRADES=True
# LARGE_TRADE_PERCENTILE=99
# MIN_LARGE_TRADE_SIZE=10000
EOF

log_info "Создание systemd службы..."
cat > /etc/systemd/system/binance-bot.service <<EOF
[Unit]
Description=Binance Futures Trading Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PYTHONPATH=$INSTALL_DIR"
ExecStart=/usr/bin/python3 $INSTALL_DIR/bot/main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/binance-bot.log
StandardError=append:/var/log/binance-bot-error.log

[Install]
WantedBy=multi-user.target
EOF

log_info "Перезагрузка systemd..."
systemctl daemon-reload

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ УСТАНОВКА ЗАВЕРШЕНА!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_warn "⚠️  ВАЖНО: Отредактируйте файл .env перед запуском:"
echo ""
echo "   nano $INSTALL_DIR/.env"
echo ""
echo "Замените следующие значения на ваши:"
echo "   • BINANCE_API_KEY"
echo "   • BINANCE_API_SECRET"
echo "   • TELEGRAM_BOT_TOKEN"
echo "   • TELEGRAM_CHAT_ID"
echo ""
log_info "После редактирования .env, запустите бота:"
echo ""
echo "   systemctl start binance-bot"
echo "   systemctl enable binance-bot"
echo ""
log_info "Просмотр логов:"
echo ""
echo "   tail -f /var/log/binance-bot.log"
echo ""
log_info "Проверка статуса:"
echo ""
echo "   systemctl status binance-bot"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
