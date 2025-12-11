# Annotator Platform

## Overview

This repository contains a **web‑based annotation platform** built with **FastAPI** and **SQLite**. It enables multiple annotators (50+ concurrent users) to translate source sentences into supported languages, while administrators can manage users, monitor language statistics, and download translation data.

## Features

- **User roles**: admin and annotator.
- **Secure authentication** with session middleware.
- **Admin dashboard** showing language statistics, source file info, and user management (approve, disapprove, reset passwords).
- **Incremental source upload**: new CSVs are merged without duplicating existing sentences.
- **Real‑time client‑side validation** for email and phone on registration.
- **Forgot username** and **forgot password** guidance.
- **Password hashing** (to be added) and admin password reset.
- **Docker support** with multi‑worker Uvicorn for handling 50+ concurrent annotators.
- **Deployment guide** and Docker‑Hub publishing instructions.

## Tech Stack

- **Backend**: FastAPI, Starlette, Jinja2 templates.
- **Database**: SQLite (WAL mode enabled for concurrency).
- **Frontend**: Vanilla HTML/CSS, JavaScript for validation.
- **Containerisation**: Docker, Docker‑Compose.

## Project Structure

```
annotator/
├── .dockerignore          # Files to ignore in Docker builds
├── Dockerfile             # Build image, installs requirements, creates data dir
├── docker-compose.yml    # Runs the container, maps port 9000 and data volume
├── requirements.txt      # Python dependencies (fastapi, uvicorn, itsdangerous, …)
├── config.py             # Paths, session secret, supported languages, admin defaults
├── database.py           # SQLite connection and init (WAL mode)
├── db_utils.py           # CRUD helpers, incremental source upload, admin init
├── main.py               # FastAPI app, routes, session middleware, startup lifespan
├── static/               # CSS assets
├── templates/            # Jinja2 HTML templates (login, register, dashboard, …)
├── data/                 # SQLite DB (annotator.db) and language CSVs (optional)
└── README.md             # **This file** – repository overview
```

## Setup & Installation

1. **Clone the repo**
   ```bash
   git clone https://github.com/saurabhdbz/annotator.git
   cd annotator
   ```
2. **Create a virtual environment & install deps**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Run the app locally**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 9000
   ```
   The admin account is created automatically on first start (see *Admin Credentials* below).

## Docker Deployment

```bash
# Build the image
sudo docker build -t skdbz/annotator:latest .
# Run with Docker Compose (recommended)
sudo docker-compose up -d
```

See `deployment_guide.md` for full instructions, including pushing to Docker Hub.

## Admin Credentials (Initial Setup)

On the first run, the system creates an admin user using the values from `config.py`:

- **Username**: `admin`
- **Password**: `admin123`
- **Email**: `admin@example.com`
- **Phone**: `0000000000`

These values are printed to the console when the app starts (via `ensure_initial_admin`). You can change them in `config.py` before the first launch.

## Usage

- **Register** as an annotator (email/phone must be unique).
- **Login** to access the annotator dashboard.
- **Admin** can approve users, reset passwords, delete pending requests, and view language statistics.
- **Upload source CSV** via the admin panel; new sentences are merged without duplication.
- **Download translations** per language from the admin dashboard.

## Contributing

Feel free to open issues or submit pull requests. Follow the existing code style, add tests where appropriate, and update documentation for any new features.

## License

This project is licensed under the MIT License.
