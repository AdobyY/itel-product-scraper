import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re # Для очищення ціни

script_start_time = time.time()

# --- Конфігурація ---
BASE_URLS = [
    "https://st.in.ua/ua/product-category/server-equipment-ua/servers-ua/",
    "https://st.in.ua/ua/product-category/server-equipment-ua/storages-ua/",
    "https://st.in.ua/ua/product-category/server-equipment-ua/tape-systems-ua/tape-libraries-ua/",
    "https://st.in.ua/ua/product-category/server-equipment-ua/tape-systems-ua/tape-cartridges-ua/", # Ця категорія, ймовірно, порожня
    "https://st.in.ua/ua/product-category/server-equipment-ua/tape-systems-ua/type-drivers-ua/",
]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br', 
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'DNT': '1'
}
OUTPUT_FILE = "data/st_in.xlsx"
all_products_data = []

# --- Допоміжні функції ---
def get_category_name_from_page(soup, base_url):
    h1_tag = soup.select_one("h1.woocommerce-products-header__title.page-title")
    if h1_tag:
        return h1_tag.text.strip()
    try:
        url_parts = base_url.strip('/').split('/')
        if 'product-category' in url_parts:
            idx = url_parts.index('product-category')
            relevant_parts = [part for part in url_parts[idx+1:] if part and part != 'page']
            if relevant_parts:
                category_candidate = relevant_parts[-1] 
                return category_candidate.replace('-ua', '').replace('-', ' ').capitalize()
    except Exception as e:
        print(f"    Помилка видобутку категорії з URL {base_url}: {e}")
    return "Невідома категорія"

# --- Основна логіка скрапінгу ---
for base_url in BASE_URLS:
    print(f"Обробка категорії: {base_url}")
    current_page = 1
    category_name_for_products = "Невідома категорія" 
    category_name_extracted_for_this_base_url = False

    while True:
        if current_page == 1:
            page_url = base_url
        else:
            page_url = f"{base_url.rstrip('/')}/page/{current_page}/"

        print(f"  Завантаження сторінки: {page_url}")
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30, verify=True)
            response.raise_for_status() 
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                if current_page == 1:
                     print(f"    Сторінка {page_url} (перша сторінка категорії) не знайдена (404). Пропуск категорії.")
                else:
                     print(f"    Сторінка {page_url} не знайдена (404). Ймовірно, кінець сторінок для цієї категорії.")
                break 
            else:
                print(f"    HTTP помилка при завантаженні сторінки {page_url}: {e}")
                break
        except requests.exceptions.RequestException as e:
            print(f"    Помилка завантаження сторінки {page_url}: {e}")
            break 

        soup = BeautifulSoup(response.content, 'lxml')

        if not category_name_extracted_for_this_base_url:
            category_name_for_products = get_category_name_from_page(soup, base_url)
            print(f"  Назва категорії визначена як: {category_name_for_products}")
            category_name_extracted_for_this_base_url = True
        
        product_cards = soup.select('div.product__item')

        if not product_cards:
            no_products_message_tag = soup.select_one('p.woocommerce-no-products-found')
            if no_products_message_tag:
                print(f"    Знайдено повідомлення: '{no_products_message_tag.text.strip()}'. Завершення для категорії {base_url}.")
            elif current_page == 1:
                print(f"    Не знайдено карток товарів ('div.product__item') на першій сторінці {base_url}.")
            else:
                print(f"    Не знайдено карток товарів ('div.product__item') на сторінці {current_page} для {base_url}. Кінець сторінок для цієї категорії.")
            break 
        
        print(f"    Знайдено {len(product_cards)} карток товарів ('div.product__item') на сторінці {current_page}.")
        
        parsed_products_on_this_page_count = 0
        for product_el in product_cards:
            product_data = {
                "Назва": "N/A",
                "Виробник": "N/A",
                "Артикул": "N/A", # Нове поле для артикула
                "Ціна": "N/A",
                "Категорія": category_name_for_products
            }

            manufacturer_tag = product_el.select_one("div.product__item-img p.product__no-img")
            if manufacturer_tag:
                product_data["Виробник"] = manufacturer_tag.text.strip()

            title_tag = product_el.select_one("div.product__item-content p.product__item-title")
            full_title_str = ""
            if title_tag:
                full_title_str = title_tag.text.strip().replace('\xa0', ' ')
                product_data["Назва"] = full_title_str 

                if '|' in full_title_str:
                    title_parts = [p.strip() for p in full_title_str.split('|')]
                    
                    # Виробник з назви (якщо не знайдено раніше і є принаймні 2 частини)
                    if product_data["Виробник"] == "N/A" and len(title_parts) >= 2 and title_parts[1]:
                        product_data["Виробник"] = title_parts[1]
                    
                    # Артикул з назви (якщо є принаймні 3 частини)
                    if len(title_parts) >= 3 and title_parts[2]:
                        product_data["Артикул"] = title_parts[2]
            else:
                product_data["Назва"] = "Назва не знайдена"
            
            # Додаткова евристика для виробника, якщо він все ще N/A
            if product_data["Виробник"] == "N/A" and full_title_str:
                 known_brands_pattern = r"\b(Dell|HP|HPE|Lenovo|Fujitsu|IBM|Supermicro|EMC|NetApp|Cisco|Juniper|Intel|AMD|Seagate|WD|Western Digital|QNAP|Synology|Tandberg)\b"
                 match = re.search(known_brands_pattern, full_title_str, re.IGNORECASE)
                 if match:
                     product_data["Виробник"] = match.group(0)

            price_span_tag = product_el.select_one("div.product__item-content p[class*='product__item-price'] span")
            if price_span_tag:
                price_text = price_span_tag.text.strip().replace('\xa0', '').replace('\u202f', '')
                cleaned_price = re.sub(r'[^\d,.]', '', price_text)
                cleaned_price = cleaned_price.replace(' ', '').replace(',', '.') 
                if cleaned_price:
                    product_data["Ціна"] = cleaned_price
                else:
                    product_data["Ціна"] = "Ціна не вказана"
            else:
                 price_na_tag = product_el.select_one("div.product__item-content p.price-na, div.product__item-content span.price-na") 
                 if price_na_tag:
                     product_data["Ціна"] = price_na_tag.text.strip()
                 else:
                    product_data["Ціна"] = "Ціна не вказана"
            
            all_products_data.append(product_data)
            parsed_products_on_this_page_count +=1
        
        print(f"    Успішно розпарсено {parsed_products_on_this_page_count} товарів зі сторінки.")
        if parsed_products_on_this_page_count == 0 and len(product_cards) > 0:
            print(f"    УВАГА: На сторінці {page_url} знайдено {len(product_cards)} 'div.product__item', але жоден не вдалося розпарсити з даними. Перевірте внутрішні селектори назви/ціни/виробника.")

        current_page += 1
        # time.sleep(1.0) 

