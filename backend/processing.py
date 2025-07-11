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

# NOVÉ IMPORTY PRO PDF GENERACI
import matplotlib 
matplotlib.use('Agg') # Nastaví neinteraktivní backend
import matplotlib.pyplot as plt
from fpdf import FPDF
import io
from matplotlib.colors import LinearSegmentedColormap 
import pandas as pd # Pro práci s datovými řadami

# Přesunuto na začátek souboru
from rasterio.transform import from_bounds
import unicodedata # NOVÝ IMPORT: Pro sanitizaci textu (odstranění diakritiky)
from PIL import Image # NOVÝ IMPORT PRO ZJIŠTĚNÍ ROZMĚRŮ PNG



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
CDSE_CLIENT_ID = os.getenv("CDSE_CLIENT_ID")
CDSE_CLIENT_SECRET = os.getenv("CDSE_CLIENT_SECRET")

if not all([CDSE_CLIENT_ID, CDSE_CLIENT_SECRET]):
    logging.error("Missing environment variables for CDSE (CDSE_CLIENT_ID/SECRET). Check .env file.")
    raise ValueError("Missing CDSE API keys in .env file.")

# Set Sentinel Hub configuration for CDSE
_GLOBAL_CDSE_CONFIG = SHConfig()
_GLOBAL_CDSE_CONFIG.sh_client_id = CDSE_CLIENT_ID
_GLOBAL_CDSE_CONFIG.sh_client_secret = CDSE_CLIENT_SECRET
_GLOBAL_CDSE_CONFIG.sh_base_url = "https://sh.dataspace.copernicus.eu"
_GLOBAL_CDSE_CONFIG.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_GLOBAL_CDSE_CONFIG.sh_auth_base_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect"

print(f"Using Python executable: {sys.executable}")
print(f"Python sys.path: {sys.path}")
logging.info(f"Global SHConfig Base URL: {_GLOBAL_CDSE_CONFIG.sh_base_url}")

catalog = SentinelHubCatalog(config=_GLOBAL_CDSE_CONFIG)

DataCollection.define(
    "SENTINEL2_L1C_CDSE_CUSTOM",
    api_id="sentinel-2-l1c",
    service_url="https://sh.dataspace.copernicus.eu"
)
S2_CDSE_CUSTOM = DataCollection.SENTINEL2_L1C_CDSE_CUSTOM

