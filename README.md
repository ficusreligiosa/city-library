# 📚 City Library - Modern Library Management System

A full-stack, responsive, and modern Library Management System built with **Flask**, **SQLite / MySQL**, and a custom **Modern Design System**.

---

## ✨ Features

- **📖 Dynamic Book Catalog**:
  - Full-text search by title, ISBN, and author.
  - Multi-faceted filters by genre, availability (In Stock / Checked Out), and sorting (Title, Newest, Year, Most Copies).
  - High-resolution book covers with fallback stylized cover art generator.
- **👤 Member Portal & Digital Library Card**:
  - Holographic digital library card with unique member barcode (`LIB-2026-XXXXX`).
  - Active loan monitoring with due-date alerts and overdue detection.
  - Instant online book checkout and self-service return.
  - 1-click loan renewals (+14 days extension).
  - Book reservation & hold queue system.
  - Wishlist management.
  - Complete reading history log.
  - Fine calculation & simulation payments.
- **🛡️ Administrative Operations Console (`/admin`)**:
  - Real-time library telemetry: total catalog, active patrons, circulation count, overdue loans, queued holds, unpaid fines.
  - Book inventory management: Add new books (with auto-author creation), edit, and remove.
  - Circulation counter: issue books directly to patrons by email & ISBN, process returns.
  - Member directory.
  - Publish library announcements & schedule community events.
- **🎨 Modern Visual Experience**:
  - Light & Dark mode toggle with `localStorage` persistence.
  - Glassmorphic navigation and cards.
  - Google Fonts (*Plus Jakarta Sans*).
  - Fully responsive across desktop, tablet, and mobile.
  - Interactive toast notifications and smooth alerts.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.8+
- Dependencies installed:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Launch Application
```bash
python app.py
```
Visit **http://127.0.0.1:5000** in your browser.

> **Zero Database Configuration Required**: On first run, the system automatically initializes an embedded SQLite database (`library.db`) and seeds it with bestselling books, authors, announcements, events, and sample loans.

---

## 🔑 Pre-Configured Demo Accounts

For instant testing, use the 1-click login buttons on the `/login` page or enter:

| Role | Email | Password | Access |
|---|---|---|---|
| **Librarian / Admin** | `admin@library.com` | `admin123` | Full Admin Console (`/admin`) |
| **Library Member** | `john@example.com` | `password123` | Member Dashboard (`/dashboard`) |
| **New Member** | Register at `/register` | Custom | Personal Dashboard |

---

## ⚙️ Database Configuration

By default, the application runs on **SQLite** with zero setup.

To switch to **MySQL**:
1. Edit `config.json`:
   ```json
   {
     "params": {
       "local_server": "True",
       "db_engine": "mysql",
       "user": "root",
       "pass": "YOUR_MYSQL_PASSWORD",
       "host": "localhost",
       "database": "library_management_system"
     }
   }
   ```
2. If MySQL is unreachable, the system automatically and safely falls back to SQLite so your app never crashes.

---

## 📁 Project Structure

```
library-management-system/
│
├── app.py                     # Main Flask application & route controllers
├── db.py                      # Unified DB adapter & automatic schema / seed generator
├── config.json                # Database & server configuration
├── requirements.txt           # Python package dependencies
├── library.db                 # Auto-generated SQLite database
├── README.md                  # Project documentation
│
├── static/
│   ├── css/
│   │   └── style.css          # Design system & dark mode CSS
│   └── js/
│       └── script.js          # Theme toggle, toasts, table filters, demo helpers
│
└── templates/
    ├── base.html              # Master layout with navbar, footer & theme toggle
    ├── home.html              # Hero, stats ribbon, featured books, events
    ├── catalog.html           # Search, faceted filters, book cards grid, pagination
    ├── book_details.html      # Book overview, metadata, borrow, hold & wishlist
    ├── user_dashboard.html    # Digital pass, active loans, holds, fines, history
    ├── admin_dashboard.html   # Telemetry, book manager, circulation, members, events
    ├── login.html             # Sign in with 1-click demo credentials
    ├── register.html          # New member registration
    ├── about.html             # Library mission, facilities, history
    ├── faq.html               # Accordion-based categorized FAQ
    └── contact.html           # Inquiries, branch info, opening hours
```
