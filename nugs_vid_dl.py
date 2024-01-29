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
global headless_driver


# Global variables (Refactor and manage)
video_directory = None
data_directory = None
audio_directory = None
folder_name = None
folder_names_set = set()
extracted_info = []
driver = None
use_headless_driver = True
date_pattern = re.compile(r'\b\w+\s\d{1,2},\s\d{4}\b')

def load_credentials():
    global nugs_email, nugs_password, data_directory, video_directory, audio_directory
    config = configparser.ConfigParser()
    config.read('nugs_vid_dl_config.ini')
    
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
        'audio': os.path.join(current_directory, 'audio_directory'),}

def get_valid_path(network_path, local_path):
    if os.path.exists(network_path):
        return network_path
    else:
        os.makedirs(local_path, exist_ok=True)
        return local_path

def update_json_config(nugs_config):
    config_file_path = 'binaries/config.json'
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

def click_load_more_button(driver):
    try:
        # Locate the "Load More" button by its text and click it
        load_more_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Load More')]")))
        load_more_button.click()
    except TimeoutException:
        print("clicked 'Load More' button. parsing...\n")
        return False
    return True

def scrape_release_info(driver, video_directory, combined_folder_names_set, args):
    try:
        url = driver.current_url
        # Check if the URL directly points to a release or exclusive content
        exclusive_tag= False

        if "/release/" in url or "/exclusive/" in url:
            if "/exclusive/" in url:
                exclusive_tag= True

            process_link(driver, url,exclusive_tag, video_directory, combined_folder_names_set, args)
        else:
            # Extract relevant links from the page for further processing
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            cards = soup.find_all(href=re.compile(r"/release/|/exclusive/\d+"))
            for card in cards:
                process_card(driver, card, video_directory, combined_folder_names_set, args)
    except Exception as e:
        print(f'Exception in scrap_release_info: {e}')

def process_card(driver, card, video_directory, combined_folder_names_set, args):
    try:
        exclusive_tag = False
        if "/release/" in card['href']:
            release_number = card['href'].split('/')[-1]
            save_link = f'https://play.nugs.net/release/{release_number}'
            process_link(driver, save_link, exclusive_tag, video_directory, combined_folder_names_set, args)
        elif "/exclusive/" in card['href']:
            exclusive_tag = True
            release_number = card['href'].split('/')[-1]
            save_link_exclusive = f'https://play.nugs.net/watch/livestreams/exclusive/{release_number}'
            process_link(driver, save_link_exclusive, exclusive_tag, video_directory, combined_folder_names_set, args)
    except Exception as e:
        print(f'Exception in process_card: {e}')
        
def process_link(driver, url, exclusive_tag, video_directory, combined_folder_names_set, args):
    try:
        # Navigate to the link and extract the page source
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "_cover_ex3y9_35")))
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        # Initialize 'details' variable
        details = None

        # Extract and process information based on URL type
        if "/exclusive/" in url:
            formatted_details, artist, venue, event_date = extract_exclusive_info(soup)
            details = (formatted_details, artist, venue, event_date)
        else:  # Assuming it's a "/release/" URL
            formatted_details, artist, venue, event_date = extract_release_info(soup)
            details = (formatted_details, artist, venue, event_date)

        # Additional processing, saving files, and downloading images
        handle_additional_processing(driver, details, exclusive_tag, video_directory, combined_folder_names_set, args, url)
    except Exception as e:
        print(f'Exception in process_link: {e}')

