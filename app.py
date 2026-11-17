import os
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from db import db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'library-modern-secure-session-key-2026')

# Initialize DB adapter (SQLite / MySQL hybrid)
db.init_app(app)
mysql = db  # Alias for compatibility

# Helper functions
def is_logged_in():
    return 'user_id' in session

def is_admin():
    return 'user_type' in session and session['user_type'] == 'admin'

# Global template context
@app.context_processor
def inject_globals():
    wishlist_count = 0
    if is_logged_in():
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM wishlist WHERE user_id = %s", (session['user_id'],))
        row = cursor.fetchone()
        wishlist_count = row['cnt'] if row else 0
        cursor.close()

    return {
        'user_logged_in': is_logged_in(),
        'is_admin_user': is_admin(),
        'current_year': datetime.now().year,
        'wishlist_count': wishlist_count
    }

# Template filter for dates
@app.template_filter('format_date')
def format_date(value, fmt='%B %d, %Y'):
    if not value:
        return ''
    if isinstance(value, str):
        for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
            try:
                value = datetime.strptime(value, pattern)
                break
            except ValueError:
                pass
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)

# ==========================================
# PUBLIC ROUTES
# ==========================================

@app.route('/')
def home():
    cursor = mysql.connection.cursor()
    
    # Featured books (latest 6 books)
    cursor.execute('''
        SELECT b.*, a.name as author_name 
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        ORDER BY b.created_at DESC 
        LIMIT 6
    ''')
    featured_books = cursor.fetchall()
    
    # Popular genres with book counts
    cursor.execute('''
        SELECT genre, COUNT(*) as count 
        FROM books 
        GROUP BY genre 
        ORDER BY count DESC 
        LIMIT 6
    ''')
    popular_genres = cursor.fetchall()
    
    # General stats
    cursor.execute('SELECT COUNT(*) as count FROM books')
    total_books = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM authors')
    total_authors = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE user_type = "member"')
    total_members = cursor.fetchone()['count']
    
    # Recent announcements
    cursor.execute('SELECT * FROM announcements WHERE active = 1 ORDER BY created_at DESC LIMIT 3')
    announcements = cursor.fetchall()
    
    # Upcoming events
    cursor.execute('SELECT * FROM events WHERE event_date >= CURDATE() ORDER BY event_date ASC LIMIT 3')
    events = cursor.fetchall()
    
    cursor.close()
    
    return render_template('home.html', 
                         featured_books=featured_books,
                         popular_genres=popular_genres,
                         total_books=total_books,
                         total_authors=total_authors,
                         total_members=total_members,
                         announcements=announcements,
                         events=events)

