import os
import threading
import json
import requests
import telebot
import http.server
import sys

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")          # ← set this in Render env vars (do NOT put token in file)
API_TOKEN = os.getenv("API_TOKEN", "demo_api_token")
LANG = "ru"
LIMIT = 300
URL = "https://leakosintapi.com/"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is not set. Exiting.")
    sys.exit(1)

# Create bot (no global parse_mode so we can set per-message)
bot = telebot.TeleBot(BOT_TOKEN)

# === HEALTH / PORT BINDING (used only if PORT env var present) ===
class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'OK')

    # silence default logging
    def log_message(self, format, *args):
        return

def run_health_server(port):
    server_address = ('0.0.0.0', port)
    try:
        httpd = http.server.HTTPServer(server_address, HealthHandler)
    except Exception as e:
        print(f"ERROR: cannot bind health server to 0.0.0.0:{port} -> {e}")
        # Fail fast so platform log shows bind error
        sys.exit(1)
    print(f"🌐 Health server listening on 0.0.0.0:{port}")
    try:
        httpd.serve_forever()
    except Exception:
        httpd.server_close()

# === TELEGRAM HANDLERS ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 Welcome to *Smarty Sunny Bot*\n\n"
        "🔍 Send your target number/email (e.g. +91********** or email@example.com)\n"
        "_I will search for leaked data if available._\n\n"
        "🔴 *Credit by Smart Sunny*"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')

def format_as_js(data):
    lines = []
    for key, value in data.items():
        value_str = json.dumps(value, ensure_ascii=False)
        lines.append(f"  {key}: {value_str}")
    return "{\n" + "\n".join(lines) + "\n}"

@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text.strip()
    if not query:
        bot.send_message(message.chat.id, "⚠️ Please send a phone number or email to search.")
        return

    payload = {
        "token": API_TOKEN,
        "request": query,
        "limit": LIMIT,
        "lang": LANG
    }

    try:
        resp = requests.post(URL, json=payload, timeout=15)
        response = resp.json()
    except requests.exceptions.RequestException as e:
        bot.send_message(message.chat.id, f"❌ API ERROR (network): {str(e)}")
        return
    except ValueError:
        bot.send_message(message.chat.id, "❌ API ERROR: invalid JSON response.")
        return

    if not isinstance(response, dict):
        bot.send_message(message.chat.id, "❌ Unexpected API response.")
        return

    if "Error code" in response:
        bot.send_message(message.chat.id, f"🚫 API Error: {response.get('Error code')}")
        return

    if not response.get("List"):
        bot.send_message(message.chat.id, "❌ No data found.")
        return

    for db, db_content in response.get("List", {}).items():
        db_title = "Smarty Sunny" if str(db).lower() == "1win" else db
        bot.send_message(message.chat.id, f"📁 *Database:* `{db_title}`", parse_mode='Markdown')

        data_list = None
        if isinstance(db_content, dict):
            data_list = db_content.get("Data")
        if not data_list:
            bot.send_message(message.chat.id, "⚠️ Empty database entry.")
            continue

        for entry in data_list:
            try:
                formatted = format_as_js(entry if isinstance(entry, dict) else {"value": entry})
                bot.send_message(message.chat.id, f"```js\n{formatted}\n```", parse_mode='Markdown')
            except Exception as e:
                bot.send_message(message.chat.id, f"⚠️ Error formatting entry: {e}")

    bot.send_message(message.chat.id, "🔴 *Credit by Smarty Sunny*", parse_mode='Markdown')

# === STARTUP: health server (if PORT set) + bot ===
def start_bot():
    print("🤖 Bot is starting (infinite polling)...")
    bot.infinity_polling()

if __name__ == "__main__":
    port_str = os.getenv("PORT")
    if port_str:
        try:
            port = int(port_str)
        except ValueError:
            print(f"ERROR: PORT value is not an integer: {port_str}")
            sys.exit(1)

        # run health server in a daemon thread so it doesn't block the bot
        t = threading.Thread(target=run_health_server, args=(port,), daemon=True)
        t.start()

    # Run the bot in the main thread (keeps process alive)
    start_bot()
