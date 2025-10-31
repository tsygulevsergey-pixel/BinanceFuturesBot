# 🚀 DYNAMIC SL/TP SYSTEM - DEPLOYMENT GUIDE

## ⚠️ **КРИТИЧЕСКИ ВАЖНО: МИГРАЦИЯ БД ПЕРЕД ДЕПЛОЕМ КОДА!**

**Новый код УПАДЕТ если в БД нет новых колонок!**

---

## 📋 **ЧТО ИЗМЕНИЛОСЬ:**

### **РАНЬШЕ (Фиксированные %):**
```
Entry: 43000
Stop: -2% → 42140
TP1: +2% → 43860
TP2: +3% → 44290
```
❌ Не учитывает рыночную структуру
❌ Стоп может быть ВНУТРИ зоны поддержки
❌ TP может быть ПЕРЕД сопротивлением

### **ТЕПЕРЬ (Динамические уровни):**
```
Entry: 43000
Stop: 42794 (ЗА support кластером 42800)
TP1: 43800 (НА resistance кластере)
TP2: 44500 (НА следующем resistance)
R/R: 3.88 (риск 206, профит 800)
```
✅ Стоп за реальным уровнем поддержки
✅ TP на реальных зонах сопротивления
✅ Учитывает ATR волатильность
✅ Фильтрует по R/R >= 0.8

---

## 🔧 **DEPLOYMENT STEPS (ТОЧНЫЙ ПОРЯДОК!)**

### **Step 1: BACKUP DATABASE (ОБЯЗАТЕЛЬНО!) ✅**

```bash
# SSH на VPS
ssh root@your_vps_ip

# Создать backup
pg_dump $DATABASE_URL > ~/backup_before_dynamic_sltp_$(date +%Y%m%d).sql

# Проверить backup
ls -lh ~/backup_before_dynamic_sltp_*
```

### **Step 2: STOP BOT ✅**

```bash
cd /root/BinanceFuturesBot
./stop_bot.sh

# Убедиться что бот остановлен
ps aux | grep python  # НЕ должно показать процессы бота
```

### **Step 3: RUN DATABASE MIGRATIONS ✅**

**ВАЖНО: Запустить ОБЕ миграции по порядку!**

```bash
cd /root/BinanceFuturesBot

# Загрузить env переменные
source .env

# Миграция 1: Partial close columns (если ещё не применена)
psql "$DATABASE_URL" -f migrations/001_add_partial_close_columns.sql

# Миграция 2: Dynamic SL/TP reasoning columns (НОВАЯ!)
psql "$DATABASE_URL" -f migrations/002_add_dynamic_sltp_columns.sql
```

**Проверка успешности миграции:**
```sql
psql "$DATABASE_URL" -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'signals' AND column_name LIKE '%reason%';"

# Должно показать:
#  column_name
# ----------------
# stop_loss_reason
# tp1_reason
# tp2_reason
```

### **Step 4: PULL NEW CODE ✅**

```bash
# Получить последний код
git pull origin main

# Проверить что новые файлы присутствуют
ls -lh bot/modules/volatility_calculator.py  # Должен существовать
ls -lh bot/modules/orderbook_levels_analyzer.py  # Должен существовать
ls -lh bot/modules/dynamic_stop_loss_finder.py  # Должен существовать
ls -lh bot/modules/dynamic_take_profit_finder.py  # Должен существовать
ls -lh bot/modules/signal_validator.py  # Должен существовать
```

### **Step 5: CLEAR OLD STATISTICS (РЕКОМЕНДУЕТСЯ) ✅**

```bash
# Очистить старую статистику для чистого старта
source .env
psql "$DATABASE_URL" -c 'TRUNCATE TABLE trades, signals, performance_metrics, daily_stats CASCADE;'

# Это гарантирует чистые данные с новой системой
```

### **Step 6: START BOT ✅**

```bash
# Запустить бота с новым кодом
./start_bot.sh

# Мониторить логи на старте
tail -f bot_production.log | head -100
```

---

## 🔍 **POST-DEPLOYMENT VERIFICATION**

### **1. Проверить что бот запущен:**
```bash
ps aux | grep python  # Должен показать процесс бота
```

### **2. Мониторить логи на ошибки:**
```bash
tail -100 bot_production.log

# Хорошие признаки:
# ✅ "VolatilityCalculator initialized"
# ✅ "OrderbookLevelsAnalyzer initialized"
# ✅ "SignalValidator initialized"
# ✅ Нет SQL ошибок про missing columns

# Плохие признаки:
# ❌ "column stop_loss_reason does not exist"
# ❌ "AttributeError"
# ❌ "OperationalError"
```

### **3. Дождаться первого сигнала (займет время!):**
```bash
tail -f bot_production.log | grep "SIGNAL CREATED"

# Новая система более строгая:
# - Требует имбаланс >= 0.25
# - Требует 2+ крупных сделок
# - Требует R/R >= 0.8
# - Отклоняет если стоп > 1.5%
```

### **4. Проверить Telegram уведомления:**
```
Должны содержать:
- Entry, Stop, TP1, TP2
- R/R ratio
- Stop reason: "Below support at..."
- TP reasons: "First resistance at..."
- Priority: HIGH/MEDIUM/LOW
```

---

## 📊 **EXPECTED CHANGES**

