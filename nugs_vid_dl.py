import argparse
import configparser
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (TimeoutException)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse
global driver_vis
global driver
global logged_into_nugs_headless
global headless_driver
global headless_driver_initialized
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Global variables (Refactor and manage)
video_directory = None
data_directory = None
audio_directory = None
folder_name = None
folder_names_set = set()
extracted_info = []
logged_into_nugs = False
logged_into_nugs_headless = False
driver = None
use_headless_driver = True
headless_driver_initialized = False

def load_credentials():
    global nugs_email, nugs_password, data_directory, video_directory, audio_directory
    config = configparser.ConfigParser()
    config.read('ngs_vid_dl_config.ini')
    
    # Read network paths from configuration file
    custom_paths = config['custom_paths']
    local_paths = get_local_paths()

    # Set the paths, using network paths if they exist, otherwise use local paths
    data_directory = get_valid_path(custom_paths['script_data_directory'], local_paths['data'])
    video_directory = get_valid_path(custom_paths['video_directory'], local_paths['video'])
    audio_directory = get_valid_path(custom_paths['audio_directory'], local_paths['audio'])
    
    print("\nData Directory:", data_directory)
    print("Video Directory:", video_directory)
    print("Audio Directory:", audio_directory)
    
    # Load email and password from configuration
    nugs_email = config['nugsDownloader']['email']
    nugs_password = config['nugsDownloader']['password']
    
    # Update JSON configuration
    update_json_config(config['nugsDownloader'])
    return nugs_email, nugs_password,video_directory

def get_local_paths():
    current_directory = os.getcwd()
    return {
        'data': os.path.join(current_directory, 'script_data_directory'),
        'video': os.path.join(current_directory, 'video_directory'),
        'audio': os.path.join(current_directory, 'audio_directory'),
    }


def get_valid_path(network_path, local_path):
    """
    Returns a valid path.
    If the network path exists, returns it. Otherwise, ensures the local path exists (creating directories if needed)
    and returns the local path.
    """
    if os.path.exists(network_path):
        return network_path
    else:
        os.makedirs(local_path, exist_ok=True)
        return local_path

def update_json_config(nugs_config):
    config_file_path = 'binaries/Nugs-Downloader-main/config.json'
    if not os.path.exists(config_file_path):
        print(f"Config file not found: {config_file_path}")
        return
    with open(config_file_path, 'r') as config_file:
        config_json = json.load(config_file)
    # Define a mapping for the keys from ini to json
    key_mapping = {
        'email': 'email',
        'password': 'password',
        'format': 'format',
        'videoFormat': 'videoFormat',
        'outPath': 'outPath',
        'token': 'token',
        'useFfmpegEnvVar': 'useFfmpegEnvVar'
    }
    # Update the values
    for ini_key, json_key in key_mapping.items():
        value = nugs_config.get(ini_key)
        if value is not None:
            if json_key in ['format', 'videoFormat'] and value.isdigit():
                config_json[json_key] = int(value)
            elif json_key == 'useFfmpegEnvVar':
                config_json[json_key] = value.lower() in ['true', '1', 't', 'y', 'yes']
            else:
                config_json[json_key] = value
    # Write the updated config back to config.json
    with open(config_file_path, 'w') as config_file:
        json.dump(config_json, config_file, indent=4)
    print("\nnugs-downloader-config.json updated successfully.")

def process_filename(file_name):

    pattern = re.compile(r"(.*?)(\d{4}-\d{2}-\d{2})")
    match = pattern.match(file_name)
    if match:
        # Extract band name and date
        band_name = match.group(1).strip()
        date = match.group(2).strip()
        return f"{band_name} {date}"
    else:
        # If the pattern does not match, return None or handle as needed
        return None

def initialize_folder_names_set(folder_path):
    folder_names_set = set()
    try:
        files = os.listdir(folder_path)
        for file_name in files:
            simplified_name = process_filename(file_name)
            if simplified_name:
                folder_names_set.add(simplified_name)
    except FileNotFoundError:
        print(f"The folder at {folder_path} does not exist.")
    except Exception as e:
        print(f"An error occurred: {e}")
    return folder_names_set

