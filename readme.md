# NDVI Field Analyzer 🛰️

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20App-brightgreen)](https://ndvi-field-analyzer.onrender.com) 
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## 📌 What it is
A full-stack geospatial web application that allows users to draw a polygon on an interactive map and generate a time-series analysis of vegetation health (NDVI) using **Sentinel-2 L2A** satellite imagery. 

## 🛠️ Tech Stack
* **Backend:** Python 3.11, Flask, SentinelHub API (Copernicus Data Space Ecosystem)
* **Geospatial Processing:** Rasterio, Shapely, NumPy, Matplotlib
* **Frontend:** Vanilla JavaScript, HTML5/CSS3, Leaflet.js, Chart.js

## 🚀 Key Technical Features
* **Smart Cloud Filtering:** Instead of rejecting whole satellite scenes, the algorithm uses the Scene Classification Layer (SCL) to calculate cloud coverage *strictly within the user-defined polygon*. 
* **Automated Data Pipeline:** Fetches multi-spectral bands (B04, B08, SCL, dataMask) from the Copernicus Data Space Ecosystem via custom evalscripts.
* **On-the-Fly Processing:** Calculates NDVI arrays, applies data masks to filter out invalid/cloudy pixels, and generates transparent, georeferenced PNG overlays.
* **Interactive UI:** Features map drawing tools, a time-series chart synchronized with map layers, opacity controls, and a custom geolocation tool.
* **Portable Reports:** Users can export their analysis (including base64-encoded graphs and map layers) into a standalone, downloadable HTML report.

## ⚙️ Quick Start (Local Development)

### Prerequisites
* Python 3.11+
* [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) credentials.
  
### Installation & Setup

1.  **Clone the repo**
    ```sh
    git clone [https://github.com/tomas-michalik11/ndvi-web-app.git](https://github.com/tomas-michalik11/ndvi-web-app.git)
    cd ndvi-web-app
    ```
2.  **Create a virtual environment**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
3.  **Install Python packages**
    ```sh
    pip install -r requirements.txt
    ```
4.  **Set up environment variables**
    * Create a file named `.env` inside the `backend` folder.
    * Add your Copernicus API credentials to it:
        ```
        CDSE_CLIENT_ID='your-client-id-goes-here'
        CDSE_CLIENT_SECRET='your-client-secret-goes-here'
        ```
5.  **Run the application**
    * Navigate to the backend directory and start the Flask server:
        ```sh
        cd backend
        flask run
        ```
    * Open your browser and go to `http://127.0.0.1:5000`

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
