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

class RSSTranslator:
    def __init__(self, file_path='url.md'):
        self.file_path = file_path
        self.translator = Translator()
        self.feeds = self.read_feed_urls()
        # Create data directory if it doesn't exist
        self.data_dir = Path('data')
        self.data_dir.mkdir(exist_ok=True)
        self.output_file = self.data_dir / 'translated_feeds.json'
        self.console = Console()
        logging.info(f"RSSTranslator initialized with {len(self.feeds)} feeds")
        self.processed_links = self.load_processed_links()

    def read_feed_urls(self):
        """Read RSS feed URLs from the file"""
        with open(self.file_path, 'r') as file:
            return [line.strip() for line in file if line.strip() and not line.startswith('#')]

    def translate_text(self, text):
        """Translate text to English"""
        try:
            if text:
                return self.translator.translate(text, dest='en').text
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
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                feed = feedparser.parse(url)
                task = progress.add_task(f"Processing feed: {feed.feed.title if hasattr(feed.feed, 'title') else url}")
                
                feed_data = []
                for entry in feed.entries[:5]:
                    # Skip if entry has already been processed
                    if entry.link in self.processed_links:
                        progress.update(task, description=f"Skipping existing entry: {entry.title[:30]}...")
                        continue

                    progress.update(task, description=f"Translating: {entry.title[:30]}...")
                    
                    title = self.translate_text(entry.title)
                    description = self.translate_text(entry.description) if hasattr(entry, 'description') else ""
                    pub_date = entry.published if hasattr(entry, 'published') else "No date"

                    # Convert pub_date to ISO format
                    try:
                        parsed_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %z')
                        iso_pub_date = parsed_date.isoformat()
                    except ValueError:
                        try:
                            # Try alternative format (some feeds use different format)
                            parsed_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                            iso_pub_date = parsed_date.isoformat()
                        except ValueError:
                            iso_pub_date = pub_date  # Keep original if parsing fails

                    # Store entry data
                    entry_data = {
                        'title': title,
                        'published': pub_date,
                        'link': entry.link,
                        'description': description[:200],
                        'original_date': iso_pub_date,
                        'translated_at': datetime.now().isoformat()
                    }

                    # Add to processed links
                    self.processed_links.add(entry.link)
                    feed_data.append(entry_data)

                    # Log entry details
                    logging.info(f"Title: {title}, Published: {pub_date}, Link: {entry.link}")

                if feed_data:  # Only save if there are new entries
                    progress.update(task, description="Saving new entries...")
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
    
    # Set up logging
    logging.basicConfig(
        filename='rss_translator.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True  # This ensures the logging config is applied
    )
    
    with console.status("[bold green]Starting RSS Feed Translator...") as status:
        app = RSSTranslator()
        
        try:
            console.print("[bold blue]Beginning feed processing[/bold blue]")
            for url in app.feeds:
                status.update(f"Processing feed: {url}")
                app.fetch_and_translate_feed(url)
                time.sleep(1)
            
            console.print("[bold green]✓ Feed processing completed successfully![/bold green]")
            
        except Exception as e:
            console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
            logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
