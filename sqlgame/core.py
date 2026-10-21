"""SQLite-backed game logic for SQL Quest."""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
GAME_DB = DATA_DIR / "sql_quest.sqlite3"
LAB_DB = DATA_DIR / "laboratory.sqlite3"
GENERATED_DIR = DATA_DIR / "generated"


@contextmanager
def _managed(conn: sqlite3.Connection):
    try:
        with conn:
            yield conn
    finally:
        conn.close()

DATABASES: dict[str, dict[str, Any]] = {
    "shop": {
        "name": "Магазин Byte&Bite",
        "description": "Покупатели, заказы и товары небольшого интернет-магазина.",
        "schema": """CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, city TEXT, joined_year INTEGER);
CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER);
CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER, product_id INTEGER, quantity INTEGER, order_date TEXT, status TEXT);""",
        "seed": """INSERT INTO customers VALUES
(1,'Аня','Москва',2022),(2,'Борис','Казань',2023),(3,'Вера','Москва',2021),(4,'Глеб','Томск',2024),(5,'Дина','Казань',2022);
INSERT INTO products VALUES
(1,'Клавиатура','Аксессуары',4500,12),(2,'Мышь','Аксессуары',2200,24),(3,'Кофе','Еда',650,40),(4,'Монитор','Техника',24000,5),(5,'Чай','Еда',420,30);
INSERT INTO orders VALUES
(1,1,1,1,'2025-01-04','delivered'),(2,1,3,2,'2025-01-10','delivered'),(3,2,2,1,'2025-01-12','shipped'),(4,3,4,1,'2025-02-02','delivered'),(5,4,5,3,'2025-02-14','cancelled'),(6,2,3,4,'2025-02-20','delivered'),(7,5,1,1,'2025-03-01','shipped'),(8,3,2,2,'2025-03-08','delivered');""",
    },
    "library": {
        "name": "Библиотека «Сова»",
        "description": "Книги, читатели, авторы и выдачи библиотеки.",
        "schema": """CREATE TABLE authors(id INTEGER PRIMARY KEY, name TEXT, country TEXT);
CREATE TABLE books(id INTEGER PRIMARY KEY, title TEXT, author_id INTEGER, genre TEXT, published_year INTEGER);
CREATE TABLE readers(id INTEGER PRIMARY KEY, name TEXT, city TEXT);
CREATE TABLE loans(id INTEGER PRIMARY KEY, book_id INTEGER, reader_id INTEGER, loan_date TEXT, returned INTEGER);""",
        "seed": """INSERT INTO authors VALUES (1,'А. Пушкин','Россия'),(2,'М. Булгаков','Россия'),(3,'А. Кристи','Великобритания'),(4,'У. Ле Гуин','США');
INSERT INTO books VALUES (1,'Капитанская дочка',1,'Роман',1836),(2,'Мастер и Маргарита',2,'Роман',1967),(3,'Убийство в Восточном экспрессе',3,'Детектив',1934),(4,'Левая рука тьмы',4,'Фантастика',1969),(5,'Десять негритят',3,'Детектив',1939);
INSERT INTO readers VALUES (1,'Лена','Москва'),(2,'Марк','Пермь'),(3,'Саша','Москва'),(4,'Таня','Омск');
INSERT INTO loans VALUES (1,1,1,'2025-03-01',1),(2,3,2,'2025-03-02',0),(3,2,1,'2025-03-05',0),(4,5,3,'2025-03-08',1),(5,4,4,'2025-03-10',0);""",
    },
    "games": {
        "name": "Pixel Arcade",
        "description": "Игры, игроки и результаты игрового клуба.",
        "schema": """CREATE TABLE players(id INTEGER PRIMARY KEY, nickname TEXT, country TEXT, level INTEGER);
CREATE TABLE games(id INTEGER PRIMARY KEY, title TEXT, genre TEXT, release_year INTEGER);
CREATE TABLE scores(id INTEGER PRIMARY KEY, player_id INTEGER, game_id INTEGER, points INTEGER, played_on TEXT);""",
        "seed": """INSERT INTO players VALUES (1,'fox','RU',18),(2,'pixel_cat','RU',25),(3,'neo','US',31),(4,'luna','JP',22),(5,'byte','DE',14);
INSERT INTO games VALUES (1,'Space Run','Arcade',2021),(2,'Dungeon SQL','Puzzle',2023),(3,'Kart Rush','Racing',2022),(4,'Tiny Farm','Simulation',2020);
INSERT INTO scores VALUES (1,1,1,4200,'2025-04-01'),(2,2,2,9100,'2025-04-01'),(3,3,1,7600,'2025-04-02'),(4,4,3,6800,'2025-04-03'),(5,1,2,5400,'2025-04-04'),(6,5,3,3100,'2025-04-04'),(7,2,1,8200,'2025-04-06'),(8,4,4,7300,'2025-04-07');""",
    },
}

