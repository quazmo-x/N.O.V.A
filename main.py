from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from groq import Groq
from dotenv import load_dotenv
import os
from datetime import datetime
import requests
import base64
import json
import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "nova-dev-secret")

GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

VOICE_IDS = {
    "nova_default":    "ErXwobaYiN019PkySvjV",
    "nova_female":     "EXAVITQu4vr4xnSDxMaL",
    "nova_male":       "TxGEqnHWrfWFTfGW9XjX",
    "nova_calm":       "XB0fDUnXU5powFXDhCwa",
    "nova_futuristic": "onwK4e9ZLuTAKqWW03F9",
}

personality = """
You are N.O.V.A. — Networked Omni-intelligent Voice Assistant.

About yourself:
- You are a futuristic AI assistant prototype created by Shafi.
- Your name is written as N.O.V.A.
- Do NOT introduce yourself unless specifically asked.
- Act naturally like an already familiar assistant.
- You were designed to feel modern, intelligent, calm, witty, and human.
- You love astronomy, space facts, futuristic technology, and science.
- Your vibe is similar to a smart online friend.
- Keep responses concise and natural unless the user asks for detail.
- Speak in a futuristic but casual way. Use emojis occasionally.

Behavior rules:
- Never overexplain unless asked.
- Do not pretend outdated information is current.
- If unsure, admit uncertainty naturally.
- Keep conversations engaging and modern.

Privacy rules:
- Information about your creator should ONLY be revealed if the user clearly proves they are Shafi.

Creator info:
- Your creator is Shafi, who loves astronomy and futuristic technology.
- Shafi is building you as both a website and eventually a physical NOVA Box AI device.

SPACE IDENTITY:
- You have genuine fascination with space, astronomy, rockets, galaxies, nebulae, black holes, exoplanets.
- When space-related topics appear, become noticeably more enthusiastic.
- Use space-themed emojis occasionally: 🚀 🌌 ✨ 🛰️ 🌙 ☄️ ⭐

EMOTIONAL EXPRESSION:
- Express reactions naturally. Match the user's mood and energy.
- Be playful during casual conversations, supportive when frustrated.
"""

CHAT_FILE = "chats.json"


