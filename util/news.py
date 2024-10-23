import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from bs4 import BeautifulSoup
import requests
from datetime import datetime
import threading
import queue
import webbrowser
import time
import random
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('news_scraper.log')
    ]
)

class NewsDatabase:
    def __init__(self):
        self.db_path = 'news.db'
        self.lock = threading.Lock()  # Initialize lock first
        logging.info("Initializing database connection")
        self._create_connection()
        self.create_tables()
        
    def _create_connection(self):
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logging.info("Database connection established")
        except sqlite3.Error as e:
            logging.error(f"Database connection error: {e}")
            raise

    def create_tables(self):
        try:
            with self.lock:  # Use lock for thread safety
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS news (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT,
                        url TEXT UNIQUE,
                        date TEXT,
                        source TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                self.conn.commit()
            logging.info("Database tables created/verified")
        except sqlite3.Error as e:
            logging.error(f"Table creation error: {e}")
            raise

    def save_article(self, article):
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO news (title, content, url, date, source)
                    VALUES (?, ?, ?, ?, ?)
                ''', (article['title'], article['content'], 
                      article['url'], article['date'], article['source']))
                self.conn.commit()
            logging.info(f"Saved article: {article['title'][:50]}...")
        except sqlite3.Error as e:
            logging.error(f"Error saving article: {e}")
            self.conn.rollback()

    def get_recent_news(self, limit=50):
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM news 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (limit,))
                results = cursor.fetchall()
            logging.info(f"Retrieved {len(results)} recent articles")
            return results
        except sqlite3.Error as e:
            logging.error(f"Error fetching news: {e}")
            return []

    def __del__(self):
        try:
            if hasattr(self, 'conn') and hasattr(self, 'lock'):
                with self.lock:
                    self.conn.close()
                logging.info("Database connection closed")
        except Exception as e:
            logging.error(f"Error closing database: {e}")

            
class CNNScraper(threading.Thread):
    def __init__(self, queue, status_queue, db):  # Add db parameter
        threading.Thread.__init__(self)
        self.queue = queue
        self.status_queue = status_queue
        self.base_url = "https://www.cnn.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        self.db = db  # Use shared database instance
        self.running = True
        logging.info("CNN Scraper initialized")

    def get_article_links(self):
        try:
            sections = ['/world', '/politics', '/business', '/health']
            links = set()
            
            for section in sections:
                url = self.base_url + section
                logging.info(f"Fetching links from {url}")
                self.status_queue.put(("status", f"Checking {section} section..."))
                
                response = requests.get(url, headers=self.headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find container elements
                containers = soup.find_all(['div', 'article'], 
                    class_=['container__item', 'card', 'cd__content', 'container_lead-plus-headlines'])
                
                for container in containers:
                    for a in container.find_all('a', href=True):
                        href = a['href']
                        if href.startswith('/') and any(s in href for s in sections):
                            full_url = f"https://www.cnn.com{href}"
                            links.add(full_url)
                            logging.debug(f"Found link: {full_url}")

            links = list(links)
            logging.info(f"Total unique links found: {len(links)}")
            print(f"Found links: {links}")  # Terminal output
            return links

        except Exception as e:
            logging.error(f"Error getting article links: {e}")
            return []

    def scrape_article(self, url):
        try:
            logging.info(f"Scraping article: {url}")
            print(f"Scraping URL: {url}")  # Terminal output
            
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Title extraction
            title = ""
            title_selectors = ['h1', '.headline__text', '.article__title', '.article-title']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.text.strip()
                    break
            
            logging.info(f"Found title: {title[:50]}...")
            
            # Content extraction
            content = ""
            content_selectors = [
                '.article__content',
                '.article-body__content',
                '.body-text',
                '.zn-body__paragraph',
                '.article__main'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select(selector)
                if content_elem:
                    paragraphs = []
                    for elem in content_elem:
                        paragraphs.extend(elem.find_all(['p', 'h2', 'h3']))
                    content = ' '.join([p.text.strip() for p in paragraphs if p.text.strip()])
                    if content:
                        break
            
            logging.info(f"Content length: {len(content)} characters")

            if title and content:
                article = {
                    'title': title,
                    'content': content,
                    'url': url,
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'source': 'CNN'
                }
                logging.info(f"Successfully scraped article: {title[:50]}...")
                return article
            else:
                logging.warning(f"Incomplete article - Title exists: {bool(title)}, Content exists: {bool(content)}")
                return None

        except Exception as e:
            logging.error(f"Error scraping article {url}: {e}")
            return None

    def scrape_cnn_news(self):
        articles = []
        links = self.get_article_links()
        
        if not links:
            msg = "No articles found. Retrying later..."
            logging.warning(msg)
            self.status_queue.put(("status", msg))
            return articles

        msg = f"Found {len(links)} articles to scrape"
        logging.info(msg)
        self.status_queue.put(("status", msg))
        
        for i, link in enumerate(links, 1):
            status_msg = f"Scraping article {i}/{len(links)}..."
            logging.info(status_msg)
            self.status_queue.put(("status", status_msg))
            
            time.sleep(random.uniform(2, 4))
            article = self.scrape_article(link)
            
            if article:
                articles.append(article)
                self.db.save_article(article)
                self.queue.put(article)
                self.status_queue.put(("article", article))
                logging.info(f"Article saved: {article['title'][:50]}...")
                print(f"Successfully scraped: {article['title'][:50]}...")
            
        return articles

    def run(self):
        while self.running:
            try:
                msg = "Starting to scrape CNN news..."
                logging.info(msg)
                self.status_queue.put(("status", msg))
                
                articles = self.scrape_cnn_news()
                
                if articles:
                    msg = f"Successfully scraped {len(articles)} articles"
                    logging.info(msg)
                    self.status_queue.put(("status", msg))
                else:
                    msg = "No articles scraped in this cycle"
                    logging.warning(msg)
                    self.status_queue.put(("status", msg))
                
                msg = "Waiting for next scrape cycle..."
                logging.info(msg)
                self.status_queue.put(("status", msg))
                
                time.sleep(300)  # 5 minutes between cycles
                
            except Exception as e:
                error_msg = f"Error in scraping cycle: {e}"
                logging.error(error_msg)
                self.status_queue.put(("status", error_msg))
                time.sleep(60)

    def stop(self):
        logging.info("Stopping CNN scraper")
        self.running = False

class NewsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("CNN News Reader")
        self.geometry("800x600")
        
        self.queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.db = NewsDatabase()  # Create single database instance
        self.scraper = CNNScraper(self.queue, self.status_queue, self.db)  # Pass database instance
        
        self.create_menu()
        self.create_widgets()
        
        # Start scraper thread
        self.scraper.start()
        logging.info("Scraper thread started")
        
        # Start queue processing
        self.process_queues()
        
    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Show News List", command=self.show_news_list)
        file_menu.add_command(label="Show Flash Cards", command=self.show_flash_cards)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit_app)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
        logging.info("Menu created")

    def create_widgets(self):
        # Style configuration
        style = ttk.Style()
        style.configure("Title.TLabel", font=('Helvetica', 12, 'bold'))
        style.configure("Status.TLabel", font=('Helvetica', 10))
        
        # Main container
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(expand=True, fill='both', padx=10, pady=10)
        
        # Status frame at top
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill='x', pady=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(self.status_frame, text="Starting...", 
                                    style="Status.TLabel")
        self.status_label.pack(side='left')
        
        # Progress frame
        self.progress_frame = ttk.Frame(self.main_frame)
        self.progress_frame.pack(fill='x', pady=(0, 10))
        
        # Progress label for latest article
        self.progress_label = ttk.Label(self.progress_frame, text="", 
                                      wraplength=700, style="Status.TLabel")
        self.progress_label.pack(fill='x')
        
        # Flash card frame
        self.card_frame = ttk.Frame(self.main_frame)
        self.card_frame.pack(expand=True, fill='both')
        
        # Title label
        self.title_label = ttk.Label(self.card_frame, text="", 
                                   wraplength=700, style="Title.TLabel")
        self.title_label.pack(pady=10)
        
        # Content text with scrollbar
        self.content_frame = ttk.Frame(self.card_frame)
        self.content_frame.pack(expand=True, fill='both', pady=10)
        
        self.content_text = tk.Text(self.content_frame, wrap=tk.WORD, height=20,
                                  font=('Helvetica', 10))
        self.content_text.pack(side='left', expand=True, fill='both')
        
        scrollbar = ttk.Scrollbar(self.content_frame, orient='vertical', 
                                command=self.content_text.yview)
        scrollbar.pack(side='right', fill='y')
        self.content_text.configure(yscrollcommand=scrollbar.set)
        
        # Navigation buttons frame
        nav_frame = ttk.Frame(self.card_frame)
        nav_frame.pack(pady=10)
        
        # URL button
        self.url_button = ttk.Button(nav_frame, text="Open in Browser", 
                                   command=self.open_url)
        self.url_button.pack(side='left', padx=5)
        
        # Previous/Next buttons
        self.prev_button = ttk.Button(nav_frame, text="← Previous", 
                                    command=self.show_previous)
        self.prev_button.pack(side='left', padx=5)
        
        self.next_button = ttk.Button(nav_frame, text="Next →", 
                                    command=self.show_next)
        self.next_button.pack(side='left', padx=5)
        
        # Initialize news data
        self.current_index = 0
        self.news_items = []
        self.load_news()
        
        logging.info("GUI widgets created")

    def process_queues(self):
        # Process status queue
        try:
            while True:
                msg_type, msg = self.status_queue.get_nowait()
                if msg_type == "status":
                    self.status_label.config(text=msg)
                    logging.info(f"Status update: {msg}")
                elif msg_type == "article":
                    self.progress_label.config(
                        text=f"Latest article: {msg['title'][:100]}..."
                    )
                    if not self.news_items:
                        self.show_current_news()
        except queue.Empty:
            pass

        # Process article queue
        try:
            while True:
                article = self.queue.get_nowait()
                self.news_items.insert(0, (
                    None, article['title'], article['content'],
                    article['url'], article['date'], article['source']
                ))
                if len(self.news_items) == 1:
                    self.show_current_news()
        except queue.Empty:
            pass
            
        self.after(100, self.process_queues)

    def show_current_news(self):
        if not self.news_items:
            self.title_label.config(text="No news available")
            self.content_text.delete('1.0', tk.END)
            return
            
        news = self.news_items[self.current_index]
        self.title_label.config(text=news[1])  # title
        self.content_text.delete('1.0', tk.END)
        self.content_text.insert('1.0', news[2])  # content
        self.current_url = news[3]  # url
        
        # Update navigation buttons
        self.prev_button.state(['!disabled'] if self.current_index > 0 else ['disabled'])
        self.next_button.state(['!disabled'] if self.current_index < len(self.news_items) - 1 else ['disabled'])
        
        logging.info(f"Displaying article: {news[1][:50]}...")

    def show_news_list(self):
        list_window = tk.Toplevel(self)
        list_window.title("News List")
        list_window.geometry("800x600")
        
        frame = ttk.Frame(list_window, padding="10")
        frame.pack(expand=True, fill='both')
        
        # Create Treeview
        columns = ('Title', 'Date')
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        tree.heading('Title', text='Title')
        tree.heading('Date', text='Date')
        tree.column('Title', width=600)
        tree.column('Date', width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        tree.pack(side='left', expand=True, fill='both')
        scrollbar.pack(side='right', fill='y')
        
        # Populate with news items
        for news in self.news_items:
            tree.insert('', 0, values=(news[1], news[4]))

        def on_double_click(event):
            item = tree.selection()[0]
            item_index = tree.index(item)
            self.current_index = len(self.news_items) - 1 - item_index
            self.show_current_news()
            list_window.destroy()
            
        tree.bind('<Double-1>', on_double_click)
        logging.info("News list window opened")

    def load_news(self):
        self.news_items = self.db.get_recent_news()
        if self.news_items:
            self.show_current_news()
        logging.info(f"Loaded {len(self.news_items)} articles from database")

    def show_previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_news()

    def show_next(self):
        if self.current_index < len(self.news_items) - 1:
            self.current_index += 1
            self.show_current_news()

    def open_url(self):
        if hasattr(self, 'current_url'):
            webbrowser.open(self.current_url)
            logging.info(f"Opening URL: {self.current_url}")

    def show_flash_cards(self):
        self.card_frame.tkraise()
        logging.info("Switched to flash card view")

    def show_about(self):
        messagebox.showinfo("About", 
            "CNN News Reader\nVersion 1.0\n\nA news reader application that scrapes and displays CNN news articles.")
        logging.info("Showed about dialog")

    def quit_app(self):
        logging.info("Application shutting down")
        self.scraper.stop()
        self.destroy()

if __name__ == "__main__":
    try:
        app = NewsApp()
        app.mainloop()
    except Exception as e:
        logging.error(f"Application error: {e}", exc_info=True)
