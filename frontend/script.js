document.addEventListener('DOMContentLoaded', () => {
    // Initialize Leaflet map
    const map = L.map('map').setView([49.795, 18.42], 12); // Havířov, Czechia

    // Base map layers
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });

    // Orthophoto layer (Esri World Imagery)
    const esriSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
    });

    // Add default layer to the map (e.g., OSM)
    osmLayer.addTo(map);

    // Define "base maps" for the layer switching control
    const baseMaps = {
        "OpenStreetMap": osmLayer,
        "Satellite Imagery (Esri)": esriSatLayer
    };

    // Add layer switching control to the map
    L.control.layers(baseMaps).addTo(map);


    // Layer group for drawing
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    // Leaflet.Draw controls
    const drawControl = new L.Control.Draw({
        edit: {
            featureGroup: drawnItems,
            poly: {
                allowIntersection: false
            }
        },
        draw: {
            polyline: false,
            marker: false,
            circlemarker: false,
            circle: false,
            rectangle: false,
            polygon: {
                allowIntersection: false,
                showArea: true,
                drawError: {
                    color: '#b00b00',
                    message: 'Oh snap! Intersections not allowed!'
                },
                shapeOptions: {
                    color: '#3388ff'
                }
            }
        }
    });
    map.addControl(drawControl);

    let currentPolygon = null;

    map.on(L.Draw.Event.CREATED, function (event) {
        const layer = event.layer;
        if (currentPolygon) {
            drawnItems.removeLayer(currentPolygon);
        }
        drawnItems.addLayer(layer);
        currentPolygon = layer;
        updateStatus('');
        console.log('Polygon drawn:', layer.toGeoJSON());
    });

    map.on(L.Draw.Event.EDITED, function (event) {
        updateStatus('');
        console.log('Polygon edited:', currentPolygon.toGeoJSON());
    });

    map.on(L.Draw.Event.DELETED, function (event) {
        currentPolygon = null;
        updateStatus('');
        console.log('Polygon deleted.');
    });

    const KM_PER_DEGREE = 111; // Approximately 111 km per degree

    function getApproximatePolygonArea(latlngs) {
        if (latlngs.length < 3) return 0;
        let area = 0;
        let i, j;
        for (i = 0, j = latlngs.length - 1; i < latlngs.length; j = i++) {
            const x1 = latlngs[j].lng * KM_PER_DEGREE * Math.cos(latlngs[j].lat * Math.PI / 180);
            const y1 = latlngs[j].lat * KM_PER_DEGREE;
            const x2 = latlngs[i].lng * KM_PER_DEGREE * Math.cos(latlngs[i].lat * Math.PI / 180);
            const y2 = latlngs[i].lat * KM_PER_DEGREE;
            area += (x1 * y2 - x2 * y1);
        }
        return Math.abs(area / 2);
    }

    const MAX_FRONTEND_AREA_ESTIMATE_SQKM = 50;

    const processBtn = document.getElementById('processNdviBtn');
    const statusMessage = document.getElementById('statusMessage');
    const downloadLinkContainer = document.getElementById('downloadLinkContainer');
    
    // Nové inputy pro datumy a frekvenci
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const frequencySelect = document.getElementById('frequency');

    function updateStatus(message, type = '') {
        statusMessage.textContent = message;
        statusMessage.className = `status ${type}`;
    }

    // Nastavení defaultních dat (dnešek a rok zpět) a limitů pro výběr
    const today = new Date();
    const sentinelLaunchDate = new Date('2015-06-23'); // Datum spuštění Sentinel-2A

    const oneYearAgo = new Date(today);
    oneYearAgo.setFullYear(today.getFullYear() - 1);

    // Nastavení výchozích hodnot inputů
    startDateInput.value = oneYearAgo.toISOString().split('T')[0];
    endDateInput.value = today.toISOString().split('T')[0];

    // NOVÉ ŘÁDKY: Nastavení limitů pro datumové inputy
    startDateInput.min = sentinelLaunchDate.toISOString().split('T')[0]; // Od kdy lze vybírat start date
    endDateInput.min = sentinelLaunchDate.toISOString().split('T')[0];   // End date nemůže být dříve než launch date
    endDateInput.max = today.toISOString().split('T')[0];                 // End date nemůže být později než dnes


    processBtn.addEventListener('click', async () => {
        if (!currentPolygon) {
            updateStatus('Please draw a polygon on the map first.', 'error');
            return;
        }

        const geoJson = currentPolygon.toGeoJSON();
        const polygonCoords = geoJson.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

        const approxArea = getApproximatePolygonArea(currentPolygon.getLatLngs()[0]);
        if (approxArea > MAX_FRONTEND_AREA_ESTIMATE_SQKM) {
             updateStatus(`Polygon is too large (estimated area: ${approxArea.toFixed(2)} km²). Max allowed frontend estimation is ${MAX_FRONTEND_AREA_ESTIMATE_SQKM} km².`, 'error');
             return;
        }

        // Získáváme hodnoty z nových inputů
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        const frequency = frequencySelect.value;
        
        // Rozšířená validace datumu
        const selectedStartDate = new Date(startDate);
        const selectedEndDate = new Date(endDate);
        const todayDateOnly = new Date(today.toISOString().split('T')[0]); 
        const sentinelLaunchDateOnly = new Date(sentinelLaunchDate.toISOString().split('T')[0]);

        if (!startDate || !endDate || selectedStartDate > selectedEndDate) {
            updateStatus('Please enter valid dates (From Date <= To Date).', 'error');
            return;
        }
        if (selectedStartDate < sentinelLaunchDateOnly) {
            updateStatus(`From Date cannot be earlier than Sentinel-2 launch date (${sentinelLaunchDateOnly.toISOString().split('T')[0]}).`, 'error');
            return;
        }
        if (selectedEndDate > todayDateOnly) {
            updateStatus(`To Date cannot be later than today (${todayDateOnly.toISOString().split('T')[0]}).`, 'error');
            return;
        }

        updateStatus('Processing data, please wait...', '');
        processBtn.disabled = true;
        downloadLinkContainer.innerHTML = ''; // Clear previous links

        try {
            const response = await fetch('/process-ndvi', { // Using relative URL
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    polygon: polygonCoords,
                    startDate: startDate,
                    endDate: endDate,
                    frequency: frequency
                })
            });

            const result = await response.json();

            if (response.ok) {
                const imageDate = result.imageDate;
                const message = result.message;

                let statusText = `${message}`;
                if (imageDate) {
                    statusText += ` Map data from: ${imageDate}`;
                }
                updateStatus(statusText, 'success');
                
                const fileUrlTiff = result.fileUrl;
                const fileUrlPdf = result.pdfUrl;

                if (fileUrlTiff) {
                    const fullDownloadUrlTiff = fileUrlTiff; 
                    const downloadLinkTiff = document.createElement('a');
                    downloadLinkTiff.href = fullDownloadUrlTiff;
                    downloadLinkTiff.textContent = 'Download NDVI GeoTIFF';
                    downloadLinkTiff.download = fileUrlTiff.split('/').pop();
                    downloadLinkContainer.appendChild(downloadLinkTiff);
                    downloadLinkContainer.appendChild(document.createElement('br'));
                }

                if (fileUrlPdf) {
                    const fullDownloadUrlPdf = fileUrlPdf; 
                    const downloadLinkPdf = document.createElement('a');
                    downloadLinkPdf.href = fullDownloadUrlPdf;
                    downloadLinkPdf.textContent = 'Download NDVI Report (PDF)';
                    downloadLinkPdf.download = fileUrlPdf.split('/').pop();
                    downloadLinkContainer.appendChild(downloadLinkPdf);
                }

            } else {
                updateStatus(`Error: ${result.error || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error('An error occurred during backend communication:', error);
            updateStatus('Error communicating with backend. Check console.', 'error');
        } finally {
            processBtn.disabled = false;
        }
    });
});