def process_filenames_from_file(file_path):
    folder_names_set = set()
    try:
        with open(file_path, 'r') as file:
            for line in file:
                simplified_name = process_filename(line.strip())
                if simplified_name:
                    folder_names_set.add(simplified_name)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return folder_names_set

def format_exclusive_details(artist, details, parsed_date):
    # Remove the country code (or anything after the last comma)
    details = re.sub(r',\s[^,]*$', '', details)
    # Extract and format the parsed_date
    date_part = parsed_date.split(',')[0]
    # Extract the year from parsed_date
    try:
        year_from_parsed_date = datetime.strptime(parsed_date, '%b %d, %Y').year
    except ValueError:
        year_from_parsed_date = datetime.now().year  # Fallback to current year if parsing fails
    # Append the year from parsed_date if necessary
    if len(date_part.split(' ')) == 2:
        date_part += f', {year_from_parsed_date}'
    try:
        formatted_parsed_date = datetime.strptime(date_part, '%b %d, %Y').strftime('%Y-%m-%d')
    except ValueError:
        formatted_parsed_date = 'Invalid Date'
    # Check for dates in the details and process accordingly
    dates_in_details = re.findall(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\s\d{1,2}(?:\s&\s\d{1,2})?,\s\d{4}', details)

    if dates_in_details:
        formatted_dates = []
        for d in dates_in_details:
            date_match = re.search(r'(\w+)\s(\d{1,2})(?:\s&\s(\d{1,2}))?,\s(\d{4})', d)
            if date_match:
                month, day1, day2, year = date_match.groups()
                formatted_date1 = datetime.strptime(f'{month} {day1} {year}', '%B %d %Y').strftime('%Y-%m-%d')
                formatted_dates.append(formatted_date1)

                if day2:
                    formatted_date2 = datetime.strptime(f'{month} {day2} {year}', '%B %d %Y').strftime('%Y-%m-%d')
                    formatted_dates.append(formatted_date2)

        # Remove the original date from details
        for d in dates_in_details:
            details = details.replace(d, '').strip()

        # Construct display_text using the modified details
        display_text = f"{artist} {formatted_parsed_date} {details}"
        print(f"Constructed display_text before sanitization: {display_text}")
    else:
        # If no dates are found in details, use this block
        # Construct display_text using the modified details
        display_text = f"{artist} {formatted_parsed_date} {details}"
        print(f"Constructed display_text before sanitization: {display_text}")

    # Sanitize and format display_text
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        display_text = display_text.replace(char, '')

    display_text = display_text.replace('&', 'and').replace(' - ', ', ')
    print(f"Final display_text after sanitization: {display_text}")

    return display_text

def click_load_more_button(driver):
    try:
        # Locate the "Load More" button by its text and click it
        load_more_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Load More')]"))
        )
        load_more_button.click()
    except TimeoutException:
        print("clicked 'Load More' button. parsing...")
        return False
    return True

