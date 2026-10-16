import streamlit as st
import csv
import json
import os

import requests
import pandas as pd
import time
from tqdm import tqdm
import re


def parse_units(description: str, product_name: str = '') -> float | None:
    # Try direct units mention first
    match = re.search(r'([\d.]+)\s*units?', description, re.IGNORECASE)
    if match:
        return float(match.group(1))

    # Try calculating from ABV and volume
    abv_match = re.search(r'([\d.]+)%\s*ABV', description, re.IGNORECASE)
    vol_match = re.search(r'([\d.]+)\s*ml', description, re.IGNORECASE)

    if abv_match and vol_match:
        abv = float(abv_match.group(1))
        vol = float(vol_match.group(1))
        return round((abv * vol) / 1000, 2)

    # ABV only — use standard serve sizes
    if abv_match:
        abv = float(abv_match.group(1))
        name_lower = product_name.lower()
        if any(w in name_lower for w in
               ['cocktail', 'martini', 'daiquiri', 'colada', 'margarita', 'spritz', 'lagoon', 'woo', 'beach',
                'godfather', 'rain', 'punch']):
            vol = 200  # standard cocktail glass
        elif any(w in name_lower for w in
                 ['wine', 'rioja', 'prosecco', 'chardonnay', 'merlot', 'pinot', 'sauvignon', 'shiraz', 'zinfandel',
                  'rosé']):
            vol = 175  # standard wine glass
        else:
            vol = 25  # spirit measure
        return round((abv * vol) / 1000, 2)

    # Hard fallback lookup
    UNIT_LOOKUP = {
        'long island iced tea': 2.0,
        'sex on the beach': 1.5,
        'woo woo': 1.5,
        'blue lagoon': 1.5,
        'porn star martini': 1.5,
        'espresso martini': 1.5,
        'strawberry daiquiri': 1.5,
        "tommy's margarita": 1.5,
        'mango monster mash': 1.5,
        'candy rosá': 1.5,
        'hawaiian pipeline punch': 1.5,
        'the godfather': 1.5,
        'purple rain': 1.5,
    }
    return UNIT_LOOKUP.get(product_name.lower().strip())


