from flask import Flask, request, jsonify, send_file, send_from_directory
import os
from datetime import datetime
# Here you import the new, modified function
from .processing import process_ndvi, calculate_polygon_area_sqkm
import logging
from flask_cors import CORS

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask application configuration
# It's assumed the structure is:
# /backend/app.py
# /frontend/index.html
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app) # Enable CORS for communication between frontend and backend

# Folder for storing generated images
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

# Constants for validation
MAX_ALLOWED_POLYGON_AREA_SQKM = 25.0
MAX_IMAGES_TO_CONSIDER = 30

# Route for serving the main page (index.html)
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# Main endpoint for NDVI processing
@app.route('/process-ndvi', methods=['POST'])
def handle_process_ndvi():
    data = request.json
    if not data:
        logging.error("No data in request.")
        return jsonify({"error": "No data provided"}), 400

    # Load parameters from the request
    polygon = data.get('polygon')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    frequency = data.get('frequency')

    # Basic input validation
    if not all([polygon, start_date_str, end_date_str, frequency]):
        logging.error("Missing parameters: polygon, startDate, endDate, or frequency.")
        return jsonify({"error": "Missing polygon, startDate, endDate, or frequency parameters"}), 400

    if not polygon or len(polygon) < 3:
        logging.error("Invalid polygon (insufficient number of points).")
        return jsonify({"error": "Invalid polygon provided (less than 3 points)"}), 400

    # Polygon size validation
    try:
        area = calculate_polygon_area_sqkm(polygon)
        if area > MAX_ALLOWED_POLYGON_AREA_SQKM:
            logging.error(f"Polygon is too large. Area: {area:.2f} km², max: {MAX_ALLOWED_POLYGON_AREA_SQKM} km².")
            return jsonify({"error": f"Polygon is too large. Max allowed area is {MAX_ALLOWED_POLYGON_AREA_SQKM} km²."}), 400
    except Exception as e:
        logging.error(f"Error calculating polygon area on the backend: {e}")
        return jsonify({"error": "Error calculating polygon area"}), 400

    # --- THIS IS THE KEY CHANGE ---
    try:
        # We call our new function, which returns a dictionary with data
        result_data = process_ndvi(
            polygon_coords=polygon,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            frequency=frequency,
            max_images_to_consider=MAX_IMAGES_TO_CONSIDER,
            max_polygon_area_sqkm=MAX_ALLOWED_POLYGON_AREA_SQKM
        )

        # If the function returned valid data...
        if result_data and result_data.get("imageLayers"):
            logging.info(f"Processing successful, returning {len(result_data['imageLayers'])} map layers.")
            # ...we send the whole data package as JSON to the frontend.
            return jsonify(result_data)
        else:
            # If something went wrong or no data was found
            logging.warning("NDVI processing failed or no suitable satellite data was found.")
            return jsonify({"error": "NDVI processing failed or no suitable satellite data found"}), 500

    except ValueError as e:
        # Errors that we define ourselves (e.g., polygon too large)
        logging.error(f"Validation/processing error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # All other unexpected errors
        logging.exception("An unexpected error occurred during NDVI processing.")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# Route for serving generated files (images)
# THIS PART REMAINS THE SAME! The frontend will call it for each PNG image.
@app.route('/output/<filename>')
def serve_output_file(filename):
    # Sanitize filename to prevent directory traversal attacks
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "Invalid filename"}), 400

    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        # as_attachment=False means the browser will try to display the file, not download it
        return send_file(file_path, as_attachment=False)
    else:
        logging.warning(f"Requested file not found: {file_path}")
        return jsonify({"error": "File not found"}), 404

# Run the application
if __name__ == '__main__':
    # port=5000 is the default, debug=True is great for development
    app.run(debug=True, port=5000)