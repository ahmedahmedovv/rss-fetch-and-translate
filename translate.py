import feedparser
from deep_translator import GoogleTranslator
import os
import time
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml
from dateutil import parser
from logging.handlers import RotatingFileHandler
import requests
from requests.exceptions import RequestException
from urllib.parse import urlparse
from bs4 import BeautifulSoup

class RSSTranslator:
    def __init__(self, config_path='config.yaml'):
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create log directory if it doesn't exist
        self.log_dir = Path(self.config['logging']['log_directory'])
        self.log_dir.mkdir(exist_ok=True)
        
        self.file_path = self.config['paths']['feed_urls']
        self.feeds = self.read_feed_urls()
        
        # Create both data and lock directories
        self.data_dir = Path(self.config['paths']['data_directory'])
        self.data_dir.mkdir(exist_ok=True)
        self.lock_dir = self.data_dir  # Lock files will be in same directory
        self.output_file = self.data_dir / self.config['paths']['output_file']
        
        self.console = Console()
        logging.info(f"RSSTranslator initialized with {len(self.feeds)} feeds")
        self.processed_links = self.load_processed_links()

    def read_feed_urls(self):
        """Read RSS feed URLs from the file"""
        with open(self.file_path, 'r') as file:
            return [line.strip() for line in file if line.strip() and not line.startswith('#')]

    def translate_text(self, text):
        """Translate text to configured target language"""
        try:
            if text:
                # First remove HTML tags
                soup = BeautifulSoup(text, 'html.parser')
                text = soup.get_text()
                
                # Strip quotes if they wrap the entire text
                text = text.strip('"')
                
                # Add delay to respect rate limits
                time.sleep(1)
                translator = GoogleTranslator(
                    source='auto',
                    target=self.config['translator']['target_language']
                )
                translated = translator.translate(text)
                
                # Strip quotes from translation if present
                translated = translated.strip('"')
                return translated
            return ""
        except Exception as e:
            return f"Translation error: {str(e)}"

    def load_processed_links(self):
        """Load previously processed entry links from the JSON file"""
        try:
            if self.output_file.exists():
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                return {entry['link'] for entry in existing_data}
            return set()
        except Exception as e:
            logging.error(f"Error loading processed links: {str(e)}")
            return set()

    def fetch_and_translate_feed(self, url):
        """Fetch and translate a single feed"""
        try:
            # Increase timeout and add retry logic
            max_retries = self.config.get('feed_processing', {}).get('max_retries', 3)
            timeout = self.config.get('feed_processing', {}).get('request_timeout', 30)
            
            for attempt in range(max_retries):
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1'
                    }
                    
                    response = requests.get(
                        url, 
                        timeout=timeout,
                        headers=headers,
                        verify=True
                    )
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                    break  # If successful, break the retry loop
                except RequestException as e:
                    if attempt == max_retries - 1:  # Last attempt
                        rprint(f"[red]Error fetching feed {url} after {max_retries} attempts: {str(e)}[/red]")
                        logging.error(f"Error fetching feed {url}: {str(e)}")
                        return
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            # Check if feed parsing was successful
            if not feed.entries and not getattr(feed, 'status', 200) == 200:
                rprint(f"[red]Error parsing feed: {url}[/red]")
                return
            
            feed_title = feed.feed.title if hasattr(feed.feed, 'title') else url
            
            if not feed.entries:
                rprint(f"[yellow]ℹ No entries found for: {feed_title}[/yellow]")
                return
            
            feed_data = []
            
            # Calculate the cutoff time (24 hours ago) with UTC timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.config['feed_processing']['max_age_days'])
            
            # Process all entries within last 24 hours
            for entry in feed.entries:
                # Skip if entry has already been processed
                if entry.link in self.processed_links:
                    continue

                pub_date = entry.published if hasattr(entry, 'published') else "No date"
                
                # Use dateutil parser instead of manual format parsing
                try:
                    parsed_date = parser.parse(pub_date)
                    # Ensure timezone info exists
                    if parsed_date.tzinfo is None:
                        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    logging.warning(f"Could not parse date '{pub_date}' for entry from {url}")
                    continue
                
                # Skip if it's too old
                if parsed_date < cutoff_time:
                    continue

                title = self.translate_text(entry.title)
                description = self.translate_text(entry.description) if hasattr(entry, 'description') else ""

                entry_data = {
                    'title': title,
                    'published': pub_date,
                    'link': entry.link,
                    'description': description[:self.config['translator']['description_length']],
                    'original_date': parsed_date.isoformat(),
                    'translated_at': datetime.now(timezone.utc).isoformat()
                }

                self.processed_links.add(entry.link)
                feed_data.append(entry_data)

            if feed_data:
                self.save_to_json(feed_data)
                rprint(f"[green]✓[/green] Added {len(feed_data)} new entries from: {feed.feed.title if hasattr(feed.feed, 'title') else url}")
            else:
                rprint(f"[yellow]ℹ[/yellow] No new entries found for: {feed.feed.title if hasattr(feed.feed, 'title') else url}")

        except Exception as e:
            error_msg = f"Error processing feed {url}: {str(e)}"
            rprint(f"[red]{error_msg}[/red]")
            logging.error(error_msg, exc_info=True)
            return

    def save_to_json(self, feed_data):
        """Save feed data to JSON file"""
        try:
            # Create lock file in data directory
            lock_file = self.lock_dir / 'translated_feeds.lock'
            
            while lock_file.exists():
                time.sleep(0.1)
            
            # Ensure parent directory exists before creating lock file
            lock_file.parent.mkdir(exist_ok=True)
            
            # Create lock file
            lock_file.touch()
            
            try:
                # Check if the file exists and is not empty
                if self.output_file.exists() and self.output_file.stat().st_size > 0:
                    try:
                        with open(self.output_file, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                    except json.JSONDecodeError:
                        logging.error("Corrupted JSON file detected, creating backup and starting fresh")
                        # Create backup of corrupted file
                        backup_file = self.output_file.with_suffix('.backup')
                        self.output_file.rename(backup_file)
                        existing_data = []
                else:
                    existing_data = []

                # Add new data
                existing_data.extend(feed_data)

                # Save updated data
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=self.config['output']['json_indent'])
                
                logging.info(f"Data saved to {self.output_file}")

            finally:
                # Only try to remove if it exists
                if lock_file.exists():
                    lock_file.unlink()

        except Exception as e:
            logging.error(f"Error saving to JSON: {str(e)}", exc_info=True)

