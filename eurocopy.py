# scraper_eurocopy_v3.py
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin

script_start_time = time.time()

# --- Конфігурація ---
BASE_SITE_URL = "https://eurocopy.ua"
MAIN_CATALOG_URL = "https://eurocopy.ua/catalog" 
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
}
OUTPUT_FILE = "data/eurocopy.xlsx"
all_products_data = []

# --- Функція для отримання посилань та назв категорій ---
def get_category_links_and_names(main_catalog_page_url):
    categories = []
    print(f"Завантаження головної сторінки каталогу для пошуку категорій: {main_catalog_page_url}")
    try:
        response = requests.get(main_catalog_page_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')

        title_elements = soup.select("div.categories__title.title-h6")
        print(f"    Знайдено {len(title_elements)} потенційних елементів назв категорій.")

        for title_tag in title_elements:
            name = title_tag.text.strip()
            link_tag = title_tag.find_parent("a") 

            if link_tag and link_tag.get('href'):
                href = link_tag.get('href')
                if href.startswith("/catalog/") and \
                   "subcategories" not in href and \
                   "Всі категорії" not in name and "Все категории" not in name and \
                   href.strip('/') != "catalog":
                    
                    full_url = urljoin(BASE_SITE_URL, href)
                    categories.append({'name': name, 'url': full_url})
            
        unique_categories = []
        seen_urls = set()
        for cat in categories:
            if cat['url'] not in seen_urls:
                unique_categories.append(cat)
                seen_urls.add(cat['url'])
                print(f"    Додано унікальну категорію: {cat['name']} ({cat['url']})")
        
        if not unique_categories:
            print("ПОПЕРЕДЖЕННЯ: Не вдалося знайти жодної унікальної категорії товарів. Перевірте селектори категорій.")
        return unique_categories

    except requests.exceptions.RequestException as e:
        print(f"Помилка завантаження головної сторінки каталогу: {e}")
        return []

# --- Функція для вилучення артикула з назви ---
def extract_article(name_str):
    match = re.search(r'\(([^)]*[A-Za-z0-9\-_/]+[^)]*)\)', name_str) 
    if match:
        return match.group(1).strip()
    
    article_match = re.search(r'(?:Код товару|Артикул|Код|Part No|P/N)\s*[:\-]?\s*([A-Za-z0-9\-_/]+)', name_str, re.IGNORECASE)
    if article_match:
        return article_match.group(1).strip()
        
    return "N/A"

# --- Основна логіка скрапінгу ---
product_categories = get_category_links_and_names(MAIN_CATALOG_URL)

if not product_categories:
    print("Не знайдено категорій для обробки. Завершення роботи.")
else:
    print(f"\nЗнайдено {len(product_categories)} категорій. Початок обробки товарів...\n")

    for category in product_categories:
        category_name = category['name']
        base_category_url = category['url'].split('?')[0] 
        print(f"Обробка категорії: {category_name} (Базовий URL: {base_category_url})")
        current_page = 1

        while True:
            paginated_url = f"{base_category_url}?search_text=&sort=1&page={current_page}"
            
            print(f"  Завантаження сторінки: {paginated_url}")
            try:
                response = requests.get(paginated_url, headers=HEADERS, timeout=25)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    print(f"    Сторінка {current_page} для категорії '{category_name}' не знайдена (404). Ймовірно, кінець сторінок.")
                else:
                    print(f"    HTTP помилка {e.response.status_code} для {paginated_url}.")
                break 
            except requests.exceptions.RequestException as e:
                print(f"    Помилка завантаження сторінки {paginated_url}: {e}")
                break 

            if current_page > 1:
                expected_page_param = f"page={current_page}"
                if expected_page_param not in response.url:
                    if "page=" not in response.url or "page=1" in response.url:
                         print(f"    Ймовірний редірект з page={current_page} на першу сторінку ({response.url}). Завершення для категорії '{category_name}'.")
                         break
            
            soup = BeautifulSoup(response.content, 'lxml')
            product_cards = soup.select("div.product") 

            if not product_cards:
                if current_page == 1:
                    print(f"    Не знайдено товарів на першій сторінці категорії '{category_name}'.")
                else: 
                    print(f"    Не знайдено товарів на сторінці {current_page} для '{category_name}'. Кінець сторінок.")
                break 

            print(f"    Знайдено {len(product_cards)} товарів на сторінці {current_page}.")
            
            for card in product_cards:
                product_name_tag = card.select_one("h3.product__desc")
                product_price_span = card.select_one("div.product__price.sub-title > span:first-child")
                
                status_button_text_tag = card.select_one("span.btn__text")
                product_status = "Доступен" 
                if status_button_text_tag and "Недоступен" in status_button_text_tag.text.strip():
                    product_status = "Недоступен"

                product_name = product_name_tag.text.strip() if product_name_tag else "Назва не знайдена"
                
                product_price_text = "Ціна не вказана"
                if product_price_span:
                    price_str = product_price_span.text.strip()
                    cleaned_price = re.sub(r'[^\d.,]', '', price_str).replace(',', '.')
                    if cleaned_price:
                        product_price_text = cleaned_price
                
                article = extract_article(product_name)

                all_products_data.append({
                    "Назва": product_name,
                    "Артикул": article,
                    "Ціна": product_price_text,
                    "Статус": product_status, 
                    "Категорія": category_name
                })
            
            # ВИДАЛЕНО БЛОК ПЕРЕВІРКИ НАЯВНОСТІ КНОПКИ "НАСТУПНА СТОРІНКА"
            # if not soup.select_one("ul.pagination li.next:not(.disabled) a"): 
            #     print(f"    Кнопка 'наступна сторінка' відсутня або неактивна на сторінці {current_page}. Завершення для категорії '{category_name}'.")
            #     break

            current_page += 1
            # time.sleep(0.8) 

# --- Збереження даних у файл ---
if all_products_data:
    column_order = ["Назва", "Артикул", "Ціна", "Статус", "Категорія"] 
    df = pd.DataFrame(all_products_data)
    
    df_ordered = pd.DataFrame()
    for col in column_order:
        if col in df.columns:
            df_ordered[col] = df[col]
        else: 
            df_ordered[col] = "N/A" if col != "Статус" else "Невідомо"

    try:
        df_ordered.to_excel(OUTPUT_FILE, index=False, engine='openpyxl')
        print(f"\nДані ({len(all_products_data)} записів) успішно збережено у файл {OUTPUT_FILE}")
    except Exception as e:
        print(f"\nПомилка збереження у Excel: {e}.")
        try:
            csv_output_file = OUTPUT_FILE.replace('.xlsx', '.csv')
            df_ordered.to_csv(csv_output_file, index=False, encoding='utf-8-sig')
            print(f"Дані успішно збережено у файл {csv_output_file}")
        except Exception as e_csv:
            print(f"Помилка збереження у CSV: {e_csv}")
else:
    print(f"\nНе знайдено жодних даних для збереження. Загальна кількість зібраних записів: {len(all_products_data)}.")

script_end_time = time.time()
execution_time = script_end_time - script_start_time
print(f"Час виконання скрипту: {execution_time:.2f} секунд.")