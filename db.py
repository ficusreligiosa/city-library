import os
import sqlite3
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

# Configure SQLite timestamp handling
sqlite3.register_adapter(datetime, lambda val: val.strftime('%Y-%m-%d %H:%M:%S'))

def convert_timestamp(val):
    if not val:
        return None
    val_str = val.decode('utf-8') if isinstance(val, bytes) else str(val)
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            pass
    return val_str

sqlite3.register_converter('TIMESTAMP', convert_timestamp)
sqlite3.register_converter('DATETIME', convert_timestamp)
sqlite3.register_converter('DATE', convert_timestamp)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.db')

class SQLiteDictCursor:
    """Cursor that wraps sqlite3 cursor to act like MySQLdb DictCursor"""
    def __init__(self, conn):
        self._conn = conn
        self.cursor = conn.cursor()
        self.rowcount = -1
        self.lastrowid = None

    def execute(self, query, params=None):
        sqlite_query = query.replace('%s', '?')
        if params is not None:
            # Handle sequence/list params
            self.cursor.execute(sqlite_query, list(params))
        else:
            self.cursor.execute(sqlite_query)
        self.rowcount = self.cursor.rowcount
        self.lastrowid = self.cursor.lastrowid
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.cursor.close()

class DatabaseAdapter:
    """Unified database adapter providing MySQL or SQLite connection seamlessly"""
    def __init__(self, app=None):
        self.app = app
        self.engine = 'sqlite' # 'sqlite' or 'mysql'
        self.mysql = None
        self._sqlite_conn = None

    def init_app(self, app):
        self.app = app
        # Check config
        config_path = os.path.join(app.root_path, 'config.json')
        use_mysql = False
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    cfg = json.load(f)
                    params = cfg.get('params', {})
                    if params.get('local_server') == 'True' and params.get('db_engine') == 'mysql':
                        use_mysql = True
            except Exception:
                pass

        if use_mysql:
            try:
                from flask_mysqldb import MySQL
                import MySQLdb.cursors
                self.mysql = MySQL(app)
                # Quick test connection
                with app.app_context():
                    conn = self.mysql.connection
                    if conn:
                        self.engine = 'mysql'
            except Exception as e:
                print(f"[DB] MySQL not available ({e}), falling back to SQLite.")
                self.engine = 'sqlite'
        else:
            self.engine = 'sqlite'

        # Initialize schema and seed data
        self.init_database()

    def get_connection(self):
        if self.engine == 'mysql' and self.mysql:
            return self.mysql.connection
        
        # SQLite connection (thread/request safe)
        from flask import g
        try:
            if 'db_conn' not in g:
                g.db_conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
                g.db_conn.row_factory = sqlite3.Row
                g.db_conn.create_function('CURDATE', 0, lambda: datetime.now().strftime('%Y-%m-%d'))
            return g.db_conn
        except RuntimeError:
            # Outside request context (e.g. init script)
            if self._sqlite_conn is None:
                self._sqlite_conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
                self._sqlite_conn.row_factory = sqlite3.Row
                self._sqlite_conn.create_function('CURDATE', 0, lambda: datetime.now().strftime('%Y-%m-%d'))
            return self._sqlite_conn

    @property
    def connection(self):
        class ConnectionProxy:
            def __init__(self, adapter):
                self.adapter = adapter

            def cursor(self, cursorclass=None):
                if self.adapter.engine == 'mysql' and self.adapter.mysql:
                    import MySQLdb.cursors
                    return self.adapter.mysql.connection.cursor(cursorclass or MySQLdb.cursors.DictCursor)
                conn = self.adapter.get_connection()
                return SQLiteDictCursor(conn)

            def commit(self):
                conn = self.adapter.get_connection()
                conn.commit()

            def rollback(self):
                conn = self.adapter.get_connection()
                conn.rollback()

        return ConnectionProxy(self)

    def init_database(self):
        """Create tables and seed initial data if needed"""
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Authors
        cur.execute('''
            CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                bio TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Books
        cur.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author_id INTEGER REFERENCES authors(id),
                isbn TEXT UNIQUE,
                genre TEXT,
                publisher TEXT,
                publication_year INTEGER,
                total_copies INTEGER DEFAULT 1,
                available_copies INTEGER DEFAULT 1,
                description TEXT,
                cover_image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Users
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password TEXT NOT NULL,
                address TEXT,
                user_type TEXT DEFAULT 'member',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Loans
        cur.execute('''
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                book_id INTEGER REFERENCES books(id),
                borrowed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date TIMESTAMP NOT NULL,
                returned_at TIMESTAMP NULL
            )
        ''')

        # Holds
        cur.execute('''
            CREATE TABLE IF NOT EXISTS holds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                book_id INTEGER REFERENCES books(id),
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Fines
        cur.execute('''
            CREATE TABLE IF NOT EXISTS fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                loan_id INTEGER REFERENCES loans(id),
                amount REAL DEFAULT 0.0,
                reason TEXT,
                status TEXT DEFAULT 'unpaid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Announcements
        cur.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Events
        cur.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                event_date TIMESTAMP NOT NULL,
                location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Wishlist
        cur.execute('''
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                book_id INTEGER REFERENCES books(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, book_id)
            )
        ''')

        conn.commit()

        # Seed data if empty
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            self._seed_data(conn)

        conn.close()

    def _seed_data(self, conn):
        cur = conn.cursor()
        now = datetime.now()

        # 1. Users (Admin + Demo Members)
        users = [
            ("Admin Librarian", "admin@library.com", "555-0100", generate_password_hash("admin123"), "Library Central Headquarters", "admin", now),
            ("John Doe", "john@example.com", "555-0142", generate_password_hash("password123"), "742 Evergreen Terrace, Springfield", "member", now - timedelta(days=60)),
            ("Jane Smith", "jane@example.com", "555-0198", generate_password_hash("password123"), "221B Baker Street, London", "member", now - timedelta(days=45)),
            ("Alex Rivera", "alex@example.com", "555-0233", generate_password_hash("password123"), "42 Wallaby Way, Sydney", "member", now - timedelta(days=20))
        ]
        cur.executemany('''
            INSERT INTO users (name, email, phone, password, address, user_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', users)

        # 2. Authors
        authors = [
            ("F. Scott Fitzgerald", "American novelist famous for depicting the flamboyance and excess of the Jazz Age."),
            ("George Orwell", "English novelist, essayist, journalist, and critic whose work is characterized by lucid prose."),
            ("Harper Lee", "American novelist best known for her 1960 Pulitzer Prize-winning novel To Kill a Mockingbird."),
            ("Frank Herbert", "American science fiction author best known for the 1965 masterpiece Dune."),
            ("J.R.R. Tolkien", "English writer and philologist, author of The Hobbit and The Lord of the Rings."),
            ("Jane Austen", "English novelist known primarily for her six major novels interpreting British gentry."),
            ("Robert C. Martin", "Software engineer and author known as 'Uncle Bob', co-author of the Agile Manifesto."),
            ("Yuval Noah Harari", "Israeli public intellectual, historian and professor known for Sapiens."),
            ("Agatha Christie", "English writer known for her 66 detective novels and 14 short story collections."),
            ("Walter Isaacson", "American author, journalist, and professor known for bestselling biographies."),
            ("James Clear", "American author and speaker focused on habits, decision making, and continuous improvement.")
        ]
        cur.executemany('''
            INSERT INTO authors (name, bio, created_at)
            VALUES (?, ?, ?)
        ''', [(a[0], a[1], now) for a in authors])

        # Author ID map
        cur.execute("SELECT id, name FROM authors")
        auth_map = {row['name']: row['id'] for row in cur.fetchall()}

        # 3. Books
        books = [
            (
                "The Great Gatsby", auth_map["F. Scott Fitzgerald"], "978-0743273565", "Classic Literature",
                "Scribner", 1925, 5, 4,
                "A portrait of the Jazz Age in all of its decadence and excess, Gatsby captured the spirit of the author's generation and earned him a permanent place in American literature.",
                "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=90)
            ),
            (
                "1984", auth_map["George Orwell"], "978-0451524935", "Science Fiction",
                "Signet Classic", 1949, 6, 3,
                "A chilling prophecy about the future. George Orwell's depiction of a totalitarian regime where Big Brother is always watching remains shockingly relevant today.",
                "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=85)
            ),
            (
                "To Kill a Mockingbird", auth_map["Harper Lee"], "978-0061120084", "Fiction",
                "Harper Perennial", 1960, 4, 2,
                "Compassionate, dramatic, and deeply moving, this Pulitzer Prize-winning masterpiece explores racism, innocence, and integrity in the American Deep South.",
                "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=80)
            ),
            (
                "Dune", auth_map["Frank Herbert"], "978-0441172719", "Science Fiction",
                "Ace Books", 1965, 5, 5,
                "Set on the desert planet Arrakis, Dune is the story of the boy Paul Atreides, heir to a noble family tasked with ruling an inhospitable world.",
                "https://images.unsplash.com/photo-1506466010722-395aa2bef877?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=70)
            ),
            (
                "The Hobbit", auth_map["J.R.R. Tolkien"], "978-0547928227", "Fantasy",
                "Houghton Mifflin", 1937, 7, 6,
                "Bilbo Baggins is a hobbit who enjoys a comfortable, unambitious life. But his contentment is interrupted when the wizard Gandalf and a company of dwarves arrive.",
                "https://images.unsplash.com/photo-1629992101753-56d196c8aabb?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=65)
            ),
            (
                "Pride and Prejudice", auth_map["Jane Austen"], "978-0141439518", "Classic Literature",
                "Penguin Classics", 1813, 4, 3,
                "The romantic clash between the opinionated Elizabeth Bennet and her proud beau, Mr. Darcy, is a splendid performance of civilized sparring.",
                "https://images.unsplash.com/photo-1476275466078-4007374efbbe?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=60)
            ),
            (
                "Clean Code: A Handbook of Agile Software Craftsmanship", auth_map["Robert C. Martin"], "978-0132350884", "Technology",
                "Prentice Hall", 2008, 3, 2,
                "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees. Master software craftsmanship with Uncle Bob.",
                "https://images.unsplash.com/photo-1532012164546-f432f2e3777a?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=50)
            ),
            (
                "Sapiens: A Brief History of Humankind", auth_map["Yuval Noah Harari"], "978-0062316097", "History",
                "Harper", 2015, 6, 4,
                "One hundred thousand years ago, at least six human species inhabited the earth. Today there is just one: Homo sapiens. How did our species succeed in the battle for dominance?",
                "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=40)
            ),
            (
                "Murder on the Orient Express", auth_map["Agatha Christie"], "978-0062073495", "Mystery",
                "William Morrow", 1934, 4, 1,
                "Just after midnight, a snowdrift stops the Orient Express in its tracks. By morning, an American tycoon lies dead in his compartment, stabbed a dozen times.",
                "https://images.unsplash.com/photo-1516979187457-637abb4f9353?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=35)
            ),
            (
                "Steve Jobs", auth_map["Walter Isaacson"], "978-1451648539", "Biography",
                "Simon & Schuster", 2011, 4, 3,
                "Based on more than forty interviews with Jobs conducted over two years, Isaacson tells the astonishing story of the rollercoaster life of a creative entrepreneur.",
                "https://images.unsplash.com/photo-1589829085413-56de8ae18c73?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=25)
            ),
            (
                "Atomic Habits", auth_map["James Clear"], "978-0735211292", "Self-Help",
                "Avery", 2018, 8, 7,
                "No matter your goals, Atomic Habits offers a proven framework for improving every day. Learn practical strategies to form good habits and break bad ones.",
                "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=15)
            ),
            (
                "Animal Farm", auth_map["George Orwell"], "978-0451526342", "Classic Literature",
                "Signet", 1945, 5, 5,
                "A timeless satirical allegory of Soviet totalitarianism, depicting farm animals who rebel against their human farmer, hoping to create a society of equality.",
                "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=600&q=80",
                now - timedelta(days=10)
            )
        ]
        cur.executemany('''
            INSERT INTO books (title, author_id, isbn, genre, publisher, publication_year, 
                               total_copies, available_copies, description, cover_image, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', books)

        # 4. Announcements
        announcements = [
            ("✨ Welcome to the Modernized City Library Portal!", 
             "We have revamped our library platform with instantaneous catalog search, online hold management, digital borrowing tracking, and mobile-friendly access.", 
             1, now - timedelta(days=1)),
            ("📚 Extended Study & Reading Room Hours", 
             "Quiet reading rooms and collaborative study zones are now open until 10:00 PM Monday through Friday. High-speed Wi-Fi and complimentary hot beverages available.", 
             1, now - timedelta(days=4)),
            ("🎉 Annual Community Book Fair & Exchange", 
             "Join us this upcoming weekend for our Community Book Fair! Bring pre-loved books to exchange, enjoy coffee with fellow book lovers, and attend live author readings.", 
             1, now - timedelta(days=7))
        ]
        cur.executemany('''
            INSERT INTO announcements (title, content, active, created_at)
            VALUES (?, ?, ?, ?)
        ''', announcements)

        # 5. Events
        events = [
            ("Creative Writing Workshop: Crafting Memorable Characters", 
             "Join award-winning authors for a hands-on masterclass in developing rich, authentic characters and compelling story arcs.", 
             now + timedelta(days=5, hours=4), "Auditorium Room A", now),
            ("Science Fiction Book Club: Exploring Asimov & Herbert", 
             "Deep dive into the world-building, political philosophies, and ecological themes of foundational sci-fi masterworks.", 
             now + timedelta(days=12, hours=6), "Discussion Lounge West", now),
            ("Introduction to Python & Data Science for Beginners", 
             "A free practical workshop introducing programming fundamentals, data analysis, and open-source software tools.", 
             now + timedelta(days=18, hours=2), "Digital Media Lab", now)
        ]
        cur.executemany('''
            INSERT INTO events (title, description, event_date, location, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', events)

        # 6. Sample Loans for John Doe (user_id = 2)
        cur.execute("SELECT id FROM users WHERE email = 'john@example.com'")
        john_id = cur.fetchone()[0]

        cur.execute("SELECT id FROM books WHERE isbn = '978-0743273565'") # Gatsby
        gatsby_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM books WHERE isbn = '978-0451524935'") # 1984
        orwell_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM books WHERE isbn = '978-0132350884'") # Clean Code
        cleancode_id = cur.fetchone()[0]

        loans = [
            (john_id, gatsby_id, now - timedelta(days=5), now + timedelta(days=9), None),
            (john_id, orwell_id, now - timedelta(days=20), now - timedelta(days=6), None), # Overdue loan
            (john_id, cleancode_id, now - timedelta(days=40), now - timedelta(days=26), now - timedelta(days=25)) # Returned
        ]
        cur.executemany('''
            INSERT INTO loans (user_id, book_id, borrowed_at, due_date, returned_at)
            VALUES (?, ?, ?, ?, ?)
        ''', loans)

        # 7. Sample Hold for John Doe
        cur.execute("SELECT id FROM books WHERE isbn = '978-0061120084'") # Mockingbird
        mockingbird_id = cur.fetchone()[0]
        cur.execute('''
            INSERT INTO holds (user_id, book_id, status, created_at)
            VALUES (?, ?, 'active', ?)
        ''', (john_id, mockingbird_id, now - timedelta(days=2)))

        # 8. Sample Fine for overdue book
        cur.execute("SELECT id FROM loans WHERE user_id = ? AND returned_at IS NULL AND due_date < ?", (john_id, now))
        overdue_loan = cur.fetchone()
        loan_id = overdue_loan[0] if overdue_loan else None
        cur.execute('''
            INSERT INTO fines (user_id, loan_id, amount, reason, status, created_at)
            VALUES (?, ?, 3.00, 'Late return fee (6 days overdue)', 'unpaid', ?)
        ''', (john_id, loan_id, now - timedelta(days=1)))

        conn.commit()
        print("[DB] Initialized schema and successfully seeded demo data!")

db = DatabaseAdapter()