### **Signal Quality:**
- **РАНЬШЕ:** ~200 сигналов/день, многие низкокачественные
- **ТЕПЕРЬ:** ~50-80 сигналов/день, все с R/R >= 0.8 ✅

### **Stop Loss Placement:**
- **РАНЬШЕ:** Фиксированные -2% (могут быть внутри поддержки)
- **ТЕПЕРЬ:** За кластерами поддержки из стакана ✅

### **Take Profit Placement:**
- **РАНЬШЕ:** Фиксированные +2%/+3%
- **ТЕПЕРЬ:** На реальных уровнях сопротивления ✅

### **Signal Rejection:**
- **РАНЬШЕ:** Принимались все сигналы с имбалансом
- **ТЕПЕРЬ:** Отклоняются если:
  - R/R < 0.8
  - Стоп > 1.5% от входа
  - Нет четких уровней в стакане
  - Слабый имбаланс (<0.25)
  - Мало крупных сделок (<2)

### **Telegram Messages:**
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

⚠️ Max stop distance: 0.48% ✅
```

---

## 🚨 **ROLLBACK PROCEDURE (ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК)**

### **Если бот падает или SQL ошибки:**

1. **Остановить бота:**
```bash
./stop_bot.sh
```

2. **Восстановить БД из backup:**
```bash
source .env
# ОСТОРОЖНО: Удаляет таблицы!
psql "$DATABASE_URL" -c "DROP TABLE IF EXISTS signals CASCADE; DROP TABLE IF EXISTS trades CASCADE;"

# Восстановить из backup
psql "$DATABASE_URL" < ~/backup_before_dynamic_sltp_*.sql
```

3. **Откатить код:**
```bash
git checkout HEAD~1  # Вернуться на предыдущий коммит
./start_bot.sh
```

---

## 🎯 **SUCCESS METRICS (48 ЧАСОВ ПОСЛЕ ДЕПЛОЯ)**

Мониторить через `/alltime` Telegram команду:

```
✅ Total Signals: 80-120 (было 200+)
✅ Win Rate: 55-65% (цель улучшения)
✅ Avg R/R: 2.0-3.0 (было не контролировалось)
✅ Total PnL: положительный
✅ Priority HIGH: 20-30 сигналов (имбаланс 0.35+)
✅ Priority MEDIUM: 40-60 сигналов (имбаланс 0.30-0.34)
✅ Priority LOW: 20-30 сигналов (имбаланс 0.25-0.29)
```

---

## 📞 **TROUBLESHOOTING**

### **Problem: Бот падает на старте**
**Symptom:** `column stop_loss_reason does not exist`
**Solution:** Запустить миграцию заново (Step 3)

### **Problem: Нет сигналов вообще**
**Symptom:** Несколько часов без сигналов
**Причина:** Новые фильтры очень строгие
**Check:** 
```bash
tail -200 bot_production.log | grep "REJECTED"
# Смотреть причины отклонения
```
**Solution:** Нормально. Система отфильтровывает слабые сигналы.

### **Problem: Все сигналы LOW priority**
**Symptom:** Нет HIGH/MEDIUM сигналов
**Причина:** Имбаланс < 0.30
**Solution:** Подождать более сильных движений рынка

### **Problem: AttributeError в логах**
**Symptom:** `'NoneType' object has no attribute 'atr'`
**Причина:** Нет исторических данных klines для расчета ATR
**Solution:** Дождаться накопления данных (~20 минут)

---

## 🔧 **CONFIGURATION TUNING (ПОСЛЕ ТЕСТИРОВАНИЯ)**

После 48 часов работы, можно подстроить параметры в `bot/config/config.py`:

```python
# Если СЛИШКОМ МАЛО сигналов:
ORDERBOOK_IMBALANCE_THRESHOLD = 0.20  # Снизить с 0.25
MIN_RR_RATIO = 0.6  # Снизить с 0.8

# Если СЛИШКОМ МНОГО сигналов:
ORDERBOOK_IMBALANCE_THRESHOLD = 0.30  # Поднять
MIN_RR_RATIO = 1.0  # Поднять

# Если стопы СЛИШКОМ ШИРОКИЕ:
MAX_STOP_DISTANCE_PCT = 1.0  # Снизить с 1.5

# Если стопы СЛИШКОМ УЗКИЕ (частые SL hits):
MAX_STOP_DISTANCE_PCT = 2.0  # Поднять
```

После изменений:
```bash
./stop_bot.sh
./start_bot.sh
```

---

## ✅ **FINAL CHECKLIST**

После 48 часов работы:

- [ ] Нет SQL ошибок в логах
- [ ] Сигналы создаются с динамическими SL/TP
- [ ] Telegram сообщения содержат reasoning
- [ ] Priority система работает (HIGH/MEDIUM/LOW)
- [ ] Win rate улучшился vs фиксированных %
- [ ] R/R ratio >= 0.8 для всех сигналов
- [ ] Стопы размещены за уровнями (не внутри)

---

**Deployment Date:** _______________  
**Deployed By:** _______________  
**Backup Location:** ~/backup_before_dynamic_sltp_*.sql  
**Migrations Applied:** 001 + 002  

**Status:** ⬜ Pending / ⬜ In Progress / ⬜ Completed / ⬜ Rolled Back
