-- =====================================================================
--  10 тестовых заявок для проверки приоритизации лидов (часть 3).
--  Ожидаемо: 4 горячих (🔥), 3 тёплых (🌤), 3 холодных (❄️).
--
--  Баллы считает backend/app/services/lead_scoring.py (максимум 100):
--    бюджет к максимуму услуги до 30 · срок до 25 · размер компании до 15 ·
--    роль до 10 · объём задачи до 10 · ниша до 10.
--    hot ≥ 70, warm 40–69, cold < 40.
--
--  Услуги ищутся ПО НАЗВАНИЮ подзапросом, поэтому сначала создайте 5 услуг
--  (вручную в таблице админки или make seed). Нет услуги → service_id = NULL.
--
--  Запуск:  make test-sql
--     или:  docker compose exec -T postgres psql -U autello -d autello < sql/test_applications.sql
--     или:  pgAdmin → Query Tool → вставить файл → F5
--  Повторный запуск безопасен: сначала удаляются прежние тестовые заявки (по метке [тест-SQL]).
--  Тот же файл читает pytest (backend/tests/test_lead_scoring.py) — не меняйте формат INSERT.
-- =====================================================================

BEGIN;

DELETE FROM applications WHERE comment LIKE '[тест-SQL]%';

-- ---------------------------------------------------------------------
--  🔥 ГОРЯЧИЕ: у каждой своя сильная сторона
-- ---------------------------------------------------------------------

-- 🔥 1. ОГРОМНЫЙ БЮДЖЕТ. Частник с Bentley, 600 000 ₽ на PPF — потолок услуги.
--    бюджет 30 + неделя 18 + «только я» 2 + собственник 10 + 1 авто 2 + премиум-частник 10 = 72
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Воронцов', 'Аркадий', 'Львович', '+7 903 111-22-33', 'a.vorontsov@mail.ru', (SELECT id FROM admin_settings WHERE services = 'Оклейка плёнкой PPF'), 'Частный владелец', 'Только я', 'Разовая услуга', 'собственник', '1 автомобиль', 'В течение недели', 'Защита нового автомобиля', 'Комплекс услуг', '600000', 'phone', 'День, 12:00–17:00', '[тест-SQL] Bentley Bentayga 2025, полная оклейка матовым PPF до выдачи из салона', now() - interval '1 day');

-- 🔥 2. СРОЧНО + РУКОВОДИТЕЛЬ. Владелец детейлинг-центра, керамика «как можно скорее».
--    бюджет 80% → 24 + срочно 25 + 11–50 чел. 9 + руководитель 10 + 2–5 авто 5 + детейлинг 8 = 81
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Кравцова', 'Марина', 'Олеговна', '+7 916 222-33-44', 'm.kravtsova@shine-detail.ru', (SELECT id FROM admin_settings WHERE services = 'Керамическое покрытие'), 'Детейлинг-центр', '11–50 человек', 'Несколько раз в год', 'руководитель', '2–5 автомобилей', 'Как можно скорее', 'Защита нового автомобиля', 'Корпоративный договор', '200000', 'telegram', 'Утро, 9:00–12:00', '[тест-SQL] Нужен подрядчик по керамике на поток: клиенты ждут, своих мастеров не хватает', now() - interval '2 hours');

-- 🔥 3. КРУПНЫЙ АВТОСАЛОН. Бюджет средний и срок не горит, но компания 200+ и регулярный поток машин.
--    бюджет 67% → 18 + месяц 10 + более 200 чел. 15 + руководитель 10 + 6–20 авто 8 + автосалон 10 = 71
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Шестаков', 'Глеб', 'Андреевич', '+7 495 333-44-55', 'g.shestakov@major-auto.ru', (SELECT id FROM admin_settings WHERE services = 'Полировка кузова'), 'Автосалон', 'Более 200 человек', 'Регулярное обслуживание автопарка', 'руководитель', '6–20 автомобилей', 'В течение месяца', 'Предпродажная подготовка', 'Корпоративный договор', '40000', 'email', NULL, '[тест-SQL] Дилерский центр: предпродажная полировка машин с пробегом, 10–15 авто в месяц', now() - interval '3 days');

-- 🔥 4. ТАКСОПАРК С БОЛЬШИМ ОБЪЁМОМ. Пишет рядовой сотрудник, но парк 20+ машин и срок — неделя.
--    бюджет 75% → 24 + неделя 18 + 51–200 чел. 12 + сотрудник 4 + более 20 авто 10 + такси-парк 10 = 78
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Гусейнов', 'Тимур', 'Рашидович', '+7 925 444-55-66', 't.guseynov@citycab.ru', (SELECT id FROM admin_settings WHERE services = 'Химчистка салона'), 'Такси-парк', '51–200 человек', 'Регулярное обслуживание автопарка', 'сотрудник', 'Более 20 автомобилей', 'В течение недели', 'Регулярный уход', 'Абонемент на уход', '30000', 'whatsapp', 'Вечер, 17:00–21:00', '[тест-SQL] Парк Kia K5 и Skoda Octavia, 35 машин: химчистка раз в квартал', now() - interval '5 days');

-- ---------------------------------------------------------------------
--  🌤 ТЁПЛЫЕ: интерес есть, но чего-то не хватает (срока, бюджета или полномочий)
-- ---------------------------------------------------------------------

