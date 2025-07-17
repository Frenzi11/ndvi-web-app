document.addEventListener('DOMContentLoaded', () => {
    // === Map and layers initialization (remains the same) ===
    const map = L.map('map').setView([49.795, 18.42], 12); // Havířov, Czech Republic

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    const esriSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, and others'
    });
    
    osmLayer.addTo(map);
    const baseMaps = { "OpenStreetMap": osmLayer, "Satellite (Esri)": esriSatLayer };
    L.control.layers(baseMaps).addTo(map);
    L.control.scale().addTo(map);

    // === Drawing on the map (remains the same) ===
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    const drawControl = new L.Control.Draw({
        edit: { featureGroup: drawnItems, poly: { allowIntersection: false } },
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

    // === Variables for new elements ===
    let ndviChart = null; // The chart object will be stored here so we can destroy and redraw it
    let activeMapLayers = []; // Here we'll remember which NDVI layers are on the map
    
    // === All HTML elements we will work with ===
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

    function updateStatus(message, type = '') {
        statusMessage.textContent = message;
        statusMessage.className = type ? `status ${type}` : ''; // Adds class .success or .error
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


    // === KEY FUNCTION: Listener for the "Process NDVI" button ===
    processBtn.addEventListener('click', async () => {
        // Basic validation (if a polygon is drawn, etc.)
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
        
        // We show the status and disable the button
        updateStatus('Processing data, please wait... This might take up to a minute.', 'info');
        processBtn.disabled = true;
        
        // We hide old results
        chartContainer.style.display = 'none';
        mapControlsContainer.style.display = 'none';
        
        const geoJson = currentPolygon.toGeoJSON();
        const polygonCoords = geoJson.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

        try {
            // We call our new backend
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

            // --- THIS IS WHERE THE MAGIC HAPPENS ---
            if (response.ok) {
                drawnItems.clearLayers();
                updateStatus(`Processing complete! Found ${result.imageLayers.length} images.`, 'success');
                
                // 1. We display the containers for the results
                chartContainer.style.display = 'block';
                mapControlsContainer.style.display = 'block';

                // 2. We render the graph using Chart.js
                const graphData = result.graphData.map(d => ({ x: d.date, y: d.value }));
                const ctx = document.getElementById('ndviChart').getContext('2d');
                if (ndviChart) {
                    ndviChart.destroy(); // We destroy the old chart if it exists
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
                
                // 3. We prepare and display the layers on the map
                // First, we delete the old layers from the map
                activeMapLayers.forEach(layer => map.removeLayer(layer));
                activeMapLayers = [];

                const imageLayers = result.imageLayers;
                slider.max = imageLayers.length - 1;
                slider.value = imageLayers.length - 1; // By default, we show the newest image

                function showLayer(index) {
                    // We remove the current layer from the map
                    activeMapLayers.forEach(layer => map.removeLayer(layer));
                    
                    const layerInfo = imageLayers[index];
                    if (layerInfo) {
                        const layer = L.imageOverlay(layerInfo.url, layerInfo.bounds, { opacity: 0.8 });
                        layer.addTo(map);
                        activeMapLayers = [layer]; // We save it as the active layer
                        dateLabel.textContent = layerInfo.date;
                    }
                }
                
                slider.addEventListener('input', (e) => showLayer(e.target.value));
                showLayer(slider.value); // We display the first layer

                // 4. We generate the legend
                legendContainer.innerHTML = `
                    <strong>NDVI Legend</strong><br>
                    <div style="display: flex; align-items: center; margin-top: 5px; font-size: 0.8em;">
                        <span>-0.2</span>
                        <span style="background: linear-gradient(to right, #d73027, #ffffbf, #1a9850); flex-grow: 1; height: 15px; margin: 0 5px; border: 1px solid #666;"></span>
                        <span>1.0</span>
                    </div>
                `;

            } else {
                updateStatus(`Error: ${result.error || 'Unknown error from backend.'}`, 'error');
            }

        } catch (error) {
            console.error('Error communicating with the backend:', error);
            updateStatus('Error: Cannot connect to the server. Check the console.', 'error');
        } finally {
            processBtn.disabled = false; // We enable the button again
        }
    });
});