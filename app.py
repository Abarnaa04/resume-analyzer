from flask import Flask, render_template, request, redirect, session, jsonify
from pypdf import PdfReader
from groq import Groq
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json

# ================= LOAD .env =================
load_dotenv()

# ================= SETUP =================
os.makedirs("static/profile", exist_ok=True)

app = Flask(__name__)

# 🔐 from .env
app.secret_key = os.getenv("SECRET_KEY")

# ================= GROQ API =================
API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("❌ GROQ_API_KEY missing in .env")

client = Groq(api_key=API_KEY)

# ================= DATABASE =================
USER_FILE = "users.json"

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(data):
    with open(USER_FILE, "w") as f:
        json.dump(data, f, indent=4)

users = load_users()

# ================= HOME =================
@app.route('/')
def home():
    return redirect('/login')

# ================= SIGNUP =================
@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')

        if not username or not password or not email:
            return render_template("signup.html", message="All fields required ❌")

        for u in users.values():
            if u.get("email") == email:
                return render_template("signup.html", message="Email already exists ❌")

        if username in users:
            return render_template("signup.html", message="Username already exists ❌")

        users[username] = {
            "password": generate_password_hash(password),
            "email": email,
            "profile_pic": "static/profile/default.png",
            "resume_text": "",
            "profile": {
                "name": username,
                "phone": "",
                "address": "",
                "gender": ""
            }
        }

        save_users(users)
        return redirect('/login')

    return render_template("signup.html")

# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = users.get(username)

        if user and check_password_hash(user["password"], password):
            session['user'] = username
            return redirect('/dashboard')

        return render_template("login.html", message="Invalid credentials ❌")

    return render_template("login.html")

# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():

    if 'user' not in session:
        return redirect('/login')

    user = users.get(session['user'])

    if not user:
        session.clear()
        return redirect('/login')

    return render_template("dashboard.html", user=user)

# ================= PROFILE =================
@app.route('/profile')
def profile():

    if 'user' not in session:
        return redirect('/login')

    return render_template("profile.html", user=users.get(session['user']))

# ================= UPLOAD PROFILE =================
@app.route('/upload_profile', methods=['POST'])
def upload_profile():

    if 'user' not in session:
        return redirect('/login')

    file = request.files.get('photo')

    if file and file.filename:
        filename = secure_filename(file.filename)
        path = os.path.join("static/profile", filename)
        file.save(path)

        users[session['user']]['profile_pic'] = path
        save_users(users)

    return redirect('/profile')

# ================= UPDATE PROFILE =================
@app.route('/update_profile', methods=['POST'])
def update_profile():

    if 'user' not in session:
        return redirect('/login')

    u = session['user']

    users[u]['profile']['name'] = request.form.get('name')
    users[u]['profile']['phone'] = request.form.get('phone')
    users[u]['profile']['address'] = request.form.get('address')
    users[u]['profile']['gender'] = request.form.get('gender')

    save_users(users)

    return redirect('/profile')

# ================= UPLOAD RESUME =================
@app.route('/upload', methods=['GET', 'POST'])
def upload():

    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':
        file = request.files.get('resume')

        if not file or file.filename == "":
            return render_template("upload.html", message="❌ No file selected")

        try:
            reader = PdfReader(file)
            text = ""

            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            users[session['user']]['resume_text'] = text
            save_users(users)

            return redirect('/analyze')

        except Exception as e:
            return render_template("upload.html", message=str(e))

    return render_template("upload.html")

# ================= ANALYZE =================
@app.route('/analyze')
def analyze():

    if 'user' not in session:
        return redirect('/login')

    resume = users[session['user']].get("resume_text", "")

    if not resume.strip():
        return redirect('/upload')

    prompt = f"""
You are a career AI advisor.

Analyze resume:
- Skills
- Missing Skills
- ATS Score
- Job Roles
- Improvements

Resume:
{resume[:2000]}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.choices[0].message.content

    except Exception as e:
        result = f"AI Error: {str(e)}"

    return render_template("result.html", result=result)

# ================= CHAT =================
@app.route('/chat', methods=['POST'])
def chat():

    if 'user' not in session:
        return jsonify({"reply": "Login required ❌"})

    resume = users[session['user']].get("resume_text", "")
    msg = request.form.get("message")

    prompt = f"""
Resume:
{resume[:2000]}

User:
{msg}

Answer simply.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({"reply": response.choices[0].message.content})

    except Exception as e:
        return jsonify({"reply": str(e)})

# ================= CHANGE PASSWORD =================
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():

    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':

        old = request.form.get('old_password')
        new = request.form.get('new_password', '').strip()

        if not new:
            return "Password cannot be empty"

        if not check_password_hash(users[session['user']]['password'], old):
            return "Wrong old password"

        users[session['user']]['password'] = generate_password_hash(new)
        save_users(users)

        return redirect('/profile')

    return render_template('change_password.html')

# ================= CAREER AI =================
@app.route('/career_ai')
def career_ai():

    if 'user' not in session:
        return redirect('/login')

    return render_template("career_ai.html", user=users[session['user']])

# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)