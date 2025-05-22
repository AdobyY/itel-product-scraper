import requests
from bs4 import BeautifulSoup
import re
import time
import pandas as pd
import os

def clean_price_text_updated(price_text_raw):
    """Очищує текст ціни від валюти, пробілів та перетворює на float."""
    if not price_text_raw:
        return None
    
    price_text_cleaned = price_text_raw.replace('\xa0', '').replace(' ', '') # \xa0 - це  
    price_text_cleaned = re.sub(r'(?i)грн\.?', '', price_text_cleaned) 
    price_text_cleaned = price_text_cleaned.replace(',', '.')
    
    match = re.search(r'(\d+\.?\d*)', price_text_cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return f"Невдала конвертація: {price_text_raw}"
    # Якщо число не знайдено взагалі, повертаємо відповідне повідомлення або оригінал
    return f"Ціна за запитом"


def parse_itel_search_all_pages_updated(search_term):
    base_url = "https://itel.ua/ru/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
    }
    
    all_products_data = []
    page_num = 1
    MAX_PAGES_TO_TRY = 50 

    print(f"Починаю парсинг для терміну: '{search_term}'")

    while page_num <= MAX_PAGES_TO_TRY:
        params = {'term': search_term, 'page': page_num}
        current_url = base_url + "?" + requests.compat.urlencode(params)
        
        print(f"Роблю запит до сторінки {page_num}: {current_url}")
        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=20, allow_redirects=True)
            response.raise_for_status()
            print(f"Сторінка {page_num}: відповідь успішно отримана. Фактичний URL: {response.url}")
            
            if page_num > 1 and f"page={page_num}" not in response.url and "page=" in response.url :
                match_page_redirect = re.search(r'page=(\\d+)', response.url)
                if match_page_redirect:
                    redirected_page_num = int(match_page_redirect.group(1))
                    if redirected_page_num < page_num:
                        print(f"Запитували сторінку {page_num}, але перенаправлено на сторінку {redirected_page_num} ({response.url}). Ймовірно, це кінець результатів.")
                        break 
                else: 
                    print(f"Запитували сторінку {page_num}, але параметр 'page' зник з URL відповіді ({response.url}). Ймовірно, це кінець результатів.")
                    break
            elif page_num > 1 and "page=" not in response.url:
                 print(f"Запитували сторінку {page_num} з параметром 'page', але він зник з URL відповіді ({response.url}). Ймовірно, це кінець результатів.")
                 break

        except requests.exceptions.RequestException as e:
            print(f"Помилка запиту на сторінці {page_num}: {e}")
            break 
            
        soup = BeautifulSoup(response.text, 'lxml')

        main_product_list_container = soup.find('div', class_='catalog-list')
        if not main_product_list_container:
            main_product_list_container = soup.find('div', class_='catalog-list-more')

        if not main_product_list_container:
            print(f"Не знайдено основного контейнера товарів ('catalog-list' або 'catalog-list-more') на сторінці {page_num}.")
            product_cards = soup.find_all('div', class_='product-card')
            if not product_cards and page_num == 1:
                print("Жодної картки товару ('product-card') не знайдено глобально на першій сторінці.")
                break
            elif not product_cards and page_num > 1:
                print(f"Жодної картки товару ('product-card') не знайдено глобально на сторінці {page_num}. Кінець результатів.")
                break
        else:
            product_cards = main_product_list_container.find_all('div', class_='product-card')
            print(f"У контейнері знайдено {len(product_cards)} елементів з класом 'product-card'.")

        if not product_cards:
            if page_num == 1:
                print(f"Не знайдено товарів для запиту '{search_term}' на першій сторінці (після перевірки контейнерів).")
            else:
                print(f"Не знайдено товарів на сторінці {page_num}. Ймовірно, це кінець результатів.")
            break 

        print(f"На сторінці {page_num} знайдено {len(product_cards)} карток товарів для обробки.")
        
        for card_index, card in enumerate(product_cards):
            name = "Назва не знайдена"
            code = "Код не знайдений"
            price_display = "Ціна не вказана"

            product_title_div = card.find('div', class_='product-title')
            if product_title_div:
                name_tag = product_title_div.find('a')
                if name_tag and name_tag.text:
                    name = " ".join(name_tag.text.split())
            
            articul_div = card.find('div', class_='articul')
            if articul_div and articul_div.text:
                code_text = articul_div.text.strip() 
                code = code_text.replace("Код:", "").strip()

            price_block = card.find('div', class_='price-block')
            if price_block:
                price_div = price_block.find('div', class_='price')
                if price_div:
                    price_value_span = price_div.find('span', class_='price-value')
                    if price_value_span and price_value_span.text:
                        raw_price_text = price_value_span.text.strip()
                        price_display = clean_price_text_updated(raw_price_text)
                    else:
                        price_display = "Ціна за запитом"
                else:
                    request_price_btn = price_block.find('a', class_=lambda x: x and 'send-dp-request' in x.split())
                    if request_price_btn and request_price_btn.text:
                        price_display = request_price_btn.text.strip()
                    else:
                        price_display = "Ціна не вказана (формат не стандартний)" 
            else:
                price_display = "Блок ціни ('price-block') не знайдений"
            
            product_info = {
                'name': name,
                'code': code,
                'price': price_display,
                'page_found': page_num 
            }
            all_products_data.append(product_info)
        
        page_num += 1
        time.sleep(1)

    if page_num > MAX_PAGES_TO_TRY:
        print(f"Досягнуто максимальної кількості сторінок для спроби ({MAX_PAGES_TO_TRY}).")
        
    return all_products_data

def save_to_excel(data, search_term):
    """Зберігає дані у файл Excel у папці data."""
    if not data:
        print("Немає даних для збереження.")
        return

    output_dir = "data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Створено директорію: {output_dir}")

    filename = os.path.join(output_dir, f'itel_{search_term}_products_all_pages.xlsx')
    print(f"\nЗберігаю дані у файл: {filename}")
    try:
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False)
        print(f"Дані успішно збережено у файл {filename}")
    except Exception as e:
        print(f"Помилка: Не вдалося записати дані у файл {filename}. Причина: {e}")

def main():
    search_query = "moxa" 
    
    scraped_products = parse_itel_search_all_pages_updated(search_query)

    if scraped_products:
        print(f"\n--- Всього зібрано {len(scraped_products)} товарів для запиту '{search_query}' ---")
        
        for i, product in enumerate(scraped_products[:5]):
             print(f"\nТовар #{i+1} (стор. {product['page_found']}):")
             print(f"  Назва: {product['name']}")
             print(f"  Код:   {product['code']}")
             print(f"  Ціна:  {product['price']}")
        if len(scraped_products) > 5:
            print(f"\n... та ще {len(scraped_products) - 5} товарів.")

        save_to_excel(scraped_products, search_query)

    else:
        print(f"Не вдалося зібрати дані для запиту '{search_query}' або товари не знайдено (кінцевий результат порожній).")
        print("Перевірте вивід вище, особливо HTML-фрагмент першої сторінки та повідомлення про контейнери/картки.")
        print("Якщо HTML виглядає порожнім або не містить товарів, які ви бачите в браузері, сайт, ймовірно, використовує JavaScript для завантаження контенту.")
        print("У такому випадку для парсингу потрібні будуть інструменти типу Selenium або Playwright.")

if __name__ == "__main__":
    main()