-- 🌤 5. Частник с обычной машиной: бюджет и срок нормальные, но объём — одна машина.
--    бюджет 58% → 18 + неделя 18 + «только я» 2 + собственник 10 + 1 авто 2 + частник 5 = 55
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Лаптева', 'Светлана', 'Игоревна', '+7 912 555-66-77', NULL, (SELECT id FROM admin_settings WHERE services = 'Полировка кузова'), 'Частный владелец', 'Только я', 'Разовая услуга', 'собственник', '1 автомобиль', 'В течение недели', 'Восстановление внешнего вида', 'Только выбранная услуга', '35000', 'phone', NULL, '[тест-SQL] Kia K5 2021, мелкие царапины после автомойки', now() - interval '6 days');

-- 🌤 6. Небольшой детейлинг: руководитель, но бюджет ниже половины и срок — месяц.
--    бюджет 48% → 10 + месяц 10 + 2–10 чел. 5 + руководитель 10 + 2–5 авто 5 + детейлинг 8 = 48
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Ершов', 'Денис', 'Валерьевич', '+7 921 666-77-88', 'd.ershov@detailbox.ru', (SELECT id FROM admin_settings WHERE services = 'Керамическое покрытие'), 'Детейлинг-центр', '2–10 человек', 'Несколько раз в год', 'руководитель', '2–5 автомобилей', 'В течение месяца', 'Защита нового автомобиля', 'Комплекс услуг', '120000', 'telegram', NULL, '[тест-SQL] Хотим отдавать на аутсорс керамику для пары клиентов в месяц', now() - interval '12 days');

-- 🌤 7. Автосалон без спешки: пишет сотрудник, бюджет 42% от максимума, «не срочно».
--    бюджет 42% → 10 + не срочно 3 + 51–200 чел. 12 + сотрудник 4 + 6–20 авто 8 + автосалон 10 = 47
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Миронова', 'Алина', 'Сергеевна', '+7 931 777-88-99', 'a.mironova@autocenter-sever.ru', (SELECT id FROM admin_settings WHERE services = 'Оклейка плёнкой PPF'), 'Автосалон', '51–200 человек', 'Несколько раз в год', 'сотрудник', '6–20 автомобилей', 'Не срочно', 'Защита нового автомобиля', 'Корпоративный договор', '250000', 'email', 'День, 12:00–17:00', '[тест-SQL] Собираю предложения для руководителя: PPF на демо-автомобили', now() - interval '20 days');

-- ---------------------------------------------------------------------
--  ❄️ ХОЛОДНЫЕ: маленький бюджет, нет срока, не наша ниша или почти пустая заявка
-- ---------------------------------------------------------------------

-- ❄️ 8. Бюджет на минимуме услуги и «не срочно».
--    бюджет 30% → 10 + не срочно 3 + «только я» 2 + собственник 10 + 1 авто 2 + частник 5 = 32
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Пахомов', 'Илья', NULL, '+7 905 888-99-00', NULL, (SELECT id FROM admin_settings WHERE services = 'Химчистка салона'), 'Частный владелец', 'Только я', 'Разовая услуга', 'собственник', '1 автомобиль', 'Не срочно', 'Регулярный уход', 'Только выбранная услуга', '12000', 'whatsapp', NULL, '[тест-SQL] Hyundai Solaris, просто узнать цену', now() - interval '9 days');

-- ❄️ 9. Дорогая услуга, но бюджет 18% от её максимума, ниша «другое».
--    бюджет 18% → 4 + месяц 10 + «только я» 2 + сотрудник 4 + 1 авто 2 + другое 2 = 24
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Зуева', 'Ксения', 'Павловна', '+7 977 999-00-11', 'k.zueva@yandex.ru', (SELECT id FROM admin_settings WHERE services = 'Установка аудиосистемы Bose премиум'), 'Другое', 'Только я', 'Разовая услуга', 'сотрудник', '1 автомобиль', 'В течение месяца', 'Восстановление внешнего вида', 'Только выбранная услуга', '90000', 'email', NULL, '[тест-SQL] Служебная машина, подбираю варианты для отдела снабжения', now() - interval '25 days');

-- ❄️ 10. Почти пустая заявка: ни бюджета, ни срока, ни размера компании.
--    бюджет 0 + срок не указан 5 + размер 0 + сотрудник 4 + объём 0 + каршеринг 6 = 15
INSERT INTO applications (last_name, first_name, middle_name, phone, email, service_id, business_niche, company_size, task_volume, role, need_volume, deadline, task_type, product_interest, budget, contact_method, contact_time, comment, created_at)
VALUES ('Сидоренко', 'Олег', NULL, '+7 999 000-11-22', NULL, (SELECT id FROM admin_settings WHERE services = 'Полировка кузова'), 'Каршеринг / прокат', NULL, NULL, 'сотрудник', NULL, NULL, NULL, NULL, NULL, 'phone', NULL, '[тест-SQL] Перезвоните', now() - interval '28 days');

COMMIT;

-- Проверка: 10 строк с меткой
SELECT id, last_name, business_niche, budget, deadline, role
FROM applications WHERE comment LIKE '[тест-SQL]%' ORDER BY id;