def setup_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Running in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Set the path to chromebrowser.exe
    chromedriver_path = os.path.join(os.getcwd(), "binaries", "chromedriver.exe")
    
    # Create a Service object with the executable path
    service = Service(chromedriver_path)
    
    # Use the Service object when creating the driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_single_release_or_exclusive(driver, url, combined_folder_names_set, args):
    try:
        if "/release/" in url: 
            exclusive_tag=False
            save_link =url # f'https://play.nugs.net/release/{release_number}'                    
            print(f'save_link: {save_link}')
        if "/exclusive/" in url:
            exclusive_tag=True
            save_link_exclusive =url # f'https://play.nugs.net/watch/livestreams/exclusive/{release_number}'
            print(f'save_link_exclusive: {save_link_exclusive}')
        save_link =url
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "_cover_ex3y9_35")))
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        if re.search(r'/exclusive/\d+$', url):
            # Extracting the artist/band name
            artist_tag = soup.find('h1')
            artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
            # Extracting the venue and location
            address_tag = soup.find('address')
            if address_tag:
                address_text = address_tag.get_text(strip=True)
                venue_location_parts = address_text.split(', ')
                if len(venue_location_parts) >= 2:
                    venue = venue_location_parts[0]
                    location = ', '.join(venue_location_parts[1:])
                else:
                    venue = "Unknown Venue"
                    location = "Unknown Location"
            else:
                venue = "Unknown Venue"
                location = "Unknown Location"
            # Extracting the date
            date_tag = soup.find('time')
            if date_tag:
                date_text = date_tag.get_text(strip=True)
                date_obj = datetime.strptime(date_text, '%b %d, %Y')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            else:
                formatted_date = "Unknown Date"
            # Creating the display text
            display_text = f"{artist} {formatted_date} "
            
            details=f'{venue}, {location}'
            FORMAT_display_text = format_exclusive_details(artist, details, date_text) 
            print(f'FORMAT_display_text: {FORMAT_display_text}')

        if re.search(r'/release/\d+$', url):
            try:
                # Extracting the artist/band name
                artist_tag = soup.find('h1')
                artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
                # Extracting the venue and location
                address_tag = soup.find('address')
                if address_tag:
                    address_text = address_tag.get_text(strip=True)
                    venue_location_parts = address_text.split(', ')
                    if len(venue_location_parts) >= 2:
                        venue = venue_location_parts[0]
                        location = venue_location_parts[1]
                    else:
                        venue = "Unknown Venue"
                        location = "Unknown Location"
                else:
                    venue = "Unknown Venue"
                    location = "Unknown Location"
                # Extracting the date
                date_tag = soup.find('time', string=re.compile(r'\b\w{3}\s\d{1,2},\s\d{4}\b'))
                if date_tag:
                    date_text = date_tag.get_text(strip=True)
                    date_obj = datetime.strptime(date_text, '%b %d, %Y')
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                else:
                    formatted_date = "Unknown Date"
                # Creating the display text
                display_text = f"{artist} {formatted_date} {venue}, {location}"
            except Exception as e:
                display_text = f"Error during extraction: {str(e)}"

        driver.get(save_link)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        page_source = driver.page_source        
        global folder_name
        folder_name=display_text.strip()
        # Wait for and find the image element
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "_cover_ex3y9_35")))
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        sanitized_text = re.sub(r'[<>:"?*]', '', display_text)
        display_text=sanitized_text
        global folder_path
        folder_path = create_data_folder(f"{sanitized_text}_xxx")
        html_path = os.path.join(data_directory,display_text.strip(), f"{sanitized_text.strip()}.html")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    
        image_element = soup.select_one(".my1 > div:nth-child(1) > div:nth-child(1) > img:nth-child(1)")
        if image_element:
            image_url = image_element['src'].replace('https://', 'http://')
            download_path =os.path.join(data_directory,display_text.strip(), f"{display_text.strip()}.jpg")
    
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
            with open(download_path, 'wb') as file:
                file.write(response.content)
    
        formatted_setlist, song_names, song_counter = parse_html_for_setlist(page_source)
        print(formatted_setlist)
        info_txt_path = os.path.join(data_directory, display_text.strip(), f"{display_text.strip()}.txt")
        with open(info_txt_path, 'w', encoding='utf-8') as f:
            f.write(f"{save_link_exclusive if exclusive_tag else save_link}\n{formatted_setlist}")
    
        # Assuming normalized_display_text, normalized_folder_names, and folder_names_set are already defined
        print(f'display_text.strip(): {display_text.strip()}')
        # Process the folder names and populate normalized_folder_names
        normalized_folder_names = {process_filename(name.strip()) for name in combined_folder_names_set}
        # Folder existence check and download decision
        normalized_display_text = process_filename(display_text.strip())
        # print(f'normalized_folder_names: {normalized_folder_names}')
        # print(f'normalized_display_text: {normalized_display_text}')
        if normalized_display_text in normalized_folder_names:
            print(f"filname is in <processed_filenames.txt> skipping: {normalized_display_text}")
        else:
            if exclusive_tag:
                perform_download(save_link_exclusive, video_directory, args, exclusive=True)  # Exclusive download
            else:
                perform_download(save_link, video_directory, args, exclusive=False)  # Regular download
        
    except Exception as e:
        print(f'exception {e}')

    # Logic to scrape details from the single release or excl