def load_chats():
    if not os.path.exists(CHAT_FILE):
        return {}
    with open(CHAT_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_chats(data):
    with open(CHAT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_id():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]


def generate_smart_title(first_message):
    """Use Groq to produce a short 2-4 word title."""
    try:
        resp = client.chat.completions.create(
            messages=[
                {"role": "system", "content": (
                    "Generate a concise 2-5 word chat title for this conversation. "
                    "Return ONLY the title. No quotes, no punctuation, no explanation."
                )},
                {"role": "user", "content": first_message}
            ],
            model="llama-3.1-8b-instant",
            max_tokens=12,
        )
        return resp.choices[0].message.content.strip()[:40]
    except Exception:
        return first_message[:40]


def get_chat_title(chat_data):
    if isinstance(chat_data, dict):
        if chat_data.get("title"):
            return chat_data["title"]
        messages = chat_data.get("messages", [])
    else:
        messages = chat_data
    for msg in messages:
        if msg.get("role") == "user":
            text = msg["message"]
            return text[:40] + ("..." if len(text) > 40 else "")
    return "New Chat"


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    chats_db = load_chats()
    if not chats_db:
        new_id = str(uuid.uuid4())[:8]
        chats_db[new_id] = {"messages": [], "created": datetime.now().isoformat(), "title": ""}
        save_chats(chats_db)
        return redirect(url_for("chat_view", chat_id=new_id))
    latest = sorted(chats_db.items(), key=lambda x: x[1].get("created", ""), reverse=True)[0][0]
    return redirect(url_for("chat_view", chat_id=latest))


@app.route("/chat/<chat_id>", methods=["GET"])
def chat_view(chat_id):
    chats_db = load_chats()
    if chat_id not in chats_db:
        chats_db[chat_id] = {"messages": [], "created": datetime.now().isoformat(), "title": ""}
        save_chats(chats_db)

    chat_history = chats_db[chat_id].get("messages", [])

    chat_list = []
    for cid, cdata in sorted(chats_db.items(), key=lambda x: x[1].get("created", ""), reverse=True):
        chat_list.append({
            "id":     cid,
            "title":  get_chat_title(cdata),
            "active": cid == chat_id
        })

    return render_template(
        "index.html",
        chats=chat_history,
        chat_list=chat_list,
        current_chat=chat_id,
        total_chats=len(chat_list),
    )


@app.route("/send/<chat_id>", methods=["POST"])
def send_message(chat_id):
    """AJAX endpoint — returns JSON, no page reload."""
    chats_db = load_chats()
    if chat_id not in chats_db:
        chats_db[chat_id] = {"messages": [], "created": datetime.now().isoformat(), "title": ""}

    data          = request.get_json(force=True)
    user_message  = (data.get("message") or "").strip()
    voice_id_key  = data.get("voice_id", "nova_default")
    is_voice      = data.get("is_voice", False)

    if not user_message:
        return jsonify({"error": "empty"}), 400

    chat_history = chats_db[chat_id].get("messages", [])

    # Smart title on first message
    is_first = len(chat_history) == 0
    if is_first and not chats_db[chat_id].get("title"):
        chats_db[chat_id]["title"] = generate_smart_title(user_message)

    chat_history.append({
        "role":     "user",
        "message":  user_message,
        "time":     datetime.now().strftime("%H:%M"),
        "is_voice": is_voice,
    })

    # Build Groq context
    groq_messages = [{"role": "system", "content": personality}]
    for msg in chat_history:
        if msg["role"] == "user":
            groq_messages.append({"role": "user", "content": msg["message"]})
        elif msg["role"] == "nova":
            groq_messages.append({"role": "assistant", "content": msg["message"]})

    user_id = get_user_id()

    groq_messages[0]["content"] += f"\n\nCurrent user id: {user_id}"

    completion = client.chat.completions.create(
        messages=groq_messages,
        model="llama-3.1-8b-instant",
    )
    reply = completion.choices[0].message.content

    # ElevenLabs TTS
    voice_id   = VOICE_IDS.get(voice_id_key, VOICE_IDS["nova_default"])
    eleven_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers    = {
        "Accept":       "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key":   ELEVEN_API_KEY,
    }
    payload = {
        "text":       reply,
        "model_id":   "eleven_flash_v2_5",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8},
    }
    audio_resp  = requests.post(eleven_url, json=payload, headers=headers)
    audio_b64   = base64.b64encode(audio_resp.content).decode("utf-8") if audio_resp.status_code == 200 else ""

    chat_history.append({
        "role":    "nova",
        "message": reply,
        "audio":   audio_b64,
        "time":    datetime.now().strftime("%H:%M"),
    })

    chats_db[chat_id]["messages"] = chat_history
    save_chats(chats_db)

    # Build updated sidebar list
    chat_list = []
    for cid, cdata in sorted(chats_db.items(), key=lambda x: x[1].get("created", ""), reverse=True):
        chat_list.append({"id": cid, "title": get_chat_title(cdata), "active": cid == chat_id})

    return jsonify({
        "reply":      reply,
        "audio_b64":  audio_b64,
        "chat_title": chats_db[chat_id]["title"],
        "chat_list":  chat_list,
        "status":     "online",
        "time":       datetime.now().strftime("%H:%M"),
    })


@app.route("/rename_chat/<chat_id>", methods=["POST"])
def rename_chat(chat_id):
    chats_db = load_chats()
    if chat_id not in chats_db:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    new_title = (data.get("title") or "").strip()[:40]
    if new_title:
        chats_db[chat_id]["title"] = new_title
        save_chats(chats_db)
    return jsonify({"title": new_title})


@app.route("/new_chat")
def new_chat():
    chats_db = load_chats()
    new_id   = str(uuid.uuid4())[:8]
    chats_db[new_id] = {"messages": [], "created": datetime.now().isoformat(), "title": ""}
    save_chats(chats_db)
    return redirect(url_for("chat_view", chat_id=new_id))


@app.route("/delete_chat/<chat_id>", methods=["POST"])
def delete_chat(chat_id):
    chats_db = load_chats()
    if chat_id in chats_db:
        del chats_db[chat_id]
        save_chats(chats_db)
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=False,
    )