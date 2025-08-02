import os
import logging
import google.generativeai as genai
from flask import (
    Flask, request, render_template, redirect, url_for,
    flash, send_from_directory, session # Ensure session is imported
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import docx
import requests
from bs4 import BeautifulSoup
import re

# --- Basic Configuration ---
# (Keep existing logging setup)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load Environment Variables ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    logging.error("FATAL ERROR: GOOGLE_API_KEY not found.")

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'docx'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16MB

# --- Initialize Flask App ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24)) # Keep this for flash messages
if not os.getenv("FLASK_SECRET_KEY"):
     logging.warning("FLASK_SECRET_KEY not set in environment, using random key.")

# --- Configure Google Generative AI ---
# (Keep existing configuration logic)
try:
    if API_KEY:
        genai.configure(api_key=API_KEY)
        logging.info("Google Generative AI configured.")
    else:
         logging.warning("Skipping GenAI configuration: API key not found.")
except Exception as e:
    logging.error(f"Error configuring Google Generative AI: {e}")


# --- Helper Functions ---
# (Keep existing helper functions: allowed_file, extract_text_from_docx, extract_text_from_url)
# --- Paste the helper functions here ---
def allowed_file(filename):
    """Checks if the filename has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_docx(filepath):
    """Extracts plain text from a DOCX file."""
    try:
        doc = docx.Document(filepath)
        full_text = [para.text for para in doc.paragraphs]
        logging.info(f"Successfully extracted text from {filepath}")
        return '\n'.join(full_text)
    except Exception as e:
        logging.error(f"Error reading docx file {filepath}: {e}")
        return None

def extract_text_from_url(url):
    """Attempts to fetch and extract meaningful text from a job posting URL."""
    logging.info(f"Attempting to fetch content from URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logging.info(f"URL fetch successful (Status: {response.status_code})")

        soup = BeautifulSoup(response.content, 'html.parser')
        for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'button', 'input']):
            element.decompose()
        body = soup.find('body')
        text_content = ""
        if body:
            text_content = body.get_text(separator='\n', strip=True)
            text_content = re.sub(r'\n\s*\n', '\n\n', text_content).strip()
            logging.info(f"Extracted ~{len(text_content)} characters from {url}")
        else:
             logging.warning(f"Could not find body tag in content from {url}")
        if len(text_content) < 100:
             logging.warning(f"Extracted very little text ({len(text_content)} chars) from {url}.")
        return text_content if text_content else None

    except requests.exceptions.Timeout:
        logging.error(f"Timeout error fetching URL {url}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error parsing URL content {url}: {e}")
        return None
# --- End of Helper Functions ---


def call_google_ai(original_resume_text, job_role, company, job_description, source_method):
    """Calls the Google AI API with the constructed prompt."""
    # (Keep the existing call_google_ai function AS IS, using 'gemini-1.5-flash-latest')
    # --- Paste the call_google_ai function here ---
    if not API_KEY:
        logging.error("Cannot call Google AI: API Key was not loaded.")
        return None, "API Key not configured."

    prompt = f"""
    You are an expert resume writer and ATS (Applicant Tracking System) optimization specialist.
    Your task is to tailor the following resume based on the provided job details to maximize the candidate's chances of getting an interview.

    **Original Resume Text:**
    ```
    {original_resume_text}
    ```

    **Job Details:**
    *   **Input Method:** {source_method}
    *   **Job Role:** {job_role if job_role else 'Not explicitly provided'}
    *   **Company:** {company if company else 'Not specified'}
    *   **Job Description/Context:** {'(Extracted from URL)' if source_method == 'URL' else ''}
        ```
        {job_description}
        ```

    **Instructions:**
    1.  Analyze... (Keep all instructions)
    2.  Tailor...
    3.  ATS Optimization...
    4.  Quantify...
    5.  Tone...
    6.  Output: Provide only the full text of the *tailored* resume. Do not include explanations or conversational text.

    **Tailored Resume Output:**
    """

    try:
        logging.info("Initializing GenerativeModel('gemini-1.5-flash-latest')...")
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        logging.info(f"Sending request to Google AI...")
        response = model.generate_content(prompt)
        logging.info("Received response from Google AI.")

        if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             logging.warning(f"Google AI request blocked. Reason: {block_reason}")
             return None, f"AI request blocked: {block_reason}. Review inputs."

        if hasattr(response, 'text') and response.text:
            return response.text, None
        else:
            logging.warning("AI response received, but no text content found.")
            return None, "AI response format was unexpected or empty."

    except Exception as api_error:
        logging.error(f"Google AI API Error: {api_error}", exc_info=True)
        # (Keep existing specific error message logic)
        error_str = str(api_error)
        if "API key not valid" in error_str:
             return None, "Authentication Error: Invalid API key."
        elif "billing account" in error_str.lower():
             return None, "Billing Error: Check Google Cloud project billing status."
        elif "permission denied" in error_str.lower() or "consumer does not have access" in error_str.lower():
            return None, "Permission Error: Check API enablement in Google Cloud project."
        elif "model" in error_str.lower() and "not found" in error_str.lower():
             return None, f"Model Error: Selected model not found."
        else:
            return None, f"An unexpected AI service error occurred: {api_error}"
    # --- End of call_google_ai ---


# --- Routes ---

@app.route('/', methods=['GET'])
def index():
    """Renders the main upload form page."""
    return render_template('index.html')

@app.route('/tailor', methods=['POST'])
def tailor_resume():
    """Handles the form submission for resume tailoring."""
    logging.info("Received POST request to /tailor")
    filepath = None # Define here for potential use in finally block

    # --- 1. Resume File Handling & Validation ---
    # (Keep existing file validation logic)
    if 'resumeFile' not in request.files:
        flash('No resume file part selected.')
        return redirect(url_for('index'))
    file = request.files['resumeFile']
    if file.filename == '':
        flash('No resume file selected.')
        return redirect(url_for('index'))
    if not allowed_file(file.filename):
        flash('Invalid resume file type (.docx only).')
        return redirect(url_for('index'))

    # Securely save the file
    filename = secure_filename(file.filename)
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logging.info(f"Resume file saved to: {filepath}")
    except Exception as e:
         logging.error(f"Error saving uploaded file {filename}: {e}", exc_info=True)
         flash("Error saving uploaded file.")
         # Clean up if file exists after failed save attempt
         if filepath and os.path.exists(filepath):
             try: os.remove(filepath)
             except OSError: pass
         return redirect(url_for('index'))

    # --- 2. Get Job Details (URL or Manual) ---
    # (Keep existing job details logic)
    job_link = request.form.get('jobLink', '').strip()
    manual_job_role = request.form.get('jobRole', '').strip()
    manual_company = request.form.get('company', '').strip()
    manual_job_description = request.form.get('jobDescription', '').strip()
    job_role_to_use, company_to_use, job_description_to_use, source_method = "", "", "", ""

    if job_link:
        # (Keep URL extraction logic...)
        if not (job_link.startswith('http://') or job_link.startswith('https://')):
            flash('Invalid Job Link URL format.')
            if filepath and os.path.exists(filepath): os.remove(filepath)
            return redirect(url_for('index'))
        scraped_description = extract_text_from_url(job_link)
        if scraped_description:
            job_description_to_use = scraped_description
            job_role_to_use = manual_job_role
            company_to_use = manual_company
            source_method = "URL"
        else:
            flash('Could not extract details from link. Enter manually.')
            if filepath and os.path.exists(filepath): os.remove(filepath)
            return redirect(url_for('index'))
    else:
        # (Keep manual input logic...)
        if not manual_job_role or not manual_job_description:
            flash('Job Role and Description required if no link.')
            if filepath and os.path.exists(filepath): os.remove(filepath)
            return redirect(url_for('index'))
        job_role_to_use = manual_job_role
        company_to_use = manual_company
        job_description_to_use = manual_job_description
        source_method = "Manual"


    # --- 3. Process Resume and Call AI ---
    try:
        original_resume_text = extract_text_from_docx(filepath)
        if not original_resume_text or not original_resume_text.strip():
            flash('Could not read resume file or it is empty.')
            return redirect(url_for('index')) # Cleanup in finally

        tailored_resume_text, error_message = call_google_ai(
            original_resume_text, job_role_to_use, company_to_use,
            job_description_to_use, source_method
        )

        if error_message:
             flash(error_message) # Show specific AI error
             return redirect(url_for('index')) # Cleanup in finally

        # --- 4. Show Result ---
        if tailored_resume_text:
            logging.info("AI call successful, rendering result page.")
            # Instead of saving/sending file, render the result template
            return render_template(
                'result.html',
                tailored_text=tailored_resume_text
            )
        else:
             flash("AI processing finished but no content generated.")
             logging.error("AI call ok but tailored_resume_text was empty.")
             return redirect(url_for('index')) # Cleanup in finally

    except Exception as e:
        logging.error(f"Unexpected error in /tailor processing: {e}", exc_info=True)
        flash("An unexpected error occurred. Please try again.")
        return redirect(url_for('index')) # Cleanup in finally

    finally:
        # --- 5. Cleanup Uploaded File ---
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                logging.info(f"Cleaned up uploaded file: {filepath}")
            except OSError as e:
                logging.error(f"Error removing uploaded file {filepath}: {e}")


# --- Error Handlers ---
# (Keep existing error handlers: 404, 500, 413)
@app.errorhandler(404)
def page_not_found(e):
    logging.warning(f"404 Not Found: {request.url}")
    return "404 Not Found", 404

@app.errorhandler(500)
def internal_server_error(e):
    logging.error(f"500 Internal Server Error", exc_info=True)
    return "500 Internal Server Error", 500

@app.errorhandler(413)
def request_entity_too_large(e):
    limit_mb = app.config['MAX_CONTENT_LENGTH'] / (1024*1024)
    logging.warning(f"413 Payload Too Large.")
    flash(f"File too large (Max: {limit_mb:.0f}MB).")
    return redirect(url_for('index'))

# Ensure upload folder exists (safe for Vercel)
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    logging.info(f"Upload directory '{app.config['UPLOAD_FOLDER']}' ensured.")
except OSError as e:
    logging.error(f"Could not create upload directory: {e}")