# ----- NOVÁ FUNKCE: To create a PDF report -----
def _create_ndvi_pdf(ndvi_array: np.ndarray, image_date: str, output_folder: str, timestamp: str, time_series_plot_path: str | None = None,
                     map_bbox: tuple = None) -> str: # NOVÝ PARAMETR: bbox mapy
    """
    Creates a PDF with NDVI image visualization and date, optionally with a time-series plot.
    map_bbox: Bounding box of the map (min_lon, min_lat, max_lon, max_lat) for coordinates.
    """
    pdf = FPDF(unit="mm", format="A4") # No 'encoding' parameter here, relies on _sanitize_text_for_pdf
    pdf.add_page()
    pdf.set_font("Arial", size=12) # Set Arial as default font for certainty

    def _sanitize_text_for_pdf(text: str) -> str:
        normalized_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
        return normalized_text
        
    pdf.set_xy(10, 10)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _sanitize_text_for_pdf("NDVI Analysis"), 0, 1, "C")
    pdf.ln(5)

    if time_series_plot_path:
        ts_plot_width = 190 # mm
        
        ts_fig_width_inches = 10 
        ts_fig_height_inches = 5 
        ts_aspect_ratio = ts_fig_height_inches / ts_fig_width_inches
        ts_plot_height = ts_plot_width * ts_aspect_ratio

        pdf.image(time_series_plot_path, x=10, y=30, w=ts_plot_width, h=ts_plot_height)
        pdf.ln(ts_plot_height + 5) 
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 10, _sanitize_text_for_pdf("NDVI Evolution Over Time"), 0, 1, "C")
        pdf.ln(5)
    else:
        pdf.ln(20)


    # --- NEW PAGE FOR NDVI MAP ---
    pdf.add_page()

    # 2. Image: NDVI map
    # INCREASED figsize for the map to make room for coordinates and scale bar
    fig_map, ax_map = plt.subplots(figsize=(8.27 * 1.5, 11.69 * 1.5), dpi=100) # Increased size
    # ax_map.set_axis_off() # REMOVED: Keep axes ON for coordinates and labels

    norm_map = plt.Normalize(vmin=np.min(ndvi_array), vmax=np.max(ndvi_array))
    cmap_map = plt.cm.RdYlGn

    im_map = ax_map.imshow(ndvi_array, cmap=cmap_map, norm=norm_map)

    # Add colorbar to the map
    cbar_map = fig_map.colorbar(im_map, ax=ax_map, orientation='horizontal', shrink=0.6, pad=0.08)
    cbar_map.set_label('NDVI Value', rotation=0, labelpad=5) 
    
    current_min_map = np.min(ndvi_array)
    current_max_map = np.max(ndvi_array)
    ticks_to_show_map = []
    ticks_to_show_map.append(current_min_map)
    ticks_to_show_map.append(current_max_map)

    if current_min_map < 0.0 and current_max_map > 0.0:
        if not (abs(current_min_map) < 0.01 and current_max_map < 0.01):
            ticks_to_show_map.append(0.0)
    
    if current_min_map < -0.1 and -0.5 >= current_min_map and -0.5 <= current_max_map:
        ticks_to_show_map.append(-0.5)
    if current_max_map > 0.1 and 0.5 >= current_min_map and 0.5 <= current_max_map:
        ticks_to_show_map.append(0.5)

    final_ticks_map = sorted(list(set([round(t, 2) for t in ticks_to_show_map])))
    
    cbar_map.set_ticks(final_ticks_map)
    cbar_map.set_ticklabels([f'{t:.2f}' for t in final_ticks_map])


    # --- NEW: Coordinates on map edges ---
    if map_bbox: # Only if map_bbox is provided
        min_lon, min_lat, max_lon, max_lat = map_bbox
        
        # Calculate coordinate ticks based on bbox (using 5 ticks for each axis)
        lon_ticks_val = np.linspace(min_lon, max_lon, num=5)
        lat_ticks_val = np.linspace(min_lat, max_lat, num=5)

        # Set pixel positions for ticks
        ax_map.set_xticks(np.linspace(0, ndvi_array.shape[1]-1, num=5))
        ax_map.set_yticks(np.linspace(0, ndvi_array.shape[0]-1, num=5))

        # Set labels for ticks (formatted coordinates)
        # Use reversed for lat_ticks_val because imshow Y-axis is typically inverted
        ax_map.set_xticklabels([f'{lon:.2f}°E' for lon in lon_ticks_val], rotation=45, ha='right')
        ax_map.set_yticklabels([f'{lat:.2f}°N' for lat in reversed(lat_ticks_val)]) 
        
        ax_map.set_xlabel('Longitude', fontsize=10)
        ax_map.set_ylabel('Latitude', fontsize=10)

        # Adjust tick label sizes
        ax_map.tick_params(axis='x', labelsize=8)
        ax_map.tick_params(axis='y', labelsize=8)
        
        # Adjust subplot margins to make space for labels
        plt.subplots_adjust(left=0.15, right=0.9, top=0.9, bottom=0.15)


    buf_map = io.BytesIO()
    plt.tight_layout() # This ensures all elements (map, colorbar, labels) fit within the figure
    plt.savefig(buf_map, format='png', bbox_inches='tight', pad_inches=0)
    buf_map.seek(0)
    plt.close(fig_map)


    # --- Save map to temporary PNG file ---
    temp_map_png_path = os.path.join(output_folder, f"temp_ndvi_map_{timestamp}.png")
    with open(temp_map_png_path, 'wb') as f:
        f.write(buf_map.getvalue())
    buf_map.close()


    # Place map in PDF
    actual_png_width_px, actual_png_height_px = 0, 0
    try:
        with Image.open(temp_map_png_path) as img:
            actual_png_width_px, actual_png_height_px = img.size
    except Exception as e:
        logging.error(f"ERROR: Could not load PNG to determine dimensions: {e}. Using estimate.")
        # Fallback to estimated dimensions if Pillow fails
        actual_png_width_px = 100 * (8.27 * 1.5) # DPI * Inches (from figsize)
        actual_png_height_px = 100 * (11.69 * 1.5) # Based on modified figsize

    logging.info(f"PNG Map Image Actual Dimensions: {actual_png_width_px}px x {actual_png_height_px}px") 
    
    map_aspect_ratio_actual_png = actual_png_height_px / actual_png_width_px

    pdf_map_width = 190 # Target width of map in PDF (mm)
    pdf_map_height = pdf_map_width * map_aspect_ratio_actual_png 

    logging.info(f"PDF Map Image Target Dimensions: {pdf_map_width}mm x {pdf_map_height}mm")

    map_start_y_mm = 20 
    
    pdf.image(temp_map_png_path, x=(210 - pdf_map_width) / 2, y=map_start_y_mm, w=pdf_map_width, h=pdf_map_height, type='png')

    pdf.rect((210 - pdf_map_width) / 2, map_start_y_mm, pdf_map_width, pdf_map_height)

    pdf.set_y(map_start_y_mm + pdf_map_height) 
    
    pdf.ln(5)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, _sanitize_text_for_pdf(f"NDVI map from: {image_date}"), 0, 1, "C")
    pdf.ln(5)


    # Save PDF
    pdf_path = os.path.join(output_folder, f"ndvi_report_{timestamp}.pdf")
    pdf.output(pdf_path)

    os.remove(temp_map_png_path)
    if time_series_plot_path:
        os.remove(time_series_plot_path)

    return pdf_path

