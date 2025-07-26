document.addEventListener('DOMContentLoaded', () => {
    // === Map and layers initialization ===
    const map = L.map('map').setView([49.795, 18.42], 12);

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    const esriSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; ...'
    });
    
    osmLayer.addTo(map);
    const baseMaps = { "OpenStreetMap": osmLayer, "Satellite (Esri)": esriSatLayer };
    L.control.layers(baseMaps).addTo(map);
    L.control.scale().addTo(map);

    // === Drawing on the map ===
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    const drawControl = new L.Control.Draw({
        draw: { polyline: false, marker: false, circlemarker: false, circle: false, rectangle: false, 
            polygon: { allowIntersection: false, showArea: true, shapeOptions: { color: '#3388ff' } }
        }
    });
    map.addControl(drawControl);
    let currentPolygon = null;
    map.on(L.Draw.Event.CREATED, (event) => {
        if (currentPolygon) drawnItems.removeLayer(currentPolygon);
        drawnItems.addLayer(event.layer);
        currentPolygon = event.layer;
    });

    // === Variables and HTML elements ===
    let ndviChart = null;
    let activeMapLayers = [];
    const processBtn = document.getElementById('processNdviBtn');
    const statusMessage = document.getElementById('statusMessage');
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const frequencySelect = document.getElementById('frequency');
    const chartContainer = document.getElementById('chartContainer');
    const mapControlsContainer = document.getElementById('mapControls');
    const slider = document.getElementById('layerSlider');
    const dateLabel = document.getElementById('sliderDateLabel');
    const legendContainer = document.getElementById('legendContainer');
    const progressBarContainer = document.getElementById('progress-bar-container'); 
    const downloadLinkContainer = document.getElementById('downloadLinkContainer'); // NEW: Get the container for the export button

    function updateStatus(message, type = '') {
        statusMessage.textContent = message;
        statusMessage.className = type ? `${type}` : '';
    }

    // Setting default dates and limits
    const today = new Date();
    const oneYearAgo = new Date(today);
    oneYearAgo.setFullYear(today.getFullYear() - 1);
    startDateInput.value = oneYearAgo.toISOString().split('T')[0];
    endDateInput.value = today.toISOString().split('T')[0];
    
    startDateInput.min = '2015-06-23';
    startDateInput.max = today.toISOString().split('T')[0];
    endDateInput.max = today.toISOString().split('T')[0];

    // --- 'Find My Location' Control ---
    const LocationControl = L.Control.extend({
        options: { position: 'topleft' },
        onAdd: function (map) {
            const container = L.DomUtil.create('div', 'leaflet-control');
            const button = L.DomUtil.create('a', 'location-control-button', container);
            button.innerHTML = `<svg>...</svg>`; // SVG content omitted for brevity
            button.href = '#';
            L.DomEvent.on(button, 'click', L.DomEvent.stop);
            L.DomEvent.on(button, 'click', this._findLocation, this);
            return container;
        },
        _findLocation: function () {
            const onLocationFound = (e) => {
                const radius = e.accuracy;
                const marker = L.marker(e.latlng).addTo(map);
                const circle = L.circle(e.latlng, radius).addTo(map);
                marker.bindPopup(`You are here (approx. ${radius.toFixed(0)}m accuracy)`).openPopup();
                map.flyTo(e.latlng, 14);
                setTimeout(() => {
                    map.removeLayer(marker);
                    map.removeLayer(circle);
                }, 3000);
            }
            const onLocationError = (err) => {
                let message = 'Could not find your location.';
                switch(err.code) {
                    case 1: message = 'Permission to access location was denied.'; break;
                    case 2: message = 'Location could not be determined.'; break;
                    case 3: message = 'Location request timed out.'; break;
                }
                updateStatus(message, 'error');
            }
            map.locate({setView: false, maxZoom: 16})
               .on('locationfound', onLocationFound)
               .on('locationerror', onLocationError);
        }
    });
    new LocationControl().addTo(map);

    // === KEY FUNCTION: Listener for the "Process NDVI" button ===
    processBtn.addEventListener('click', async () => {
        if (!currentPolygon) {
            updateStatus('Please draw a polygon on the map first.', 'error');
            return;
        }
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        if (!startDate || !endDate || new Date(startDate) > new Date(endDate)) {
            updateStatus('Please enter valid dates (From <= To).', 'error');
            return;
        }
        
        progressBarContainer.classList.remove('hidden');
        processBtn.disabled = true;
        updateStatus('Processing data, please wait...', 'info');
        
        chartContainer.style.display = 'none';
        mapControlsContainer.style.display = 'none';
        downloadLinkContainer.innerHTML = ''; // Clear old export buttons
        
        const geoJson = currentPolygon.toGeoJSON();
        const polygonCoords = geo.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

        try {
            const response = await fetch('/process-ndvi', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    polygon: polygonCoords,
                    startDate: startDate,
                    endDate: endDate,
                    frequency: frequencySelect.value
                })
            });

            const result = await response.json();

            if (response.ok) {
                drawnItems.clearLayers();
                updateStatus(`Processing complete! Found ${result.imageLayers.length} images.`, 'success');
                
                // ... (kód pro zobrazení grafu a mapy zůstává stejný)
                chartContainer.style.display = 'block';
                mapControlsContainer.style.display = 'block';

                const graphData = result.graphData.map(d => ({ x: d.date, y: d.value }));
                const ctx = document.getElementById('ndviChart').getContext('2d');
                if (ndviChart) ndviChart.destroy();
                ndviChart = new Chart(ctx, { /* ... chart config ... */ });
                
                activeMapLayers.forEach(layer => map.removeLayer(layer));
                activeMapLayers = [];
                const imageLayers = result.imageLayers;
                slider.max = imageLayers.length - 1;
                slider.value = imageLayers.length - 1;

                function showLayer(index) { /* ... showLayer logic ... */ }
                slider.addEventListener('input', (e) => showLayer(e.target.value));
                showLayer(slider.value);

                legendContainer.innerHTML = `<strong>NDVI Legend</strong>...`;

                // --- NEW: Create and show the Export to HTML button ---
                const exportBtn = document.createElement('button');
                exportBtn.id = 'exportBtn';
                exportBtn.textContent = 'Export to HTML';
                
                exportBtn.onclick = () => {
                    // Build the URL for the export endpoint with parameters
                    const params = new URLSearchParams({
                        startDate: startDateInput.value,
                        endDate: endDateInput.value,
                        frequency: frequencySelect.value,
                        // Pass polygon as a URL-safe JSON string
                        polygon: JSON.stringify(polygonCoords) 
                    });
                    
                    const exportUrl = `/export-html?${params.toString()}`;
                    
                    // Open the URL in a new tab to trigger the download
                    window.open(exportUrl, '_blank');
                };
                downloadLinkContainer.appendChild(exportBtn);

            } else {
                updateStatus(`Error: ${result.error || 'Unknown error from backend.'}`, 'error');
            }

        } catch (error) {
            console.error('Error communicating with the backend:', error);
            updateStatus('Error: Cannot connect to the server. Check the console.', error);
        } finally {
            progressBarContainer.classList.add('hidden');
            processBtn.disabled = false;
        }
    });
});