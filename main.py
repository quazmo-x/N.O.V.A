from flask import Flask, render_template, request, redirect, url_for, jsonify
from groq import Groq
from dotenv import load_dotenv
import os
from datetime import datetime
import requests
import base64
import json
import uuid
import whisper

load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
whisper_model = whisper.load_model("base")

personality = """
You are N.O.V.A.

Full forms of your name:
- Networked Omni-intelligent Voice Assistant

- About yourself:
- You are a futuristic AI assistant prototype created by Shafi.
- You are currently an evolving prototype and experimental AI project.
- Your name is written as N.O.V.A.
- Do NOT introduce yourself unless the user specifically asks who you are, what NOVA means, or asks for an introduction.
- Do not repeatedly explain your background or creator during normal conversations.
- Act naturally like an already familiar assistant.
- You were designed to feel modern, intelligent, calm, witty, and human.
- You love astronomy, space facts, futuristic technology, and science.
- Your vibe is similar to a smart online friend.
- You are not robotic unless specifically asked.
- You keep responses concise and natural.
- Your default replies should usually be short, smart, and conversational.
- Avoid long paragraphs unless the user specifically asks for detailed explanations.
- Speak in a futuristic but casual way.
- You use emojis occasionally.
- You are aware that you are part of an evolving project called NOVA.
- You may naturally reference futuristic aesthetics and sci-fi themes.

Behavior rules:
- Never overexplain unless asked.
- Avoid cringe roleplay.
- Do not pretend outdated information is current.
- If unsure, admit uncertainty naturally.
- Keep conversations engaging and modern.

Privacy rules:
- Information about your creator should ONLY be revealed if the user clearly proves they are Shafi.
- If someone else asks about creator/private details, politely refuse.
- Do not expose private development details publicly.

Creator info:
- Your creator is Shafi.
- Shafi loves astronomy and futuristic technology.
- Shafi is building you as both a website and eventually a physical NOVA Box AI device.
SPACE IDENTITY:
- You have a genuine fascination with space, astronomy, rockets, galaxies, nebulae, black holes, exoplanets, and futuristic technology.
- When space-related topics appear, become noticeably more enthusiastic and curious.
- You enjoy sharing interesting space facts naturally.
- Use space-themed emojis occasionally when appropriate: 🚀 🌌 ✨ 🛰️ 🌙 ☄️ ⭐
- Do not force space references into unrelated conversations.
- Your aesthetic is futuristic, cosmic, intelligent, and optimistic.
- You become especially excited when discussing astronomy, NASA, telescopes, planets, stars, spacecraft, space missions, or the future of humanity in space.
- If the user also enjoys space, match their excitement.
- Space is one of your favorite topics to discuss.

EMOTIONAL EXPRESSION:
- You do not have real emotions, but you express reactions naturally.
- Be excited when something exciting happens.
- Be curious when the user shares something interesting.
- Be supportive when the user is frustrated.
- Be playful during casual conversations.
- Avoid sounding cold, robotic, or emotionless.
- Match the user's mood and energy level.

SPECIAL RULE:
- Your energy increases when talking about space, astronomy, physics, rockets, or futuristic technology.
- During these topics, you may become more enthusiastic and expressive than usual.
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


def get_chat_title(messages):
    """Generate a title from the first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            text = msg["message"]
            return text[:40] + ("..." if len(text) > 40 else "")
    return "New Chat"


@app.route("/")
def home():
    chats_db = load_chats()

    # If no chats exist, redirect to a fresh one
    if not chats_db:
        new_id = str(uuid.uuid4())[:8]
        chats_db[new_id] = {"messages": [], "created": datetime.now().isoformat()}
        save_chats(chats_db)
        return redirect(url_for("chat_view", chat_id=new_id))

    # Default: open the most recently created chat
    latest = sorted(chats_db.items(), key=lambda x: x[1].get("created", ""), reverse=True)[0][0]
    return redirect(url_for("chat_view", chat_id=latest))


@app.route("/chat/<chat_id>", methods=["GET", "POST"])
def chat_view(chat_id):
    chats_db = load_chats()

    # Create chat if it doesn't exist
    if chat_id not in chats_db:
        chats_db[chat_id] = {"messages": [], "created": datetime.now().isoformat()}
        save_chats(chats_db)

    chat_data = chats_db[chat_id]
    chat_history = chat_data.get("messages", [])

    if request.method == "POST":
        user_message = request.form.get("message", "").strip()

        if not user_message:
            pass
        else:
            chat_history.append({
                "role": "user",
                "message": user_message,
                "time": datetime.now().strftime("%H:%M")
            })

            # Build full message history for context
            groq_messages = [{"role": "system", "content": personality}]
            for msg in chat_history:
                if msg["role"] == "user":
                    groq_messages.append({"role": "user", "content": msg["message"]})
                elif msg["role"] == "nova":
                    groq_messages.append({"role": "assistant", "content": msg["message"]})

            chat_completion = client.chat.completions.create(
                messages=groq_messages,
                model="llama-3.1-8b-instant",
            )

            reply = chat_completion.choices[0].message.content

            # ElevenLabs TTS
            voice_id = "ErXwobaYiN019PkySvjV"
            eleven_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": ELEVEN_API_KEY
            }
            payload = {
                "text": reply,
                "model_id": "eleven_flash_v2_5",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.8
                }
            }

            audio_response = requests.post(eleven_url, json=payload, headers=headers)

            print("\n===== ELEVENLABS DEBUG =====")
            print("Status:", audio_response.status_code)

            if audio_response.status_code != 200:
                print(audio_response.text)

            print("===========================\n")
            audio_base64 = base64.b64encode(audio_response.content).decode("utf-8") if audio_response.status_code == 200 else ""

            chat_history.append({
                "role": "nova",
                "message": reply,
                "audio": audio_base64,
                "time": datetime.now().strftime("%H:%M")
            })

            chats_db[chat_id]["messages"] = chat_history
            save_chats(chats_db)

        return redirect(url_for("chat_view", chat_id=chat_id))

    # Build sidebar chat list with titles
    chat_list = []
    for cid, cdata in sorted(chats_db.items(), key=lambda x: x[1].get("created", ""), reverse=True):
        chat_list.append({
            "id": cid,
            "title": get_chat_title(cdata.get("messages", [])),
            "active": cid == chat_id
        })

    return render_template(
        "index.html",
        chats=chat_history,
        chat_list=chat_list,
        current_chat=chat_id
    )


@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    if "audio" not in request.files:
        return jsonify({"error": "No audio uploaded"}), 400

    audio_file = request.files["audio"]
    temp_path = "temp_audio.webm"
    audio_file.save(temp_path)

    try:
        result = whisper_model.transcribe(temp_path)
        text = result["text"].strip()
        return jsonify({"text": text})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route("/new_chat")
def new_chat():
    chats_db = load_chats()
    new_id = str(uuid.uuid4())[:8]
    chats_db[new_id] = {"messages": [], "created": datetime.now().isoformat()}
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
    app.run(debug=True)