def extract_and_process_date(details):
    # Extended pattern to match a wider range of date formats, including "MM DD YYYY"
    date_patterns = [
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b',
        r'\b\d{2}\s\d{2}\s\d{4}\b'  # Pattern for "MM DD YYYY"
    ]
    for pattern in date_patterns:
        date_match = re.search(pattern, details)
        if date_match:
            date_str = date_match.group()
            # Attempt to parse the date string
            try:
                date_obj = datetime.strptime(date_str, '%B %d, %Y')
            except ValueError:
                try:
                    date_obj = datetime.strptime(date_str, '%b %d, %Y')
                except ValueError:
                    try:
                        # Handle "MM DD YYYY" format
                        date_obj = datetime.strptime(date_str, '%m %d %Y')
                    except ValueError:
                        # Handle case where year is missing
                        date_obj = datetime.strptime(f"{date_str}, {datetime.now().year}", '%b %d, %Y')
            formatted_date = date_obj.strftime('%Y-%m-%d')
            new_details = re.sub(pattern, '', details).strip()
            new_details = re.sub(r'\s*:\s*,', ':', new_details)
            new_details = re.sub(r'\s*,\s*', ', ', new_details).strip(', ')
            new_details = re.sub(r'\s*:\s*', ': ', new_details)
    return formatted_date, new_details if new_details is not None else ''    

def extract_exclusive_info(soup):
    try:
        artist_tag = soup.find('h1')
        artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"

        address_tag = soup.find('address')
        venue = address_tag.get_text(strip=True) if address_tag else "Unknown Venue"
        
        time_tag = soup.find('time')
        if time_tag and time_tag.has_attr('datetime'):
            # Extract and format the date
            date_str = time_tag['datetime']
            try:
                event_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d')
            except ValueError:
                event_date = 'Invalid Date'
        else:
            event_date = 'Unknown Date'
    
        formatted_details = format_exclusive_details(artist, venue, event_date)
        return formatted_details, artist, venue, event_date
    except Exception as e:
        print(f'Error in extract_exclusive_info: {e}')
        return "Unknown Artist at Unknown Venue on Unknown Date", "Unknown Artist", "Unknown Venue", "Unknown Date"
    
def format_exclusive_details(artist, venue_location, event_date):
    # Regular expression to find and extract date in the details
    date_pattern = re.compile(r'(\w+)\s(\d{1,2}),\s(\d{4})')
    date_match = date_pattern.search(venue_location)

    if date_match:
        # Extract and format the date
        month, day, year = date_match.groups()
        try:
            formatted_date = datetime.strptime(f'{month} {day} {year}', '%B %d %Y').strftime('%Y-%m-%d')
        except ValueError:
            formatted_date = 'Invalid Date'
        venue_location = date_pattern.sub('', venue_location)
        venue_location = venue_location.replace('  ', ' ').strip()
    else:
        # If no date found in details, use event_date
        formatted_date = event_date if event_date else 'Invalid Date'
    # Construct the display text
    display_text = f"{artist} {formatted_date} {venue_location}"
    return display_text
    
def extract_release_info(soup):
    try:
        artist, venue_location, date_text = extract_common_details(soup)
        formatted_details = f"{artist} {date_text} {venue_location}"
        return formatted_details, artist, venue_location, date_text
    except Exception as e:
        print(f'Error in extract_release_info: {e}')
        # Ensure to return four values as expected by the calling function
        return "Unknown Artist at Unknown Venue on Unknown Date", "Unknown Artist", "Unknown Venue", "Unknown Date"

def extract_common_details(soup):
    artist_tag = soup.find('h1')
    artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
    address_tag = soup.find('address')
    venue_location = extract_venue_location(address_tag)
    date_tag = soup.find('time')
    date_text = extract_date(date_tag)
    return artist, venue_location, date_text

def extract_venue_location(address_tag):
    if address_tag:
        # Directly use the text from the <address> tag
        full_address = address_tag.get_text(strip=True)
        # If the address contains more details (like 'Premiere:', 'Friday Night Cheese:', etc.), extract only the venue and location part
        venue_location = re.sub(r'^(Premiere:|Friday Night Cheese:)\s*', '', full_address)
    else:
        venue_location = "Unknown Venue_Location"
    return venue_location

def handle_additional_processing(driver, details, exclusive_tag, video_directory, combined_folder_names_set, args, url):
    global data_directory
    # Handles additional processing steps
    display_text, artist, venue_location, date_text = details
    folder_name = process_folder_name(display_text)
    folder_path = create_data_folder(folder_name, data_directory)
    save_html_content(driver, folder_path, display_text)
    download_image(driver, folder_path, display_text)
    formatted_setlist = handle_setlist_and_info(driver, folder_path, display_text, exclusive_tag, args)
    download_video_if_applicable(display_text, exclusive_tag, folder_path, video_directory, args, combined_folder_names_set,url)
    # Write the link and formatted setlist to the file
    info_txt_path = os.path.join(folder_path, "info.txt")
    with open(info_txt_path, 'w', encoding='utf-8') as f:
        f.write(f"{url}\n{formatted_setlist}")