def scrape_for_release_links(driver,video_directory,combined_folder_names_set,args):
    url = driver.current_url
    print(f'url_in_scrape: {url}')
    # Check if the URL is for a single release or exclusive
    if "/release/" in url or "/exclusive/" in url:
        scrape_single_release_or_exclusive(driver, url,combined_folder_names_set,args)  # New function to handle single link scraping
    else:
        scraped_titles = []
        year_url = driver.current_url
        driver.get(year_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        while True:
            # Get the current page source
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            # Find all cards
            cards = soup.find_all(href=re.compile(r"/release/|/exclusive/\d+"))
            # Click the "Load More" button
            click_load_more_button(driver)
            # Check if there are any new cards loaded, and if not, exit the loop
            new_page_source = driver.page_source
            if page_source == new_page_source:
                break
        url=driver.current_url  
        if re.search(r'/exclusive/\d+$', url):
            # Extracting the artist/band name
            artist_tag = soup.find('h1')
            artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
            # Extracting the venue and location
            address_tag = soup.find('address')
            if address_tag:
                address_text = address_tag.get_text(strip=True)
                venue_location_parts = address_text.split(', ')
                if len(venue_location_parts) >= 2:
                    venue = venue_location_parts[0]
                    location = ', '.join(venue_location_parts[1:])
                else:
                    venue = "Unknown Venue"
                    location = "Unknown Location"
            else:
                venue = "Unknown Venue"
                location = "Unknown Location"
            # Extracting the date
            date_tag = soup.find('time')
            if date_tag:
                date_text = date_tag.get_text(strip=True)
                date_obj = datetime.strptime(date_text, '%b %d, %Y')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            else:
                formatted_date = "Unknown Date"
            # Creating the display text
            display_text = f"{artist} {formatted_date} {venue}, {location}"
            # Output
        if re.search(r'/release/\d+$', url):
            release_number = url.split('/')[-2]
            try:
                # Extracting the artist/band name
                artist_tag = soup.find('h1')
                artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
                # Extracting the venue and location
                address_tag = soup.find('address')
                if address_tag:
                    address_text = address_tag.get_text(strip=True)
                    venue_location_parts = address_text.split(', ')
                    if len(venue_location_parts) >= 2:
                        venue = venue_location_parts[0]
                        location = venue_location_parts[1]
                    else:
                        venue = "Unknown Venue"
                        location = "Unknown Location"
                else:
                    venue = "Unknown Venue"
                    location = "Unknown Location"
                # Extracting the date
                date_tag = soup.find('time', string=re.compile(r'\b\w{3}\s\d{1,2},\s\d{4}\b'))
                if date_tag:
                    date_text = date_tag.get_text(strip=True)
                    date_obj = datetime.strptime(date_text, '%b %d, %Y')
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                else:
                    formatted_date = "Unknown Date"
                # Creating the display text
                display_text = f"{artist} {formatted_date} {venue}, {location}"
            except Exception as e:
                display_text = f"Error during extraction: {str(e)}"
        else:    
            extracted_info = []
            scraped_titles=[]    
            for card in cards:
                exclusive_tag=False
                if "/release/" in card['href']:
                    release_number = card['href'].split('/')[-1]
                    img_tag = card.find('img')
                    if img_tag and 'alt' in img_tag.attrs:
                        alt_text = img_tag['alt']
                        # Parsing the alt text to extract information
                        band = re.search(r"Artist\s(.*?),", alt_text).group(1) if re.search(r"Artist\s(.*?),", alt_text) else None
                        date = re.search(r"released\sat\s-\s(.*?\d{4})", alt_text).group(1) if re.search(r"released\sat\s-\s(.*?\d{4})", alt_text) else None
                        # Extracting venue and location from div tags with class 'text-overflow'
                        venue_divs = card.find_all("div", class_="text-overflow")
                        venue = venue_divs[0].get_text(strip=True) if venue_divs and len(venue_divs) > 0 else None
                        location = venue_divs[1].get_text(strip=True) if venue_divs and len(venue_divs) > 1 else None
                    else:
                        band, venue, location, date = None, None, None, None
                    extracted_info.append({
                        'band': band,
                        'date': date,
                        'venue': venue,
                        'location': location,
                        'release_number': release_number,
                    })
                    date_obj = datetime.strptime(date, '%b %d, %Y')
                    formatted_date=date_obj.strftime('%Y-%m-%d')
                    display_text = f"{band} {formatted_date} {venue}, {location}"
                    print(display_text)
        
                elif "/exclusive/" in card['href']:
                    exclusive_tag=True
                    release_number = card['href'].split('/')[-1]
                    save_link_exclusive = f'https://play.nugs.net/watch/livestreams/exclusive/{release_number}'
        
                    # Logic for livestream links
                    artist = card.find('a', class_='white link').get_text(strip=True)
                    details = card.find('div', class_='text-overflow').get('title')
                    date = card.find('time').get_text(strip=True)
                    print(f"artist: {artist}")            
                    print(f"details: {details}")
                    print(f"date: {date}")
                    
                    #if livestream has date at location in the details insteasd of just the location
                    if 'at' in details:
                        parsed_details = details.split('at', 1)
                        details = parsed_details[1].strip()
                        date_parse = parsed_details[0].strip()
                        date_final = datetime.strptime(date_parse, "%B %d, %Y").strftime("%b %d, %Y")
                        date=date_final
    
                    display_text = format_exclusive_details(artist, details, date) 
                    print(display_text)
                if display_text.strip() in folder_names_set:
                    continue
                # Construct the save link
                save_link = f'https://play.nugs.net/release/{release_number}'
                print(f"save_link: {save_link}")
                driver.get(save_link)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                page_source = driver.page_source        
                global folder_name
                folder_name=display_text.strip()
                # Wait for and find the image element
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "_cover_ex3y9_35")))
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                # event_output_folder, event_folder_name = get_event_folder_name(event_info)
                sanitized_text = re.sub(r'[<>:"?*]', '', display_text)
                display_text=sanitized_text
                global folder_path
                folder_path = create_data_folder(f"{sanitized_text}_xxx")
                # print(folder_path)
                html_path = os.path.join(data_directory,display_text.strip(), f"{sanitized_text.strip()}.html")
                
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
    
                image_element = soup.select_one(".my1 > div:nth-child(1) > div:nth-child(1) > img:nth-child(1)")
                if image_element:
                    image_url = image_element['src'].replace('https://', 'http://')
                    download_path =os.path.join(data_directory,display_text.strip(), f"{display_text.strip()}.jpg")
        
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
                    with open(download_path, 'wb') as file:
                        file.write(response.content)
    
                formatted_setlist, song_names, song_counter = parse_html_for_setlist(page_source)
                print(formatted_setlist)
                info_txt_path = os.path.join(data_directory, display_text.strip(), f"{display_text.strip()}.txt")
                # Assuming normalized_display_text, normalized_folder_names, and folder_names_set are already defined
                print(f'\nfilename to process: {display_text.strip()}')
                # Process the folder names and populate normalized_folder_names
                normalized_folder_names = {process_filename(name.strip()) for name in combined_folder_names_set}
                # Folder existence check and download decision
                normalized_display_text = process_filename(display_text.strip())
                # print(f'normalized_folder_names: {normalized_folder_names}')
                # print(f'normalized_display_text: {normalized_display_text}')
                if normalized_display_text in normalized_folder_names:
                    print(f"Folder already exists: {normalized_display_text}")
                else:
                    # Folder does not exist, proceed with download
                    if exclusive_tag:
                        perform_download(save_link_exclusive, video_directory, args, exclusive=True)  # Exclusive download
                    else:
                        perform_download(save_link, video_directory, args, exclusive=False)  # Regular download
                
                    # Write info to the text file regardless of the tag
                    with open(info_txt_path, 'w', encoding='utf-8') as f:
                        f.write(f"{save_link_exclusive if exclusive_tag else save_link}\n{formatted_setlist}")
            
                folder_name=sanitize_name_colon(folder_name)
                html_path = os.path.join(data_directory,folder_name, f"{folder_name}.html")
                os.makedirs(os.path.join(data_directory,folder_name), exist_ok=True)
                with open(html_path, 'w', encoding='utf-8') as f:
                  f.write(driver.page_source)
                scraped_titles.append(display_text)
    
