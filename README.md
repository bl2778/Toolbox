# Bain Toolbox

A personal consulting toolkit web application with AI-powered audio transcription and other productivity tools.

## Features

- 🔐 **Authentication**: Secure access with password protection
- 🎤 **Audio Transcription**: Convert client interview recordings to text using Gemini AI
- 📱 **Responsive Design**: Works on desktop and mobile devices
- 🖱️ **Drag & Drop Upload**: Easy file upload interface

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

1. Copy the environment template:
   ```bash
   cp .env.template .env
   ```

2. Edit `.env` and add your API keys:
   ```
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   SECRET_KEY=your_flask_secret_key_here
   ```

### 3. Get Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the key to your `.env` file

### 4. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

### 5. Access the Application

1. Open your browser and go to `http://localhost:5000`
2. Enter the password: `BAIN2025`
3. Use the audio transcription tool

## Supported Audio Formats

- MP3
- WAV
- M4A
- MP4
- WEBM

Maximum file size: 100MB

## Project Structure

```
/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env.template         # Environment variables template
├── templates/            # HTML templates
│   ├── auth.html        # Authentication page
│   ├── dashboard.html   # Navigation dashboard
│   └── transcription.html # Audio transcription page
├── static/              # Static files
│   ├── css/
│   │   └── style.css   # Main stylesheet
│   └── js/             # JavaScript files
└── uploads/            # Temporary file uploads
```

## Deployment

For production deployment, use a WSGI server like Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Security Notes

- The access password is hardcoded as `BAIN2025`
- Change the `SECRET_KEY` in production
- Consider using environment-based password configuration for production
- Uploaded files are temporarily stored and then deleted after processing

## Future Features

- ✏️ Writing Optimizer
- 📄 Meeting Summary Generator
- 🧾 Invoice Processor
- 📊 Data Analysis Tools