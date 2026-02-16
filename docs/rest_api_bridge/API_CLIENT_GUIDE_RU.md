# REST API манипулятора - Руководство для клиента

Полное руководство по интеграции с REST API роботизированной системы управления медикаментами.

## Базовая информация

**Базовый URL:**
```
http://<robot-ip>:8080/api/v1
```

**Формат данных:** JSON

**Кодировка:** UTF-8

**Аутентификация:** JWT (JSON Web Token)

---

## Быстрый старт

### 1. Получение токена доступа

Перед использованием API необходимо получить токен доступа.

**Запрос:**
```http
POST /api/v1/auth/token
Content-Type: application/json

{
  "client_id": "wms_system",
  "client_secret": "ваш_секретный_ключ"
}
```

**Ответ (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Параметры ответа:**
- `access_token` - JWT токен для авторизации запросов
- `token_type` - Тип токена (всегда "bearer")
- `expires_in` - Время жизни токена в секундах (по умолчанию 3600 = 1 час)

### 2. Использование токена

Полученный токен необходимо передавать в заголовке всех последующих запросов:

```http
Authorization: Bearer <access_token>
```

**Пример с curl:**
```bash
curl http://<robot-ip>:8080/api/v1/is_ready \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## Проверка состояния системы

### Проверка доступности API

**Эндпоинт:** `GET /health`

**Аутентификация:** Не требуется

**Описание:** Проверка работоспособности REST API сервера.

**Запрос:**
```http
GET /api/v1/health
```

**Ответ (200 OK):**
```json
{
  "status": "ok"
}
```

**Использование:** Используйте для проверки доступности API перед началом работы или для мониторинга.

---

### Проверка готовности робота

**Эндпоинт:** `GET /is_ready`

**Аутентификация:** Требуется

**Описание:** Проверка готовности всех модулей роботизированной системы к работе.

**Запрос:**
```http
GET /api/v1/is_ready
Authorization: Bearer <token>
```

**Ответ (200 OK) - Система готова:**
```json
{
  "status": "ok"
}
```

**Ответ (200 OK) - Система не готова:**
```json
{
  "status": "not ready"
}
```

**Важно:** Перед началом работы с роботом **обязательно** убедитесь, что система вернула `"status": "ok"`.

---

## Работа с контейнерами

### Получение контейнера

**Эндпоинт:** `POST /getcontainer`

**Аутентификация:** Требуется

**Описание:** Запуск задачи захвата контейнера и установки его на платформу робота.

**Запрос:**
```http
POST /api/v1/getcontainer
Authorization: Bearer <token>
Content-Type: application/json

{
  "unload": false
}
```

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| unload | boolean | Да | Тип контейнера:<br>`false` - контейнер для загрузки медикаментов<br>`true` - контейнер для выгрузки медикаментов |

**Ответ (202 Accepted):**
```json
{
  "status": "ok",
  "accepted": true
}
```

**Коды ответов:**
- `202` - Задача принята в обработку
- `400` - Неверные параметры запроса
- `403` - Ошибка авторизации
- `409` - Конфликт состояния (например, уже выполняется другая задача)

**Получение результата:**

После получения ответа `202` необходимо опрашивать эндпоинт `/task/status` для получения информации о ходе выполнения и результата:

```http
GET /api/v1/task/status
Authorization: Bearer <token>
```

При успешном выполнении задачи в поле `task.container_id` будет содержаться QR-код полученного контейнера.

**Пример:**
```json
{
  "status": "ok",
  "task": {
    "task_id": "38b32a48-30a0-4be3-8c1d-fae9d11af94e",
    "progress": 100,
    "current_operation": "getcontainer",
    "finished_at": "2026-02-16T10:20:53.623185",
    "error_code": null,
    "message": "Контейнер успешно получен",
    "container_id": "CNT-BBADD933",
    "medicine_qr": []
  }
}
```

---

### Возврат контейнера

**Эндпоинт:** `GET /retcontainer`

**Аутентификация:** Требуется

**Описание:** Запуск задачи возврата контейнера с платформы робота на склад.

**Важно:** Это GET запрос с параметром в URL, а не POST!

**Запрос:**
```http
GET /api/v1/retcontainer?unload=true
Authorization: Bearer <token>
```

**Параметры запроса (query string):**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| unload | boolean | Да | Тип контейнера:<br>`false` - контейнер загрузки<br>`true` - контейнер выгрузки |

**Ответ (202 Accepted):**
```json
{
  "status": "ok",
  "accepted": true
}
```

**Коды ответов:**
- `202` - Задача принята в обработку
- `400` - Неверные параметры запроса
- `403` - Ошибка авторизации
- `409` - Конфликт состояния

---

## Работа с медикаментами

### Извлечение медикаментов

**Эндпоинт:** `POST /get_items`

**Аутентификация:** Требуется

**Описание:** Запуск задачи извлечения медикаментов из указанного ящика склада.

**Запрос:**
```http
POST /api/v1/get_items
Authorization: Bearer <token>
Content-Type: application/json

{
  "medicine_list": [
    {
      "image_id": "med-001",
      "raw_id": 0
    },
    {
      "image_id": "med-002",
      "raw_id": 1
    }
  ],
  "box_id": "BOX-12345",
  "task_id": "task-get-001"
}
```

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| medicine_list | array | Да | Список медикаментов для извлечения |
| medicine_list[].image_id | string | Да | Идентификатор изображения медикамента |
| medicine_list[].raw_id | integer | Да | Номер ряда в ящике (начиная с 0) |
| box_id | string | Да | Уникальный идентификатор ящика на складе |
| task_id | string | Да | Уникальный идентификатор задачи |

**Ответ (202 Accepted):**
```json
{
  "status": "ok",
  "accepted": true
}
```

**Коды ответов:**
- `202` - Задача принята в обработку
- `400` - Неверные параметры запроса
- `403` - Ошибка авторизации
- `409` - Конфликт состояния
- `422` - Ошибка валидации данных
- `500` - Внутренняя ошибка сервера

**Получение результата:**

После выполнения задачи в `/task/status` поле `task.medicine_qr` будет содержать массив DataMatrix кодов извлеченных медикаментов:

```json
{
  "status": "ok",
  "task": {
    "task_id": "task-get-001",
    "progress": 100,
    "current_operation": "get_items",
    "finished_at": "2026-02-16T10:21:03.843513",
    "error_code": null,
    "message": "Извлечено 2 медикамента из BOX-12345",
    "medicine_qr": [
      "DM-FB75BFD1A76A",
      "DM-8781738E8D5F"
    ],
    "container_id": null
  }
}
```

**Важно:** Порядок кодов в массиве `medicine_qr` соответствует порядку медикаментов в исходном запросе `medicine_list`.

---

### Размещение медикаментов

**Эндпоинт:** `POST /put_items`

**Аутентификация:** Требуется

**Описание:** Запуск задачи размещения медикаментов в указанный ящик склада.

**Запрос:**
```http
POST /api/v1/put_items
Authorization: Bearer <token>
Content-Type: application/json

{
  "medicine_list": [
    {
      "image_id": "med-001",
      "cell_id": 0,
      "row_id": 2,
      "position": {
        "x_side": 0.5,
        "y_side": 1.2
      }
    },
    {
      "image_id": "med-003",
      "cell_id": 1,
      "row_id": 3,
      "position": {
        "x_side": 1.0,
        "y_side": 0.8
      }
    }
  ],
  "box_id": "BOX-67890",
  "task_id": "task-put-001"
}
```

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| medicine_list | array | Да | Список медикаментов для размещения |
| medicine_list[].image_id | string | Да | Идентификатор изображения медикамента |
| medicine_list[].cell_id | integer | Да | Номер ячейки в контейнере |
| medicine_list[].row_id | integer | Да | Номер ряда в ящике |
| medicine_list[].position | object | Да | Координаты размещения в ряду |
| medicine_list[].position.x_side | float | Да | Координата X (в мм или относительных единицах) |
| medicine_list[].position.y_side | float | Да | Координата Y (в мм или относительных единицах) |
| box_id | string | Да | Уникальный идентификатор ящика на складе |
| task_id | string | Да | Уникальный идентификатор задачи |

**Ответ (202 Accepted):**
```json
{
  "status": "ok",
  "accepted": true
}
```

**Коды ответов:**
- `202` - Задача принята в обработку
- `400` - Неверные параметры запроса
- `403` - Ошибка авторизации
- `409` - Конфликт состояния
- `422` - Ошибка валидации данных
- `500` - Внутренняя ошибка сервера

---

## Управление задачами

### Получение статуса задачи

**Эндпоинт:** `GET /task/status`

**Аутентификация:** Требуется

**Описание:** Получение информации о текущей или последней выполненной задаче.

**Запрос:**
```http
GET /api/v1/task/status
Authorization: Bearer <token>
```

**Ответ (200 OK):**
```json
{
  "status": "ok",
  "task": {
    "task_id": "task-001",
    "progress": 100,
    "current_operation": "get_items",
    "started_at": "2026-02-16T10:21:03.843498",
    "updated_at": "2026-02-16T10:21:03.843509",
    "finished_at": "2026-02-16T10:21:03.843513",
    "error_code": null,
    "message": "Извлечено 2 медикамента из BOX-12345",
    "medicine_qr": [
      "DM-FB75BFD1A76A",
      "DM-8781738E8D5F"
    ],
    "container_id": null
  }
}
```

**Поля объекта task:**

| Поле | Тип | Описание |
|------|-----|----------|
| task_id | string | Уникальный идентификатор задачи |
| progress | integer | Прогресс выполнения (0-100) |
| current_operation | string | Текущая операция: `getcontainer`, `retcontainer`, `get_items`, `put_items`, `is_ready` |
| started_at | string | Время начала задачи (ISO 8601) |
| updated_at | string | Время последнего обновления (ISO 8601) |
| finished_at | string\|null | Время завершения задачи (ISO 8601) или null если не завершена |
| error_code | string\|null | Код ошибки или null если ошибок нет |
| message | string | Сообщение о состоянии или описание ошибки |
| medicine_qr | array | Массив DataMatrix кодов извлеченных медикаментов (заполняется после `get_items`) |
| container_id | string\|null | QR-код полученного контейнера (заполняется после `getcontainer`) |

**Состояния задачи:**

- `progress: 0-99, finished_at: null` - Задача выполняется
- `progress: 100, finished_at: "...", error_code: null` - Задача успешно завершена
- `error_code: "..."` - Задача завершена с ошибкой

---

### Отмена задачи

**Эндпоинт:** `GET /task/cancel`

**Аутентификация:** Требуется

**Описание:** Отмена текущей выполняемой задачи.

**Запрос:**
```http
GET /api/v1/task/cancel
Authorization: Bearer <token>
```

**Ответ (200 OK):**
```json
{
  "status": "ok"
}
```

**Коды ответов:**
- `200` - Команда отмены отправлена
- `403` - Ошибка авторизации
- `409` - Нет активной задачи для отмены

**Важно:**
- Отмена может произойти не мгновенно, робот завершит текущее безопасное движение
- После отмены проверьте статус через `/task/status`

---

## Типичные сценарии использования

### Сценарий 1: Извлечение медикаментов из склада

**Шаг 1. Аутентификация**
```bash
curl -X POST http://robot-ip:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "wms_system",
    "client_secret": "ваш_секрет"
  }'