@app.route('/catalog')
def catalog():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    genre = request.args.get('genre', '').strip()
    author = request.args.get('author', '').strip()
    availability = request.args.get('availability', '').strip()
    sort_by = request.args.get('sort', 'title').strip()
    
    per_page = 12
    offset = (page - 1) * per_page
    
    cursor = mysql.connection.cursor()
    
    where_conditions = []
    params = []
    
    if search:
        where_conditions.append("(b.title LIKE %s OR b.isbn LIKE %s OR a.name LIKE %s)")
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    if genre:
        where_conditions.append("b.genre = %s")
        params.append(genre)
    
    if author:
        where_conditions.append("a.name LIKE %s")
        params.append(f'%{author}%')
    
    if availability == 'available':
        where_conditions.append("b.available_copies > 0")
    elif availability == 'unavailable':
        where_conditions.append("b.available_copies = 0")
    
    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
    
    order_clause = "b.title ASC"
    if sort_by == 'newest':
        order_clause = "b.created_at DESC"
    elif sort_by == 'year':
        order_clause = "b.publication_year DESC"
    elif sort_by == 'available':
        order_clause = "b.available_copies DESC"
    
    query = f'''
        SELECT b.*, a.name as author_name,
               CASE WHEN b.available_copies > 0 THEN 'Available' ELSE 'Unavailable' END as status
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s
    '''
    cursor.execute(query, params + [per_page, offset])
    books = cursor.fetchall()
    
    # Get total count for pagination
    count_query = f'''
        SELECT COUNT(*) as total
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        WHERE {where_clause}
    '''
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']
    
    # Get genres for filter dropdown
    cursor.execute('SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL AND genre != "" ORDER BY genre')
    genres = cursor.fetchall()
    
    # Get authors for filter dropdown
    cursor.execute('SELECT DISTINCT name FROM authors ORDER BY name')
    authors = cursor.fetchall()
    
    cursor.close()
    
    total_pages = max(1, (total + per_page - 1) // per_page)
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('catalog.html',
                         books=books,
                         page=page,
                         total=total,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         search=search,
                         genre=genre,
                         author=author,
                         availability=availability,
                         sort=sort_by,
                         genres=genres,
                         authors=authors)

@app.route('/book/<int:book_id>')
def book_details(book_id):
    cursor = mysql.connection.cursor()
    
    cursor.execute('''
        SELECT b.*, a.name as author_name, a.bio as author_bio,
               CASE WHEN b.available_copies > 0 THEN 'Available' ELSE 'Unavailable' END as status
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        WHERE b.id = %s
    ''', (book_id,))
    book = cursor.fetchone()
    
    if not book:
        flash('Book not found in library catalog.', 'error')
        cursor.close()
        return redirect(url_for('catalog'))
    
    # Check if user has active hold or current loan or in wishlist
    user_has_hold = False
    user_has_loan = False
    is_in_wishlist = False
    if is_logged_in():
        user_id = session['user_id']
        cursor.execute('SELECT id FROM holds WHERE user_id = %s AND book_id = %s AND status = "active"', (user_id, book_id))
        user_has_hold = cursor.fetchone() is not None
        
        cursor.execute('SELECT id FROM loans WHERE user_id = %s AND book_id = %s AND returned_at IS NULL', (user_id, book_id))
        user_has_loan = cursor.fetchone() is not None

        cursor.execute('SELECT id FROM wishlist WHERE user_id = %s AND book_id = %s', (user_id, book_id))
        is_in_wishlist = cursor.fetchone() is not None
    
    # Related books in same genre
    cursor.execute('''
        SELECT b.*, a.name as author_name 
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        WHERE b.genre = %s AND b.id != %s 
        LIMIT 4
    ''', (book['genre'], book_id))
    related_books = cursor.fetchall()
    
    cursor.close()
    
    return render_template('book_details.html',
                         book=book,
                         user_has_hold=user_has_hold,
                         user_has_loan=user_has_loan,
                         is_in_wishlist=is_in_wishlist,
                         related_books=related_books)

@app.route('/about')
def about():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT COUNT(*) as total_books FROM books')
    total_books = cursor.fetchone()['total_books']
    cursor.execute('SELECT COUNT(*) as total_members FROM users WHERE user_type = "member"')
    total_members = cursor.fetchone()['total_members']
    cursor.close()
    return render_template('about.html', total_books=total_books, total_members=total_members)

@app.route('/faq')
def faq():
    faqs = [
        {
            'category': 'Borrowing & Returns',
            'question': 'How do I borrow a book from the library?',
            'answer': 'Once logged in to your account, find the book in the catalog. If copies are available, click "Borrow Now" or visit the front desk. Books are checked out for 14 days.'
        },
        {
            'category': 'Borrowing & Returns',
            'question': 'How long can I keep borrowed books?',
            'answer': 'The standard lending period is 14 days. You can renew an active loan from your Dashboard for an additional 14 days as long as no other member has placed a hold.'
        },
        {
            'category': 'Fines & Holds',
            'question': 'What are the late fee policies?',
            'answer': 'Late fines accrue at $0.50 per day past the due date up to a maximum of $10.00 per book. Fines can be paid directly through your member dashboard.'
        },
        {
            'category': 'Fines & Holds',
            'question': 'How do book holds work?',
            'answer': 'When all physical copies are currently checked out, you can click "Place Hold" on the book details page. You will receive first priority when a copy is returned.'
        },
        {
            'category': 'Membership & Account',
            'question': 'Is library membership free?',
            'answer': 'Yes! Basic community membership is completely free. Simply create an account online to start browsing, reserving, and tracking reading history.'
        },
        {
            'category': 'Library Services',
            'question': 'Can I book quiet study rooms or computers?',
            'answer': 'Yes, quiet study rooms, high-speed Wi-Fi workstations, and research terminals are available on a walk-in basis or reservation via our contact desk.'
        }
    ]
    return render_template('faq.html', faqs=faqs)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not name or not email or not message:
            flash('Please complete all required fields.', 'error')
            return render_template('contact.html')
            
        flash(f'Thank you, {name}! Your inquiry has been sent to our librarians. We will respond within 24 hours.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if is_logged_in():
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        address = request.form.get('address', '').strip()
        
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Please enter a valid email address.', 'error')
            return render_template('register.html')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html')
        
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cursor.fetchone():
            cursor.close()
            flash('This email address is already registered. Please login.', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (name, email, phone, password, address, user_type, created_at)
            VALUES (%s, %s, %s, %s, %s, 'member', %s)
        ''', (name, email, phone, hashed_password, address, datetime.now()))
        mysql.connection.commit()
        
        # Auto-login newly registered user
        cursor.execute('SELECT id, name, user_type FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_type'] = user['user_type']
        
        flash(f'Welcome to City Library, {name}! Your account is now ready.', 'success')
        return redirect(url_for('user_dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        if is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_type'] = user['user_type']
            session['user_email'] = user['email']
            
            flash(f'Welcome back, {user["name"]}!', 'success')
            if user['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out safely.', 'info')
    return redirect(url_for('home'))

# ==========================================
# MEMBER ACTIONS & DASHBOARD
# ==========================================

@app.route('/dashboard')
def user_dashboard():
    if not is_logged_in():
        flash('Please login to access your member dashboard.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # User Profile details
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    
    # Current active loans
    cursor.execute('''
        SELECT l.*, b.title, b.isbn, b.cover_image, a.name as author_name,
               CASE WHEN l.due_date < CURDATE() THEN 1 ELSE 0 END as is_overdue
        FROM loans l
        JOIN books b ON l.book_id = b.id
        JOIN authors a ON b.author_id = a.id
        WHERE l.user_id = %s AND l.returned_at IS NULL
        ORDER BY l.due_date ASC
    ''', (user_id,))
    current_loans = cursor.fetchall()
    
    # Active holds
    cursor.execute('''
        SELECT h.*, b.title, b.isbn, b.cover_image, b.available_copies, a.name as author_name
        FROM holds h
        JOIN books b ON h.book_id = b.id
        JOIN authors a ON b.author_id = a.id
        WHERE h.user_id = %s AND h.status = 'active'
        ORDER BY h.created_at ASC
    ''', (user_id,))
    holds = cursor.fetchall()
    
    # Outstanding & past fines
    cursor.execute('''
        SELECT f.*, b.title as book_title
        FROM fines f
        LEFT JOIN loans l ON f.loan_id = l.id
        LEFT JOIN books b ON l.book_id = b.id
        WHERE f.user_id = %s 
        ORDER BY f.status DESC, f.created_at DESC
    ''', (user_id,))
    all_fines = cursor.fetchall()
    unpaid_fines = [f for f in all_fines if f['status'] == 'unpaid']
    
    # Reading history (returned loans)
    cursor.execute('''
        SELECT l.*, b.title, b.isbn, b.cover_image, a.name as author_name
        FROM loans l
        JOIN books b ON l.book_id = b.id
        JOIN authors a ON b.author_id = a.id
        WHERE l.user_id = %s AND l.returned_at IS NOT NULL
        ORDER BY l.returned_at DESC
        LIMIT 10
    ''', (user_id,))
    reading_history = cursor.fetchall()
    
    # Wishlist books
    cursor.execute('''
        SELECT w.id as wishlist_id, b.*, a.name as author_name
        FROM wishlist w
        JOIN books b ON w.book_id = b.id
        JOIN authors a ON b.author_id = a.id
        WHERE w.user_id = %s
        ORDER BY w.created_at DESC
    ''', (user_id,))
    wishlist = cursor.fetchall()
    
    cursor.close()
    
    return render_template('user_dashboard.html',
                         user=user,
                         current_loans=current_loans,
                         holds=holds,
                         fines=unpaid_fines,
                         all_fines=all_fines,
                         reading_history=reading_history,
                         wishlist=wishlist)

@app.route('/borrow/<int:book_id>', methods=['POST', 'GET'])
def borrow_book(book_id):
    if not is_logged_in():
        flash('Please login to borrow books.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # Check book availability
    cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
    book = cursor.fetchone()
    if not book:
        flash('Book not found.', 'error')
        cursor.close()
        return redirect(url_for('catalog'))
        
    if book['available_copies'] <= 0:
        flash('Sorry, this book is currently unavailable. You can place a hold instead.', 'warning')
        cursor.close()
        return redirect(url_for('book_details', book_id=book_id))
        
    # Check if user already borrowed this book
    cursor.execute('SELECT id FROM loans WHERE user_id = %s AND book_id = %s AND returned_at IS NULL', (user_id, book_id))
    if cursor.fetchone():
        flash('You already have an active loan for this book.', 'info')
        cursor.close()
        return redirect(url_for('user_dashboard'))
        
    now = datetime.now()
    due_date = now + timedelta(days=14)
    
    # Create loan & decrease available copies
    cursor.execute('''
        INSERT INTO loans (user_id, book_id, borrowed_at, due_date)
        VALUES (%s, %s, %s, %s)
    ''', (user_id, book_id, now, due_date))
    
    cursor.execute('UPDATE books SET available_copies = available_copies - 1 WHERE id = %s', (book_id,))
    
    # Mark hold as fulfilled if user had a hold
    cursor.execute('''
        UPDATE holds SET status = 'fulfilled' 
        WHERE user_id = %s AND book_id = %s AND status = 'active'
    ''', (user_id, book_id))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Successfully borrowed "{book["title"]}"! Due date is {due_date.strftime("%B %d, %Y")}.', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/return/<int:loan_id>', methods=['POST', 'GET'])
def return_book(loan_id):
    if not is_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    # Get loan info
    cursor.execute('SELECT * FROM loans WHERE id = %s AND user_id = %s AND returned_at IS NULL', (loan_id, user_id))
    loan = cursor.fetchone()
    if not loan:
        flash('Active loan record not found.', 'error')
        cursor.close()
        return redirect(url_for('user_dashboard'))
        
    now = datetime.now()
    cursor.execute('UPDATE loans SET returned_at = %s WHERE id = %s', (now, loan_id))
    cursor.execute('UPDATE books SET available_copies = available_copies + 1 WHERE id = %s', (loan['book_id'],))
    
    # Assess fine if overdue
    due_date = loan['due_date']
    if isinstance(due_date, str):
        try:
            due_date = datetime.strptime(due_date.split('.')[0], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            due_date = datetime.strptime(due_date, '%Y-%m-%d')
            
    if now > due_date:
        days_overdue = (now - due_date).days
        if days_overdue > 0:
            fine_amount = min(10.0, days_overdue * 0.50)
            cursor.execute('''
                INSERT INTO fines (user_id, loan_id, amount, reason, status, created_at)
                VALUES (%s, %s, %s, %s, 'unpaid', %s)
            ''', (user_id, loan_id, fine_amount, f'Late return ({days_overdue} days overdue)', now))
            flash(f'Book returned. A late fee of ${fine_amount:.2f} has been added to your account.', 'warning')
        else:
            flash('Book returned successfully! Thank you.', 'success')
    else:
        flash('Book returned successfully! Thank you.', 'success')
        
    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('user_dashboard'))

@app.route('/renew/<int:loan_id>', methods=['POST', 'GET'])
def renew_loan(loan_id):
    if not is_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    
    cursor.execute('SELECT * FROM loans WHERE id = %s AND user_id = %s AND returned_at IS NULL', (loan_id, user_id))
    loan = cursor.fetchone()
    if not loan:
        flash('Active loan record not found.', 'error')
        cursor.close()
        return redirect(url_for('user_dashboard'))
        
    # Check if another user has hold on this book
    cursor.execute('SELECT id FROM holds WHERE book_id = %s AND status = "active" AND user_id != %s', (loan['book_id'], user_id))
    if cursor.fetchone():
        flash('Cannot renew this book because another member has placed a hold on it.', 'warning')
        cursor.close()
        return redirect(url_for('user_dashboard'))
        
    # Extend due date by 14 days
    current_due = loan['due_date']
    if isinstance(current_due, str):
        try:
            current_due = datetime.strptime(current_due.split('.')[0], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            current_due = datetime.strptime(current_due, '%Y-%m-%d')
            
    new_due = max(datetime.now(), current_due) + timedelta(days=14)
    cursor.execute('UPDATE loans SET due_date = %s WHERE id = %s', (new_due, loan_id))
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Loan successfully renewed! New due date is {new_due.strftime("%B %d, %Y")}.', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/place_hold/<int:book_id>')
def place_hold(book_id):
    if not is_logged_in():
        flash('Please login to place a hold.', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
    book = cursor.fetchone()
    
    if not book:
        flash('Book not found.', 'error')
        cursor.close()
        return redirect(url_for('catalog'))
    
    cursor.execute('SELECT id FROM holds WHERE user_id = %s AND book_id = %s AND status = "active"', (session['user_id'], book_id))
    if cursor.fetchone():
        flash('You already have an active hold on this book.', 'warning')
        cursor.close()
        return redirect(url_for('book_details', book_id=book_id))
    
    cursor.execute('''
        INSERT INTO holds (user_id, book_id, status, created_at)
        VALUES (%s, %s, 'active', %s)
    ''', (session['user_id'], book_id, datetime.now()))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Hold placed successfully on "{book["title"]}"!', 'success')
    return redirect(url_for('book_details', book_id=book_id))

@app.route('/cancel_hold/<int:hold_id>')
def cancel_hold(hold_id):
    if not is_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor()
    cursor.execute('''
        UPDATE holds 
        SET status = 'cancelled' 
        WHERE id = %s AND user_id = %s AND status = 'active'
    ''', (hold_id, session['user_id']))
    
    if cursor.rowcount > 0:
        mysql.connection.commit()
        flash('Hold cancelled successfully.', 'success')
    else:
        flash('Hold not found or already cancelled.', 'error')
    
    cursor.close()
    return redirect(url_for('user_dashboard'))

@app.route('/pay_fine/<int:fine_id>', methods=['POST', 'GET'])
def pay_fine(fine_id):
    if not is_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
        
    cursor = mysql.connection.cursor()
    cursor.execute('UPDATE fines SET status = "paid" WHERE id = %s AND user_id = %s', (fine_id, session['user_id']))
    if cursor.rowcount > 0:
        mysql.connection.commit()
        flash('Fine payment processed successfully. Thank you!', 'success')
    else:
        flash('Fine record not found.', 'error')
    cursor.close()
    return redirect(url_for('user_dashboard'))

@app.route('/toggle_wishlist/<int:book_id>', methods=['POST', 'GET'])
def toggle_wishlist(book_id):
    if not is_logged_in():
        flash('Please login to save books to your wishlist.', 'info')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id FROM wishlist WHERE user_id = %s AND book_id = %s', (user_id, book_id))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('DELETE FROM wishlist WHERE id = %s', (existing['id'],))
        mysql.connection.commit()
        flash('Removed book from your wishlist.', 'info')
    else:
        cursor.execute('INSERT INTO wishlist (user_id, book_id, created_at) VALUES (%s, %s, %s)', (user_id, book_id, datetime.now()))
        mysql.connection.commit()
        flash('Added book to your wishlist!', 'success')
        
    cursor.close()
    return redirect(request.referrer or url_for('book_details', book_id=book_id))

# ==========================================
# ADMIN DASHBOARD & MANAGEMENT
# ==========================================

@app.route('/admin')
def admin_dashboard():
    if not is_admin():
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('home'))
    
    cursor = mysql.connection.cursor()
    
    # Statistical counters
    cursor.execute('SELECT COUNT(*) as total FROM books')
    total_books = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM users WHERE user_type = "member"')
    total_members = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM loans WHERE returned_at IS NULL')
    active_loans = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM holds WHERE status = "active"')
    pending_holds = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM loans WHERE returned_at IS NULL AND due_date < CURDATE()')
    overdue_loans = cursor.fetchone()['total']
    
    cursor.execute('SELECT COALESCE(SUM(amount), 0) as total FROM fines WHERE status = "unpaid"')
    unpaid_fines_total = cursor.fetchone()['total']
    
    # Recent Loans
    cursor.execute('''
        SELECT l.*, b.title as book_title, u.name as user_name, u.email as user_email
        FROM loans l
        JOIN books b ON l.book_id = b.id
        JOIN users u ON l.user_id = u.id
        ORDER BY l.borrowed_at DESC
        LIMIT 8
    ''')
    recent_loans = cursor.fetchall()
    
    # All Books with author info
    cursor.execute('''
        SELECT b.*, a.name as author_name 
        FROM books b 
        JOIN authors a ON b.author_id = a.id 
        ORDER BY b.id DESC
    ''')
    all_books = cursor.fetchall()
    
    # All Authors
    cursor.execute('SELECT * FROM authors ORDER BY name')
    all_authors = cursor.fetchall()
    
    # All Members with active loans count
    cursor.execute('''
        SELECT u.*, 
               (SELECT COUNT(*) FROM loans l WHERE l.user_id = u.id AND l.returned_at IS NULL) as active_loans_count
        FROM users u 
        WHERE u.user_type = "member" 
        ORDER BY u.created_at DESC
    ''')
    members = cursor.fetchall()
    
    # Announcements
    cursor.execute('SELECT * FROM announcements ORDER BY created_at DESC')
    announcements = cursor.fetchall()
    
    # Events
    cursor.execute('SELECT * FROM events ORDER BY event_date ASC')
    events = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin_dashboard.html',
                         total_books=total_books,
                         total_members=total_members,
                         active_loans=active_loans,
                         pending_holds=pending_holds,
                         overdue_loans=overdue_loans,
                         unpaid_fines_total=unpaid_fines_total,
                         recent_loans=recent_loans,
                         all_books=all_books,
                         all_authors=all_authors,
                         members=members,
                         announcements=announcements,
                         events=events)

# Admin Book Management
@app.route('/admin/books/add', methods=['POST'])
def admin_add_book():
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    title = request.form.get('title', '').strip()
    author_id = request.form.get('author_id')
    new_author_name = request.form.get('new_author_name', '').strip()
    isbn = request.form.get('isbn', '').strip()
    genre = request.form.get('genre', '').strip()
    publisher = request.form.get('publisher', '').strip()
    pub_year = request.form.get('publication_year', 2024, type=int)
    total_copies = request.form.get('total_copies', 1, type=int)
    description = request.form.get('description', '').strip()
    cover_image = request.form.get('cover_image', '').strip()
    
    if not title or not isbn:
        flash('Title and ISBN are required.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    cursor = mysql.connection.cursor()
    
    # Check ISBN uniqueness
    cursor.execute('SELECT id FROM books WHERE isbn = %s', (isbn,))
    if cursor.fetchone():
        flash('A book with this ISBN already exists.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    # Handle author
    if new_author_name:
        cursor.execute('INSERT INTO authors (name, bio, created_at) VALUES (%s, %s, %s)', 
                       (new_author_name, 'Author added via Library Admin.', datetime.now()))
        cursor.execute('SELECT last_insert_rowid() as id')
        row = cursor.fetchone()
        author_id = row['id'] if row else cursor.lastrowid
    elif not author_id:
        flash('Please select or specify an author.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    cursor.execute('''
        INSERT INTO books (title, author_id, isbn, genre, publisher, publication_year, 
                           total_copies, available_copies, description, cover_image, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (title, author_id, isbn, genre, publisher, pub_year, total_copies, total_copies, description, cover_image, datetime.now()))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Book "{title}" added to catalog successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/books/edit/<int:book_id>', methods=['POST'])
def admin_edit_book(book_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    title = request.form.get('title', '').strip()
    author_id = request.form.get('author_id', type=int)
    isbn = request.form.get('isbn', '').strip()
    genre = request.form.get('genre', '').strip()
    publisher = request.form.get('publisher', '').strip()
    pub_year = request.form.get('publication_year', type=int)
    total_copies = request.form.get('total_copies', type=int)
    available_copies = request.form.get('available_copies', type=int)
    description = request.form.get('description', '').strip()
    cover_image = request.form.get('cover_image', '').strip()
    
    cursor = mysql.connection.cursor()
    cursor.execute('''
        UPDATE books 
        SET title=%s, author_id=%s, isbn=%s, genre=%s, publisher=%s, 
            publication_year=%s, total_copies=%s, available_copies=%s, 
            description=%s, cover_image=%s
        WHERE id = %s
    ''', (title, author_id, isbn, genre, publisher, pub_year, total_copies, available_copies, description, cover_image, book_id))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Book "{title}" updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/books/delete/<int:book_id>', methods=['POST'])
def admin_delete_book(book_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    cursor = mysql.connection.cursor()
    # Check if active loans exist
    cursor.execute('SELECT id FROM loans WHERE book_id = %s AND returned_at IS NULL', (book_id,))
    if cursor.fetchone():
        flash('Cannot delete book while active loans exist for it.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    cursor.execute('DELETE FROM holds WHERE book_id = %s', (book_id,))
    cursor.execute('DELETE FROM wishlist WHERE book_id = %s', (book_id,))
    cursor.execute('DELETE FROM books WHERE id = %s', (book_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Book deleted from catalog.', 'info')
    return redirect(url_for('admin_dashboard'))

# Admin Member Management
@app.route('/admin/members/add', methods=['POST'])
def admin_add_member():
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '').strip()
    address = request.form.get('address', '').strip()
    user_type = request.form.get('user_type', 'member').strip()
    issue_after = request.form.get('issue_after', '0')
    
    if not name or not email:
        flash('Member name and email address are required.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
        flash('Please enter a valid email address.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    if not password:
        password = 'password123'  # Default password if left blank
        
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
    if cursor.fetchone():
        flash(f'A member with email "{email}" already exists.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    hashed_password = generate_password_hash(password)
    cursor.execute('''
        INSERT INTO users (name, email, phone, password, address, user_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (name, email, phone, hashed_password, address, user_type, datetime.now()))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Member "{name}" ({email}) registered successfully! You can now issue books to this member.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/members/delete/<int:user_id>', methods=['POST'])
def admin_delete_member(user_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id FROM loans WHERE user_id = %s AND returned_at IS NULL', (user_id,))
    if cursor.fetchone():
        flash('Cannot delete member while they have active, unreturned book loans.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    cursor.execute('DELETE FROM holds WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM fines WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM wishlist WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM loans WHERE user_id = %s', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = %s AND user_type = "member"', (user_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Member removed from library registry.', 'info')
    return redirect(url_for('admin_dashboard'))

# Admin Loan Operations
@app.route('/admin/loans/issue', methods=['POST'])
def admin_issue_loan():
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    user_email = request.form.get('user_email', '').strip().lower()
    book_isbn = request.form.get('book_isbn', '').strip()
    duration_days = request.form.get('duration_days', 14, type=int)
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id, name, email FROM users WHERE email = %s', (user_email,))
    user = cursor.fetchone()
    if not user:
        flash(f'No member found with email "{user_email}". Please register the member first.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    cursor.execute('SELECT id, available_copies, title FROM books WHERE isbn = %s', (book_isbn,))
    book = cursor.fetchone()
    if not book:
        flash(f'No book found with ISBN "{book_isbn}".', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    if book['available_copies'] <= 0:
        flash(f'No available copies of "{book["title"]}" to issue.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    now = datetime.now()
    due_date = now + timedelta(days=duration_days)
    
    cursor.execute('''
        INSERT INTO loans (user_id, book_id, borrowed_at, due_date)
        VALUES (%s, %s, %s, %s)
    ''', (user['id'], book['id'], now, due_date))
    
    cursor.execute('UPDATE books SET available_copies = available_copies - 1 WHERE id = %s', (book['id'],))
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Successfully issued "{book["title"]}" to {user["name"]} ({user["email"]})! Due date is {due_date.strftime("%B %d, %Y")}.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/loans/return/<int:loan_id>', methods=['POST', 'GET'])
def admin_return_loan(loan_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM loans WHERE id = %s AND returned_at IS NULL', (loan_id,))
    loan = cursor.fetchone()
    if not loan:
        flash('Loan record not found or already returned.', 'error')
        cursor.close()
        return redirect(url_for('admin_dashboard'))
        
    now = datetime.now()
    cursor.execute('UPDATE loans SET returned_at = %s WHERE id = %s', (now, loan_id))
    cursor.execute('UPDATE books SET available_copies = available_copies + 1 WHERE id = %s', (loan['book_id'],))
    mysql.connection.commit()
    cursor.close()
    
    flash('Loan marked as returned and inventory updated.', 'success')
    return redirect(url_for('admin_dashboard'))

# Admin Announcements & Events
@app.route('/admin/announcements/add', methods=['POST'])
def admin_add_announcement():
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    
    if title and content:
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO announcements (title, content, active, created_at) VALUES (%s, %s, 1, %s)',
                       (title, content, datetime.now()))
        mysql.connection.commit()
        cursor.close()
        flash('Announcement published!', 'success')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/announcements/delete/<int:announcement_id>', methods=['POST'])
def admin_delete_announcement(announcement_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    cursor = mysql.connection.cursor()
    cursor.execute('DELETE FROM announcements WHERE id = %s', (announcement_id,))
    mysql.connection.commit()
    cursor.close()
    flash('Announcement deleted.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/events/add', methods=['POST'])
def admin_add_event():
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    date_str = request.form.get('event_date', '').strip()
    location = request.form.get('location', '').strip()
    
    try:
        event_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
    except Exception:
        event_date = datetime.now() + timedelta(days=7)
        
    if title and description:
        cursor = mysql.connection.cursor()
        cursor.execute('''
            INSERT INTO events (title, description, event_date, location, created_at)
            VALUES (%s, %s, %s, %s, %s)
        ''', (title, description, event_date, location, datetime.now()))
        mysql.connection.commit()
        cursor.close()
        flash('Event created successfully!', 'success')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/events/delete/<int:event_id>', methods=['POST'])
def admin_delete_event(event_id):
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
        
    cursor = mysql.connection.cursor()
    cursor.execute('DELETE FROM events WHERE id = %s', (event_id,))
    mysql.connection.commit()
    cursor.close()
    flash('Event deleted.', 'info')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
