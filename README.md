# MEDIC CARE – Python backend

    cd backend
    pip install -r requirements.txt
    python app.py        # open http://localhost:5000

- `frontend/`  – HTML/CSS/JS (dapat dito binubuksan via Flask, hindi double-click ng file)
- `backend/app.py` – Flask API (signup, verify, login, logout, profile, password, delete account, per-user data)
- `backend/db.py`  – lahat ng database access; ito lang papalitan pag dumating na yung actual DB
- Env vars: `SECRET_KEY`, `DATABASE_PATH`, `PORT`, `COOKIE_SECURE=1` (kapag HTTPS)
