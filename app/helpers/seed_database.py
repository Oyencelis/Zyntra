# pyrefly: ignore [missing-import]
import mysql.connector
import requests
import os
import uuid
import time
import random

# --- CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',     # Leave empty if you use XAMPP default
    'database': 'zyntra'
}

# The User ID of the Seller
SELLER_ID = 24 

# Your specific Tech Categories
TECH_CATEGORIES = [
    "Mobile Phones & Accessories",
    "Laptops, Desktops & Monitors",
    "Audio & Video Equipment",
    "Smart Home Devices",
    "Cameras & Photography",
    "Wearable Technology"
]

# Keywords to filter Platzi products
TECH_KEYWORDS = [
    "electronic", "monitor", "laptop", "mouse", "keyboard", "headphone", 
    "earphone", "camera", "watch", "smart", "phone", "tv", "screen", 
    "speaker", "bluetooth", "wifi", "usb", "drive", "console", "game"
]

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'app', 'static', 'uploads', 'products')

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# --- FETCH FUNCTIONS ---

def fetch_fakestore_products():
    """Fetch electronics from FakeStoreAPI"""
    print("Fetching 'electronics' from FakeStoreAPI...")
    normalized_products = []
    try:
        response = requests.get('https://fakestoreapi.com/products/category/electronics')
        if response.status_code == 200:
            data = response.json()
            for item in data:
                normalized_products.append({
                    'title': item['title'],
                    'price': item['price'],
                    'description': item['description'],
                    'image_url': item['image'],
                    'source': 'FakeStore'
                })
    except Exception as e:
        print(f"FakeStoreAPI Error: {e}")
    return normalized_products

def fetch_platzi_products():
    """Fetch products from Platzi Fake API and filter for Tech"""
    print("Fetching data from Platzi API...")
    normalized_products = []
    try:
        response = requests.get('https://api.escuelajs.co/api/v1/products')
        if response.status_code == 200:
            data = response.json()
            for item in data:
                is_tech = False
                title_lower = item['title'].lower()
                category_name = item['category']['name'].lower()
                
                if 'electronic' in category_name:
                    is_tech = True
                else:
                    for keyword in TECH_KEYWORDS:
                        if keyword in title_lower:
                            is_tech = True
                            break
                
                if is_tech and item.get('images') and len(item['images']) > 0:
                    image_url = item['images'][0]
                    image_url = image_url.replace('["', '').replace('"]', '').replace('"', '')
                    
                    if image_url.startswith('http'):
                        normalized_products.append({
                            'title': item['title'],
                            'price': item['price'],
                            'description': item['description'],
                            'image_url': image_url,
                            'source': 'Platzi'
                        })
    except Exception as e:
        print(f"Platzi API Error: {e}")
    return normalized_products

def fetch_dummyjson_products():
    """Fetch dedicated tech categories from DummyJSON"""
    print("Fetching data from DummyJSON...")
    normalized_products = []
    
    # DummyJSON specific categories to target
    target_endpoints = [
        'smartphones',
        'laptops',
        'tablets',
        'mobile-accessories'
    ]
    
    try:
        for cat in target_endpoints:
            url = f'https://dummyjson.com/products/category/{cat}'
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                for item in data['products']:
                    # DummyJSON sends a thumbnail and a list of images. We prefer the first high-res image.
                    image_url = item['images'][0] if item.get('images') else item['thumbnail']
                    
                    normalized_products.append({
                        'title': item['title'],
                        'price': item['price'],
                        'description': item['description'],
                        'image_url': image_url,
                        'source': 'DummyJSON'
                    })
            time.sleep(0.2) # Polite delay between categories
            
    except Exception as e:
        print(f"DummyJSON Error: {e}")
    return normalized_products

# --- CORE LOGIC ---

