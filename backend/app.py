from flask import Flask, request, jsonify, send_file
import os
from datetime import datetime
from processing import process_ndvi, calculate_polygon_area_sqkm
import logging
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ZMĚNA ZDE: Konfigurace Flask aplikace pro servírování statických souborů z 'frontend' složky
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app) # Enable CORS

OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

MAX_ALLOWED_POLYGON_AREA_SQKM = 25.0
MAX_DAYS_AGO = 60
MAX_IMAGES_TO_CONSIDER = 30

# NOVÁ CESTA: Servírování hlavní stránky (index.html)
@app.route('/')
def serve_index():
    return send_file('index.html')

@app.route('/process-ndvi', methods=['POST'])
def handle_process_ndvi():
    data = request.json
    if not data:
        logging.error("No data provided in request.")
        return jsonify({"error": "No data provided"}), 400

    polygon = data.get('polygon')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    frequency = data.get('frequency')

    if not all([polygon, start_date_str, end_date_str, frequency]):
        logging.error("Missing parameters: polygon, startDate, endDate or frequency.")
        return jsonify({"error": "Missing polygon, startDate, endDate, or frequency parameters"}), 400

    if not polygon or len(polygon) < 3:
        logging.error("Invalid polygon (insufficient number of points).")
        return jsonify({"error": "Invalid polygon provided (less than 3 points)"}), 400

    try:
        area = calculate_polygon_area_sqkm(polygon)
        if area > MAX_ALLOWED_POLYGON_AREA_SQKM:
            logging.error(f"Polygon is too large. Area: {area:.2f} km², max allowed: {MAX_ALLOWED_POLYGON_AREA_SQKM} km².")
            return jsonify({"error": f"Polygon is too large. Max allowed area is {MAX_ALLOWED_POLYGON_AREA_SQKM} km²."}), 400
    except Exception as e:
        logging.error(f"Error calculating polygon area on backend: {e}")
        return jsonify({"error": "Error calculating polygon area"}), 400

    try:
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
            file_url_tif = f"/output/{filename_tif}"

            filename_pdf = os.path.basename(pdf_file_path)
            file_url_pdf = f"/output/{filename_pdf}"

            logging.info(f"NDVI GeoTIFF file processed and available: {file_url_tif}")
            logging.info(f"NDVI PDF report processed and available: {file_url_pdf}")

            return jsonify({
                "message": "NDVI processing complete",
                "fileUrl": file_url_tif,
                "imageDate": image_date,
                "pdfUrl": file_url_pdf
            })
        else:
            logging.warning("NDVI processing incomplete, no file created.")
            return jsonify({"error": "NDVI processing failed or no data found"}), 500

    except ValueError as e:
        logging.error(f"Validation/Processing error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.exception("An unexpected error occurred during NDVI processing.")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/output/<filename>')
def serve_output_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        if filename.endswith(".tif"):
            mime_type = "image/tiff"
        elif filename.endswith(".pdf"):
            mime_type = "application/pdf"
        else:
            mime_type = "application/octet-stream"

        return send_file(file_path, as_attachment=True, mimetype=mime_type)
    else:
        logging.warning(f"Requested file not found: {file_path}")
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)