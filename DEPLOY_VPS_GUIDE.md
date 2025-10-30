# 🚀 ИНСТРУКЦИЯ: РАЗВЁРТЫВАНИЕ БОТА НА VPS

## 📋 Данные вашего сервера

```
IP адрес: [ВАШ_IP_АДРЕС]
Пользователь: root
Пароль: a1806B2812A
```

---

## 🔧 ШАГ 1: ПОДКЛЮЧЕНИЕ К СЕРВЕРУ

### Windows (PowerShell или CMD):
```bash
ssh root@[ВАШ_IP_АДРЕС]
```

### Linux/Mac:
```bash
ssh root@[ВАШ_IP_АДРЕС]
```

**Введите пароль:** `a1806B2812A`

---

## 🤖 ШАГ 2: АВТОМАТИЧЕСКАЯ УСТАНОВКА (БЫСТРЫЙ СПОСОБ)

После подключения выполните одну команду:

```bash
curl -sSL https://raw.githubusercontent.com/tsygulevsergey-pixel/BinanceFuturesBot/main/setup_vps.sh | bash
```

Скрипт автоматически:
- ✅ Установит Python 3.11, pip, git
- ✅ Клонирует репозиторий
- ✅ Установит все зависимости
- ✅ Создаст .env файл
- ✅ Настроит systemd для 24/7 работы
- ✅ Запустит бота

---

## 📝 ШАГ 3: РУЧНАЯ УСТАНОВКА (ЕСЛИ АВТОУСТАНОВКА НЕ СРАБОТАЛА)

### 3.1. Обновление системы
```bash
apt update && apt upgrade -y
```

### 3.2. Установка необходимых пакетов
```bash
apt install -y python3 python3-pip git redis-server postgresql screen
```

### 3.3. Клонирование репозитория
```bash
cd /root
git clone https://github.com/tsygulevsergey-pixel/BinanceFuturesBot.git
cd BinanceFuturesBot
```

### 3.4. Установка Python зависимостей
```bash
pip3 install -r requirements.txt
```

### 3.5. Настройка переменных окружения
```bash
nano .env
```

**Вставьте следующий текст (замените значения на ваши):**

```env
# Binance API
BINANCE_API_KEY=ваш_binance_api_key
BINANCE_API_SECRET=ваш_binance_api_secret

# Telegram
TELEGRAM_BOT_TOKEN=ваш_telegram_bot_token
TELEGRAM_CHAT_ID=ваш_telegram_chat_id

# Database
DATABASE_URL=postgresql://bot_user:bot_password@localhost/binance_bot

# Proxy
PROXY_HOST=23.27.184.165
PROXY_PORT=5766
PROXY_USER=ваш_proxy_user
PROXY_PASS=ваш_proxy_pass

# Trading Settings
USE_DYNAMIC_LARGE_TRADES=True
LARGE_TRADE_PERCENTILE=99
MIN_LARGE_TRADE_SIZE=10000
```

**Сохраните:** `Ctrl+X`, затем `Y`, затем `Enter`

### 3.6. Настройка PostgreSQL
```bash
# Создать пользователя и базу данных
sudo -u postgres psql -c "CREATE USER bot_user WITH PASSWORD 'bot_password';"
sudo -u postgres psql -c "CREATE DATABASE binance_bot OWNER bot_user;"
```

### 3.7. Запуск Redis
```bash
systemctl start redis-server
systemctl enable redis-server
```

---

## 🚀 ШАГ 4: ЗАПУСК БОТА

### Вариант 1: Простой запуск (для тестирования)
```bash
cd /root/BinanceFuturesBot
python3 bot/main.py
```

### Вариант 2: Запуск в screen (бот работает в фоне)
```bash
screen -S binance-bot
cd /root/BinanceFuturesBot
python3 bot/main.py

# Отключиться от screen (бот продолжит работать):
# Нажмите: Ctrl+A, затем D
```

**Вернуться к боту:**
```bash
screen -r binance-bot
```

