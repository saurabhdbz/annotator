
# main.py
import os
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND

from config import TEMPLATES_DIR, DATA_DIR, SESSION_SECRET_KEY, SUPPORTED_LANG_CODES

from database import init_db
from db_utils import (
    get_user,
    add_user,
    approve_user,
    read_users,
    delete_user,
    update_password,
    get_username_by_email_phone,
    ensure_initial_admin,
    import_source_sentences,
    pop_next_sentence_for_lang,
    append_translation,
    mark_sentence_completed,
    get_annotator_stats,
    unassign_sentence,
    get_language_stats,

    get_translations_csv_for_lang,
    count_remaining_sentences,
    get_translations_csv_for_lang,
    count_remaining_sentences,
    migrate_csv_to_db,
    source_sentences_exist
)

# ------------- Setup -------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    # migrate_csv_to_db() # Disabled as we have moved to full DB and deleted legacy CSVs
    ensure_initial_admin()
    yield
    # Shutdown (if needed)

app = FastAPI(lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

# Static dir (optional, for CSS if you add later)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Ensure data dir exists
os.makedirs(DATA_DIR, exist_ok=True)

# ------------- Helpers -------------

def get_current_user(request: Request):
    user_session = request.session.get("user")
    if not user_session:
        return None
    # Fetch full user details from CSV to ensure we have all fields (like language)
    # and to ensure the user still exists/is approved.
    username = user_session.get("username")
    if not username:
        return None
        
    user = get_user(username)
    return user

def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    return user

def require_admin(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    return user

def require_annotator(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "annotator":
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    return user

# ------------- Routes -------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    if user["role"] == "admin":
        return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)
    else:
        return RedirectResponse(url="/annotator/dashboard", status_code=HTTP_302_FOUND)

# ----- Authentication -----

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.get("/forgot_username", response_class=HTMLResponse)
async def forgot_username_get(request: Request):
    return templates.TemplateResponse("forgot_username.html", {"request": request})

@app.post("/forgot_username", response_class=HTMLResponse)
async def forgot_username_post(
    request: Request,
    email: str = Form(...),
    phone: str = Form(...)
):
    username = get_username_by_email_phone(email, phone)
    if username:
        return templates.TemplateResponse(
            "forgot_username.html",
            {
                "request": request,
                "success": f"Your username is: {username}"
            }
        )
    else:
        return templates.TemplateResponse(
            "forgot_username.html",
            {
                "request": request,
                "error": "No account found with these details."
            }
        )

@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = get_user(username)
    error = None
    if not user or user["password"] != password:
        error = "Invalid username or password."
    # Check for string "1" (legacy/CSV) or integer 1 (DB)
    elif str(user["is_approved"]) != "1":
        error = "Your account is not approved yet."
    if error:
        return templates.TemplateResponse("login.html", {"request": request, "error": error})

    # Set session
    request.session["user"] = {"username": user["username"], "role": user["role"]}
    # Redirect based on role
    if user["role"] == "admin":
        return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)
    else:
        return RedirectResponse(url="/annotator/dashboard", status_code=HTTP_302_FOUND)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)

@app.get("/change_password", response_class=HTMLResponse)
async def change_password_get(request: Request):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    return templates.TemplateResponse("change_password.html", {"request": request})

@app.post("/change_password", response_class=HTMLResponse)
async def change_password_post(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    
    user_session = request.session["user"]
    username = user_session["username"]
    
    # Verify current password
    # Since we don't have a direct verify_password function and passwords aren't hashed yet,
    # we can just fetch the user and compare.
    user = get_user(username)
    if not user or user["password"] != current_password:
        return templates.TemplateResponse(
            "change_password.html",
            {"request": request, "error": "Incorrect current password."}
        )
    
    # Update password
    update_password(username, new_password)
    
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request, "success": "Password changed successfully."}
    )

# ----- Registration (annotators) -----

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "languages": SUPPORTED_LANG_CODES, "error": None, "success": None}
    )


@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    language: str = Form(...)
):
    # Required checks
    if not (full_name and username and email and phone and password and language):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "All fields are required.", "success": None},
        )

    # Username collision
    if get_user(username):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already exists.", "success": None},
        )

    # Email validation
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Invalid email address.", "success": None},
        )

    # Phone number validation (digits only)
    if not phone.isdigit():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Phone number must contain only digits.", "success": None},
        )
    if language not in SUPPORTED_LANG_CODES:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Invalid language selection.",
                "success": None,
                "languages": SUPPORTED_LANG_CODES
            },
        )


    # Save user
    success, error_msg = add_user(
        full_name=full_name,
        username=username,
        email=email,
        phone=phone,
        password=password,
        language=language,
        role="annotator",
        is_approved=False
    )

    if not success:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": error_msg,
                "success": None,
                "languages": SUPPORTED_LANG_CODES
            },
        )

    success_msg = "Registration successful. Wait for admin approval."
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None, "success": success_msg, "languages": SUPPORTED_LANG_CODES},
    )