def sanitize_name(name):
    # Define illegal characters for file names
    illegal_chars = r'[<>:"/\\|?*]'
    # Replace illegal characters with an underscore
    return re.sub(illegal_chars, '_', name)

def parse_html_for_setlist(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    setlist_data = []
    song_names = []
    song_counter = 0
    # Identify all headers and track cards
    elements = soup.find_all(['h2', 'div'], class_=['mt2 gray fs fs-14 ls-1 lh-20 bold', '_TrackCard_btsdq_2 track-card track-item'])
    # Initialize current set and track list
    current_set_name = "Set 1"
    current_tracks = []
    for element in elements:
        if element.name == 'h2':  # Check if it is a header
            # If the current track list is not empty, append it to the setlist data
            if current_tracks:
                setlist_data.append(f"    {current_set_name}:\n" + ''.join(current_tracks))
                current_tracks = []  # Reset the current tracks for the next set
            set_name = element.get_text(strip=True)
            if 'set one' in set_name.lower() or 'set 1' in set_name.lower():
                current_set_name = "Set 1"
            elif 'set two' in set_name.lower() or 'set 2' in set_name.lower():
                current_set_name = "Set 2"
            elif 'encore' in set_name.lower():
                current_set_name = "Encore"
        elif element.name == 'div':  # Check if it is a track card
            track_info = element.find('span', class_='hidden')
            if track_info:
                song_counter += 1
                track_name = track_info.get_text(strip=True).split('. ', 1)[-1]
                song_names.append(track_name)
                current_tracks.append(f"    {song_counter}. {track_name}\n")
    # Append any remaining tracks to the setlist data
    if current_tracks:
        setlist_data.append(f"    {current_set_name}:\n" + ''.join(current_tracks))
    # Join the setlist parts into one formatted string
    formatted_setlist = "SETLIST:\n" + ''.join(setlist_data)
    return formatted_setlist.strip(), song_names, song_counter

def extract_identifier(video_name):
    # Strip the resolution part from the video file name
    # Assuming the resolution part is formatted like "_1080p.mkv"
    return video_name.rsplit('_', 1)[0]
def sanitize_name_colon(name):
    # Replace illegal characters with underscores
    sanitized_name = re.sub(r':', '_', name)
    return sanitized_name

def create_data_folder(video_name):
    global data_directory, folder_path
    identifier = sanitize_name_colon(extract_identifier(video_name))
    folder_path = os.path.join(data_directory, identifier).strip()

    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        print(f"Created folder: {folder_path}")
    return folder_path

def login_to_nugs(driver, nugs_email, nugs_password):
    print('Logging in to Nugs...')
    driver.get('https://id.nugs.net/account/login')
    email_elem = driver.find_element(By.NAME, "Input.Email")
    email_elem.send_keys(nugs_email)
    password_elem = driver.find_element(By.NAME, "Input.Password")
    password_elem.send_keys(nugs_password)
    login_button = driver.find_element(By.CSS_SELECTOR, 'button.btn.btn-block.btn-primary')
    login_button.click()
    WebDriverWait(driver, 20).until(EC.url_changes('https://id.nugs.net/account/login'))
    print('Logged in successfully.')
    return driver

def navigate_to_page(driver, page):
    # Simplified URL mapping
    urls = {
        'livestreams': 'https://play.nugs.net/watch/livestreams/recent',
        'videos': 'https://play.nugs.net/watch/videos/recent'
    }
    target_url = urls.get(page, page)  # Use the provided page URL if not in predefined list
    print(f'Navigating to {target_url}...')
    driver.get(target_url)
    try:
        # Wait for specific elements indicating page load completion
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Finish')] | //a[contains(@href, '/release/') or contains(@href, '/exclusive/')]"))
        )
        finish_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Finish')]")
        if finish_buttons:
            finish_buttons[0].click()
            print('Clicked Finish')
    except TimeoutException:
        print('Timeout waiting for elements on page.')
    except Exception as e:
        print(f'Unexpected error: {e}')
    return driver

