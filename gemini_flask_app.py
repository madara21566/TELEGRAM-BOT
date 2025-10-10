from flask import Flask, render_template_string, request, redirect, url_for, jsonify, flash
import requests
import threading
import time
import json
import os
from typing import List

# ---------------------- CONFIG ----------------------
# EMBEDDED API KEY (from user)
API_KEY = "573177cda41e57971a35342ed0920bae"
# Base URL for Gemini (Google Generative Language API v1beta)
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# File to persist history
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.json")

# Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ---------------------- UTILITIES ----------------------

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] Failed to save history:", e)


# Simple encoder/decoder from original tool
def encode_string(text: str) -> str:
    encoded = ""
    for char in text:
        encoded += str(ord(char) * 3 + 7) + " "
    return encoded.strip()


def decode_string(encoded: str) -> str:
    try:
        numbers = encoded.split()
        decoded = ""
        for num in numbers:
            if num:
                decoded += chr(int((int(num) - 7) / 3))
        return decoded
    except Exception:
        return "[ERROR] Decoding failed"


# ---------------------- Gemini API wrapper ----------------------
class GeminiAITool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.history = []
        self.model_name = None
        self.base_url = BASE_URL

    def list_models(self) -> bool:
        url = f"{self.base_url}/models?key={self.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                # look for a generation-capable Gemini model
                for model in models:
                    name = model.get("name", "")
                    supp = model.get("supportedGenerationMethods", [])
                    if "gemini" in name.lower() and "generateContent" in supp:
                        self.model_name = name.split("/")[-1]
                        return True
                for model in models:
                    name = model.get("name", "")
                    if "gemini" in name.lower():
                        self.model_name = name.split("/")[-1]
                        return True
                return False
            else:
                print("[ERROR] list_models status:", resp.status_code, resp.text)
                return False
        except Exception as e:
            print("[ERROR] Exception in list_models:", e)
            return False

    def send_prompt(self, prompt: str, timeout: int = 30) -> str:
        # Ensure model_name
        if not self.model_name:
            ok = self.list_models()
            if not ok:
                return "[ERROR] Could not find a Gemini model. Check API key or network."

        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=timeout)
            if resp.status_code == 200:
                result = resp.json()
                # Path to text depends on API response structure
                candidate = result.get("candidates", [])
                if candidate:
                    content = candidate[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        ai_text = parts[0].get("text", "")
                    else:
                        ai_text = json.dumps(content)[:2000]
                else:
                    # Fallback: try 'output' / 'response'
                    ai_text = result.get("output", "") or str(result)[:2000]

                # store in local history (not persisted here; caller will persist)
                self.history.append({"prompt": prompt, "response": ai_text, "time": int(time.time())})
                return ai_text
            else:
                return f"[ERROR] API Error: {resp.status_code} - {resp.text}"
        except requests.exceptions.Timeout:
            return "[ERROR] Request timed out"
        except Exception as e:
            return f"[ERROR] Failed to generate response: {e}"


# ---------------------- Flask routes ----------------------
TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gemini Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { padding-top: 2rem; }
      pre { white-space: pre-wrap; word-wrap: break-word; }
      .response-box { background:#f8f9fa; padding:1rem; border-radius:6px; }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="row mb-3">
        <div class="col-md-8">
          <h3>Gemini Dashboard</h3>
          <p class="text-muted">Send prompts to Gemini. API key is embedded on server.</p>
        </div>
        <div class="col-md-4 text-end">
          <form method="post" action="/clear_history" onsubmit="return confirm('Clear all history?');">
            <button class="btn btn-danger btn-sm">Clear History</button>
          </form>
        </div>
      </div>

      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="alert alert-info">{{ messages[0] }}</div>
        {% endif %}
      {% endwith %}

      <div class="row">
        <div class="col-md-8">
          <form method="post" action="/send_prompt">
            <div class="mb-3">
              <label class="form-label">Prompt</label>
              <textarea name="prompt" class="form-control" rows="4" required>{{ last_prompt or '' }}</textarea>
            </div>
            <div class="d-flex gap-2">
              <button class="btn btn-primary" type="submit">Send to Gemini</button>
              <button class="btn btn-secondary" type="button" onclick="fillExample()">Fill example</button>
            </div>
          </form>

          <hr/>

          <h5>Latest Response</h5>
          {% if latest_response %}
            <div class="response-box mb-3">
              <pre>{{ latest_response }}</pre>
            </div>
          {% else %}
            <div class="text-muted">No response yet.</div>
          {% endif %}

          <h5>Encode / Decode</h5>
          <form id="encodForm" method="post" action="/encode" class="mb-2">
            <div class="input-group mb-2">
              <input name="text" class="form-control" placeholder="Text to encode">
              <button class="btn btn-outline-secondary" type="submit">Encode</button>
            </div>
          </form>

          <form id="decodForm" method="post" action="/decode">
            <div class="input-group mb-2">
              <input name="encoded" class="form-control" placeholder="Encoded text to decode">
              <button class="btn btn-outline-secondary" type="submit">Decode</button>
            </div>
          </form>

        </div>

        <div class="col-md-4">
          <h6>Conversation History</h6>
          <div style="max-height:60vh; overflow:auto;">
            {% if history %}
              <ul class="list-group">
                {% for item in history|reverse %}
                  <li class="list-group-item">
                    <small class="text-muted">{{ item.time_human }}</small>
                    <div><strong>Q:</strong> {{ item.prompt }}</div>
                    <div><strong>A:</strong> <pre>{{ item.response }}</pre></div>
                  </li>
                {% endfor %}
              </ul>
            {% else %}
              <div class="text-muted">No history yet.</div>
            {% endif %}
          </div>
        </div>
      </div>

      <footer class="mt-4 text-muted small">
        Gemini Dashboard • Keep this app private (API key embedded)
      </footer>
    </div>

    <script>
      function fillExample(){
        document.querySelector('textarea[name="prompt"]').value = 'Write a short friendly greeting in Hindi and English.';
      }
    </script>
  </body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    history = load_history()
    # add human time
    for item in history:
        item['time_human'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item.get('time', 0)))
    latest = history[-1]['response'] if history else None
    last_prompt = history[-1]['prompt'] if history else ''
    return render_template_string(TEMPLATE, history=history, latest_response=latest, last_prompt=last_prompt)


@app.route("/send_prompt", methods=["POST"])
def send_prompt():
    prompt = request.form.get('prompt', '').strip()
    if not prompt:
        flash('Prompt cannot be empty')
        return redirect(url_for('index'))

    tool = GeminiAITool(API_KEY)
    # synchronous call — might take a few seconds
    response_text = tool.send_prompt(prompt)

    # Persist to history
    history = load_history()
    entry = {"prompt": prompt, "response": response_text, "time": int(time.time())}
    history.append(entry)
    save_history(history)

    flash('Prompt sent — response received')
    return redirect(url_for('index'))


@app.route("/encode", methods=["POST"])
def encode_route():
    text = request.form.get('text', '')
    if not text:
        flash('No text provided to encode')
        return redirect(url_for('index'))
    encoded = encode_string(text)
    # store as a history item
    history = load_history()
    history.append({"prompt": f"[ENCODE] {text}", "response": encoded, "time": int(time.time())})
    save_history(history)
    flash('Text encoded')
    return redirect(url_for('index'))


@app.route("/decode", methods=["POST"])
def decode_route():
    encoded = request.form.get('encoded', '')
    if not encoded:
        flash('No encoded text provided')
        return redirect(url_for('index'))
    decoded = decode_string(encoded)
    history = load_history()
    history.append({"prompt": f"[DECODE] {encoded}", "response": decoded, "time": int(time.time())})
    save_history(history)
    flash('Text decoded')
    return redirect(url_for('index'))


@app.route("/clear_history", methods=["POST"])
def clear_history():
    save_history([])
    flash('History cleared')
    return redirect(url_for('index'))


# Healthcheck for Render / load balancers
@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    # create history file if missing
    if not os.path.exists(HISTORY_FILE):
        save_history([])
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
