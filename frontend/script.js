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
    const downloadLinkContainer = document.getElementById('downloadLinkContainer');
    // NEW: Get opacity slider elements
    const opacitySlider = document.getElementById('opacitySlider');
    const opacityValueLabel = document.getElementById('opacityValueLabel');

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
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                    <path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/>
                </svg>`;
            button.href = '#';
            button.role = 'button';
            button.ariaLabel = 'Find my location';
            L.DomEvent.on(button, 'click', L.DomEvent.stop);
            L.DomEvent.on(button, 'click', this._findLocation, this);
            return container;
        },
        _findLocation: function () { /* ... kód pro lokaci ... */ }
    });
    new LocationControl().addTo(map);

    // NEW: --- Opacity Slider Logic ---
    opacitySlider.addEventListener('input', (e) => {
        const newOpacity = e.target.value;
        // Update the label to show the percentage
        opacityValueLabel.textContent = `${Math.round(newOpacity * 100)}%`;
        // If there is an active layer on the map, change its opacity
        if (activeMapLayers.length > 0 && activeMapLayers[0]) {
            activeMapLayers[0].setOpacity(newOpacity);
        }
    });

    // === KEY FUNCTION: Listener for the "Process NDVI" button ===
    processBtn.addEventListener('click', async () => {
        if (!currentPolygon) { /* ... validace ... */ return; }
        
        progressBarContainer.classList.remove('hidden');
        processBtn.disabled = true;
        updateStatus('Processing data, please wait...', 'info');
        
        chartContainer.style.display = 'none';
        mapControlsContainer.style.display = 'none';
        downloadLinkContainer.innerHTML = '';
        
        const geoJson = currentPolygon.toGeoJSON();
        const polygonCoords = geoJson.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

        try {
            const response = await fetch('/process-ndvi', { /* ... fetch ... */ });
            const result = await response.json();

            if (response.ok) {
                drawnItems.clearLayers();
                updateStatus(`Processing complete! Found ${result.imageLayers.length} images.`, 'success');
                
                chartContainer.style.display = 'block';
                mapControlsContainer.style.display = 'block';

                const graphData = result.graphData.map(d => ({ x: d.date, y: d.value }));
                const ctx = document.getElementById('ndviChart').getContext('2d');
                if (ndviChart) {
                    ndviChart.destroy();
                }
                ndviChart = new Chart(ctx, { /* ... chart config ... */ });
                
                // --- MODIFICATION: The 'showLayer' function now uses the opacity slider's value ---
                activeMapLayers.forEach(layer => map.removeLayer(layer));
                activeMapLayers = [];
                const imageLayers = result.imageLayers;
                slider.max = imageLayers.length - 1;
                slider.value = imageLayers.length - 1;

                function showLayer(index) {
                    activeMapLayers.forEach(layer => map.removeLayer(layer));
                    const layerInfo = imageLayers[index];
                    if (layerInfo) {
                        // MODIFIED: Read the current opacity from the slider when creating the layer
                        const layer = L.imageOverlay(layerInfo.url, layerInfo.bounds, { 
                            opacity: opacitySlider.value 
                        });
                        layer.addTo(map);
                        activeMapLayers = [layer];
                        dateLabel.textContent = layerInfo.date;
                    }
                }
                
                slider.addEventListener('input', (e) => showLayer(e.target.value));
                showLayer(slider.value); // Display the first layer

                legendContainer.innerHTML = `<strong>NDVI Legend</strong>...`;

                // --- Export to HTML button logic ---
                const exportBtn = document.createElement('button');
                exportBtn.id = 'exportBtn';
                exportBtn.textContent = 'Export to HTML';
                exportBtn.onclick = () => { /* ... export logic ... */ };
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