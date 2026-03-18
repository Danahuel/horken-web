# 🎉 Village Events Website

A modern, beautiful web application built with Python Flask for managing village events.

## ✨ Features

- 📅 Visual calendar with upcoming events
- ✏️ Full event management (create, edit, delete)
- 🔐 Authentication system for administrators
- 📰 Event news and reports
- 📱 Fully responsive design (mobile, tablet, desktop)
- 🎨 Modern, attractive design with gradients and animations
- 🗂️ Single-page application (all content on one page)
- 💾 JSON-based storage (no database required)

## 🚀 Installation

### Requirements
- Python 3.7 or higher
- pip (Python package manager)

### Setup Steps

1. **Navigate to project folder**
```bash
cd pueblo_web_english
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
python app.py
```

Or use Python 3.12:
```bash
py -3.12 app.py
```

4. **Open in browser**
```
http://localhost:5000
```

## 🔐 Demo Accounts

- **Admin:** `admin` / Password: `admin123`
- **User:** `user1` / Password: `pass123`

## 📂 Project Structure

```
pueblo_web_english/
│
├── app.py                    # Main Flask application
├── requirements.txt          # Dependencies
├── events_data.json         # JSON database
│
├── templates/               # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── add_event.html
│   └── edit_event.html
│
└── static/                  # Static files
    ├── style.css           # Custom CSS with modern design
    └── script.js           # JavaScript for interactivity
```

## 🎨 Design Features

- Modern gradient backgrounds
- Smooth animations and transitions
- Custom color palette (purple, pink, amber)
- Google Fonts integration (Inter, Playfair Display)
- Responsive design for all devices
- Glassmorphism effects
- Beautiful card designs

## ⚙️ Customization

### Change Colors
Edit `static/style.css`:
```css
:root {
    --primary: #6366f1;
    --secondary: #ec4899;
    --accent: #f59e0b;
}
```

### Change Users
Edit `app.py`:
```python
USERS = {
    'your_username': 'your_password'
}
```

---

