import os
import tempfile
import time
import uuid
import threading
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
MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Store transcription status in memory (in production, use Redis or database)
transcription_status = {}

# Status constants
STATUS_FILE_READING = 'file_reading'
STATUS_FILE_UPLOADED = 'file_uploaded'
STATUS_API_UPLOADING = 'api_uploading'
STATUS_API_UPLOADED = 'api_uploaded'
STATUS_PROCESSING = 'processing'
STATUS_TRANSCRIBING = 'transcribing'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
STATUS_TIMEOUT = 'timeout'

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

def process_transcription_async(task_id, temp_file_path, custom_prompt, file_size, filename, model_name="gemini-2.5-pro"):
    """Async function to handle transcription processing"""
    try:
        # Update status - API uploading
        transcription_status[task_id].update({
            'status': STATUS_API_UPLOADING,
            'progress': 30,
            'message': '正在上传到Gemini API...',
            'last_update': time.time()
        })

        # Upload to Gemini
        model = genai.GenerativeModel(model_name)
        audio_file = genai.upload_file(temp_file_path)

        # Update status - API uploaded
        transcription_status[task_id].update({
            'status': STATUS_API_UPLOADED,
            'progress': 50,
            'message': 'API上传成功，等待处理...',
            'last_update': time.time()
        })

        # Wait for file to be processed with timeout
        processing_start_time = time.time()
        timeout_seconds = 300  # 5 minutes timeout

        while audio_file.state.name == "PROCESSING":
            elapsed_time = time.time() - processing_start_time

            # Check for timeout
            if elapsed_time > timeout_seconds:
                transcription_status[task_id].update({
                    'status': STATUS_TIMEOUT,
                    'message': f'处理超时（超过{timeout_seconds//60}分钟），请重新尝试',
                    'last_update': time.time()
                })
                return

            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)

            # Update status with timer
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            transcription_status[task_id].update({
                'status': STATUS_PROCESSING,
                'progress': 60,
                'message': f'AI正在分析音频文件... 已耗时: {minutes:02d}:{seconds:02d}',
                'elapsed_time': elapsed_time,
                'last_update': time.time()
            })

        if audio_file.state.name == "FAILED":
            transcription_status[task_id].update({
                'status': STATUS_FAILED,
                'message': 'API处理失败，请重试',
                'last_update': time.time()
            })
            return

        # Update status - transcribing with initial timer
        transcribing_start_time = time.time()
        total_elapsed = transcribing_start_time - transcription_status[task_id]['start_time']
        minutes = int(total_elapsed // 60)
        seconds = int(total_elapsed % 60)

        transcription_status[task_id].update({
            'status': STATUS_TRANSCRIBING,
            'progress': 80,
            'message': f'正在生成转写文本... 已耗时: {minutes:02d}:{seconds:02d}',
            'last_update': time.time()
        })

        # Use custom prompt if provided, otherwise use default
        default_prompt = "You are a Bain & Company consultant, just had an interview with your client, pls transcribe with timestamp"
        prompt = custom_prompt if custom_prompt.strip() else default_prompt

        # Generate transcription with periodic status updates
        def update_transcribing_status():
            while transcription_status[task_id]['status'] == STATUS_TRANSCRIBING:
                current_time = time.time()
                total_elapsed = current_time - transcription_status[task_id]['start_time']
                minutes = int(total_elapsed // 60)
                seconds = int(total_elapsed % 60)

                transcription_status[task_id].update({
                    'message': f'正在生成转写文本... 已耗时: {minutes:02d}:{seconds:02d}',
                    'last_update': current_time
                })
                time.sleep(2)  # Update every 2 seconds

        # Start timer thread for transcribing phase
        timer_thread = threading.Thread(target=update_transcribing_status)
        timer_thread.daemon = True
        timer_thread.start()

        # Generate transcription
        response = model.generate_content([audio_file, prompt])

        # Update status - completed
        total_time = time.time() - transcription_status[task_id]['start_time']
        transcription_status[task_id].update({
            'status': STATUS_COMPLETED,
            'progress': 100,
            'message': f'转写完成！总耗时: {int(total_time//60):02d}:{int(total_time%60):02d}',
            'transcription': response.text,
            'prompt_used': prompt,
            'completion_time': time.time(),
            'total_time': total_time,
            'last_update': time.time()
        })

    except Exception as e:
        # Update status - failed
        transcription_status[task_id].update({
            'status': STATUS_FAILED,
            'progress': 0,
            'message': f'处理失败: {str(e)}',
            'last_update': time.time()
        })
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

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    if 'audio_file' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400

    file = request.files['audio_file']
    custom_prompt = request.form.get('prompt', '')
    selected_model = request.form.get('model', 'gemini-2.5-pro')

    # Validate model selection
    valid_models = ['gemini-2.5-pro', 'gemini-2.5-flash']
    if selected_model not in valid_models:
        return jsonify({'error': f'Invalid model. Must be one of: {", ".join(valid_models)}'}), 400

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        # Generate unique task ID
        task_id = str(uuid.uuid4())

        try:
            # Initialize status tracking
            transcription_status[task_id] = {
                'status': STATUS_FILE_READING,
                'progress': 5,
                'message': '文件读取中...',
                'filename': file.filename,
                'start_time': time.time(),
                'last_update': time.time()
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

            # Update status - file uploaded
            transcription_status[task_id].update({
                'status': STATUS_FILE_UPLOADED,
                'progress': 20,
                'message': '文件上传成功，准备上传到API...',
                'file_size': file_size,
                'last_update': time.time()
            })

            # Start async processing
            thread = threading.Thread(
                target=process_transcription_async,
                args=(task_id, temp_file_path, custom_prompt, file_size, file.filename, selected_model)
            )
            thread.daemon = True
            thread.start()

            # Return immediately with task ID
            return jsonify({
                'success': False,  # Processing in background
                'task_id': task_id,
                'message': 'Processing started',
                'file_info': {
                    'name': file.filename,
                    'size': file_size,
                    'processed': False
                }
            })

        except Exception as e:
            # Update status - failed
            if task_id in transcription_status:
                transcription_status[task_id].update({
                    'status': STATUS_FAILED,
                    'progress': 0,
                    'message': f'处理失败: {str(e)}',
                    'last_update': time.time()
                })
            return jsonify({'error': f'Transcription failed: {str(e)}', 'task_id': task_id}), 500

    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/api/status/<task_id>')
def get_transcription_status(task_id):
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    status = transcription_status.get(task_id, {'status': 'not_found'})
    return jsonify(status)

@app.route('/api/edit/<task_id>', methods=['POST'])
def edit_transcription(task_id):
    """Edit the transcription result"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    if task_id not in transcription_status:
        return jsonify({'error': 'Task not found'}), 404

    # Check if transcription is completed
    if transcription_status[task_id]['status'] != STATUS_COMPLETED:
        return jsonify({'error': 'Transcription not completed'}), 400

    try:
        data = request.get_json()
        if not data or 'edited_transcription' not in data:
            return jsonify({'error': 'Missing edited_transcription field'}), 400

        edited_text = data['edited_transcription'].strip()
        if not edited_text:
            return jsonify({'error': 'Edited transcription cannot be empty'}), 400

        # Update the transcription
        transcription_status[task_id]['transcription'] = edited_text
        transcription_status[task_id]['edited'] = True
        transcription_status[task_id]['edit_time'] = time.time()
        transcription_status[task_id]['last_update'] = time.time()

        return jsonify({
            'success': True,
            'message': 'Transcription updated successfully',
            'transcription': edited_text
        })

    except Exception as e:
        return jsonify({'error': f'Edit failed: {str(e)}'}), 500

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)