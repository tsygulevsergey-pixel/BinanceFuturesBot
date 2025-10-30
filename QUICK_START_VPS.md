# ⚡ БЫСТРЫЙ СТАРТ - ЗАПУСК БОТА НА VPS

## 📋 У вас есть:
```
Сервер: [ВАШ_IP]
User: root
Password: a1806B2812A
GitHub: https://github.com/tsygulevsergey-pixel/BinanceFuturesBot
```

---

## 🚀 УСТАНОВКА В 3 ШАГА

### 1️⃣ Подключитесь к серверу:
```bash
ssh root@[ВАШ_IP_АДРЕС]
# Введите пароль: a1806B2812A
```

### 2️⃣ Запустите автоустановку:
```bash
cd /root
git clone https://github.com/tsygulevsergey-pixel/BinanceFuturesBot.git
cd BinanceFuturesBot
chmod +x setup_vps.sh
./setup_vps.sh
```

**Скрипт установит:**
- ✅ Python 3, pip, git
- ✅ PostgreSQL, Redis
- ✅ Все зависимости
- ✅ Создаст .env файл
- ✅ Настроит автозапуск

### 3️⃣ Настройте API ключи:
```bash
nano /root/BinanceFuturesBot/.env
```

**Замените на ваши:**
```env
BINANCE_API_KEY=ваш_ключ
BINANCE_API_SECRET=ваш_секрет
TELEGRAM_BOT_TOKEN=ваш_токен
TELEGRAM_CHAT_ID=ваш_chat_id
```

**Сохраните:** `Ctrl+X` → `Y` → `Enter`

---

## ✅ ЗАПУСК БОТА

```bash
systemctl start binance-bot
systemctl enable binance-bot
```

---

## 📊 МОНИТОРИНГ

### Логи в реальном времени:
```bash
tail -f /var/log/binance-bot.log
```

### Статус:
```bash
systemctl status binance-bot
```

### Перезапуск:
```bash
systemctl restart binance-bot
```

---

## 🎯 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

Через 1-2 минуты в логах вы увидите:
```
🚀 Binance Futures Scanner Bot Initializing...
✅ [UniverseSelector] Universe scan completed, selected 63 symbols
🔌 [DataCollector] WebSocket connected for 63 symbols
💓 [DataCollector] WebSocket alive - 1000 messages processed
💰 [DIAGNOSTIC] LARGE BUY BTCUSDT: $50,000
```

**Telegram уведомления придут когда появятся сигналы!**

---

## 💡 TELEGRAM КОМАНДЫ

После запуска протестируйте:
- `/status` - текущий статус бота
- `/stats` - статистика работы

---

## ❓ ЕСЛИ ЧТО-ТО НЕ РАБОТАЕТ

### Проверить логи:
```bash
journalctl -u binance-bot -n 100
```

### Проверить .env:
```bash
cat /root/BinanceFuturesBot/.env
```

### Проверить службы:
```bash
systemctl status postgresql
systemctl status redis-server
```

---

**БОТ ГОТОВ К 24/7 РАБОТЕ!** 🚀