MODULES = [
    {"id": "select", "name": "Основы SELECT", "icon": "⌘", "description": "Выбирай нужные строки и столбцы.", "topics": ["SELECT", "DISTINCT", "алиасы"]},
    {"id": "filtering", "name": "Фильтрация данных", "icon": "⌕", "description": "Точные условия, диапазоны и наборы значений.", "topics": ["WHERE", "AND/OR", "IN", "BETWEEN", "LIKE"]},
    {"id": "sorting", "name": "Сортировка и страницы", "icon": "⇅", "description": "Управляй порядком и размером результата.", "topics": ["ORDER BY", "ASC/DESC", "LIMIT", "OFFSET"]},
    {"id": "aggregate", "name": "Агрегатные функции", "icon": "∑", "description": "Считай итоги и сводные показатели.", "topics": ["COUNT", "SUM", "AVG", "MIN/MAX"]},
    {"id": "grouping", "name": "Группировка", "icon": "▦", "description": "Собирай строки в группы и фильтруй итоги.", "topics": ["GROUP BY", "HAVING"]},
    {"id": "joins", "name": "Связи и JOIN", "icon": "⇄", "description": "Собирай данные из нескольких таблиц.", "topics": ["INNER JOIN", "LEFT JOIN", "ON"]},
    {"id": "subqueries", "name": "Подзапросы", "icon": "⤴", "description": "Используй запрос как часть другого запроса.", "topics": ["IN", "EXISTS", "скалярные подзапросы"]},
    {"id": "cte", "name": "CTE и WITH", "icon": "≋", "description": "Делай сложные запросы понятными по шагам.", "topics": ["WITH", "CTE", "рекурсивные CTE"]},
    {"id": "windows", "name": "Оконные функции", "icon": "◫", "description": "Ранжируй и анализируй строки внутри групп.", "topics": ["OVER", "PARTITION BY", "RANK", "ROW_NUMBER"]},
    {"id": "functions", "name": "Функции и выражения", "icon": "ƒ", "description": "Преобразуй текст и вычисляй новые значения.", "topics": ["ROUND", "UPPER", "LENGTH", "CASE"]},
    {"id": "dates", "name": "Дата и время", "icon": "◷", "description": "Извлекай части дат и строй временные сводки.", "topics": ["strftime", "date", "временные группы"]},
    {"id": "conditional", "name": "Условная логика", "icon": "◇", "description": "Формируй значения по правилам с CASE.", "topics": ["CASE", "WHEN", "ELSE"]},
    {"id": "set-ops", "name": "Операции над множествами", "icon": "∪", "description": "Объединяй и сравнивай результаты запросов.", "topics": ["UNION", "INTERSECT", "EXCEPT"]},
]

