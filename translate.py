import feedparser
from googletrans import Translator
import os
import time
from datetime import datetime
import json
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml

class RSSTranslator:
    def __init__(self, config_path='config.yaml'):
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create log directory if it doesn't exist
        self.log_dir = Path(self.config['logging']['log_directory'])
        self.log_dir.mkdir(exist_ok=True)
        
        self.file_path = self.config['paths']['feed_urls']
        self.translator = Translator()
        self.feeds = self.read_feed_urls()
        
        # Create data directory if it doesn't exist
        self.data_dir = Path(self.config['paths']['data_directory'])
        self.data_dir.mkdir(exist_ok=True)
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
                return self.translator.translate(
                    text, 
                    dest=self.config['translator']['target_language']
                ).text
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
            feed = feedparser.parse(url)
            feed_data = []
            
            for entry in feed.entries[:self.config['translator']['entries_limit']]:
                # Skip if entry has already been processed
                if entry.link in self.processed_links:
                    continue

                title = self.translate_text(entry.title)
                description = self.translate_text(entry.description) if hasattr(entry, 'description') else ""
                pub_date = entry.published if hasattr(entry, 'published') else "No date"

                # Convert pub_date to ISO format
                try:
                    parsed_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %z')
                    iso_pub_date = parsed_date.isoformat()
                except ValueError:
                    try:
                        parsed_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                        iso_pub_date = parsed_date.isoformat()
                    except ValueError:
                        iso_pub_date = pub_date

                entry_data = {
                    'title': title,
                    'published': pub_date,
                    'link': entry.link,
                    'description': description[:self.config['translator']['description_length']],
                    'original_date': iso_pub_date,
                    'translated_at': datetime.now().isoformat()
                }

                self.processed_links.add(entry.link)
                feed_data.append(entry_data)

            if feed_data:
                self.save_to_json(feed_data)
                rprint(f"[green]✓[/green] Added {len(feed_data)} new entries from: {feed.feed.title if hasattr(feed.feed, 'title') else url}")
            else:
                rprint(f"[yellow]ℹ[/yellow] No new entries found for: {feed.feed.title if hasattr(feed.feed, 'title') else url}")

        except Exception as e:
            rprint(f"[red]Error processing feed {url}: {str(e)}[/red]")
            logging.error(f"Error processing feed {url}: {str(e)}")

    def save_to_json(self, feed_data):
        """Save feed data to JSON file"""
        try:
            # Load existing data if file exists
            if self.output_file.exists():
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            else:
                existing_data = []

            # Add new data
            existing_data.extend(feed_data)

            # Save updated data
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Data saved to {self.output_file}")

        except Exception as e:
            logging.error(f"Error saving to JSON: {str(e)}")

def main():
    console = Console()
    
    # Create log directory before setting up logging
    log_dir = Path('log')
    log_dir.mkdir(exist_ok=True)
    
    # Set up logging with new log directory
    log_file = log_dir / 'rss_translator.log'
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True
    )
    
    app = RSSTranslator()
    
    try:
        console.print("[bold blue]Beginning feed processing[/bold blue]")
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Create a simple status display
            total_feeds = len(app.feeds)
            processed_feeds = 0
            
            futures = [
                executor.submit(app.fetch_and_translate_feed, url)
                for url in app.feeds
            ]
            
            for future in as_completed(futures):
                try:
                    future.result()
                    processed_feeds += 1
                    console.print(f"[cyan]Progress: {processed_feeds}/{total_feeds} feeds processed[/cyan]")
                except Exception as e:
                    console.print(f"[bold red]Error in feed processing: {str(e)}[/bold red]")
                    logging.error(f"Error in feed processing: {str(e)}")
        
        console.print("[bold green]✓ Feed processing completed successfully![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