def parse_volume_ml(text: str) -> float | None:
    match = re.search(r'([\d.]+)\s*ml', text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    if re.search(r'\bthird\s+pint\b', text, re.IGNORECASE):
        return round(568 / 3, 1)
    if re.search(r'\bhalf(?:\s+pint)?\b', text, re.IGNORECASE):
        return 284.0
    if re.search(r'\bpint\b', text, re.IGNORECASE):
        return 568.0
    return None


def parse_portion_units(
    portion_text: str,
    description: str,
    product_name: str,
) -> float | None:
    """Get units for a portion, scaling product-level units where necessary."""
    units = parse_units(portion_text, product_name)
    if units is not None:
        return units

    product_units = parse_units(description, product_name)
    if product_units is None:
        return None

    portion_volume = parse_volume_ml(portion_text)
    product_volume = parse_volume_ml(description)
    if portion_volume is not None and product_volume is not None:
        return round(product_units * portion_volume / product_volume, 2)

    if re.search(r'\bhalf(?:\s+pint)?\b', portion_text, re.IGNORECASE):
        return round(product_units / 2, 2)
    if re.search(r'\bthird\s+pint\b', portion_text, re.IGNORECASE):
        return round(product_units / 3, 2)
    if re.search(r'\bpint\b', portion_text, re.IGNORECASE):
        return product_units

    return product_units


# Configuration
BASE_URL = "https://ca.jdw-apps.net/api/v0.1"
HEADERS = {'Authorization': f'Bearer {st.secrets["JDW_TOKEN"]}'}

NON_ALCOHOLIC_CATEGORIES = [
    'low and alcohol free',
    '0% cocktails',
    'soft drinks',
    "children's drinks",
    'hot drinks',
    'bar snacks',
    'includes a drink'
]

ALCOHOLIC_CATEGORIES= [
    'lager, beer, stout and craft | draught',
    'cider | draught and bottles',
    'real ale',
    'craft | draught, bottles & cans',
    'world beers | bottles',
    'spritz cocktails',
    'cocktails and buzzballz',
    'wine, prosecco & sparkling',
    'vodka',
    'gin',
    'rum',
    'whisky',
    'tequila',
    'liqueurs, cognac and brandy',
    'premixed drinks',
    'bombs and shots',
]


def show_cheapest_deals(df):
    if not df.empty:
        cheapest = df.sort_values(by='price')
        print(cheapest[['venuename', 'productname', 'price']].to_string(index=False))
        return cheapest
    else:
        print("No data available to analyze.")
        return None

def cheapest_per_location(df):
    if not df.empty:
        cheapest = df.sort_values(by='price')
        return cheapest
    else:
        print("No data available to analyze.")
        return

def PPU_per_location(df):
    if not df.empty:
        PPU = df.sort_values(by='ppu')
        return PPU
    else:
        print("No data available to analyze.")
        return None

def name_per_location(df):
    if not df.empty:
        names = df.sort_values(by='productname')
        return names
    else:
        print("No data available to analyze.")
        return None

def fetch_all_data():
    if not os.path.exists('export.csv'):
        with open('export.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['venuename', 'productname', 'price'])
            writer.writeheader()

    print("Fetching venue list...")
    try:
        venues_resp = requests.get(f"{BASE_URL}/venues", headers=HEADERS)
        venues = venues_resp.json().get('data', [])
    except Exception as e:
        print(f"Failed to fetch venue list: {e}")
        return

    for venue in tqdm(venues):
        venue_ref = venue['venueRef']
        franchise = venue['franchise']
        name = venue['name']

        try:
            details_resp = requests.get(f"{BASE_URL}/venues/{venue_ref}", headers=HEADERS).json()
            sales_areas = details_resp['data'].get('salesAreas', [])

            if not sales_areas:
                continue

            sales_area_id = sales_areas[0]['id']

            url = f"{BASE_URL}/{franchise}/venues/{venue_ref}/sales-areas/{sales_area_id}/menus"
            menus_resp = requests.get(url, headers=HEADERS).json()
            menus = menus_resp.get('data', [])

            drinks_menu = next((m for m in menus if m['name'] == 'Drinks'), None)

            if not drinks_menu:
                continue

            menu_url = f"{BASE_URL}/{franchise}/venues/{venue_ref}/sales-areas/{sales_area_id}/menus/{drinks_menu['id']}"
            menu_data = requests.get(menu_url, headers=HEADERS).json()

            venue_products = []
            for cat in menu_data['data']['categories']:
                if cat['name'].lower().strip() in NON_ALCOHOLIC_CATEGORIES:
                    continue
                for group in cat['itemGroups']:
                    for item in group['items']:
                        if item.get('itemType') == 'product':
                            price = item['options']['portion']['options'][0]['value']['price']['value']
                            venue_products.append({
                                'venuename': name,
                                'productname': item['name'],
                                'price': price
                            })

            with open('export.csv', 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['venuename', 'productname', 'price'])
                writer.writerows(venue_products)

            time.sleep(0.5)

        except Exception as e:
            print(f"Error processing {name}: {e}")

    print("\nDone.")

def fetch_venue_names():
    names = []

    print("Fetching venue list...")
    try:
        venues_resp = requests.get(f"{BASE_URL}/venues", headers=HEADERS)
        venues = venues_resp.json().get('data', [])
    except Exception as e:
        print(f"Failed to fetch venue list: {e}")
        return None

    for venue in venues:
        names.append(venue['name'])

    names.sort()
    return names

def fetch_raw_specific_venue(input_name):
    """Save the unmodified Drinks menu response for one venue as JSON."""
    print("Fetching venue list...")
    try:
        venues_resp = requests.get(f"{BASE_URL}/venues", headers=HEADERS)
        venues_resp.raise_for_status()
        venues = venues_resp.json().get('data', [])
    except (requests.RequestException, ValueError) as e:
        print(f"Failed to fetch venue list: {e}")
        return

    venue = next((venue for venue in venues if venue.get('name') == input_name), None)
    if venue is None:
        print(f"Venue not found: {input_name}")
        return

    venue_ref = venue['venueRef']
    franchise = venue['franchise']

    try:
        details_response = requests.get(
            f"{BASE_URL}/venues/{venue_ref}",
            headers=HEADERS,
        )
        details_response.raise_for_status()
        details_data = details_response.json()
        sales_areas = details_data['data'].get('salesAreas', [])

        if not sales_areas:
            print(f"No sales areas found for {input_name}")
            return

        sales_area_id = sales_areas[0]['id']
        menus_url = (
            f"{BASE_URL}/{franchise}/venues/{venue_ref}/"
            f"sales-areas/{sales_area_id}/menus"
        )
        menus_response = requests.get(menus_url, headers=HEADERS)
        menus_response.raise_for_status()
        menus = menus_response.json().get('data', [])
        drinks_menu = next((menu for menu in menus if menu.get('name') == 'Drinks'), None)

        if drinks_menu is None:
            print(f"No Drinks menu found for {input_name}")
            return

        menu_url = (
            f"{BASE_URL}/{franchise}/venues/{venue_ref}/"
            f"sales-areas/{sales_area_id}/menus/{drinks_menu['id']}"
        )
        menu_response = requests.get(menu_url, headers=HEADERS)
        menu_response.raise_for_status()
        raw_menu = menu_response.json()

        with open('raw_specificLocation.json', 'w', encoding='utf-8') as file:
            json.dump(raw_menu, file, indent=2, ensure_ascii=False)

        print("\nSuccessfully saved raw Drinks menu to raw_specificLocation.json")
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Error fetching raw menu for {input_name}: {e}")

def fetch_specific_venue(Input_Name):
    all_products = []

    name = Input_Name

    ref = 0

    print("Fetching venue list...")
    try:
        venues_resp = requests.get(f"{BASE_URL}/venues", headers=HEADERS)
        venues = venues_resp.json().get('data', [])
    except Exception as e:
        print(f"Failed to fetch venue list: {e}")
        return

    for venue in venues:
        if (Input_Name == venue['name']):
            venue_ref = venue['venueRef']
            franchise = venue['franchise']

            try:
                details_resp = requests.get(f"{BASE_URL}/venues/{venue_ref}", headers=HEADERS).json()
                sales_areas = details_resp['data'].get('salesAreas', [])

                if not sales_areas:
                    continue

                sales_area_id = sales_areas[0]['id']

                url = f"{BASE_URL}/{franchise}/venues/{venue_ref}/sales-areas/{sales_area_id}/menus"
                menus_resp = requests.get(url, headers=HEADERS).json()
                menus = menus_resp.get('data', [])

                drinks_menu = next((m for m in menus if m['name'] == 'Drinks'), None)

                if not drinks_menu:
                    continue

                menu_url = f"{BASE_URL}/{franchise}/venues/{venue_ref}/sales-areas/{sales_area_id}/menus/{drinks_menu['id']}"
                menu_data = requests.get(menu_url, headers=HEADERS).json()

                for cat in menu_data['data']['categories']:
                    if cat['name'].lower().strip() in NON_ALCOHOLIC_CATEGORIES:
                        continue
                    for group in cat['itemGroups']:
                        for item in group['items']:
                            if item.get('itemType') == 'product':
                                if item.get('isOutOfStock', False):
                                    continue

                                description = item.get('description', '') or ''
                                portion_options = (
                                    item.get('options', {})
                                    .get('portion', {})
                                    .get('options', [])
                                )

                                for portion in portion_options:
                                    portion_value = portion.get('value', {})
                                    if portion_value.get('hidden', False):
                                        continue

                                    portion_label = (
                                        portion.get('label')
                                        or portion_value.get('name', '')
                                    )
                                    price = portion_value.get('price', {}).get('value')

                                    if price is None:
                                        continue

                                    portion_text = portion_label or description
                                    units = parse_portion_units(
                                        portion_text,
                                        description,
                                        item['name'],
                                    )
                                    volume_ml = parse_volume_ml(portion_text)

                                    if volume_ml is None and len(portion_options) == 1:
                                        volume_ml = parse_volume_ml(description)

                                    all_products.append({
                                        'venuename': name,
                                        'productname': item['name'],
                                        'portion': portion_label,
                                        'volume_ml': volume_ml,
                                        'price': price,
                                        'units': units,
                                        'ppu': round(price / units, 2) if units else None,
                                        'category': cat['name'],
                                    })

                time.sleep(0.5)

            except Exception as e:
                print(f"Error processing {name}: {e}")




    df = pd.DataFrame(all_products)
    if not df.empty:
        df = df.drop_duplicates(
            subset=['venuename', 'productname', 'portion', 'price', 'category']
        )
    df.to_csv('specificLocation.csv', index=False)
    print("\nSuccessfully saved to specificLocation.csv")




if __name__ == "__main__":
    #fetch_all_data()

    #fetch_specific_venue("The Captain Flinders")
    #df = pd.read_csv('specificLocation.csv')
    #if not df.empty:
    #   print(df.to_string())
    #else:
    #   print("No data available to analyze.")

    fetch_raw_specific_venue("The Captain Flinders")
