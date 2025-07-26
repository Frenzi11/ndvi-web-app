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
            // FIXED: Full SVG code is now here
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
        const polygonCoords = geoJson.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

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
                
                chartContainer.style.display = 'block';
                mapControlsContainer.style.display = 'block';

                const graphData = result.graphData.map(d => ({ x: d.date, y: d.value }));
                const ctx = document.getElementById('ndviChart').getContext('2d');
                if (ndviChart) {
                    ndviChart.destroy();
                }
                ndviChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        datasets: [{
                            label: 'Average NDVI',
                            data: graphData,
                            borderColor: 'green',
                            backgroundColor: 'rgba(0, 255, 0, 0.1)',
                            tension: 0.1,
                            fill: true
                        }]
                    },
                    options: {
                        scales: {
                            x: { type: 'time', time: { unit: 'month', tooltipFormat: 'dd.MM.yyyy' } },
                            y: { title: { display: true, text: 'NDVI' }, min: -0.2, max: 1.0 }
                        },
                        interaction: { intersect: false, mode: 'index' }
                    }
                });
                
                activeMapLayers.forEach(layer => map.removeLayer(layer));
                activeMapLayers = [];
                const imageLayers = result.imageLayers;
                slider.max = imageLayers.length - 1;
                slider.value = imageLayers.length - 1;

                function showLayer(index) {
                    activeMapLayers.forEach(layer => map.removeLayer(layer));
                    const layerInfo = imageLayers[index];
                    if (layerInfo) {
                        const layer = L.imageOverlay(layerInfo.url, layerInfo.bounds, { opacity: 0.8 });
                        layer.addTo(map);
                        activeMapLayers = [layer];
                        dateLabel.textContent = layerInfo.date;
                    }
                }
                slider.addEventListener('input', (e) => showLayer(e.target.value));
                showLayer(slider.value);

                legendContainer.innerHTML = `
                    <strong>NDVI Legend</strong><br>
                    <div style="display: flex; align-items: center; margin-top: 5px; font-size: 0.8em;">
                        <span>-0.2</span>
                        <span style="background: linear-gradient(to right, #d73027, #ffffbf, #1a9850); flex-grow: 1; height: 15px; margin: 0 5px; border: 1px solid #666;"></span>
                        <span>1.0</span>
                    </div>
                `;

                // --- NEW: Create and show the Export to HTML button ---
                const exportBtn = document.createElement('button');
                exportBtn.id = 'exportBtn';
                exportBtn.textContent = 'Export to HTML';
                
                exportBtn.onclick = () => {
                    const params = new URLSearchParams({
                        startDate: startDateInput.value,
                        endDate: endDateInput.value,
                        frequency: frequencySelect.value,
                        polygon: JSON.stringify(polygonCoords) 
                    });
                    
                    const exportUrl = `/export-html?${params.toString()}`;
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