# ----- Admin portal -----

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    users = read_users()

    pending = [u for u in users if u["role"] == "annotator" and str(u["is_approved"]) != "1"]
    approved = [u for u in users if u["role"] == "annotator" and str(u["is_approved"]) == "1"]

    # Translation stats
    # translations = read_translations()  <-- Removed, using DB stats directly

    stats = {}
    for u in approved:
        lang = u["language"]
        # total_done = sum(1 for t in translations if t["username"] == u["username"])
        user_stats = get_annotator_stats(u["username"])
        total_done = user_stats["count"]
        remaining = count_remaining_sentences(lang)

        stats[u["username"]] = {
            "language": lang,
            "completed": total_done,
            "remaining": remaining
        }

    # File details
    language_stats = get_language_stats()

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "user": admin,
            "pending_users": pending,
            "approved_users": approved,
            "stats": stats,
            "language_stats": language_stats,
        },
    )

@app.get("/admin/download_translations/{lang}")
async def download_translations(lang: str, request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    file_path = get_translations_csv_for_lang(lang)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Translation file not found")

    return FileResponse(
        path=file_path,
        filename=f"translations_{lang}.csv",
        media_type='text/csv'
    )

@app.post("/admin/delete_user")
async def admin_delete_user(request: Request, username: str = Form(...)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    delete_user(username)

    return RedirectResponse("/admin/dashboard", status_code=302)

@app.post("/admin/reset_password")
async def admin_reset_password(request: Request, username: str = Form(...)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    update_password(username, "password")
    return RedirectResponse("/admin/dashboard", status_code=302)

@app.post("/admin/approve")
async def admin_approve(request: Request, username: str = Form(...)):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    approve_user(username)
    return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)

@app.post("/admin/upload_source", response_class=HTMLResponse)
async def admin_upload_source_post(
    request: Request,
    language: str = Form(...),
    file: UploadFile = File(...)
):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    temp_path = os.path.join(DATA_DIR, "tmp_upload.csv")
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    try:
        added_count = import_source_sentences(temp_path, language)
        msg = f"Imported {added_count} new sentences for language {language}."
    except ValueError as e:
        msg = None
        error = f"Error: {e}"
    except Exception as e:
        msg = None
        error = f"An unexpected error occurred: {e}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return templates.TemplateResponse(
        "upload_source.html",
        {"request": request, "message": msg, "error": error if 'error' in locals() else None, "languages": SUPPORTED_LANG_CODES}
    )

@app.get("/admin/upload_source", response_class=HTMLResponse)
async def admin_upload_source_get(request: Request):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    return templates.TemplateResponse(
        "upload_source.html",
        {"request": request, "user": admin, "languages": SUPPORTED_LANG_CODES, "message": None, "error": None},
    )


# ----- Annotator portal -----

@app.get("/annotator/dashboard", response_class=HTMLResponse)
async def annotator_dashboard(request: Request):
    user = require_annotator(request)
    if isinstance(user, RedirectResponse):
        return user


    stats = get_annotator_stats(user["username"])
    
    data_unavailable = not source_sentences_exist(user["language"])

    return templates.TemplateResponse(
        "annotator_dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "data_unavailable": data_unavailable,
            "language": user["language"]
        },
    )

@app.get("/annotator/next", response_class=HTMLResponse)
async def annotator_next(request: Request):
    user = require_annotator(request)
    if isinstance(user, RedirectResponse):
        return user

    # sentence = pop_next_sentence()
    sentence = pop_next_sentence_for_lang(user["language"], user["username"])
    if not sentence:
        return templates.TemplateResponse(
            "annotator_dashboard.html",
            {"request": request, "user": user, "message": "No more sentences to translate."},
        )

    return templates.TemplateResponse(
        "translate.html",
        {"request": request, "user": user, "sentence": sentence},
    )

@app.post("/annotator/submit", response_class=HTMLResponse)
async def annotator_submit(
    request: Request,
    sentence_id: str = Form(...),
    source_text: str = Form(...),
    translated_text: str = Form(...),
    action: str = Form(...),
):
    user = require_annotator(request)
    if isinstance(user, RedirectResponse):
        return user

    if action == "cancel":
        unassign_sentence(user["language"], sentence_id)
        return RedirectResponse(url="/annotator/dashboard", status_code=HTTP_302_FOUND)

    translated_text = translated_text.strip()
    if not translated_text:
        # Redisplay form with error
        sentence = {"id": sentence_id, "text": source_text}
        return templates.TemplateResponse(
            "translate.html",
            {
                "request": request,
                "user": user,
                "sentence": sentence,
                "error": "Translation cannot be empty.",
            },
        )

    append_translation(
        sentence_id=sentence_id,
        source_text=source_text,
        translated_text=translated_text,
        username=user["username"],
        lang=user["language"],
    )
    
    # Mark sentence as completed in source CSV
    mark_sentence_completed(user["language"], sentence_id)

    if action == "next":
        return RedirectResponse(url="/annotator/next", status_code=HTTP_302_FOUND)
    
    # Default: Go back to dashboard
    stats = get_annotator_stats(user["username"])
    return templates.TemplateResponse(
        "annotator_dashboard.html",
        {
            "request": request,
            "user": user,
            "message": "Translation submitted successfully.",
            "stats": stats,
        },
    )