def create_target_categories(cursor):
    """Creates the specific tech categories requested by the user"""
    category_map = {}
    print("Ensuring specific tech categories exist...")
    
    for cat_name in TECH_CATEGORIES:
        cursor.execute("SELECT category_id FROM categories WHERE category_name = %s", (cat_name,))
        result = cursor.fetchone()
        
        if result:
            category_map[cat_name] = result[0]
        else:
            print(f"Creating category: {cat_name}")
            cursor.execute(
                "INSERT INTO categories (category_name, status, created_at, updated_at) VALUES (%s, 1, NOW(), NOW())", 
                (cat_name,)
            )
            category_map[cat_name] = cursor.lastrowid
            
    return category_map

def download_image(image_url):
    try:
        response = requests.get(image_url, stream=True, timeout=10)
        if response.status_code == 200:
            ext = 'jpg' 
            filename = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            
            return f"uploads/products/{filename}"
    except Exception as e:
        print(f"Error downloading image {image_url}: {e}")
    return None

def assign_category(product_title, category_map):
    """Matches a product title to the strict TECH_CATEGORIES list."""
    title_lower = product_title.lower()
    
    if any(x in title_lower for x in ['laptop', 'desktop', 'monitor', 'screen', 'ssd', 'hard drive', 'pc', 'macbook', 'surface']):
        return category_map["Laptops, Desktops & Monitors"]
    
    elif any(x in title_lower for x in ['camera', 'lens', 'tripod', 'photo']):
        return category_map["Cameras & Photography"]
    
    elif any(x in title_lower for x in ['phone', 'iphone', 'samsung', 'case', 'charger', 'mobile', 'smartphone']):
        return category_map["Mobile Phones & Accessories"]
    
    elif any(x in title_lower for x in ['watch', 'tracker', 'band', 'wearable']):
        return category_map["Wearable Technology"]
    
    elif any(x in title_lower for x in ['home', 'smart', 'alexa', 'google', 'wifi', 'hub']):
        return category_map["Smart Home Devices"]
        
    elif any(x in title_lower for x in ['audio', 'sound', 'speaker', 'headphone', 'earphone', 'tv', 'television']):
        return category_map["Audio & Video Equipment"]
    
    # Fallback
    random_cat_name = random.choice(TECH_CATEGORIES)
    return category_map[random_cat_name]

def seed():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Setup Categories
    cat_map = create_target_categories(cursor)
    
    # 2. Fetch Data from all 3 sources
    fakestore_items = fetch_fakestore_products()
    platzi_items = fetch_platzi_products()
    dummy_items = fetch_dummyjson_products()
    
    all_products = fakestore_items + platzi_items + dummy_items
    
    # Shuffle for variety
    random.shuffle(all_products)
    
    if not all_products:
        print("No products found to import.")
        return

    print(f"Found {len(all_products)} total tech products. Importing...")
    
    imported_count = 0
    
    for item in all_products:
        try:
            # Assign category
            cat_id = assign_category(item['title'], cat_map)
            
            print(f"[{item['source']}] Processing: {item['title'][:30]}...")
            
            # Download Image
            local_image_path = download_image(item['image_url'])
            
            if not local_image_path:
                print("  Skipping: Image download failed.")
                continue

            # Insert Product
            query_product = """
                INSERT INTO products 
                (user_id, category_id, product_name, description, price, qty, status, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
            """
            
            desc_html = f"<p>{item['description']}</p>"
            qty = random.randint(5, 50)
            
            cursor.execute(query_product, (
                SELLER_ID,
                cat_id,
                item['title'],
                desc_html,
                item['price'],
                qty
            ))
            
            new_product_id = cursor.lastrowid
            
            # Insert Attachment
            query_attachment = """
                INSERT INTO product_attachments (product_id, attachment, status, created_at, updated_at)
                VALUES (%s, %s, 1, NOW(), NOW())
            """
            cursor.execute(query_attachment, (new_product_id, local_image_path))
            
            imported_count += 1
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error importing item: {e}")
            continue

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\nSuccessfully imported {imported_count} tech products from 3 sources!")

if __name__ == '__main__':
    seed()