from flask import Flask, request, jsonify, send_file
import os
from datetime import datetime
# Import our function and helper function (process_ndvi now returns date and PDF path)
from processing import process_ndvi, calculate_polygon_area_sqkm
import logging
from flask_cors import CORS # Important for CORS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app) # Enable CORS

# Path where resulting NDVI files will be stored
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

# Set limits for polygon size and time range
MAX_ALLOWED_POLYGON_AREA_SQKM = 25.0 # Max allowed polygon area in km^2
MAX_DAYS_AGO = 60 # Max search range (days back)
MAX_IMAGES_TO_CONSIDER = 30 # Max number of images to consider for selection

# Endpoint for processing NDVI request
@app.route('/process-ndvi', methods=['POST'])
def handle_process_ndvi():
    data = request.json
    if not data:
        logging.error("No data provided in request.") # Translated log message
        return jsonify({"error": "No data provided"}), 400

    polygon = data.get('polygon')
    # Now accepting startDate, endDate, and frequency
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    frequency = data.get('frequency')

    # Validate input parameters
    if not all([polygon, start_date_str, end_date_str, frequency]):
        logging.error("Missing parameters: polygon, startDate, endDate or frequency.") # Translated log message
        return jsonify({"error": "Missing polygon, startDate, endDate, or frequency parameters"}), 400

    # Basic polygon validation (at least 3 points)
    if not polygon or len(polygon) < 3:
        logging.error("Invalid polygon (insufficient number of points).") # Translated log message
        return jsonify({"error": "Invalid polygon provided (less than 3 points)"}), 400

    # Backend polygon size validation (redundant but important for security)
    try:
        area = calculate_polygon_area_sqkm(polygon)
        if area > MAX_ALLOWED_POLYGON_AREA_SQKM:
            logging.error(f"Polygon is too large. Area: {area:.2f} km², max allowed: {MAX_ALLOWED_POLYGON_AREA_SQKM} km².") # Translated log message
            return jsonify({"error": f"Polygon is too large. Max allowed area is {MAX_ALLOWED_POLYGON_AREA_SQKM} km²."}), 400
    except Exception as e:
        logging.error(f"Error calculating polygon area on backend: {e}") # Translated log message
        return jsonify({"error": "Error calculating polygon area"}), 400

    try:
        # Call process_ndvi function, which now returns a tuple (GeoTIFF_path, image_date, PDF_path)
        result_tuple = process_ndvi(
            polygon_coords=polygon,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            frequency=frequency,
            max_images_to_consider=MAX_IMAGES_TO_CONSIDER,
            max_polygon_area_sqkm=MAX_ALLOWED_POLYGON_AREA_SQKM
        )

        if result_tuple:
            output_file_path, image_date, pdf_file_path = result_tuple
            
            filename_tif = os.path.basename(output_file_path)
            file_url_tif = f"/output/{filename_tif}" # URL for GeoTIFF

            filename_pdf = os.path.basename(pdf_file_path)
            file_url_pdf = f"/output/{filename_pdf}" # URL for PDF

            logging.info(f"NDVI GeoTIFF file processed and available: {file_url_tif}") # Translated log message
            logging.info(f"NDVI PDF report processed and available: {file_url_pdf}") # Translated log message

            return jsonify({
                "message": "NDVI processing complete", # Translated message
                "fileUrl": file_url_tif,
                "imageDate": image_date,
                "pdfUrl": file_url_pdf
            })
        else:
            logging.warning("NDVI processing incomplete, no file created.") # Translated log message
            return jsonify({"error": "NDVI processing failed or no data found"}), 500

    except ValueError as e: # Catch validation errors from process_ndvi (e.g., invalid dates, limits)
        logging.error(f"Validation/Processing error: {e}") # Translated log message
        return jsonify({"error": str(e)}), 400
    except Exception as e: # Catch any other unexpected errors
        logging.exception("An unexpected error occurred during NDVI processing.") # Translated log message
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# Endpoint for serving static files (resulting GeoTIFFs and PDFs)
@app.route('/output/<filename>')
def serve_output_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        # Infer mime type for browsers to handle downloads correctly
        if filename.endswith(".tif"):
            mime_type = "image/tiff"
        elif filename.endswith(".pdf"):
            mime_type = "application/pdf"
        else:
            mime_type = "application/octet-stream" # Generic binary

        return send_file(file_path, as_attachment=True, mimetype=mime_type)
    else:
        logging.warning(f"Requested file not found: {file_path}") # Translated log message
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)