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

# Matplotlib is still needed for generating PNG images
import matplotlib
matplotlib.use('Agg') # Setting the non-interactive backend is still important for the server
import matplotlib.pyplot as plt

# From rasterio, we need transform for georeferencing images
from rasterio.transform import from_bounds

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Loading .env variables
load_dotenv()
CDSE_CLIENT_ID = os.getenv("CDSE_CLIENT_ID")
CDSE_CLIENT_SECRET = os.getenv("CDSE_CLIENT_SECRET")

if not all([CDSE_CLIENT_ID, CDSE_CLIENT_SECRET]):
    logging.error("Missing environment variables for CDSE (CDSE_CLIENT_ID/SECRET). Check the .env file.")
    raise ValueError("Missing CDSE API keys in the .env file.")

# Sentinel Hub configuration for Copernicus Data Space Ecosystem (CDSE)
_GLOBAL_CDSE_CONFIG = SHConfig()
_GLOBAL_CDSE_CONFIG.sh_client_id = CDSE_CLIENT_ID
_GLOBAL_CDSE_CONFIG.sh_client_secret = CDSE_CLIENT_SECRET
_GLOBAL_CDSE_CONFIG.sh_base_url = "https://sh.dataspace.copernicus.eu"
_GLOBAL_CDSE_CONFIG.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_GLOBAL_CDSE_CONFIG.sh_auth_base_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect"

logging.info(f"Global SHConfig Base URL: {_GLOBAL_CDSE_CONFIG.sh_base_url}")

# Initialize catalog for searching images
catalog = SentinelHubCatalog(config=_GLOBAL_CDSE_CONFIG)

# Define a custom data collection for CDSE
DataCollection.define(
    "SENTINEL2_L1C_CDSE_CUSTOM",
    api_id="sentinel-2-l1c",
    service_url="https://sh.dataspace.copernicus.eu"
)
S2_CDSE_CUSTOM = DataCollection.SENTINEL2_L1C_CDSE_CUSTOM