def run_go_program(release_link, video_save_path, video_dl_base_url):
    match = re.search(r'/(\d+)$', release_link)
    numbers = match.group(1) if match else None
    if numbers:
        video_dl_link = video_dl_base_url + numbers
        command = f'cd binaries/Nugs-Downloader-main; go run main.go structs.go -o "{video_save_path}" "{video_dl_link}"'
        powershell_command = ['powershell', '-Command', command]
        last_percentage = None
        with subprocess.Popen(powershell_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            for line in proc.stdout:
                match = re.search(r'(\d+)%', line)
                if match:
                    current_percentage = match.group(1)
                    if current_percentage != last_percentage:
                        print(f"{current_percentage}% complete", end='\r', flush=True)
                        last_percentage = current_percentage
                else:
                    print(line.strip())
            for line in proc.stderr:
                print(f"Error: {line.strip()}")
    else:
        print("Invalid release link provided.")

def perform_download(link,video_directory , args, exclusive=False):
    target_drive=video_directory
    if not link:
        print("No link provided for download.")
        return
    video_dl_base_url = 'https://play.nugs.net/#/videos/artist/1045/Dead%20and%20Company/container/' if not exclusive else 'https://play.nugs.net/watch/livestreams/exclusive/'
    with tempfile.TemporaryDirectory(dir=target_drive) as temp_dir:
        print(f"\ntemporary download path: {temp_dir}")
        # print(f"Link: {link}")
        try:
            run_go_program(link, temp_dir, video_dl_base_url)
        except Exception as e:
            print(f"Error running Go program: {e}")
            return
        files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir)]
        files.sort(key=os.path.getctime, reverse=True)
        if not files:
            print("No files found in the temporary directory.")
            return

        latest_file = files[0]
        latest_filename = os.path.basename(latest_file)
        latest_filename = sanitize_name_colon(latest_filename)  # Ensure sanitize_name_colon is defined

        last_underscore_index = latest_filename.rfind('_')
        suffix = latest_filename[last_underscore_index + 1:]
        new_folder_name = f"{folder_name} {suffix}"
        new_file_path = os.path.join(video_directory, new_folder_name)
        
        with open('processed_filenames.txt', 'a') as file:
            file.write(f"{new_folder_name}\n")    
        os.makedirs(video_directory, exist_ok=True)
        shutil.move(latest_file, new_file_path)
        print(f"{latest_filename} renamed and moved to: {new_file_path}")

        # # New upload integration
        # if args.upload:
        #     # upload_file_path = args.upload 

            # command = [
            #     wetransfertool -ul new_file_path
            # ]
        # try:
        #     subprocess.run(command, check=True)
        # except subprocess.CalledProcessError as e:
        #     print(f"An error occurred during file upload: {e}")

