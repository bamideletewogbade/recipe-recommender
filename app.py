import os
import sys
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import tempfile
import markdown
from dotenv import load_dotenv
from PIL import Image
import io

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")  # For flash messages and sessions
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16MB
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()  # Use temp directory for uploads
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}

# Determine which Google AI package to use
try:
    import google.generativeai as genai
    print("Using google.generativeai package")
    USING_GENERATIVE_AI = True
except ImportError:
    try:
        import google_genai as genai
        print("Using google_genai package")
        USING_GENERATIVE_AI = False
    except ImportError:
        print("Error: Neither google.generativeai nor google_genai could be imported")
        sys.exit(1)

# Configure Gemini API
def configure_gemini():
    api_key = "AIzaSyDqmVHh_JDcl-0F4BSUOcg_8wOUmWj1yH0"
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY environment variable")
    genai.configure(api_key=api_key)

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Function to analyze image with Gemini
def analyze_image_with_gemini(image_path):
    configure_gemini()
    
    # Load the image
    with Image.open(image_path) as img:
        # Create a copy of the image in memory
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format=img.format or 'JPEG')
        img_bytes = img_byte_arr.getvalue()
    
    # Set up Gemini model
    if USING_GENERATIVE_AI:
        generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
        )
        
        # Handle image analysis
        try:
            # Try with direct image object first
            img = Image.open(image_path)
            chat = model.start_chat(history=[])
            prompt = "Identify all ingredients in this image. Then suggest 5 recipes I can make with these ingredients. For each recipe, provide a name, list of ingredients (marking which ones were identified in the image with '(found)' and which ones are missing with '(not found)'), and step-by-step instructions. Format this nicely with markdown."
            response = chat.send_message([img, prompt])
        except Exception as e:
            print(f"Direct image method failed: {e}")
            try:
                # Try with content parts
                response = model.generate_content([
                    {"mime_type": "image/jpeg", "data": img_bytes},
                    {"text": "Identify all ingredients in this image. Then suggest 5 recipes I can make with these ingredients. For each recipe, provide a name, list of ingredients (marking which ones were identified in the image with '(found)' and which ones are missing with '(not found)'), and step-by-step instructions. Format this nicely with markdown."}
                ])
            except Exception as e2:
                print(f"Content parts method failed: {e2}")
                raise
    else:
        # Handling for google_genai package if needed
        # This would need to be implemented based on the google_genai API
        raise NotImplementedError("Support for google_genai package not yet implemented")
    
    # Convert markdown to HTML
    html_content = markdown.markdown(response.text)
    return html_content

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if the post request has the file part
    if 'image' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['image']
    
    # If user does not select file, browser also submits an empty part without filename
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Analyze image with Gemini
            result = analyze_image_with_gemini(file_path)
            
            # Store result in session
            session['recipes'] = result
            
            # Clean up the file
            os.remove(file_path)
            
            return redirect(url_for('results'))
        except Exception as e:
            import traceback
            traceback.print_exc()  # Print detailed error for debugging
            flash(f"Error processing image: {str(e)}")
            return redirect(url_for('index'))
    else:
        flash('Allowed file types are png, jpg, jpeg')
        return redirect(url_for('index'))

@app.route('/results')
def results():
    recipes = session.get('recipes', None)
    if not recipes:
        flash('No recipe results found, please upload an image first')
        return redirect(url_for('index'))
    
    return render_template('results.html', recipes=recipes)

if __name__ == '__main__':
    app.run(debug=True)