### Вариант 3: Systemd служба (автозапуск при перезагрузке) - РЕКОМЕНДУЕТСЯ
```bash
nano /etc/systemd/system/binance-bot.service
```

**Вставьте:**
```ini
[Unit]
Description=Binance Futures Trading Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/BinanceFuturesBot
Environment="PYTHONPATH=/root/BinanceFuturesBot"
ExecStart=/usr/bin/python3 /root/BinanceFuturesBot/bot/main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/binance-bot.log
StandardError=append:/var/log/binance-bot-error.log

[Install]
WantedBy=multi-user.target
```

**Сохраните:** `Ctrl+X`, `Y`, `Enter`

**Запуск службы:**
```bash
systemctl daemon-reload
systemctl enable binance-bot
systemctl start binance-bot
```

---

## 📊 ШАГ 5: МОНИТОРИНГ БОТА

### Проверка статуса службы:
```bash
systemctl status binance-bot
```

### Просмотр логов в реальном времени:
```bash
tail -f /var/log/binance-bot.log
```

### Просмотр только ошибок:
```bash
tail -f /var/log/binance-bot-error.log
```

### Проверка процесса:
```bash
ps aux | grep "python.*bot/main"
```

### Статистика в Telegram:
Отправьте боту команды:
- `/status` - текущий статус
- `/stats` - статистика

---

## 🔧 УПРАВЛЕНИЕ БОТОМ

### Остановить бота:
```bash
systemctl stop binance-bot
```

### Перезапустить бота:
```bash
systemctl restart binance-bot
```

### Обновить код с GitHub:
```bash
cd /root/BinanceFuturesBot
git pull
systemctl restart binance-bot
```

### Отключить автозапуск:
```bash
systemctl disable binance-bot
```

---

## 🐛 РЕШЕНИЕ ПРОБЛЕМ

### Бот не запускается:
```bash
# Проверить логи
journalctl -u binance-bot -n 100 --no-pager

# Проверить .env файл
cat /root/BinanceFuturesBot/.env

# Проверить зависимости
pip3 install -r /root/BinanceFuturesBot/requirements.txt
```

### Ошибки подключения к Binance:
```bash
# Проверить прокси
curl --proxy http://23.27.184.165:5766 https://fapi.binance.com/fapi/v1/ping
```

### PostgreSQL проблемы:
```bash
# Проверить статус
systemctl status postgresql

# Перезапустить
systemctl restart postgresql
```

### Redis проблемы:
```bash
# Проверить статус
systemctl status redis-server

# Перезапустить
systemctl restart redis-server
```

---

## 📈 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

После запуска вы увидите в логах:

```
🚀 Binance Futures Scanner Bot Initializing...
🔧 [TradeFlowAnalyzer] Initialized with window=5min, mode=DYNAMIC (top 1%, min $10,000)
📊 [UniverseSelector] Scanning 530 symbols...
✅ [UniverseSelector] Universe scan completed, selected 63 symbols
🔌 [DataCollector] WebSocket connected for 63 symbols
💓 [DataCollector] WebSocket alive - 1000 messages processed
💰 [DIAGNOSTIC] LARGE BUY BTCUSDT: $50,000...
📊 [Main] Completed signal check for 63 symbols - Generated 0 signals
```

**Telegram уведомления будут приходить когда появятся сигналы!**

---

## ✅ ЧЕКЛИСТ

- [ ] SSH подключение работает
- [ ] Python 3.11+ установлен
- [ ] Репозиторий склонирован
- [ ] Зависимости установлены
- [ ] .env файл настроен
- [ ] PostgreSQL запущен
- [ ] Redis запущен
- [ ] Бот запущен как служба
- [ ] Логи показывают работу
- [ ] Telegram команды работают

---

## 📞 ПОДДЕРЖКА

Если возникли проблемы:
1. Проверьте логи: `tail -f /var/log/binance-bot.log`
2. Проверьте статус: `systemctl status binance-bot`
3. Проверьте .env файл на правильность API ключей

**Бот готов к 24/7 работе!** 🚀
