import os
import numpy as np
import rasterio
from sentinelhub import (
    SHConfig, SentinelHubRequest, DataCollection, MimeType, CRS, BBox, bbox_to_dimensions,
    SentinelHubCatalog
)
from datetime import date, timedelta, datetime
from dotenv import load_dotenv
import logging
from shapely.geometry import Polygon
import math
import sys

# Matplotlib je stále potřeba pro generování PNG obrázků
import matplotlib
matplotlib.use('Agg') # Nastavení non-interactive backendu je stále důležité pro server
import matplotlib.pyplot as plt

# Z rasterio potřebujeme transform pro georeferencování obrázků
from rasterio.transform import from_bounds

# Setup logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Načtení .env proměnných
load_dotenv()
CDSE_CLIENT_ID = os.getenv("CDSE_CLIENT_ID")
CDSE_CLIENT_SECRET = os.getenv("CDSE_CLIENT_SECRET")

if not all([CDSE_CLIENT_ID, CDSE_CLIENT_SECRET]):
    logging.error("Chybí proměnné prostředí pro CDSE (CDSE_CLIENT_ID/SECRET). Zkontroluj .env soubor.")
    raise ValueError("Chybí CDSE API klíče v .env souboru.")

# Konfigurace Sentinel Hub pro Copernicus Data Space Ecosystem (CDSE)
_GLOBAL_CDSE_CONFIG = SHConfig()
_GLOBAL_CDSE_CONFIG.sh_client_id = CDSE_CLIENT_ID
_GLOBAL_CDSE_CONFIG.sh_client_secret = CDSE_CLIENT_SECRET
_GLOBAL_CDSE_CONFIG.sh_base_url = "https://sh.dataspace.copernicus.eu"
_GLOBAL_CDSE_CONFIG.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_GLOBAL_CDSE_CONFIG.sh_auth_base_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect"

logging.info(f"Global SHConfig Base URL: {_GLOBAL_CDSE_CONFIG.sh_base_url}")

# Inicializace katalogu pro vyhledávání snímků
catalog = SentinelHubCatalog(config=_GLOBAL_CDSE_CONFIG)

# Definice vlastní datové kolekce pro CDSE
DataCollection.define(
    "SENTINEL2_L1C_CDSE_CUSTOM",
    api_id="sentinel-2-l1c",
    service_url="https://sh.dataspace.copernicus.eu"
)
S2_CDSE_CUSTOM = DataCollection.SENTINEL2_L1C_CDSE_CUSTOM

# ----- FUNKCE PRO VÝPOČET PLOCHY (zůstává beze změny) -----
def calculate_polygon_area_sqkm(polygon_coords: list) -> float:
    """
    Vypočítá přibližnou plochu polygonu v km^2.
    """
    if not polygon_coords or len(polygon_coords) < 3:
        return 0.0
    try:
        polygon_shape = Polygon(polygon_coords)
    except Exception as e:
        logging.error(f"Chyba při vytváření Shapely polygonu: {e}")
        return 0.0
    centroid_lat = polygon_shape.centroid.y
    lat_rad = math.radians(centroid_lat)
    km_per_deg_lon = 111.32 * math.cos(lat_rad)
    km_per_deg_lat = 110.574
    approx_projected_coords = []
    for lon, lat in polygon_coords:
        approx_projected_coords.append((lon * km_per_deg_lon, lat * km_per_deg_lat))
    try:
        approx_projected_polygon = Polygon(approx_projected_coords)
        return approx_projected_polygon.area
    except Exception as e:
        logging.error(f"Chyba při výpočtu plochy aproximovaného polygonu: {e}")
        return 0.0