```

Сохраните полученный `access_token`.

**Шаг 2. Проверка готовности системы**
```bash
curl http://robot-ip:8080/api/v1/is_ready \
  -H "Authorization: Bearer <token>"
```

Ожидаемый ответ: `{"status": "ok"}`

**Шаг 3. Получение контейнера**
```bash
curl -X POST http://robot-ip:8080/api/v1/getcontainer \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}'
```

Ожидаемый ответ: `{"status": "ok", "accepted": true}`

**Шаг 4. Ожидание получения контейнера**

Опрашивайте статус каждые 2-5 секунд:
```bash
curl http://robot-ip:8080/api/v1/task/status \
  -H "Authorization: Bearer <token>"
```

Ждите `progress: 100` и сохраните `container_id`.

**Шаг 5. Извлечение медикаментов**
```bash
curl -X POST http://robot-ip:8080/api/v1/get_items \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [
      {"image_id": "med-001", "raw_id": 0},
      {"image_id": "med-002", "raw_id": 1}
    ],
    "box_id": "BOX-12345",
    "task_id": "wms-task-123"
  }'
```

**Шаг 6. Ожидание извлечения**

Опрашивайте статус:
```bash
curl http://robot-ip:8080/api/v1/task/status \
  -H "Authorization: Bearer <token>"
