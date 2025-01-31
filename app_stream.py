from flask import Flask, render_template, request, jsonify, Response
import requests
import json
import markdown
import html
import time
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension

app = Flask(__name__)
OLLAMA_API_URL = "http://localhost:11434/api/generate"

def convert_markdown(text):
    md = markdown.Markdown(extensions=['fenced_code', 'tables', 'nl2br'])
    return md.convert(text)

def escape_json_string(s):
    return json.dumps(s)[1:-1]

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/stream', methods=['POST'])
def stream():
    user_input = request.json.get('prompt', '')
    print(f"Received prompt: {user_input[:50]}...")
    
    payload = {
        "model": "deepseek-r1:70b",
        "prompt": user_input,
        "stream": True
    }

    def generate_response():
        try:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Connected'})}\n\n"
            
            response = requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=30)
            print(f"Connected to Ollama, status code: {response.status_code}")
            
            if response.status_code == 200:
                in_think_block = False
                last_time = time.time()
                
                for line in response.iter_lines():
                    current_time = time.time()
                    
                    if current_time - last_time > 5:
                        yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                        last_time = current_time
                    
                    if line:
                        try:
                            json_response = json.loads(line)
                            text = json_response.get('response', '')
                            
                            if text == "<think>":
                                in_think_block = True
                                yield f"data: {json.dumps({'type': 'think_start'})}\n\n"
                            elif text == "</think>":
                                in_think_block = False
                                yield f"data: {json.dumps({'type': 'think_end'})}\n\n"
                            else:
                                if in_think_block:
                                    yield f"data: {json.dumps({'type': 'think_content', 'content': text})}\n\n"
                                else:
                                    # Stream the content immediately
                                    content = text
                                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                                    
                            last_time = current_time
                                        
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}, line: {line[:100]}...")
                            error_msg = escape_json_string(f"Error decoding response: {str(e)}")
                            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
                
                print("Stream completed successfully")
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                print(f"Error response from Ollama: {response.status_code}")
                error_msg = escape_json_string(f"Error: Received status code {response.status_code}")
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        
        except requests.Timeout as e:
            print(f"Timeout error: {e}")
            error_msg = escape_json_string("Connection timed out. Please try again.")
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
            
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
            error_msg = escape_json_string(f"Error: Could not connect to Ollama server: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        
        except Exception as e:
            print(f"Unexpected error: {e}")
            error_msg = escape_json_string(f"An unexpected error occurred: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

    return Response(generate_response(), mimetype='text/event-stream')

@app.route('/health', methods=['GET'])
def health():
    try:
        response = requests.get("http://localhost:11434/api/version")
        if response.status_code == 200:
            return jsonify({"status": "healthy", "ollama_version": response.json()})
        else:
            return jsonify({"status": "error", "message": "Ollama server returned non-200 status"}), 500
    except requests.exceptions.RequestException:
        return jsonify({"status": "error", "message": "Could not connect to Ollama server"}), 500

if __name__ == '__main__':
    app.run(debug=True)