def parse_arguments():
    parser = argparse.ArgumentParser(description='Automated video downloader for Nugs.net.')
    parser.add_argument('--page-url', 
                        help='URL of the page to navigate to (default: videos). Can be "videos", "livestreams", or any valid URL.', 
                        default='https://play.nugs.net/watch/videos/recent')
    parser.add_argument('--upload', 
                        action='store_true', 
                        help='Enable upload functionality for the downloaded video.')
    
    return parser.parse_args()
def main():
    print("\n**starting script**")

    args = parse_arguments()  # Parse command-line arguments

    # Load credentials for Nugs.net
    nugs_email, nugs_password, video_directory = load_credentials()

    # Initialize folder names sets
    folder_names_set_from_file = process_filenames_from_file('processed_filenames.txt')
    folder_names_set_from_dir = initialize_folder_names_set(video_directory)
    combined_folder_names_set = folder_names_set_from_dir.union(folder_names_set_from_file)

    # Display combined folder names for verification
    print("\nalready processed files (artist, date) set:")
    for name in sorted(combined_folder_names_set):
        print(name)

    # Setup WebDriver and login to Nugs.net
    driver = setup_headless_driver()
    driver = login_to_nugs(driver, nugs_email, nugs_password)

    # Validate the page-url argument
    valid_choices = ['videos', 'livestreams']
    if args.page_url not in valid_choices:
        parsed_url = urlparse(args.page_url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            print(f"Invalid URL provided: {args.page_url}")
            return

    # Determine pages to scrape
    pages_to_scrape = [args.page_url]  # Directly use the provided page URL
    for page in pages_to_scrape:
        print(f'pages_to_scrape: {pages_to_scrape}')

        driver = navigate_to_page(driver, page)  # Navigate to each page
    #scrape
    scrape_for_release_links(driver,video_directory,combined_folder_names_set,args)
if __name__ == '__main__':
    main()