# ----- HLAVNÍ ZPRACOVÁVACÍ FUNKCE (kompletně předělaná) -----
def process_ndvi(
    polygon_coords: list,
    start_date_str: str,
    end_date_str: str,
    frequency: str,
    max_images_to_consider: int = 30,
    max_polygon_area_sqkm: float = 25.0
) -> dict | None:
    """
    Zpracuje NDVI pro daný polygon a časové období. Pro každý časový interval najde nejlepší
    snímek, vygeneruje z něj PNG obrázek NDVI mapy a vrátí strukturovaná data pro frontend.
    """
    # Evalscript pro stažení potřebných pásem (B04 - červená, B08 - blízká infračervená)
    evalscript_bands = """
        //VERSION=3
        function setup() {
            return {
                input: [{
                    bands: ["B04", "B08", "dataMask"]
                }],
                output: [
                    { id: "B04", bands: 1, sampleType: SampleType.FLOAT32 },
                    { id: "B08", bands: 1, sampleType: SampleType.FLOAT32 },
                    { id: "dataMask", bands: 1, sampleType: SampleType.UINT8 }
                ]
            };
        }
        function evaluatePixel(samples) {
            // Pokud pixel nemá data, vrátíme NaN
            if (!samples.dataMask) {
                return { B04: [NaN], B08: [NaN], dataMask: [0] };
            }
            return { B04: [samples.B04], B08: [samples.B08], dataMask: [samples.dataMask] };
        }
    """

    FIXED_MAX_CLOUD_COVERAGE = 0.8 # Povolíme až 80% oblačnost pro hledání snímků

    logging.info(f"Startuji NDVI zpracování pro polygon, od {start_date_str} do {end_date_str}, frekvence: {frequency}")

    # Kontrola velikosti polygonu
    area = calculate_polygon_area_sqkm(polygon_coords)
    if area > max_polygon_area_sqkm:
        raise ValueError(f"Plocha polygonu ({area:.2f} km²) překračuje maximální povolenou velikost ({max_polygon_area_sqkm} km²).")

    # Zpracování datumu a validace
    start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    MAX_DURATION_DAYS = 365 # Max 1 rok
    MAX_TS_IMAGES = 50 # Max 50 snímků v časové řadě
    
    if (end_date_dt - start_date_dt).days > MAX_DURATION_DAYS:
        raise ValueError(f"Maximální délka časové řady je omezena na {MAX_DURATION_DAYS} dní (1 rok).")

    # Vytvoření časových intervalů pro hledání snímků
    time_series_intervals = []
    if frequency == 'weekly':
        current_date = start_date_dt
        while current_date <= end_date_dt:
            interval_end = current_date + timedelta(days=6)
            time_series_intervals.append((current_date.strftime('%Y-%m-%d'), interval_end.strftime('%Y-%m-%d')))
            current_date += timedelta(days=7)
    elif frequency == 'monthly':
        current_date = start_date_dt
        while current_date <= end_date_dt:
            next_month = current_date.replace(day=28) + timedelta(days=4)
            interval_end = next_month - timedelta(days=next_month.day)
            time_series_intervals.append((current_date.strftime('%Y-%m-%d'), min(interval_end, end_date_dt).strftime('%Y-%m-%d')))
            current_date = min(interval_end, end_date_dt) + timedelta(days=1)
    else:
        raise ValueError("Nepodporovaná frekvence. Použij 'weekly' nebo 'monthly'.")

    if len(time_series_intervals) > MAX_TS_IMAGES:
        raise ValueError(f"Počet snímků v časové řadě ({len(time_series_intervals)}) překračuje limit {MAX_TS_IMAGES}. Zkraťte období nebo změňte frekvenci.")

    # Geometrie pro dotazy
    min_lon, max_lon = min(p[0] for p in polygon_coords), max(p[0] for p in polygon_coords)
    min_lat, max_lat = min(p[1] for p in polygon_coords), max(p[1] for p in polygon_coords)
    bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
    size = bbox_to_dimensions(bbox, resolution=10) # 10m rozlišení pro Sentinel-2

    # Cesta k výstupní složce
    output_folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Příprava datových struktur pro výsledky
    time_series_for_graph = []
    image_layers_for_map = []

    # Hlavní cyklus - procházení časových intervalů
    for ts_start_str, ts_end_str in time_series_intervals:
        logging.info(f"Hledám snímky pro interval: {ts_start_str} až {ts_end_str}")
        
        # Hledání v katalogu
        search_iterator = catalog.search(
            S2_CDSE_CUSTOM,
            bbox=bbox,
            time=(ts_start_str, ts_end_str),
            filter=f"eo:cloud_cover <= {FIXED_MAX_CLOUD_COVERAGE * 100}",
            limit=max_images_to_consider
        )
        results = list(search_iterator)

        if not results:
            logging.warning(f"Pro interval {ts_start_str} - {ts_end_str} nebyly nalezeny žádné snímky. Přeskakuji.")
            continue

        # Seřazení výsledků podle oblačnosti (nejlepší první)
        best_image_metadata = sorted(results, key=lambda x: x['properties']['eo:cloud_cover'])[0]
        image_date = best_image_metadata['properties']['datetime'][:10]
        logging.info(f"  Vybrán snímek pro interval: {best_image_metadata['id']} z data {image_date} (oblačnost: {best_image_metadata['properties']['eo:cloud_cover']:.2f}%)")

        # Stahování dat pro vybraný snímek
        request_data = SentinelHubRequest(
            evalscript=evalscript_bands,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=S2_CDSE_CUSTOM,
                    time_interval=(image_date, image_date), # Stahujeme jen konkrétní den
                )
            ],
            responses=[
                SentinelHubRequest.output_response("B04", MimeType.TIFF),
                SentinelHubRequest.output_response("B08", MimeType.TIFF),
                SentinelHubRequest.output_response("dataMask", MimeType.TIFF)
            ],
            bbox=bbox,
            size=size,
            config=_GLOBAL_CDSE_CONFIG
        )

        try:
            downloaded_data = request_data.get_data()[0]
        except Exception as e:
            logging.error(f"Chyba při stahování dat pro {image_date}: {e}. Přeskakuji.")
            continue
        
        # Výpočet NDVI
        red_band = downloaded_data['B04.tif']
        nir_band = downloaded_data['B08.tif']
        
        with np.errstate(divide='ignore', invalid='ignore'):
            ndvi_array = (nir_band.astype(float) - red_band.astype(float)) / (nir_band.astype(float) + red_band.astype(float))
        
        # Ošetření hodnot
        ndvi_array = np.clip(ndvi_array, -1.0, 1.0)
        ndvi_array[np.isnan(ndvi_array)] = -999 # Specifická hodnota pro "no data"

        # Výpočet průměrného NDVI pro graf
        data_mask = downloaded_data['dataMask.tif']
        valid_ndvi_pixels = ndvi_array[data_mask == 1]
        
        if valid_ndvi_pixels.size > 0:
            mean_ndvi = np.mean(valid_ndvi_pixels)
        else:
            logging.warning(f"Žádné platné pixely v masce pro {image_date}. Průměrné NDVI bude NaN.")
            mean_ndvi = np.nan
        
        # Uložení dat pro graf
        time_series_for_graph.append({'date': image_date, 'value': round(mean_ndvi, 4) if not np.isnan(mean_ndvi) else None})
        
        # --- NOVÁ ČÁST: Generování a uložení PNG pro každý snímek ---
        if not np.isnan(mean_ndvi):
            fig, ax = plt.subplots(figsize=(6, 6), dpi=150) # Rozumná velikost a DPI pro web
            ax.set_axis_off()
            
            # POUŽIJ KONZISTENTNÍ BAREVNOU ŠKÁLU PRO VŠECHNY OBRÁZKY! To je super důležité pro porovnání.
            cmap = plt.cm.RdYlGn
            norm = plt.Normalize(vmin=-0.2, vmax=1.0) # Pevná škála od stresu po zdravou vegetaci
            
            # Zobrazení NDVI pole, ale pixely s "no data" uděláme průhledné
            masked_ndvi = np.ma.masked_where(ndvi_array == -999, ndvi_array)
            ax.imshow(masked_ndvi, cmap=cmap, norm=norm)
            
            # Uložení do souboru
            png_filename = f"ndvi_map_{image_date}_{timestamp}.png"
            png_path = os.path.join(output_folder_path, png_filename)
            plt.savefig(png_path, format='png', bbox_inches='tight', pad_inches=0, transparent=True)
            plt.close(fig) # Uvolnění paměti
            
            # Přidání informací o vrstvě pro frontend
            image_layers_for_map.append({
                "date": image_date,
                "url": f"/output/{png_filename}",
                "bounds": [[bbox.min_y, bbox.min_x], [bbox.max_y, bbox.max_x]],
                "mean_ndvi": round(mean_ndvi, 4)
            })

    # Pokud jsme nic nenašli, vrátíme None
    if not image_layers_for_map:
        logging.warning("Zpracování skončilo, ale nebyly vygenerovány žádné mapové vrstvy.")
        return None

    # Návratová hodnota je teď slovník s daty pro frontend
    return {
        "graphData": sorted(time_series_for_graph, key=lambda x: x['date']),
        "imageLayers": sorted(image_layers_for_map, key=lambda x: x['date'])
    }


# ----- TESTOVACÍ BLOK (pokud spustíš soubor přímo) -----
if __name__ == '__main__':
    # Testovací polygon v Havířově
    test_polygon = [
        [18.435, 49.792],
        [18.435, 49.801],
        [18.448, 49.801],
        [18.448, 49.792],
        [18.435, 49.792]
    ]
    print("Spouštím testovací běh `process_ndvi`...")
    try:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
        
        # Zavolání nové funkce
        result_data = process_ndvi(test_polygon, start_date, end_date, 'monthly')
        
        if result_data:
            print("\n✅ Zpracování proběhlo úspěšně!")
            print(f"Počet bodů v grafu: {len(result_data['graphData'])}")
            print(f"Počet vygenerovaných mapových vrstev: {len(result_data['imageLayers'])}")
            print("\nUkázka dat pro první mapovou vrstvu:")
            print(result_data['imageLayers'][0] if result_data['imageLayers'] else "Žádná data")
        else:
            print("\n❌ Zpracování selhalo nebo nevrátilo žádná data.")
            
    except ValueError as e:
        print(f"Chyba: {e}")
    except Exception as e:
        logging.exception("Během testovacího běhu došlo k neočekávané chybě.")
        print(f"Neočekávaná chyba: {e}")