EXERCISES = [
    {"id": "s1", "module": "select", "database": "shop", "title": "Товары для перекуса", "difficulty": 1, "prompt": "Покажи названия и цены всех товаров категории «Еда» дороже 500. Отсортируй по цене от дешёвых к дорогим.", "hint": "Нужны WHERE с двумя условиями и ORDER BY.", "solution": "SELECT name, price FROM products WHERE category = 'Еда' AND price > 500 ORDER BY price", "explanation": "Отфильтровали категорию и цену, затем отсортировали результат."},
    {"id": "s2", "module": "select", "database": "shop", "title": "Города покупателей", "difficulty": 1, "prompt": "Найди уникальные города покупателей и выведи их в алфавитном порядке.", "hint": "Вспомни DISTINCT.", "solution": "SELECT DISTINCT city FROM customers ORDER BY city", "explanation": "DISTINCT убирает повторяющиеся города."},
    {"id": "s3", "module": "select", "database": "games", "title": "Топ игроков", "difficulty": 1, "prompt": "Покажи никнеймы и уровни игроков с уровнем не ниже 20, от самого высокого уровня. Оставь первые три строки.", "hint": "WHERE, ORDER BY DESC и LIMIT.", "solution": "SELECT nickname, level FROM players WHERE level >= 20 ORDER BY level DESC LIMIT 3", "explanation": "Фильтр уровня применяется до сортировки и ограничения результата."},
    {"id": "s4", "module": "select", "database": "library", "title": "Детективная полка", "difficulty": 1, "prompt": "Выведи название и год публикации всех детективов, начиная с самого нового.", "hint": "Таблица books содержит жанр и год.", "solution": "SELECT title, published_year FROM books WHERE genre = 'Детектив' ORDER BY published_year DESC", "explanation": "WHERE выбирает жанр, DESC сортирует годы по убыванию."},
    {"id": "agg1", "module": "aggregate", "database": "shop", "title": "Средняя цена", "difficulty": 1, "prompt": "Найди среднюю цену всех товаров и округли результат до двух знаков.", "hint": "Используй AVG и ROUND.", "solution": "SELECT ROUND(AVG(price), 2) FROM products", "explanation": "AVG вычисляет среднее, ROUND округляет итог."},
    {"id": "agg2", "module": "aggregate", "database": "games", "title": "Рекорд клуба", "difficulty": 1, "prompt": "Найди максимальное количество очков среди всех игровых результатов.", "hint": "Нужна агрегатная функция MAX.", "solution": "SELECT MAX(points) FROM scores", "explanation": "MAX возвращает наибольшее значение столбца."},
    {"id": "a1", "module": "grouping", "database": "shop", "title": "Средний чек по заказам", "difficulty": 2, "prompt": "Для каждого товара покажи product_id и общее количество заказанных единиц. Оставь товары, у которых заказали больше одной штуки, отсортируй по количеству по убыванию.", "hint": "Сгруппируй по product_id, а условие для суммы задай через HAVING.", "solution": "SELECT product_id, SUM(quantity) FROM orders GROUP BY product_id HAVING SUM(quantity) > 1 ORDER BY SUM(quantity) DESC", "explanation": "GROUP BY формирует группы, HAVING фильтрует агрегированные значения."},
    {"id": "a2", "module": "grouping", "database": "games", "title": "Лучший результат игр", "difficulty": 2, "prompt": "Для каждой игры найди максимальное количество очков и покажи только игры с результатом выше 7000. Отсортируй по рекорду.", "hint": "Сгруппируй scores по game_id.", "solution": "SELECT game_id, MAX(points) FROM scores GROUP BY game_id HAVING MAX(points) > 7000 ORDER BY MAX(points) DESC", "explanation": "MAX находит рекорд внутри каждой группы."},
    {"id": "a3", "module": "grouping", "database": "library", "title": "Книги по жанрам", "difficulty": 2, "prompt": "Посчитай книги каждого жанра и выведи жанры, где книг больше одной.", "hint": "COUNT(*) и HAVING COUNT(*) > 1.", "solution": "SELECT genre, COUNT(*) FROM books GROUP BY genre HAVING COUNT(*) > 1", "explanation": "COUNT(*) считает строки каждой группы."},
    {"id": "a4", "module": "grouping", "database": "shop", "title": "Выручка покупателей", "difficulty": 2, "prompt": "Для каждого customer_id посчитай сумму quantity во всех заказах. Покажи покупателей с суммой не меньше двух.", "hint": "Сгруппируй таблицу orders по customer_id.", "solution": "SELECT customer_id, SUM(quantity) FROM orders GROUP BY customer_id HAVING SUM(quantity) >= 2", "explanation": "Суммируем количество товаров для каждого покупателя."},
    {"id": "j1", "module": "joins", "database": "shop", "title": "Состав заказов", "difficulty": 2, "prompt": "Выведи id заказа, имя товара и количество для всех заказов. Отсортируй по id заказа.", "hint": "Свяжи orders и products по product_id.", "solution": "SELECT orders.id, products.name, orders.quantity FROM orders JOIN products ON orders.product_id = products.id ORDER BY orders.id", "explanation": "JOIN соединяет строки, для которых совпали идентификаторы товара."},
    {"id": "j2", "module": "joins", "database": "library", "title": "Кто взял книгу?", "difficulty": 2, "prompt": "Выведи название книги и имя читателя для каждой выдачи, включая только книги, которые ещё не возвращены.", "hint": "Соедини loans с books и readers; returned = 0.", "solution": "SELECT books.title, readers.name FROM loans JOIN books ON loans.book_id = books.id JOIN readers ON loans.reader_id = readers.id WHERE loans.returned = 0", "explanation": "Два JOIN связывают выдачу и с книгой, и с читателем."},
    {"id": "j3", "module": "joins", "database": "games", "title": "Таблица рекордов", "difficulty": 2, "prompt": "Покажи ник игрока, название игры и очки за каждый результат выше 6000. Отсортируй по очкам по убыванию.", "hint": "Таблица scores связывает игроков и игры.", "solution": "SELECT players.nickname, games.title, scores.points FROM scores JOIN players ON scores.player_id = players.id JOIN games ON scores.game_id = games.id WHERE scores.points > 6000 ORDER BY scores.points DESC", "explanation": "Через scores связываются игроки, игры и результат."},
    {"id": "j4", "module": "joins", "database": "shop", "title": "Покупатели и заказы", "difficulty": 2, "prompt": "Покажи имена покупателей и даты их заказов со статусом delivered.", "hint": "Свяжи customers и orders, затем отфильтруй статус.", "solution": "SELECT customers.name, orders.order_date FROM customers JOIN orders ON customers.id = orders.customer_id WHERE orders.status = 'delivered'", "explanation": "JOIN по customer_id добавляет имя к каждой подходящей покупке."},
    {"id": "f1", "module": "filtering", "database": "shop", "title": "В подарок до 5000", "difficulty": 1, "prompt": "Покажи название и цену товаров стоимостью от 500 до 5000 включительно.", "hint": "Оператор BETWEEN включает обе границы диапазона.", "solution": "SELECT name, price FROM products WHERE price BETWEEN 500 AND 5000", "explanation": "BETWEEN задаёт удобный диапазон значений."},
    {"id": "f2", "module": "filtering", "database": "games", "title": "Игроки из Азии и СНГ", "difficulty": 1, "prompt": "Найди никнеймы игроков из RU или JP.", "hint": "Проверь country с помощью IN.", "solution": "SELECT nickname FROM players WHERE country IN ('RU', 'JP')", "explanation": "IN проверяет значение сразу по нескольким вариантам."},
    {"id": "sort1", "module": "sorting", "database": "shop", "title": "Три дорогие покупки", "difficulty": 1, "prompt": "Покажи три самых дорогих товара: название и цену, от дорогого к дешёвому.", "hint": "ORDER BY price DESC вместе с LIMIT.", "solution": "SELECT name, price FROM products ORDER BY price DESC LIMIT 3", "explanation": "Сначала упорядочили цены по убыванию, затем ограничили выдачу."},
    {"id": "sort2", "module": "sorting", "database": "games", "title": "Вторая страница игроков", "difficulty": 2, "prompt": "Выведи никнеймы игроков из RU по уровню от большего к меньшему. Пропусти первого и покажи следующих двух.", "hint": "Соедини WHERE, ORDER BY, LIMIT и OFFSET.", "solution": "SELECT nickname FROM players WHERE country = 'RU' ORDER BY level DESC LIMIT 2 OFFSET 1", "explanation": "OFFSET пропускает строки после сортировки, LIMIT задаёт размер страницы."},
    {"id": "sub1", "module": "subqueries", "database": "shop", "title": "Выше среднего", "difficulty": 2, "prompt": "Найди названия и цены товаров дороже средней цены всех товаров.", "hint": "Подзапрос с AVG можно использовать прямо в WHERE.", "solution": "SELECT name, price FROM products WHERE price > (SELECT AVG(price) FROM products)", "explanation": "Внутренний запрос вычисляет среднюю цену для внешнего фильтра."},
    {"id": "sub2", "module": "subqueries", "database": "shop", "title": "Покупатели с доставкой", "difficulty": 2, "prompt": "Покажи имена покупателей, у которых есть хотя бы один доставленный заказ.", "hint": "Используй IN с подзапросом по таблице orders.", "solution": "SELECT name FROM customers WHERE id IN (SELECT customer_id FROM orders WHERE status = 'delivered')", "explanation": "Подзапрос возвращает подходящие customer_id, а внешний запрос находит имена."},
    {"id": "cte1", "module": "cte", "database": "shop", "title": "CTE доставленных заказов", "difficulty": 2, "prompt": "С помощью WITH посчитай доставленные заказы каждого покупателя и выведи тех, у кого их больше одного.", "hint": "Создай CTE с customer_id и COUNT(*), затем отфильтруй его.", "solution": "WITH delivered AS (SELECT customer_id, COUNT(*) AS order_count FROM orders WHERE status = 'delivered' GROUP BY customer_id) SELECT customer_id, order_count FROM delivered WHERE order_count > 1", "explanation": "CTE именует промежуточный результат и делает основной запрос короче."},
    {"id": "cte2", "module": "cte", "database": "games", "title": "Очки выше среднего через WITH", "difficulty": 2, "prompt": "Найди player_id и points результатов выше среднего числа очков, вычислив среднее в CTE.", "hint": "Объяви CTE avg_score через WITH, затем сравни с ним строки scores.", "solution": "WITH avg_score AS (SELECT AVG(points) AS value FROM scores) SELECT player_id, points FROM scores WHERE points > (SELECT value FROM avg_score)", "explanation": "CTE хранит вычисленное среднее, которое затем использует основной запрос."},
    {"id": "win1", "module": "windows", "database": "games", "title": "Рейтинг внутри каждой игры", "difficulty": 3, "prompt": "Для каждого результата покажи game_id, player_id, points и место игрока внутри этой игры. При равных очках места должны совпадать.", "hint": "Используй RANK() OVER (PARTITION BY game_id ORDER BY points DESC).", "solution": "SELECT game_id, player_id, points, RANK() OVER (PARTITION BY game_id ORDER BY points DESC) FROM scores", "explanation": "PARTITION BY начинает рейтинг заново для каждой игры, а RANK сохраняет одинаковые места при равенстве очков."},
    {"id": "win2", "module": "windows", "database": "shop", "title": "Нумерация заказов покупателей", "difficulty": 3, "prompt": "Покажи customer_id, дату заказа и порядковый номер заказа покупателя по дате от раннего к позднему.", "hint": "ROW_NUMBER() с PARTITION BY customer_id и ORDER BY order_date.", "solution": "SELECT customer_id, order_date, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date) FROM orders", "explanation": "Оконная функция нумерует заказы отдельно внутри каждого покупателя."},
    {"id": "fn1", "module": "functions", "database": "shop", "title": "Новая цена с налогом", "difficulty": 1, "prompt": "Покажи название каждого товара и его цену с добавлением 10%, округлённую до целых.", "hint": "Вычисли price * 1.1 и оберни в ROUND.", "solution": "SELECT name, ROUND(price * 1.1) FROM products", "explanation": "SQL-функция ROUND округляет вычисленное выражение."},
    {"id": "fn2", "module": "functions", "database": "games", "title": "Никнеймы капсом", "difficulty": 1, "prompt": "Для игроков из RU выведи никнейм заглавными буквами и количество символов в исходном никнейме.", "hint": "В SQLite есть UPPER и LENGTH.", "solution": "SELECT UPPER(nickname), LENGTH(nickname) FROM players WHERE country = 'RU'", "explanation": "Функции преобразуют текст и вычисляют длину строки."},
    {"id": "date1", "module": "dates", "database": "shop", "title": "Заказы по годам", "difficulty": 2, "prompt": "Посчитай количество заказов по годам, извлекая год из order_date функцией SQLite.", "hint": "strftime('%Y', order_date) можно использовать и в SELECT, и в GROUP BY.", "solution": "SELECT strftime('%Y', order_date), COUNT(*) FROM orders GROUP BY strftime('%Y', order_date)", "explanation": "strftime извлекает год из текстовой даты SQLite."},
    {"id": "date2", "module": "dates", "database": "library", "title": "Выдачи по месяцам", "difficulty": 2, "prompt": "Посчитай выдачи книг по месяцам в формате YYYY-MM.", "hint": "Используй strftime('%Y-%m', loan_date) и GROUP BY.", "solution": "SELECT strftime('%Y-%m', loan_date), COUNT(*) FROM loans GROUP BY strftime('%Y-%m', loan_date)", "explanation": "strftime форматирует даты для построения временных сводок."},
    {"id": "case1", "module": "conditional", "database": "shop", "title": "Ценовые категории", "difficulty": 2, "prompt": "Для каждого товара выведи название и ценовую категорию: 'доступный' для цены ниже 1000, иначе 'премиум'. Используй CASE.", "hint": "CASE WHEN price < 1000 THEN ... ELSE ... END.", "solution": "SELECT name, CASE WHEN price < 1000 THEN 'доступный' ELSE 'премиум' END FROM products", "explanation": "CASE возвращает значение по условиям для каждой строки."},
    {"id": "case2", "module": "conditional", "database": "games", "title": "Уровни игроков", "difficulty": 2, "prompt": "Покажи никнейм и категорию уровня: 'pro' для level >= 25, 'starter' в остальных случаях.", "hint": "Составь ветвление CASE WHEN ... ELSE ... END.", "solution": "SELECT nickname, CASE WHEN level >= 25 THEN 'pro' ELSE 'starter' END FROM players", "explanation": "CASE позволяет строить условные значения в SELECT."},
    {"id": "set1", "module": "set-ops", "database": "shop", "title": "Города из двух сегментов", "difficulty": 2, "prompt": "Объедини в уникальный список города покупателей из Москвы и Казани, отсортируй список по алфавиту.", "hint": "Сделай два SELECT city с разными условиями и объедини их через UNION.", "solution": "SELECT city FROM customers WHERE city = 'Москва' UNION SELECT city FROM customers WHERE city = 'Казань' ORDER BY city", "explanation": "UNION объединяет результаты двух запросов и убирает повторы."},
    {"id": "set2", "module": "set-ops", "database": "shop", "title": "Общие города покупателей", "difficulty": 3, "prompt": "Найди города, в которых есть покупатели с именами, начинающимися на А или В, и покупатели, присоединившиеся не позже 2022 года. Используй INTERSECT.", "hint": "Сделай два SELECT city из customers и пересечь их через INTERSECT.", "solution": "SELECT city FROM customers WHERE name LIKE 'А%' OR name LIKE 'В%' INTERSECT SELECT city FROM customers WHERE joined_year <= 2022", "explanation": "INTERSECT возвращает только строки, присутствующие в обоих запросах."},
]