```

При `progress: 100` сохраните массив `medicine_qr` - это DataMatrix коды извлеченных медикаментов.

**Шаг 7. Возврат контейнера**
```bash
curl "http://robot-ip:8080/api/v1/retcontainer?unload=false" \
  -H "Authorization: Bearer <token>"
```

**Шаг 8. Ожидание возврата**

Опрашивайте статус до `progress: 100`.

---

### Сценарий 2: Размещение медикаментов на склад

**Шаги 1-4:** Аналогично сценарию 1 (аутентификация, проверка, получение контейнера)

**Шаг 5. Размещение медикаментов**
```bash
curl -X POST http://robot-ip:8080/api/v1/put_items \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [
      {
        "image_id": "med-001",
        "cell_id": 0,
        "row_id": 2,
        "position": {"x_side": 0.5, "y_side": 1.2}
      }
    ],
    "box_id": "BOX-67890",
    "task_id": "wms-task-456"
  }'
```

**Шаг 6-8:** Ожидание размещения и возврат контейнера (аналогично сценарию 1)

---

## Обработка ошибок

### Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "status": "error",
  "error_code": "validation_error",
  "message": "Подробное описание ошибки"
}
```

### Коды HTTP статусов

| Код | Значение | Действие |
|-----|----------|----------|
| 200 | Успешный запрос | Обработать результат |
| 202 | Задача принята | Опрашивать `/task/status` |
| 400 | Неверные параметры | Проверить формат запроса |
| 403 | Ошибка авторизации | Получить новый токен |
| 409 | Конфликт состояния | Дождаться завершения текущей задачи |
| 422 | Ошибка валидации | Проверить типы и значения полей |
| 500 | Ошибка сервера | Повторить запрос позже или обратиться в поддержку |

### Типичные ошибки

**1. Истек срок действия токена (403)**

Симптом:
```json
{
  "detail": "Invalid authentication credentials"
}
```

Решение: Получите новый токен через `/auth/token`

**2. Задача уже выполняется (409)**

Симптом:
```json
{
  "status": "error",
  "error_code": "task_in_progress",
  "message": "Cannot start new task: another task is in progress"
}
```

Решение:
- Дождитесь завершения текущей задачи
- Или отмените её через `/task/cancel`

**3. Неверный формат данных (422)**

Симптом:
```json
{
  "detail": [
    {
      "loc": ["body", "medicine_list", 0, "raw_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

Решение: Проверьте структуру JSON запроса согласно документации

---