# ----- FUNCTION FOR AREA CALCULATION (remains unchanged) -----
def calculate_polygon_area_sqkm(polygon_coords: list) -> float:
    """
    Calculates the approximate area of a polygon in km^2.
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

# ----- MAIN PROCESSING FUNCTION (completely revamped) -----
def process_ndvi(
    polygon_coords: list,
    start_date_str: str,
    end_date_str: str,
    frequency: str,
    max_images_to_consider: int = 30,
    max_polygon_area_sqkm: float = 25.0
) -> dict | None:
    """
    Processes NDVI for a given polygon and time period. For each time interval, it finds the best
    image, generates a PNG image of the NDVI map from it, and returns structured data for the frontend.
    """
    # Evalscript for downloading the necessary bands (B04 - red, B08 - near-infrared)
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
            // If the pixel has no data, we return NaN
            if (!samples.dataMask) {
                return { B04: [NaN], B08: [NaN], dataMask: [0] };
            }
            return { B04: [samples.B04], B08: [samples.B08], dataMask: [samples.dataMask] };
        }
    """

    FIXED_MAX_CLOUD_COVERAGE = 0.8 # Allow up to 80% cloud coverage for image search

    logging.info(f"Starting NDVI processing for polygon, from {start_date_str} to {end_date_str}, frequency: {frequency}")

    # Check polygon size
    area = calculate_polygon_area_sqkm(polygon_coords)
    if area > max_polygon_area_sqkm:
        raise ValueError(f"Polygon area ({area:.2f} km²) exceeds the maximum allowed size ({max_polygon_area_sqkm} km²).")

    # Date processing and validation
    start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    MAX_DURATION_DAYS = 365 # Max 1 year
    MAX_TS_IMAGES = 50 # Max 50 images in the time series
    
    if (end_date_dt - start_date_dt).days > MAX_DURATION_DAYS:
        raise ValueError(f"The maximum duration of the time series is limited to {MAX_DURATION_DAYS} days (1 year).")

    # Create time intervals for image searching
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
        raise ValueError("Unsupported frequency. Use 'weekly' or 'monthly'.")

    if len(time_series_intervals) > MAX_TS_IMAGES:
        raise ValueError(f"The number of images in the time series ({len(time_series_intervals)}) exceeds the limit of {MAX_TS_IMAGES}. Shorten the period or change the frequency.")

    # Geometry for queries
    min_lon, max_lon = min(p[0] for p in polygon_coords), max(p[0] for p in polygon_coords)
    min_lat, max_lat = min(p[1] for p in polygon_coords), max(p[1] for p in polygon_coords)
    bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
    size = bbox_to_dimensions(bbox, resolution=10) # 10m resolution for Sentinel-2

    # Path to the output folder
    output_folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Prepare data structures for results
    time_series_for_graph = []
    image_layers_for_map = []

    # Main loop - iterating through time intervals
    for ts_start_str, ts_end_str in time_series_intervals:
        logging.info(f"Searching for images for the interval: {ts_start_str} to {ts_end_str}")
        
        # Searching in the catalog
        search_iterator = catalog.search(
            S2_CDSE_CUSTOM,
            bbox=bbox,
            time=(ts_start_str, ts_end_str),
            filter=f"eo:cloud_cover <= {FIXED_MAX_CLOUD_COVERAGE * 100}",
            limit=max_images_to_consider
        )
        results = list(search_iterator)

        if not results:
            logging.warning(f"No images found for the interval {ts_start_str} - {ts_end_str}. Skipping.")
            continue

        # Sort results by cloud cover (best first)
        best_image_metadata = sorted(results, key=lambda x: x['properties']['eo:cloud_cover'])[0]
        image_date = best_image_metadata['properties']['datetime'][:10]
        logging.info(f"  Selected image for interval: {best_image_metadata['id']} from date {image_date} (cloud cover: {best_image_metadata['properties']['eo:cloud_cover']:.2f}%)")

        # Downloading data for the selected image
        request_data = SentinelHubRequest(
            evalscript=evalscript_bands,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=S2_CDSE_CUSTOM,
                    time_interval=(image_date, image_date), # We download only the specific day
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
            logging.error(f"Error downloading data for {image_date}: {e}. Skipping.")
            continue
        
        # NDVI calculation
        red_band = downloaded_data['B04.tif']
        nir_band = downloaded_data['B08.tif']
        
        with np.errstate(divide='ignore', invalid='ignore'):
            ndvi_array = (nir_band.astype(float) - red_band.astype(float)) / (nir_band.astype(float) + red_band.astype(float))
        
        # Handle values
        ndvi_array = np.clip(ndvi_array, -1.0, 1.0)
        ndvi_array[np.isnan(ndvi_array)] = -999 # Specific value for "no data"

        # Calculate average NDVI for the graph
        data_mask = downloaded_data['dataMask.tif']
        valid_ndvi_pixels = ndvi_array[data_mask == 1]
        
        if valid_ndvi_pixels.size > 0:
            mean_ndvi = np.mean(valid_ndvi_pixels)
        else:
            logging.warning(f"No valid pixels in the mask for {image_date}. Average NDVI will be NaN.")
            mean_ndvi = np.nan
        
        # Store data for the graph
        time_series_for_graph.append({'date': image_date, 'value': round(mean_ndvi, 4) if not np.isnan(mean_ndvi) else None})
        
        # --- NEW PART: Generate and save PNG for each image ---
        if not np.isnan(mean_ndvi):
            fig, ax = plt.subplots(figsize=(6, 6), dpi=150) # Reasonable size and DPI for the web
            ax.set_axis_off()
            
            # USE A CONSISTENT COLOR SCALE FOR ALL IMAGES! This is crucial for comparison.
            cmap = plt.cm.RdYlGn
            norm = plt.Normalize(vmin=-0.2, vmax=1.0) # Fixed scale from stress to healthy vegetation
            
            # Display NDVI array, but make "no data" pixels transparent
            masked_ndvi = np.ma.masked_where(ndvi_array == -999, ndvi_array)
            ax.imshow(masked_ndvi, cmap=cmap, norm=norm)
            
            # Save to file
            png_filename = f"ndvi_map_{image_date}_{timestamp}.png"
            png_path = os.path.join(output_folder_path, png_filename)
            plt.savefig(png_path, format='png', bbox_inches='tight', pad_inches=0, transparent=True)
            plt.close(fig) # Free up memory
            
            # Add layer information for the frontend
            image_layers_for_map.append({
                "date": image_date,
                "url": f"/output/{png_filename}",
                "bounds": [[bbox.min_y, bbox.min_x], [bbox.max_y, bbox.max_x]],
                "mean_ndvi": round(mean_ndvi, 4)
            })

    # If we found nothing, return None
    if not image_layers_for_map:
        logging.warning("Processing finished, but no map layers were generated.")
        return None

    # The return value is now a dictionary with data for the frontend
    return {
        "graphData": sorted(time_series_for_graph, key=lambda x: x['date']),
        "imageLayers": sorted(image_layers_for_map, key=lambda x: x['date'])
    }


# ----- TEST BLOCK (if you run the file directly) -----
if __name__ == '__main__':
    # Test polygon in Havířov
    test_polygon = [
        [18.435, 49.792],
        [18.435, 49.801],
        [18.448, 49.801],
        [18.448, 49.792],
        [18.435, 49.792]
    ]
    print("Starting a test run of `process_ndvi`...")
    try:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
        
        # Call the new function
        result_data = process_ndvi(test_polygon, start_date, end_date, 'monthly')
        
        if result_data:
            print("\n✅ Processing was successful!")
            print(f"Number of points in the graph: {len(result_data['graphData'])}")
            print(f"Number of generated map layers: {len(result_data['imageLayers'])}")
            print("\nSample data for the first map layer:")
            print(result_data['imageLayers'][0] if result_data['imageLayers'] else "No data")
        else:
            print("\n❌ Processing failed or returned no data.")
            
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        logging.exception("An unexpected error occurred during the test run.")
        print(f"Unexpected error: {e}")