def process_folder_name(display_text):
    # Sanitizes and processes folder name
    sanitized_text = sanitize_name(display_text)
    return sanitized_text.strip()

def create_data_folder(folder_name, video_directory):
    folder_path = os.path.join(video_directory, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def save_html_content(driver, folder_path, display_text):
    html_path = os.path.join(folder_path, f"{display_text}.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)

def download_image(driver, folder_path, display_text):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    image_element = soup.select_one(".my1 > div:nth-child(1) > div:nth-child(1) > img:nth-child(1)")
    if image_element:
        image_url = image_element['src'].replace('https://', 'http://')
        download_path = os.path.join(folder_path, f"{display_text}.jpg")
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        with open(download_path, 'wb') as file:
            file.write(response.content)

def handle_setlist_and_info(driver, folder_path, display_text, exclusive_tag, args):
    # Parses HTML content for setlist and handles additional info
    page_source = driver.page_source
    formatted_setlist, song_names, song_counter = parse_html_for_setlist(page_source)
    # Additional logic for handling info
    return formatted_setlist

def download_video_if_applicable(display_text, exclusive_tag, folder_path, video_directory, args, combined_folder_names_set,url):
    normalized_folder_names = {process_filename(name.strip()) for name in combined_folder_names_set}
    normalized_display_text = process_filename(display_text.strip())
    if normalized_display_text not in normalized_folder_names:
        if exclusive_tag:
            print(display_text)
            perform_download(url, video_directory, args, display_text, exclusive=True)
        else:
            print(display_text)
            perform_download(url, video_directory, args, display_text, exclusive=False)
    else:
        print(f"{display_text} is in processed_filenames.txt, skipping: {normalized_display_text}")

def extract_date(date_tag):
    if date_tag:
        date_text = date_tag.get_text(strip=True)
        date_obj = datetime.strptime(date_text, '%b %d, %Y')
        formatted_date = date_obj.strftime('%Y-%m-%d')
    else:
        formatted_date = "Unknown Date"
    return formatted_date

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

def setup_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Running in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chromedriver_path = os.path.join(os.getcwd(), "binaries", "chromedriver.exe")
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

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
    print('\n\nlogged in successfully\n')
    return driver

def navigate_to_page(driver, page):
    urls = {
        'exclusive': 'https://play.nugs.net/watch/livestreams/recent',
        'watch': 'https://play.nugs.net/watch/videos/recent'
    }
    target_url = urls.get(page, page)  # Use the provided page URL if not in predefined list
    print(f'\nNavigating to {target_url}...\n')
    driver.get(target_url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Finish')] | //a[contains(@href, '/release/') or contains(@href, '/exclusive/')]")))
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
    print("starting nugs-downloader...")
    match = re.search(r'/(\d+)$', release_link)
    numbers = match.group(1) if match else None

    if numbers:
        video_dl_link = video_dl_base_url + numbers
        # Convert the path to Unix-style
        unix_style_video_save_path = video_save_path.replace('\\', '/')
        working_dir = 'binaries/'
        # Construct the command to run the nugs_downloader executable
        command = f'main.exe -o "{unix_style_video_save_path}" {video_dl_link}'
        print(f"Command to be executed: {command}")
        # Use the working directory in subprocess
        with subprocess.Popen(command, cwd=working_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            last_percentage = None
            for line in proc.stdout:
                match = re.search(r'(\d+)%', line)
                if match:
                    current_percentage = match.group(1)
                    if current_percentage != last_percentage:
                        print(f"{current_percentage}% complete", end='\r', flush=True)
                        last_percentage = current_percentage
                else:
                    # Printing the remaining stdout line only if it's not a percentage update
                    print(f"STDOUT: {line.strip()}", end='\r')
            for line in proc.stderr:
                print(f"STDERR: {line.strip()}")
    else:
        print("Invalid release link provided.")
    print("\nrun_go_program completed.")

def perform_download(link,video_directory , args,display_text, exclusive=False):
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
        latest_file=convert_to_mkv(latest_file)
        latest_filename = os.path.basename(latest_file)
        latest_filename = sanitize_name_colon(latest_filename)  # Ensure sanitize_name_colon is defined
        
        last_underscore_index = latest_filename.rfind('_')
        suffix = latest_filename[last_underscore_index + 1:]
        new_folder_name = f"{display_text} {suffix}"
        new_file_path = os.path.join(video_directory, new_folder_name)
        
        with open('processed_filenames.txt', 'a') as file:
            file.write(f"{new_folder_name}\n")    
        os.makedirs(video_directory, exist_ok=True)
        shutil.move(latest_file, new_file_path)
        print(f"{latest_filename} renamed and moved to: {new_file_path}")

def convert_to_mkv(filename):
    if not filename.endswith('.mkv'):
        # Construct the FFmpeg command to convert the file to .mkv
        new_filename = filename.rsplit('.', 1)[0] + '.mkv'
        ffmpeg_convert_command = [ os.path.join(os.getcwd(), "binaries",'ffmpeg'), '-i', filename, '-c', 'copy', new_filename]
        subprocess.run(ffmpeg_convert_command)
        return new_filename
    return filename

def parse_arguments():
    parser = argparse.ArgumentParser(description='Automated video downloader for Nugs.net.')
    parser.add_argument('--page-url', nargs='+', help='URLs of the pages to navigate to. Can be multiple URLs.', default=['https://play.nugs.net/watch/videos/recent'])
    parser.add_argument('--upload', action='store_true', help='Enable upload functionality for the downloaded video.')
    return parser.parse_args()

def main():
    print("\n**starting script**")
    nugs_email, nugs_password, video_directory = load_credentials()
    args = parse_arguments()  # Parse command-line arguments
    pages_to_scrape = []  # Initialize an empty list to hold valid URLs
    folder_names_set_from_file = process_filenames_from_file('processed_filenames.txt')
    folder_names_set_from_dir = initialize_folder_names_set(video_directory)
    combined_folder_names_set = folder_names_set_from_dir.union(folder_names_set_from_file)
    # Display combined folder names for verification
    print("\npotentially skipping the following (form processed.txt):")
    for name in sorted(combined_folder_names_set):
        print(name)
        
    valid_choices = ['watch', 'exclusive']
    for page_url in args.page_url:
        # Check if the URL is one of the valid choices
        if page_url in valid_choices:
            pages_to_scrape.append(page_url)
        else:
            # Validate the URL format for other URLs
            parsed_url = urlparse(page_url)
            if all([parsed_url.scheme, parsed_url.netloc]):
                pages_to_scrape.append(page_url)
            else:
                print(f"Invalid URL provided: {page_url}")

    if not pages_to_scrape:
        print("No valid URLs provided. Exiting.")
        return

    print(f'Pages to scrape: {pages_to_scrape}')
    for page in pages_to_scrape:
        # Validate each URL in the list
        parsed_url = urlparse(page)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            print(f"Invalid URL provided: {page}")
            continue  # Skip to the next URL

        # Assuming you have defined setup_headless_driver, login_to_nugs, etc.
        driver = setup_headless_driver()
        driver = login_to_nugs(driver, nugs_email, nugs_password)
        driver = navigate_to_page(driver, page)  # Navigate to each page
        scrape_release_info(driver, video_directory, combined_folder_names_set, args)

    
    
if __name__ == '__main__':
    main()





#------------------------------------------------------------------------------
        # # upload integration
        # if args.upload:
        #     # upload_file_path = args.upload 

            # command = [
            #     wetransfertool -ul new_file_path
            # ]
        # try:
        #     subprocess.run(command, check=True)
        # except subprocess.CalledProcessError as e:
        #     print(f"An error occurred during file upload: {e}")