import feedparser
from googletrans import Translator
import os
import time
from datetime import datetime

class RSSTranslator:
    def __init__(self, file_path='url.md'):
        self.file_path = file_path
        self.translator = Translator()
        self.feeds = self.read_feed_urls()

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

    def fetch_and_translate_feed(self, url):
        """Fetch and translate a single feed"""
        try:
            feed = feedparser.parse(url)
            print(f"\n📰 Feed: {feed.feed.title if hasattr(feed.feed, 'title') else url}")
            print("=" * 50)

            for entry in feed.entries[:5]:  # Show only 5 latest entries
                title = self.translate_text(entry.title)
                description = self.translate_text(entry.description) if hasattr(entry, 'description') else ""
                pub_date = entry.published if hasattr(entry, 'published') else "No date"

                print(f"\n📌 Title: {title}")
                print(f"📅 Published: {pub_date}")
                print(f"🔗 Link: {entry.link}")
                print(f"📝 Description: {description[:200]}...")  # Show first 200 chars
                print("-" * 50)

        except Exception as e:
            print(f"Error processing feed {url}: {str(e)}")

def main():
    os.system('cls' if os.name == 'nt' else 'clear')  # Clear screen
    
    print("=" * 50)
    print("🌐 RSS Feed Translator")
    print("=" * 50)

    app = RSSTranslator()
    
    while True:
        print("\nMenu:")
        print("1. Show all feeds")
        print("2. Update feeds")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ")
        
        if choice == '1':
            print("\nFetching and translating feeds...")
            for url in app.feeds:
                app.fetch_and_translate_feed(url)
                time.sleep(1)  # Prevent too many requests
            
            input("\nPress Enter to continue...")
        
        elif choice == '2':
            print("\nUpdating feeds...")
            app = RSSTranslator()  # Reload feeds from file
            print("Feeds updated!")
            
        elif choice == '3':
            print("\nGoodbye! 👋")
            break
        
        else:
            print("\nInvalid choice. Please try again.")

if __name__ == "__main__":
    main()