DATABASE_RELATIONSHIPS: dict[str, list[dict[str, str]]] = {
    "shop": [
        {"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "id", "cardinality": "N:1"},
        {"from_table": "orders", "from_column": "product_id", "to_table": "products", "to_column": "id", "cardinality": "N:1"},
    ],
    "library": [
        {"from_table": "books", "from_column": "author_id", "to_table": "authors", "to_column": "id", "cardinality": "N:1"},
        {"from_table": "loans", "from_column": "book_id", "to_table": "books", "to_column": "id", "cardinality": "N:1"},
        {"from_table": "loans", "from_column": "reader_id", "to_table": "readers", "to_column": "id", "cardinality": "N:1"},
    ],
    "games": [
        {"from_table": "scores", "from_column": "player_id", "to_table": "players", "to_column": "id", "cardinality": "N:1"},
        {"from_table": "scores", "from_column": "game_id", "to_table": "games", "to_column": "id", "cardinality": "N:1"},
    ],
}


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or GAME_DB
    conn = sqlite3.connect(path, timeout=3)
    conn.row_factory = sqlite3.Row
    return conn


def get_ai_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {"base_url": "http://localhost:1234/v1", "model": "", "api_key": "", "configured": False}
    with _managed(_connect()) as conn:
        values = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM app_settings")}
    defaults.update({key: values[key] for key in ("base_url", "model", "api_key") if key in values})
    defaults["configured"] = values.get("enabled") == "1"
    return defaults


def save_ai_settings(base_url: str, model: str = "", api_key: str = "", clear_api_key: bool = False) -> dict[str, Any]:
    base_url = str(base_url).strip().rstrip("/")
    model = str(model).strip()
    api_key = str(api_key).strip()
    parsed = urlparse(base_url)
    if len(base_url) > 500 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Укажи корректный адрес API, например http://localhost:1234/v1")
    if len(model) > 200 or len(api_key) > 1000:
        raise ValueError("Слишком длинное значение модели или API-ключа")
    with _managed(_connect()) as conn:
        conn.execute("INSERT INTO app_settings(key,value) VALUES('base_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (base_url,))
        conn.execute("INSERT INTO app_settings(key,value) VALUES('model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model,))
        if api_key:
            conn.execute("INSERT INTO app_settings(key,value) VALUES('api_key',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (api_key,))
        elif clear_api_key:
            conn.execute("DELETE FROM app_settings WHERE key='api_key'")
        conn.execute("INSERT INTO app_settings(key,value) VALUES('enabled','1') ON CONFLICT(key) DO UPDATE SET value='1'")
    return get_ai_settings()


def initialize() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with _managed(_connect()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), xp INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0, last_active TEXT);
        INSERT OR IGNORE INTO profile(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS completions (id INTEGER PRIMARY KEY, exercise_id TEXT NOT NULL, mode TEXT NOT NULL, completed_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, query_ms REAL NOT NULL, xp INTEGER NOT NULL, optimal INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS lab_runs (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, query_ms REAL NOT NULL, row_count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS lab_challenges (challenge_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL, xp INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ai_challenges (id TEXT PRIMARY KEY, title TEXT NOT NULL, topic TEXT NOT NULL, module_id TEXT NOT NULL, difficulty INTEGER NOT NULL, prompt TEXT NOT NULL, hint TEXT NOT NULL, solution TEXT NOT NULL, explanation TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
    for key, database in DATABASES.items():
        path = DATA_DIR / f"{key}.sqlite3"
        if not path.exists():
            with sqlite3.connect(path) as conn:
                conn.executescript(database["schema"])
                conn.executescript(database["seed"])


def _safe_connection(database: str) -> sqlite3.Connection:
    if database not in DATABASES:
        raise ValueError("Неизвестная учебная база данных")
    uri = f"file:{(DATA_DIR / f'{database}.sqlite3').as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _execute_readonly(conn: sqlite3.Connection, sql: str, timeout_ms: int = 1200) -> tuple[list[str], list[tuple[Any, ...]], float]:
    sql = sql.strip()
    if not sql:
        raise ValueError("Введите SQL-запрос")
    start = time.perf_counter()
    deadline = start + timeout_ms / 1000
    conn.set_progress_handler(lambda: int(time.perf_counter() > deadline), 5000)
    try:
        cursor = conn.execute(sql)
        if cursor.description is None:
            raise ValueError("Нужен запрос, возвращающий результат (например, SELECT)")
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchmany(501)
        if len(rows) > 500:
            raise ValueError("Слишком много строк (лимит — 500). Добавьте WHERE или LIMIT.")
        elapsed = (time.perf_counter() - start) * 1000
        return columns, [tuple(row) for row in rows], elapsed
    except sqlite3.Error as exc:
        if isinstance(exc, sqlite3.OperationalError) and "interrupted" in str(exc).lower():
            raise ValueError("Запрос выполнялся слишком долго (лимит — 1,2 секунды)") from exc
        raise ValueError(str(exc)) from exc
    finally:
        conn.set_progress_handler(None, 0)


def run_query(database: str, sql: str) -> dict[str, Any]:
    if database.startswith("g-"):
        return run_generated_query(database, sql)
    with _managed(_safe_connection(database)) as conn:
        columns, rows, elapsed = _execute_readonly(conn, sql)
    return {"columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3)}


def grade(exercise_id: str, sql: str) -> dict[str, Any]:
    exercise = next((e for e in EXERCISES if e["id"] == exercise_id), None)
    if exercise is None:
        return grade_generated(exercise_id, sql)
    try:
        with _managed(_safe_connection(exercise["database"])) as conn:
            expected_cols, expected_rows, _ = _execute_readonly(conn, exercise["solution"])
            columns, rows, elapsed = _execute_readonly(conn, sql)
    except ValueError as exc:
        return {"correct": False, "message": str(exc)}
    if len(columns) != len(expected_cols):
        return {"correct": False, "message": f"Пока не совпадает число столбцов: ожидалось {len(expected_cols)}, у тебя {len(columns)}.", "columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3)}
    # SQL result order is only meaningful when explicitly requested; compare as multisets.
    correct = Counter(map(_freeze, rows)) == Counter(map(_freeze, expected_rows))
    return {
        "correct": correct,
        "message": "Точно в цель! Результат запроса совпал." if correct else "Результат пока отличается. Проверь фильтры, группировку и соединения.",
        "columns": columns,
        "rows": [list(row) for row in rows],
        "elapsed_ms": round(elapsed, 3),
    }


def _freeze(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    return value


def schema(database: str) -> list[dict[str, Any]]:
    with _managed(_safe_connection(database)) as conn:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        result = []
        for table in tables:
            columns = conn.execute(f'PRAGMA table_info("{table["name"]}")').fetchall()
            relations = _foreign_keys(conn, table["name"])
            for relation in DATABASE_RELATIONSHIPS.get(database, []):
                if relation["from_table"] == table["name"] and relation not in relations:
                    relations.append(relation)
            result.append({"name": table["name"], "sql": table["sql"], "columns": [{"name": col["name"], "type": col["type"], "primary_key": bool(col["pk"])} for col in columns], "foreign_keys": relations})
        return result


def _foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict[str, str]]:
    return [
        {"from_table": table_name, "from_column": row["from"], "to_table": row["table"], "to_column": row["to"], "cardinality": "N:1"}
        for row in conn.execute(f'PRAGMA foreign_key_list("{table_name}")')
    ]


def _generated_record(challenge_id: str) -> dict[str, Any]:
    if not isinstance(challenge_id, str) or not challenge_id.startswith("g-") or len(challenge_id) != 34 or any(ch not in "0123456789abcdef" for ch in challenge_id[2:]):
        raise ValueError("AI-задание не найдено")
    with _managed(_connect()) as conn:
        row = conn.execute("SELECT * FROM ai_challenges WHERE id=?", (challenge_id,)).fetchone()
    if row is None or not (GENERATED_DIR / f"{challenge_id}.sqlite3").is_file():
        raise ValueError("AI-задание не найдено или его база удалена")
    return dict(row)


def _describe_tables(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    result = []
    tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    for table in tables:
        columns = conn.execute(f'PRAGMA table_info("{table["name"]}")').fetchall()
        result.append({
            "name": table["name"],
            "sql": table["sql"],
            "columns": [{"name": col["name"], "type": col["type"], "primary_key": bool(col["pk"])} for col in columns],
            "foreign_keys": _foreign_keys(conn, table["name"]),
        })
    return result


def _generated_schema(challenge_id: str) -> list[dict[str, Any]]:
    record = _generated_record(challenge_id)
    conn = sqlite3.connect(f"file:{(GENERATED_DIR / f'{challenge_id}.sqlite3').as_posix()}?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        return _describe_tables(conn)
    finally:
        conn.close()


def register_ai_challenge(payload: dict[str, Any], requested_topic: str, difficulty: int, requested_module_id: str = "") -> dict[str, Any]:
    """Validate AI-authored schema/data/solution, then persist an isolated challenge DB."""
    difficulty = max(1, min(3, int(difficulty)))
    title = str(payload.get("title", "Случайный SQL-квест")).strip()[:160]
    topic = str(payload.get("topic") or requested_topic or "SQL").strip()[:120]
    prompt = str(payload.get("task") or payload.get("prompt") or "").strip()[:2000]
    hint = str(payload.get("hint") or "").strip()[:1000]
    explanation = str(payload.get("explanation") or "").strip()[:2000]
    schema_sql = payload.get("schema_sql", "")
    seed_sql = payload.get("seed_sql", "")
    solution = payload.get("solution_sql", "")
    if not all(isinstance(value, str) for value in (schema_sql, seed_sql, solution)):
        raise ValueError("AI-квест должен содержать schema_sql, seed_sql и solution_sql в виде текста")
    def strip_fence(sql: str) -> str:
        cleaned = sql.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return cleaned
    schema_sql, seed_sql, solution = strip_fence(schema_sql), strip_fence(seed_sql), strip_fence(solution)
    if not prompt or not solution.strip() or not schema_sql.strip():
        raise ValueError("AI-квест неполный: нужны задание, схема и правильный SQL-ответ")
    if len(schema_sql) > 50_000 or len(seed_sql) > 100_000 or len(solution) > 10_000:
        raise ValueError("AI-квест слишком большой; попробуй сгенерировать его ещё раз")

    challenge_id = f"g-{uuid.uuid4().hex}"
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    memory = sqlite3.connect(":memory:", timeout=3)
    memory.row_factory = sqlite3.Row

    def authorizer(action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None) -> int:
        blocked = {
            sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH,
            sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_DROP_TRIGGER,
            sqlite3.SQLITE_CREATE_TEMP_TRIGGER, sqlite3.SQLITE_DROP_TEMP_TRIGGER,
            sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_DROP_VTABLE,
        }
        if action in blocked:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_PRAGMA and not (arg1 in {"table_info", "foreign_key_list"} or (arg1 == "query_only" and (arg2 or "").upper() == "ON")):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or "").lower() in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    path = GENERATED_DIR / f"{challenge_id}.sqlite3"
    try:
        memory.execute("PRAGMA foreign_keys=ON")
        memory.set_authorizer(authorizer)
        deadline = time.perf_counter() + 2.5
        memory.set_progress_handler(lambda: int(time.perf_counter() > deadline), 1000)
        memory.executescript(schema_sql + "\n" + seed_sql)
        memory.set_progress_handler(None, 0)
        table_count = memory.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
        if not 1 <= table_count <= 15:
            raise ValueError("В сгенерированной базе должно быть от 1 до 15 таблиц")
        row_count = 0
        for table in memory.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            quoted = table["name"].replace('"', '""')
            row_count += memory.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
        if row_count > 5000:
            raise ValueError("В учебной базе слишком много строк (лимит — 5000)")
        memory.execute("PRAGMA query_only=ON")
        expected_columns, expected_rows, _ = _execute_readonly(memory, solution, timeout_ms=1500)
        if not expected_columns or not expected_rows:
            raise ValueError("Правильный SQL должен вернуть хотя бы одну строку")
        tables = _describe_tables(memory)
        target = sqlite3.connect(path)
        try:
            memory.backup(target)
        finally:
            target.close()
        module_ids = {module["id"] for module in MODULES}
        module_id = requested_module_id or str(payload.get("module_id", ""))
        if module_id not in module_ids:
            match = next((m["id"] for m in MODULES if topic.casefold() == m["name"].casefold() or topic.casefold() in {t.casefold() for t in m["topics"]}), "generated")
            module_id = match
        with _managed(_connect()) as game:
            game.execute(
                "INSERT INTO ai_challenges(id,title,topic,module_id,difficulty,prompt,hint,solution,explanation,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (challenge_id, title or "SQL-квест", topic, module_id, difficulty, prompt, hint, solution.strip(), explanation, time.strftime("%Y-%m-%dT%H:%M:%S")),
            )
        return {"id": challenge_id, "module": module_id, "topic": topic, "database": challenge_id, "title": title or "SQL-квест", "difficulty": difficulty, "prompt": prompt, "hint": hint, "generated": True, "schema": tables}
    except sqlite3.Error as exc:
        path.unlink(missing_ok=True)
        message = "Задание AI не прошло проверку SQLite"
        if "interrupted" in str(exc).lower():
            message = "AI-схема выполнялась слишком долго. Попробуй сгенерировать задание ещё раз."
        raise ValueError(f"{message}: {exc}") from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        memory.close()


def list_ai_challenges(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(50, int(limit)))
    with _managed(_connect()) as conn:
        rows = conn.execute("SELECT id, title, topic, module_id AS module, difficulty, prompt, hint, created_at, id AS database, 1 AS generated FROM ai_challenges ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows if (GENERATED_DIR / f"{row['id']}.sqlite3").is_file()]


def run_generated_query(challenge_id: str, sql: str) -> dict[str, Any]:
    _generated_record(challenge_id)
    uri = f"file:{(GENERATED_DIR / f'{challenge_id}.sqlite3').as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        columns, rows, elapsed = _execute_readonly(conn, sql)
        return {"columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3)}
    finally:
        conn.close()


def grade_generated(challenge_id: str, sql: str) -> dict[str, Any]:
    record = _generated_record(challenge_id)
    uri = f"file:{(GENERATED_DIR / f'{challenge_id}.sqlite3').as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        expected_columns, expected_rows, _ = _execute_readonly(conn, record["solution"])
        columns, rows, elapsed = _execute_readonly(conn, sql)
    except ValueError as exc:
        return {"correct": False, "message": str(exc)}
    finally:
        conn.close()
    same_shape = len(columns) == len(expected_columns)
    correct = same_shape and Counter(map(_freeze, rows)) == Counter(map(_freeze, expected_rows))
    message = "Точно в цель! AI-квест решён." if correct else "Результат отличается от ожидаемого. Проверь фильтры, группировку и связи."
    if not same_shape:
        message = f"Ожидалось {len(expected_columns)} столбцов, у тебя {len(columns)}."
    return {"correct": correct, "message": message, "columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3)}


def lab_schema() -> list[dict[str, Any]]:
    if not LAB_DB.exists():
        return []
    uri = f"file:{LAB_DB.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        result = [{"name": row["name"], "sql": row["sql"], "columns": [{"name": col["name"], "type": col["type"], "primary_key": bool(col["pk"])} for col in conn.execute(f'PRAGMA table_info("{row["name"]}")')], "foreign_keys": _foreign_keys(conn, row["name"])} for row in tables]
        return result
    finally:
        conn.close()


def _init_player() -> sqlite3.Row:
    with _managed(_connect()) as conn:
        profile = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
        today = date.today().isoformat()
        if profile["last_active"] != today:
            streak = profile["streak"]
            if profile["last_active"]:
                streak = streak + 1 if (date.today() - date.fromisoformat(profile["last_active"])).days == 1 else 1
            else:
                streak = 1
            conn.execute("UPDATE profile SET streak=?, last_active=? WHERE id=1", (streak, today))
            profile = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
        return profile


def dashboard() -> dict[str, Any]:
    profile = _init_player()
    with _managed(_connect()) as conn:
        completions = conn.execute("SELECT exercise_id, COUNT(*) AS attempts, MIN(duration_ms) AS best_ms, MIN(query_ms) AS best_query_ms FROM completions GROUP BY exercise_id").fetchall()
        recent = conn.execute("SELECT c.exercise_id, c.mode, c.completed_at, c.duration_ms, c.query_ms, c.xp, a.title FROM completions c LEFT JOIN ai_challenges a ON a.id=c.exercise_id ORDER BY c.id DESC LIMIT 8").fetchall()
        complete_ids = {row["exercise_id"] for row in conn.execute("SELECT DISTINCT exercise_id FROM completions")}
        total = conn.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
        avg_query = conn.execute("SELECT AVG(query_ms) FROM completions").fetchone()[0] or 0
        daily_done = conn.execute("SELECT 1 FROM completions WHERE exercise_id=? AND completed_at LIKE ?", (daily_exercise()["id"], date.today().isoformat() + "%")).fetchone() is not None
        lab_count = conn.execute("SELECT COUNT(*) FROM lab_runs").fetchone()[0]
        lab_avg = conn.execute("SELECT AVG(query_ms) FROM lab_runs").fetchone()[0] or 0
    return {
        "profile": {"xp": profile["xp"], "level": profile["xp"] // 100 + 1, "level_progress": profile["xp"] % 100, "streak": profile["streak"]},
        "modules": [{**m, "completed": sum(1 for e in EXERCISES if e["module"] == m["id"] and e["id"] in complete_ids), "total": sum(1 for e in EXERCISES if e["module"] == m["id"])} for m in MODULES],
        "completed_count": sum(1 for exercise in EXERCISES if exercise["id"] in complete_ids), "exercise_count": len(EXERCISES), "attempt_count": total,
        "avg_query_ms": round(avg_query, 3), "lab_runs": lab_count, "lab_avg_ms": round(lab_avg, 3), "daily": {"exercise": daily_exercise(), "completed": daily_done},
        "records": {row["exercise_id"]: {"attempts": row["attempts"], "best_ms": row["best_ms"], "best_query_ms": row["best_query_ms"]} for row in completions},
        "recent": [dict(row) for row in recent],
    }


def daily_exercise() -> dict[str, Any]:
    # Stable for the local day, no external scheduler required.
    index = date.today().toordinal() % len(EXERCISES)
    return EXERCISES[index]


def list_exercises(module: str | None = None) -> list[dict[str, Any]]:
    exercises = EXERCISES if not module or module == "daily" else [e for e in EXERCISES if e["module"] == module]
    return [{key: value for key, value in e.items() if key not in {"solution", "explanation"}} for e in exercises]


def exercise_details(exercise_id: str) -> dict[str, Any]:
    exercise = next((e for e in EXERCISES if e["id"] == exercise_id), None)
    if not exercise:
        record = _generated_record(exercise_id)
        return {
            "id": exercise_id, "module": record["module_id"], "topic": record["topic"], "database": exercise_id,
            "title": record["title"], "difficulty": record["difficulty"], "prompt": record["prompt"],
            "hint": record["hint"], "generated": True, "schema": _generated_schema(exercise_id),
        }
    return {**{key: value for key, value in exercise.items() if key not in {"solution", "explanation"}}, "schema": schema(exercise["database"])}


def record_completion(exercise_id: str, mode: str, duration_ms: int, query_ms: float, correct: bool) -> dict[str, Any]:
    if not correct:
        return {"xp_gained": 0, "message": "Опыт начисляется после правильного решения."}
    duration_ms = max(0, min(int(duration_ms), 86_400_000))
    mode = mode if mode in {"practice", "timed", "fastest", "optimal"} else "practice"
    exercise = next((e for e in EXERCISES if e["id"] == exercise_id), None)
    if not exercise:
        record = _generated_record(exercise_id)
        exercise = {"difficulty": record["difficulty"]}
    bonus = 0
    xp = 25 + exercise["difficulty"] * 5 + bonus
    optimal = 0
    with _managed(_connect()) as conn:
        previous = conn.execute("SELECT MIN(duration_ms) AS best_duration, MIN(query_ms) AS best_query FROM completions WHERE exercise_id=?", (exercise_id,)).fetchone()
        existing = previous["best_duration"] is not None
        if existing:
            xp = 5 + bonus
        if mode == "timed":
            bonus = 15 if duration_ms <= 120_000 else 0
        elif mode == "fastest":
            bonus = 20 if not existing or duration_ms < previous["best_duration"] else 8
        elif mode == "optimal":
            bonus = 25 if previous["best_query"] is None or query_ms < previous["best_query"] else 10
        xp += bonus
        if mode == "optimal" and query_ms < 10:
            xp += 5
            optimal = 1
        today = date.today().isoformat()
        daily_already_done = conn.execute("SELECT 1 FROM completions WHERE exercise_id=? AND completed_at LIKE ?", (daily_exercise()["id"], today + "%")).fetchone()
        if exercise_id == daily_exercise()["id"] and not daily_already_done:
            xp += 5
        conn.execute("INSERT INTO completions(exercise_id, mode, completed_at, duration_ms, query_ms, xp, optimal) VALUES(?,?,?,?,?,?,?)", (exercise_id, mode, time.strftime("%Y-%m-%dT%H:%M:%S"), duration_ms, query_ms, xp, optimal))
        conn.execute("UPDATE profile SET xp=xp+? WHERE id=1", (xp,))
    return {"xp_gained": xp, "message": f"+{xp} XP! Продолжай в том же духе."}


def run_lab(sql: str, mode: str = "query") -> dict[str, Any]:
    """Execute user SQL only against the app's isolated laboratory database."""
    conn = sqlite3.connect(LAB_DB, timeout=2)
    conn.row_factory = sqlite3.Row
    def lab_authorizer(action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None) -> int:
        blocked = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}
        if action in blocked and not (action == sqlite3.SQLITE_PRAGMA and (arg1 in {"table_info", "foreign_key_list"} or (arg1 == "query_only" and (arg2 or "").upper() == "ON"))):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or "").lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    conn.set_authorizer(lab_authorizer)
    if mode == "setup":
        try:
            for table in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                conn.execute(f'DROP TABLE "{table["name"]}"')
            conn.executescript(sql)
            tables = []
            for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                columns = conn.execute(f'PRAGMA table_info("{row["name"]}")').fetchall()
                tables.append({"name": row["name"], "sql": row["sql"], "columns": [{"name": c["name"], "type": c["type"], "primary_key": bool(c["pk"])} for c in columns], "foreign_keys": _foreign_keys(conn, row["name"])})
            conn.close()
            return {"tables": tables, "message": f"Лаборатория сохранена: таблиц — {len(tables)}."}
        except sqlite3.Error as exc:
            conn.close()
            raise ValueError(str(exc)) from exc
    try:
        conn.execute("PRAGMA query_only=ON")
        columns, rows, elapsed = _execute_readonly(conn, sql, 1500)
        with _managed(_connect()) as game:
            game.execute("INSERT INTO lab_runs(created_at,duration_ms,query_ms,row_count) VALUES(?,?,?,?)", (time.strftime("%Y-%m-%dT%H:%M:%S"), 0, elapsed, len(rows)))
        return {"columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3), "row_count": len(rows)}
    finally:
        conn.close()


def grade_lab(sql: str, solution: str) -> dict[str, Any]:
    """Check an AI-generated exercise against the current laboratory dataset."""
    if not LAB_DB.exists():
        raise ValueError("Сначала создай таблицы в SQL-лаборатории")
    conn = sqlite3.connect(f"file:{LAB_DB.as_posix()}?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        expected_columns, expected_rows, _ = _execute_readonly(conn, solution)
        columns, rows, elapsed = _execute_readonly(conn, sql)
    finally:
        conn.close()
    same_shape = len(columns) == len(expected_columns)
    correct = same_shape and Counter(map(_freeze, rows)) == Counter(map(_freeze, expected_rows))
    message = "Отличное решение! Результат совпал с ожидаемым." if correct else "Результат отличается от ожидаемого. Проверь условие и столбцы."
    if not same_shape:
        message = f"Ожидалось {len(expected_columns)} столбцов, у тебя {len(columns)}."
    return {"correct": correct, "message": message, "columns": columns, "rows": [list(row) for row in rows], "elapsed_ms": round(elapsed, 3)}


def complete_lab_task(challenge_id: str, correct: bool) -> dict[str, Any]:
    if not correct:
        return {"xp_gained": 0, "message": "Опыт начисляется после правильного решения."}
    challenge_id = str(challenge_id).strip()[:100]
    if not challenge_id:
        raise ValueError("Не указан идентификатор AI-задания")
    with _managed(_connect()) as conn:
        cursor = conn.execute("INSERT OR IGNORE INTO lab_challenges(challenge_id, completed_at, xp) VALUES(?,?,30)", (challenge_id, time.strftime("%Y-%m-%dT%H:%M:%S")))
        if cursor.rowcount:
            conn.execute("UPDATE profile SET xp=xp+30 WHERE id=1")
            return {"xp_gained": 30, "message": "+30 XP за AI-квест!"}
    return {"xp_gained": 0, "message": "Этот AI-квест уже засчитан."}


def lab_template() -> str:
    return """CREATE TABLE events (id INTEGER PRIMARY KEY, user_id INTEGER, event_name TEXT, duration_ms INTEGER);
INSERT INTO events VALUES (1, 10, 'login', 120), (2, 10, 'search', 340), (3, 11, 'login', 90), (4, 11, 'purchase', 800), (5, 10, 'purchase', 620);"""