if all_products_data:
    # Визначення бажаного порядку колонок
    column_order = ["Назва", "Виробник", "Артикул", "Ціна", "Категорія"]
    df = pd.DataFrame(all_products_data)
    
    # Перевірка наявності всіх колонок та їх впорядкування
    # Створюємо новий DataFrame з потрібним порядком колонок, 
    # додаючи відсутні колонки зі значеннями N/A (хоча вони мають бути ініціалізовані)
    df_ordered = pd.DataFrame()
    for col in column_order:
        if col in df.columns:
            df_ordered[col] = df[col]
        else:
            df_ordered[col] = "N/A" # На випадок, якщо колонка чомусь не створилася

    try:
        df_ordered.to_excel(OUTPUT_FILE, index=False, engine='openpyxl')
        print(f"\nДані ({len(all_products_data)} записів) успішно збережено у файл {OUTPUT_FILE}")
    except Exception as e:
        print(f"\nПомилка збереження у Excel: {e}.")
        print("Спробуйте встановити 'openpyxl': pip install openpyxl")
        try:
            csv_output_file = OUTPUT_FILE.replace('.xlsx', '.csv')
            df_ordered.to_csv(csv_output_file, index=False, encoding='utf-8-sig')
            print(f"Дані успішно збережено у файл {csv_output_file}")
        except Exception as e_csv:
            print(f"Помилка збереження у CSV: {e_csv}")
else:
    print(f"\nНе знайдено жодних даних для збереження. Загальна кількість зібраних записів: {len(all_products_data)}.")

print("Скрапінг завершено.")

script_end_time = time.time()
execution_time = script_end_time - script_start_time
print(f"Час виконання скрипту: {execution_time:.2f} секунд.")