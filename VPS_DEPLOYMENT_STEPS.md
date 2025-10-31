# 🚀 VPS DEPLOYMENT - DYNAMIC SL/TP SYSTEM

## ⚠️ **КРИТИЧЕСКИ ВАЖНО: БД МИГРАЦИЯ ПЕРЕД ЗАПУСКОМ!**

Код уже на VPS, но **БОТ НЕ ЗАПУСТИТСЯ** без миграции БД!

---

## 📋 **ШАГ ЗА ШАГОМ:**

### **1️⃣ BACKUP БД (ОБЯЗАТЕЛЬНО!)**

```bash
# SSH на VPS
ssh root@your_vps_ip

cd /root/BinanceFuturesBot

# Загрузить переменные окружения
source .env

# Создать backup
pg_dump "$DATABASE_URL" > ~/backup_$(date +%Y%m%d_%H%M).sql

# Проверить
ls -lh ~/backup_*.sql
```

---

### **2️⃣ ОСТАНОВИТЬ БОТА**

```bash
./stop_bot.sh

# Убедиться что остановлен
ps aux | grep python
# НЕ должно показывать процессы бота
```

---

### **3️⃣ ПРИМЕНИТЬ МИГРАЦИИ БД**

**Нужны ОБЕ миграции:**

```bash
# Миграция 1 (partial close - если еще не применена)
psql "$DATABASE_URL" -f migrations/001_add_partial_close_columns.sql

# Миграция 2 (НОВАЯ - dynamic SL/TP reasoning)
psql "$DATABASE_URL" -f migrations/002_add_dynamic_sltp_columns.sql
```

**Проверка успешности:**

```bash
psql "$DATABASE_URL" -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'signals' AND column_name LIKE '%reason%';"
```

**Должно показать:**
```
 column_name      
------------------
 stop_loss_reason
 tp1_reason
 tp2_reason
```

---

### **4️⃣ ПРОВЕРИТЬ НОВЫЕ ФАЙЛЫ**

```bash
ls -lh bot/modules/volatility_calculator.py
ls -lh bot/modules/orderbook_levels_analyzer.py
ls -lh bot/modules/dynamic_stop_loss_finder.py
ls -lh bot/modules/dynamic_take_profit_finder.py
ls -lh bot/modules/signal_validator.py
```

Все 5 файлов должны существовать.

---

### **5️⃣ ОЧИСТИТЬ СТАРУЮ СТАТИСТИКУ (РЕКОМЕНДУЮ)**

Для чистого старта с новой системой:

```bash
psql "$DATABASE_URL" -c 'TRUNCATE TABLE trades, signals, performance_metrics, daily_stats CASCADE;'
```

---

### **6️⃣ ЗАПУСТИТЬ БОТА**

```bash
./start_bot.sh

# Мониторить логи
tail -f bot_production.log
```

---

## ✅ **ПРОВЕРКА РАБОТЫ**

### **Убедиться что бот запустился:**

```bash
ps aux | grep python
# Должен показать процесс bot/main.py
```

### **Смотреть логи:**

```bash
tail -100 bot_production.log
```

**✅ ХОРОШИЕ ПРИЗНАКИ:**
```
✅ [Main] SignalGenerator initialized with db_pool
🔧 [SignalGenerator] Initialized with dynamic SL/TP modules
✓ Volatility: MEDIUM (ATR: 15.50, 0.36%)
✓ Levels: 3 support, 4 resistance
✓ Stop: $42794.00 (0.48% away)
✓ TP1: $43800.00 (R/R: 3.88)
✓ Validation: PASSED - HIGH priority (score: 85.0)
```

**❌ ПЛОХИЕ ПРИЗНАКИ:**
```
ImportError: cannot import name 'signal_generator'
column stop_loss_reason does not exist
AttributeError: 'NoneType' object has no attribute
```

---

## 📊 **ОЖИДАТЬ ПЕРВОГО СИГНАЛА**

```bash
tail -f bot_production.log | grep "SIGNAL CREATED"
```

**Новая система СТРОЖЕ:**
- Требует R/R >= 0.8
- Отклоняет стоп > 1.5%
- Требует четкие уровни в стакане
- Требует имбаланс >= 0.25

**Сигналов будет МЕНЬШЕ, но КАЧЕСТВЕННЕЕ!**

---

## 🔍 **TELEGRAM УВЕДОМЛЕНИЕ**

```
🔔 НОВЫЙ СИГНАЛ - LONG
Symbol: BTCUSDT
Priority: HIGH (imbalance: 0.37)

📊 Входные данные:
Entry: 43000.00
Stop: 42794.00 (-0.48%)
TP1: 43800.00 (+1.86%)
TP2: 44500.00 (+3.49%)

💡 Обоснование:
Stop: Below support at 42800
TP1: First resistance at 43800
TP2: Second resistance at 44500

📈 Risk/Reward: 3.88
Quality Score: 85/100
```

---

## 🚨 **ЕСЛИ БОТ НЕ ЗАПУСКАЕТСЯ**

### **Ошибка: `ImportError: cannot import name 'signal_generator'`**

**Причина:** Код не обновился или git pull не сработал

**Решение:**
```bash
cd /root/BinanceFuturesBot
git fetch origin
git reset --hard origin/main
./start_bot.sh
```

---

### **Ошибка: `column stop_loss_reason does not exist`**

**Причина:** Миграция БД не применена

**Решение:**
```bash
./stop_bot.sh
source .env
psql "$DATABASE_URL" -f migrations/002_add_dynamic_sltp_columns.sql
./start_bot.sh
```

---

### **Ошибка: `AttributeError: 'NoneType' object has no attribute 'atr'`**

**Причина:** Нет данных klines для расчета ATR

**Решение:** Подождать 15-20 минут накопления данных

---

## 📈 **МОНИТОРИНГ (48 ЧАСОВ)**

После запуска мониторить через Telegram команду `/alltime`:

**Ожидаемые результаты:**
```
✅ Total Signals: 50-80 (было 200+)
✅ Win Rate: 55-65% (было 38.6%)
✅ Avg R/R: 2.0-3.0 (не контролировалось)
✅ Total PnL: положительный (было -1.83%)
✅ HIGH priority: 15-25 сигналов (имбаланс 0.35+)
✅ MEDIUM priority: 30-40 сигналов (имбаланс 0.30-0.34)
✅ LOW priority: 10-20 сигналов (имбаланс 0.25-0.29)
```

---

## 🎯 **ФИНАЛЬНЫЙ CHECKLIST**

- [ ] Backup БД создан
- [ ] Бот остановлен
- [ ] Миграция 001 применена
- [ ] Миграция 002 применена
- [ ] Новые файлы на месте (5 модулей)
- [ ] Старая статистика очищена
- [ ] Бот запущен
- [ ] Логи без ошибок
- [ ] Первый сигнал получен в Telegram

---

**Deployment Date:** _______________  
**Status:** ⬜ Ready / ⬜ Running / ⬜ Tested  

**После 48 часов работы отпиши результаты!** 🚀
