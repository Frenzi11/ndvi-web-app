# NDVI Field Analyzer 🛰️

A full-stack web application for analyzing the health of agricultural fields and vegetation over time using Sentinel-2 satellite imagery. This tool provides an interactive map-based interface to calculate and visualize the Normalized Difference Vegetation Index (NDVI).

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20App-brightgreen)](https://ndvi-field-analyzer.onrender.com) 
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

---

## About The Project

This project was built to make agricultural remote sensing accessible to everyone. Traditional GIS software can be complex and expensive. The NDVI Field Analyzer provides a simple, web-based solution for farmers, agronomists, researchers, and students to monitor vegetation health without needing specialized tools.

The application allows users to draw a polygon over any area of interest on a world map, select a date range, and receive a detailed analysis including an interactive time-series graph and browsable NDVI maps for each available satellite image in that period.

---

## Key Features

* **Interactive Map Interface:** Uses Leaflet.js for a smooth map experience.
* **Polygon Drawing Tool:** Users can define their exact area of interest.
* **Time-Series Analysis:** Generates an interactive chart showing the average NDVI value over the selected period.
* **Visual Map Overlays:** Displays generated NDVI maps directly on the satellite imagery.
* **Image Slider:** Easily switch between NDVI maps from different dates.
* **Opacity Control:** Adjust the transparency of the NDVI layer to compare it with the underlying satellite map.
* **Find My Location:** A convenient button to quickly navigate to the user's current location.
* **Responsive Design:** Fully functional on both desktop and mobile devices.
* **HTML Report Export:** Users can export the complete analysis (graph and all maps) into a single, self-contained, and printable HTML file.

---

## Tech Stack

This project is built with a modern, full-stack approach:

* **Backend:**
    * **Python 3.11**
    * **Flask:** A lightweight web framework for the backend server and API.
    * **Gunicorn:** A production-ready WSGI server.
    * **SentinelHub API:** The `sentinelhub-py` library to search and download satellite data from the Copernicus Data Space Ecosystem.
    * **NumPy & Rasterio:** For efficient processing of satellite raster data and NDVI calculation.
    * **Matplotlib:** For generating the time-series graph and map images.
    * **Shapely:** For geospatial calculations like polygon area.

* **Frontend:**
    * **HTML5, CSS3, Vanilla JavaScript (ES6+)**
    * **Leaflet.js:** An open-source library for interactive maps.
    * **Leaflet.Draw:** A plugin for drawing polygons.
    * **Chart.js:** For creating beautiful and interactive charts.

* **Deployment:**
    * **Render:** A cloud platform for deploying the full-stack application.
    * **Git & GitHub:** For version control and continuous deployment.

---

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

* Python 3.9+
* pip (Python package installer)
* A free account on the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) to get API credentials.

### Installation & Setup

1.  **Clone the repo**
    ```sh
    git clone [https://github.com/Frenzi11/ndvi-web-app.git](https://github.com/Frenzi11/ndvi-web-app.git)
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