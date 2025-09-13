import os
import tempfile
import time
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Configuration
ACCESS_PASSWORD = "BAIN2025"
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'mp4', 'mpeg', 'mpga', 'webm'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Store transcription status in memory (in production, use Redis or database)
transcription_status = {}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_authenticated():
    return session.get('authenticated', False)

@app.route('/')
def index():
    if is_authenticated():
        return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/auth', methods=['POST'])
def authenticate():
    password = request.form.get('password')
    if password == ACCESS_PASSWORD:
        session['authenticated'] = True
        return redirect(url_for('dashboard'))
    return render_template('auth.html', error='Invalid password')

@app.route('/dashboard')
def dashboard():
    if not is_authenticated():
        return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/transcription')
def transcription():
    if not is_authenticated():
        return redirect(url_for('index'))
    return render_template('transcription.html')

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    if 'audio_file' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400

    file = request.files['audio_file']
    custom_prompt = request.form.get('prompt', '')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        # Generate unique task ID
        task_id = str(uuid.uuid4())

        temp_file_path = None
        try:
            # Initialize status tracking
            transcription_status[task_id] = {
                'status': 'uploading',
                'progress': 10,
                'message': 'Uploading file...',
                'filename': file.filename,
                'start_time': time.time()
            }

            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
            temp_file_path = temp_file.name
            temp_file.close()

            # Get file size before saving
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)

            # Save uploaded file
            file.save(temp_file_path)

            # Update status
            transcription_status[task_id].update({
                'status': 'processing',
                'progress': 30,
                'message': 'Processing file with Gemini AI...',
                'file_size': file_size
            })

            # Upload to Gemini
            model = genai.GenerativeModel("gemini-2.5-pro")
            audio_file = genai.upload_file(temp_file_path)

            # Update status
            transcription_status[task_id].update({
                'progress': 50,
                'message': 'Waiting for AI processing...'
            })

            # Wait for file to be processed
            while audio_file.state.name == "PROCESSING":
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
                transcription_status[task_id].update({
                    'message': 'AI is analyzing your audio file...'
                })

            if audio_file.state.name == "FAILED":
                transcription_status[task_id].update({
                    'status': 'failed',
                    'message': 'File processing failed'
                })
                return jsonify({'error': 'File processing failed', 'task_id': task_id}), 500

            # Update status
            transcription_status[task_id].update({
                'progress': 80,
                'message': 'Generating transcription...'
            })

            # Use custom prompt if provided, otherwise use default
            default_prompt = "You are a Bain & Company consultant, just had an interview with your client, pls transcribe with timestamp"
            prompt = custom_prompt if custom_prompt.strip() else default_prompt

            # Generate transcription
            response = model.generate_content([audio_file, prompt])

            # Update status - completed
            transcription_status[task_id].update({
                'status': 'completed',
                'progress': 100,
                'message': 'Transcription completed successfully!',
                'transcription': response.text,
                'prompt_used': prompt,
                'completion_time': time.time()
            })

            return jsonify({
                'success': True,
                'task_id': task_id,
                'transcription': response.text,
                'prompt_used': prompt,
                'file_info': {
                    'name': file.filename,
                    'size': file_size,
                    'processed': True
                }
            })

        except Exception as e:
            # Update status - failed
            if task_id in transcription_status:
                transcription_status[task_id].update({
                    'status': 'failed',
                    'progress': 0,
                    'message': f'Error: {str(e)}'
                })
            return jsonify({'error': f'Transcription failed: {str(e)}', 'task_id': task_id}), 500

        finally:
            # Clean up temporary file with retry mechanism
            if temp_file_path and os.path.exists(temp_file_path):
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        os.unlink(temp_file_path)
                        break
                    except PermissionError:
                        if attempt < max_retries - 1:
                            time.sleep(1)
                        else:
                            print(f"Warning: Could not delete temporary file {temp_file_path}")

    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/api/status/<task_id>')
def get_transcription_status(task_id):
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    status = transcription_status.get(task_id, {'status': 'not_found'})
    return jsonify(status)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)