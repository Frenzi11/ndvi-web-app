from flask import Flask, request, jsonify, send_file, send_from_directory
import os
from datetime import datetime
# Tady si importuješ tu novou, upravenou funkci
from .processing import process_ndvi, calculate_polygon_area_sqkm
import logging
from flask_cors import CORS

# Základní nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Konfigurace Flask aplikace
# Předpokládá se, že struktura je:
# /backend/app.py
# /frontend/index.html
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app) # Povolení CORS pro komunikaci mezi frontendem a backendem

# Složka pro ukládání vygenerovaných obrázků
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

# Konstanty pro validaci
MAX_ALLOWED_POLYGON_AREA_SQKM = 25.0
MAX_IMAGES_TO_CONSIDER = 30

# Route pro servírování hlavní stránky (index.html)
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# Hlavní endpoint pro zpracování NDVI
@app.route('/process-ndvi', methods=['POST'])
def handle_process_ndvi():
    data = request.json
    if not data:
        logging.error("V requestu chybí data.")
        return jsonify({"error": "No data provided"}), 400

    # Načtení parametrů z requestu
    polygon = data.get('polygon')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    frequency = data.get('frequency')

    # Základní validace vstupů
    if not all([polygon, start_date_str, end_date_str, frequency]):
        logging.error("Chybí parametry: polygon, startDate, endDate nebo frequency.")
        return jsonify({"error": "Missing polygon, startDate, endDate, or frequency parameters"}), 400

    if not polygon or len(polygon) < 3:
        logging.error("Neplatný polygon (nedostatečný počet bodů).")
        return jsonify({"error": "Invalid polygon provided (less than 3 points)"}), 400

    # Validace velikosti polygonu
    try:
        area = calculate_polygon_area_sqkm(polygon)
        if area > MAX_ALLOWED_POLYGON_AREA_SQKM:
            logging.error(f"Polygon je moc velký. Plocha: {area:.2f} km², max: {MAX_ALLOWED_POLYGON_AREA_SQKM} km².")
            return jsonify({"error": f"Polygon is too large. Max allowed area is {MAX_ALLOWED_POLYGON_AREA_SQKM} km²."}), 400
    except Exception as e:
        logging.error(f"Chyba při výpočtu plochy polygonu na backendu: {e}")
        return jsonify({"error": "Error calculating polygon area"}), 400

    # --- ZDE JE KLÍČOVÁ ZMĚNA ---
    try:
        # Zavoláme naši novou funkci, která vrací slovník s daty
        result_data = process_ndvi(
            polygon_coords=polygon,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            frequency=frequency,
            max_images_to_consider=MAX_IMAGES_TO_CONSIDER,
            max_polygon_area_sqkm=MAX_ALLOWED_POLYGON_AREA_SQKM
        )

        # Pokud funkce vrátila platná data...
        if result_data and result_data.get("imageLayers"):
            logging.info(f"Zpracování úspěšné, vracím {len(result_data['imageLayers'])} mapových vrstev.")
            # ...tak celý ten balík dat pošleme jako JSON na frontend.
            return jsonify(result_data)
        else:
            # Pokud se něco pokazilo nebo se nenašla žádná data
            logging.warning("Zpracování NDVI selhalo nebo nebyla nalezena žádná data.")
            return jsonify({"error": "NDVI processing failed or no suitable satellite data found"}), 500

    except ValueError as e:
        # Chyby, které si sami definujeme (např. moc velký polygon)
        logging.error(f"Chyba validace/zpracování: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # Všechny ostatní nečekané chyby
        logging.exception("Během zpracování NDVI došlo k neočekávané chybě.")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# Route pro servírování vygenerovaných souborů (obrázků)
# TATO ČÁST ZŮSTÁVÁ STEJNÁ! Frontend ji bude volat pro každý PNG obrázek.
@app.route('/output/<filename>')
def serve_output_file(filename):
    # Sanitize filename to prevent directory traversal attacks
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "Invalid filename"}), 400

    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        # as_attachment=False znamená, že se prohlížeč pokusí soubor zobrazit, ne stáhnout
        return send_file(file_path, as_attachment=False)
    else:
        logging.warning(f"Požadovaný soubor nebyl nalezen: {file_path}")
        return jsonify({"error": "File not found"}), 404

# Spuštění aplikace
if __name__ == '__main__':
    # port=5000 je defaultní, debug=True je super pro vývoj
    app.run(debug=True, port=5000)