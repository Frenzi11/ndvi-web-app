from flask import Flask, request, jsonify, send_file, send_from_directory, render_template, Response
import os
from datetime import datetime
import base64
import json

from .processing import process_ndvi, calculate_polygon_area_sqkm
import logging
from flask_cors import CORS

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask application configuration
# Tell Flask where to find the templates folder
app = Flask(__name__, static_folder='../frontend', static_url_path='', template_folder='templates')
CORS(app) 

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
    # ... (tato funkce zůstává úplně stejná) ...
    data = request.json
    if not data:
        logging.error("No data in request.")
        return jsonify({"error": "No data provided"}), 400
    polygon = data.get('polygon')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    frequency = data.get('frequency')
    if not all([polygon, start_date_str, end_date_str, frequency]):
        return jsonify({"error": "Missing parameters"}), 400
    try:
        result_data = process_ndvi(
            polygon_coords=polygon,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            frequency=frequency,
            max_images_to_consider=MAX_IMAGES_TO_CONSIDER,
            max_polygon_area_sqkm=MAX_ALLOWED_POLYGON_AREA_SQKM
        )
        if result_data and result_data.get("imageLayers"):
            return jsonify(result_data)
        else:
            return jsonify({"error": "NDVI processing failed or no suitable satellite data found"}), 500
    except Exception as e:
        logging.exception("An unexpected error occurred during NDVI processing.")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


# --- NEW: Endpoint for exporting HTML report ---
@app.route('/export-html')
def export_html_report():
    try:
        # Get parameters from URL query string
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        frequency = request.args.get('frequency')
        polygon_str = request.args.get('polygon')
        
        if not all([start_date, end_date, frequency, polygon_str]):
            return "Error: Missing parameters in URL.", 400
        
        # Convert polygon string back to list of lists
        polygon = json.loads(polygon_str)

        # Re-run the processing to get the data and generate images
        # Note: In a production app, you might cache this result to avoid re-processing.
        result_data = process_ndvi(
            polygon_coords=polygon,
            start_date_str=start_date,
            end_date_str=end_date,
            frequency=frequency
        )

        if not result_data:
            return "Error: Could not generate data for the report.", 500

        # --- Base64 Encoding Magic ---
        def to_base64(file_path):
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')

        # The graph and legend are part of the main result now
        graph_base64 = to_base64(result_data['graphPngPath'])
        legend_base64 = to_base64(result_data['legendPngPath'])

        # Prepare map data for the template
        maps_data_for_template = []
        for layer in result_data['imageLayers']:
            # layer['url'] is like '/output/ndvi_map_2025-07-25...png'
            # We need the full file system path.
            image_filename = os.path.basename(layer['url'])
            image_filepath = os.path.join(OUTPUT_FOLDER, image_filename)
            maps_data_for_template.append({
                'date': layer['date'],
                'src': to_base64(image_filepath)
            })
        
        # Render the HTML template with our data
        html_report = render_template('report_template.html', 
                                      start_date=start_date,
                                      end_date=end_date,
                                      frequency=frequency.capitalize(),
                                      graph_base64=graph_base64,
                                      legend_base64=legend_base64,
                                      maps=maps_data_for_template)
        
        # Return the rendered HTML as a downloadable file
        return Response(
            html_report,
            mimetype='text/html',
            headers={'Content-disposition': 'attachment; filename=ndvi_report.html'}
        )

    except Exception as e:
        logging.exception("Error generating HTML report.")
        return f"An error occurred while generating the report: {e}", 500


# Route for serving generated files (images)
@app.route('/output/<filename>')
def serve_output_file(filename):
    # ... (tato funkce zůstává stejná) ...
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "Invalid filename"}), 400
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=False)
    else:
        return jsonify({"error": "File not found"}), 404

# Run the application
if __name__ == '__main__':
    app.run(debug=True, port=5000)