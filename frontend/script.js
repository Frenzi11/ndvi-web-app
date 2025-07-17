document.addEventListener('DOMContentLoaded', () => {
    // === Inicializace mapy a vrstev (zůstává stejné) ===
    const map = L.map('map').setView([49.795, 18.42], 12); // Havířov, Česká republika

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    const esriSatLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, a další'
    });
    
    osmLayer.addTo(map);
    const baseMaps = { "OpenStreetMap": osmLayer, "Satellite (Esri)": esriSatLayer };
    L.control.layers(baseMaps).addTo(map);
    L.control.scale().addTo(map);

    // === Kreslení na mapě (zůstává stejné) ===
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

    // === Proměnné pro nové prvky ===
    let ndviChart = null; // Zde bude uložen objekt grafu, abychom ho mohli zničit a překreslit
    let activeMapLayers = []; // Zde si budeme pamatovat, které NDVI vrstvy jsou na mapě
    
    // === Všechny HTML elementy, se kterými budeme pracovat ===
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
        statusMessage.className = type ? `status ${type}` : ''; // Přidá class .success nebo .error
    }

    // Nastavení defaultních dat a limitů
    const today = new Date();
    const oneYearAgo = new Date(today);
    oneYearAgo.setFullYear(today.getFullYear() - 1);
    startDateInput.value = oneYearAgo.toISOString().split('T')[0];
    endDateInput.value = today.toISOString().split('T')[0];
    
    startDateInput.min = '2015-06-23';
    startDateInput.max = today.toISOString().split('T')[0]; // <<< TADY JE TA NOVÁ ŘÁDKA
    endDateInput.max = today.toISOString().split('T')[0];


    // === KLÍČOVÁ FUNKCE: Listener na tlačítko "Process NDVI" ===
    processBtn.addEventListener('click', async () => {
        // Základní validace (zda je nakreslený polygon atd.)
        if (!currentPolygon) {
            updateStatus('Nejdřív prosím nakresli polygon na mapě.', 'error');
            return;
        }
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        if (!startDate || !endDate || new Date(startDate) > new Date(endDate)) {
            updateStatus('Prosím zadej platná data (Od <= Do).', 'error');
            return;
        }
        
        // Zobrazíme status a zablokujeme tlačítko
        updateStatus('Zpracovávám data, prosím čekej... Může to trvat i minutu.', 'info');
        processBtn.disabled = true;
        
        // Schováme staré výsledky
        chartContainer.style.display = 'none';
        mapControlsContainer.style.display = 'none';
        
        const geoJson = currentPolygon.toGeoJSON();
        const polygonCoords = geoJson.geometry.coordinates[0].map(coord => [coord[0], coord[1]]);

        try {
            // Zavoláme náš nový backend
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

            // --- ZDE SE DĚJE TA MAGIE ---
            if (response.ok) {
                updateStatus(`Zpracování dokončeno! Nalezeno ${result.imageLayers.length} snímků.`, 'success');
                
                // 1. Zobrazíme kontejnery pro výsledky
                chartContainer.style.display = 'block';
                mapControlsContainer.style.display = 'block';

                // 2. Vykreslíme graf pomocí Chart.js
                const graphData = result.graphData.map(d => ({ x: d.date, y: d.value }));
                const ctx = document.getElementById('ndviChart').getContext('2d');
                if (ndviChart) {
                    ndviChart.destroy(); // Zničíme starý graf, pokud existuje
                }
                ndviChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        datasets: [{
                            label: 'Průměrné NDVI',
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
                
                // 3. Připravíme a zobrazíme vrstvy na mapě
                // Nejdřív smažeme staré vrstvy z mapy
                activeMapLayers.forEach(layer => map.removeLayer(layer));
                activeMapLayers = [];

                const imageLayers = result.imageLayers;
                slider.max = imageLayers.length - 1;
                slider.value = imageLayers.length - 1; // Defaultně ukážeme nejnovější snímek

                function showLayer(index) {
                    // Odstraníme aktuální vrstvu z mapy
                    activeMapLayers.forEach(layer => map.removeLayer(layer));
                    
                    const layerInfo = imageLayers[index];
                    if (layerInfo) {
                        const layer = L.imageOverlay(layerInfo.url, layerInfo.bounds, { opacity: 0.8 });
                        layer.addTo(map);
                        activeMapLayers = [layer]; // Uložíme si ji jako aktivní
                        dateLabel.textContent = layerInfo.date;
                    }
                }
                
                slider.addEventListener('input', (e) => showLayer(e.target.value));
                showLayer(slider.value); // Zobrazíme první vrstvu

                // 4. Vygenerujeme legendu
                legendContainer.innerHTML = `
                    <strong>NDVI Legenda</strong><br>
                    <div style="display: flex; align-items: center; margin-top: 5px; font-size: 0.8em;">
                        <span>-0.2</span>
                        <span style="background: linear-gradient(to right, #d73027, #ffffbf, #1a9850); flex-grow: 1; height: 15px; margin: 0 5px; border: 1px solid #666;"></span>
                        <span>1.0</span>
                    </div>
                `;

            } else {
                updateStatus(`Chyba: ${result.error || 'Neznámá chyba z backendu.'}`, 'error');
            }

        } catch (error) {
            console.error('Chyba komunikace s backendem:', error);
            updateStatus('Chyba: Nelze se spojit se serverem. Zkontroluj konzoli.', 'error');
        } finally {
            processBtn.disabled = false; // Zase povolíme tlačítko
        }
    });
});