def calculate_polygon_area_sqkm(polygon_coords: list) -> float:
    """
    Calculates the approximate area of a polygon in km^2.
    Uses a simple approximation for small polygons on Earth (Earth's radius).
    """
    if not polygon_coords or len(polygon_coords) < 3:
        return 0.0
    try:
        polygon_shape = Polygon(polygon_coords)
    except Exception as e:
        logging.error(f"Error creating Shapely polygon: {e}")
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
        logging.error(f"Error calculating area of approximated polygon: {e}")
        return 0.0

def process_ndvi(
    polygon_coords: list,
    start_date_str: str,
    end_date_str: str,
    frequency: str,
    max_images_to_consider: int = 30,
    max_polygon_area_sqkm: float = 25.0
) -> tuple[str, str, str] | None:
    """
    Processes NDVI for a given polygon and time period, downloading from CDSE via Sentinel Hub API.
    Selects the image with the least cloud cover and generates a time series.
    """
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
            if (!samples.dataMask) {
                return {
                    B04: [NaN],
                    B08: [NaN],
                    dataMask: [0]
                };
            }
            return {
                B04: [samples.B04],
                B08: [samples.B08],
                dataMask: [samples.dataMask]
            };
        }
    """

    FIXED_MAX_CLOUD_COVERAGE = 0.8 # Allow up to 80% cloudiness for time series.

    logging.info(f"Starting NDVI processing for polygon: {polygon_coords}, from {start_date_str} to {end_date_str} frequency: {frequency} (CDSE mode with cloudiness {FIXED_MAX_CLOUD_COVERAGE*100}%)")

    current_catalog = catalog
    current_config = _GLOBAL_CDSE_CONFIG

    logging.info(f"process_ndvi: SHConfig Base URL used: {current_config.sh_base_url}")
    logging.info(f"process_ndvi: SHConfig Token URL used: {current_config.sh_token_url}")


    area = calculate_polygon_area_sqkm(polygon_coords)
    if area > max_polygon_area_sqkm:
        raise ValueError(f"Polygon area ({area:.2f} km²) exceeds maximum allowed size ({max_polygon_area_sqkm} km²).")

    start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    MAX_DURATION_DAYS = 365 # Max 1 year
    MAX_TS_IMAGES = 50 # Max 50 images in time series
    
    if (end_date_dt - start_date_dt).days > MAX_DURATION_DAYS:
        raise ValueError(f"Maximum time series length is limited to {MAX_DURATION_DAYS} days (1 year).")

    time_series_intervals = []
    if frequency == 'weekly':
        current_interval_start = start_date_dt
        while current_interval_start <= end_date_dt:
            current_interval_end = current_interval_start + timedelta(days=6) # Weekly interval
            if current_interval_end > end_date_dt:
                current_interval_end = end_date_dt
            time_series_intervals.append((current_interval_start.strftime('%Y-%m-%d'), current_interval_end.strftime('%Y-%m-%d')))
            current_interval_start += timedelta(days=7) # Move to next week
    elif frequency == 'monthly':
        current_interval_start = start_date_dt
        while current_interval_start <= end_date_dt:
            next_month = current_interval_start.replace(day=28) + timedelta(days=4)
            current_interval_end = next_month - timedelta(days=next_month.day)
            
            if current_interval_end > end_date_dt:
                current_interval_end = end_date_dt
            
            time_series_intervals.append((current_interval_start.strftime('%Y-%m-%d'), current_interval_end.strftime('%Y-%m-%d')))
            current_interval_start = current_interval_end + timedelta(days=1)
    else:
        raise ValueError("Unsupported frequency. Use 'weekly' or 'monthly'.")

    if len(time_series_intervals) > MAX_TS_IMAGES:
        raise ValueError(f"Number of images in time series ({len(time_series_intervals)}) exceeds limit {MAX_TS_IMAGES}. Shorten period or change frequency.")


    min_lon = min(p[0] for p in polygon_coords)
    max_lon = max(p[0] for p in polygon_coords)
    min_lat = min(p[1] for p in polygon_coords)
    max_lat = max(p[1] for p in polygon_coords)
    bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
    size = bbox_to_dimensions(bbox, resolution=10)

    output_folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    ndvi_time_series_data = []
    best_image_for_map = None
    best_cloud_cover_for_map = 101.0

    for ts_start_str, ts_end_str in time_series_intervals:
        logging.info(f"Searching for images for interval: from {ts_start_str} to {ts_end_str}")
        
        search_iterator = current_catalog.search(
            S2_CDSE_CUSTOM,
            bbox=bbox,
            time=(ts_start_str, ts_end_str),
            filter=f"eo:cloud_cover <= {FIXED_MAX_CLOUD_COVERAGE * 100}",
            limit=max_images_to_consider
        )

        results = list(search_iterator)
        if not results:
            logging.warning(f"No images found for criteria in CDSE catalog for interval {ts_start_str} - {ts_end_str}. Skipping.")
            ndvi_time_series_data.append((ts_start_str, np.nan))
            continue

        sorted_results = sorted(results, key=lambda x: (x['properties']['eo:cloud_cover'], x['properties']['datetime']), reverse=False)
        best_image_metadata_ts = sorted_results[0]
        logging.info(f"  Image selected for TS: {best_image_metadata_ts['id']} (cloudiness: {best_image_metadata_ts['properties']['eo:cloud_cover']:.2f}%)")

        if best_image_metadata_ts['properties']['eo:cloud_cover'] < best_cloud_cover_for_map:
            best_cloud_cover_for_map = best_image_metadata_ts['properties']['eo:cloud_cover']
            best_image_for_map = best_image_metadata_ts
        
        selected_time_range_ts = (best_image_metadata_ts['properties']['datetime'][:10], best_image_metadata_ts['properties']['datetime'][:10])

        request_ts = SentinelHubRequest(
            evalscript=evalscript_bands,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=S2_CDSE_CUSTOM,
                    time_interval=selected_time_range_ts,
                )
            ],
            responses=[
                SentinelHubRequest.output_response("B04", MimeType.TIFF),
                MimeType.TIFF # User did not provide full code
            ],
            bbox=bbox,
            size=size,
            config=current_config
        )

        try:
            data_ts = request_ts.get_data()
        except Exception as e:
            logging.error(f"Error downloading data for {ts_start_str}: {e}. Skipping.")
            ndvi_time_series_data.append((ts_start_str, np.nan))
            continue
        
        if not data_ts:
            logging.warning(f"No image data downloaded for TS image {ts_start_str}. Skipping.")
            ndvi_time_series_data.append((ts_start_str, np.nan))
            continue

        single_image_data_ts = data_ts[0]
        red_band_data_ts = single_image_data_ts['B04.tif']
        nir_band_data_ts = single_image_data_ts['B08.tif']

        if red_band_data_ts is None or nir_band_data_ts is None:
            logging.warning(f"Downloaded TS image {ts_start_str} contains empty data. Skipping.")
            ndvi_time_series_data.append((ts_start_str, np.nan))
            continue
        
        ndvi_ts = (nir_band_data_ts.astype(float) - red_band_data_ts.astype(float)) / \
                  (nir_band_data_ts.astype(float) + red_band_data_ts.astype(float))
        ndvi_ts = np.clip(ndvi_ts, -1.0, 1.0)
        ndvi_ts = np.nan_to_num(ndvi_ts, nan=0.0)

        data_mask_ts = single_image_data_ts['dataMask.tif']
        valid_ndvi_pixels = ndvi_ts[data_mask_ts == 1]
        
        if valid_ndvi_pixels.size > 0:
            mean_ndvi = np.mean(valid_ndvi_pixels)
        else:
            mean_ndvi = np.nan
            logging.warning(f"No valid pixels in mask for {ts_start_str}. Average NDVI is NaN.")

        ndvi_time_series_data.append((best_image_metadata_ts['properties']['datetime'][:10], mean_ndvi))
    
    logging.info(f"Number of data points for time series: {len(ndvi_time_series_data)}")
    logging.info(f"Time series data (first 5 and last 5): {ndvi_time_series_data[:5]} ... {ndvi_time_series_data[-5:]}")

    ts_dates = [pd.to_datetime(d[0]) for d in ndvi_time_series_data]
    ts_values = [d[1] for d in ndvi_time_series_data]

    fig_ts, ax_ts = plt.subplots(figsize=(10, 5), dpi=100)
    ax_ts.plot(ts_dates, ts_values, marker='o', linestyle='-', color='green')
    ax_ts.set_title('NDVI Evolution Over Time')
    ax_ts.set_xlabel('Date')
    ax_ts.set_ylabel('Average NDVI')
    ax_ts.grid(True)
    fig_ts.autofmt_xdate()

    temp_ts_plot_path = os.path.join(output_folder_path, f"temp_ndvi_timeseries_{timestamp}.png")
    plt.tight_layout()
    plt.savefig(temp_ts_plot_path, format='png', bbox_inches='tight', pad_inches=0)
    plt.close(fig_ts)

    if not best_image_for_map:
        logging.warning("No suitable image found for NDVI map within the time series.")
        return None

    selected_time_range_map = (best_image_for_map['properties']['datetime'][:10], best_image_for_map['properties']['datetime'][:10])

    request_map = SentinelHubRequest(
        evalscript=evalscript_bands,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=S2_CDSE_CUSTOM,
                time_interval=selected_time_range_map,
            )
        ],
        responses=[
            SentinelHubRequest.output_response("B04", MimeType.TIFF),
            SentinelHubRequest.output_response("B08", MimeType.TIFF),
            MimeType.TIFF # User did not provide full code
        ],
        bbox=bbox,
        size=size,
        config=current_config
    )

    try:
        data_map = request_map.get_data()
    except Exception as e:
        logging.error(f"Error downloading data for main map: {e}.")
        return None
    
    if not data_map:
        logging.warning("No image data downloaded for main NDVI map.")
        return None
    
    single_image_data_map = data_map[0]
    red_band_data_map = single_image_data_map['B04.tif']
    nir_band_data_map = single_image_data_map['B08.tif']

    if red_band_data_map is None or nir_band_data_map is None:
        logging.warning(f"Main map image contains empty data.")
        return None

    ndvi_map = (nir_band_data_map.astype(float) - red_band_data_map.astype(float)) / \
               (nir_band_data_map.astype(float) + red_band_data_map.astype(float))
    ndvi_map = np.clip(ndvi_map, -1.0, 1.0)
    ndvi_map = np.nan_to_num(ndvi_map, nan=0.0)

    out_path = os.path.join(output_folder_path, f"ndvi_result_{timestamp}.tif")
    
    profile_base_map = {
        'driver': 'GTiff',
        'height': ndvi_map.shape[0],
        'width': ndvi_map.shape[1],
        'count': 1,
        'dtype': 'float32',
        'crs': CRS.WGS84.ogc_string(),
        'transform': from_bounds(min_lon, min_lat, max_lon, max_lat, ndvi_map.shape[1], ndvi_map.shape[0])
    }
    profile_ndvi_map = profile_base_map.copy()
    profile_ndvi_map.update({'nodata': 0.0})
    with rasterio.open(out_path, 'w', **profile_ndvi_map) as dst:
        dst.write(ndvi_map.astype('float32'), 1)
    logging.info(f"NDVI GeoTIFF file successfully saved to {out_path}")

    pdf_path = _create_ndvi_pdf(ndvi_map, best_image_for_map['properties']['datetime'][:10], output_folder_path, timestamp, time_series_plot_path=temp_ts_plot_path)
    logging.info(f"NDVI PDF report successfully saved to {pdf_path}")

    return out_path, best_image_for_map['properties']['datetime'][:10], pdf_path


if __name__ == '__main__':
    test_polygon = [
        [18.435, 49.792],
        [18.435, 49.801],
        [18.448, 49.801],
        [18.448, 49.792],
        [18.435, 49.792]
    ]
    print("Running NDVI time series test (CDSE mode)...")
    try:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        result_tuple = process_ndvi(test_polygon, start_date, end_date, 'monthly', max_images_to_consider=30, max_polygon_area_sqkm=25)
        
        if result_tuple:
            out_path, image_date, pdf_path = result_tuple
            print(f"NDVI GeoTIFF successfully created: {out_path}")
            print(f"NDVI PDF report successfully created: {pdf_path}")
        else:
            print("NDVI time series processing not completed.")
    except ValueError as e:
        print(f"Error processing time series: {e}")
    except Exception as e:
        logging.exception("An unexpected error occurred during CDSE time series processing.")
        print(f"An unexpected error occurred during CDSE time series processing: {e}")