def main():
    console = Console()
    
    # Create log directory before setting up logging
    log_dir = Path('log')
    log_dir.mkdir(exist_ok=True)
    
    # Initialize RSSTranslator first
    app = RSSTranslator()
    
    # Now set up logging with the app config
    log_file = log_dir / 'rss_translator.log'
    handler = RotatingFileHandler(
        log_file,
        maxBytes=app.config['logging'].get('max_bytes', 10485760),
        backupCount=app.config['logging'].get('backup_count', 5)
    )
    handler.setFormatter(logging.Formatter(app.config['logging']['log_format']))
    
    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    
    try:
        console.print("[bold blue]Beginning feed processing[/bold blue]")
        
        # Use ThreadPoolExecutor with timeout
        with ThreadPoolExecutor(max_workers=app.config['threading']['max_workers']) as executor:
            futures = []
            for url in app.feeds:
                future = executor.submit(app.fetch_and_translate_feed, url)
                futures.append(future)
            
            # Add timeout for each future
            for future in as_completed(futures, timeout=30):  # 30 second timeout per feed
                try:
                    future.result(timeout=30)
                except TimeoutError:
                    console.print("[yellow]Warning: Feed processing timed out[/yellow]")
                except Exception as e:
                    console.print(f"[bold red]Error in feed processing: {str(e)}[/bold red]")
        
        console.print("[bold green]✓ Feed processing completed successfully![/bold green]")
        
    except TimeoutError:
        console.print("[bold red]Process timed out![/bold red]")
        logging.error("Process timed out")
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
