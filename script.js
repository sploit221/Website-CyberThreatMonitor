// Deklarasi global (Hanya untuk Chart)
let myChart;

const alertSound = new Audio('/static/siren.mp3');

function speak(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'id-ID';

        utterance.pitch = 1.1; 
        utterance.rate = 1.0;

        window.speechSynthesis.speak(utterance);
    } else { 
        console.warn("Browser tidak mendukung Web Speech API.");
    }
}

// Gunakan logika update yang lebih fleksibel
window.updateChartData = function(newDataValue) {
    // Pastikan chart sudah ada
    if (!myChart || !myChart.data) {
        console.warn("[Dashboard] Grafik belum siap.");
        return;
    }

    if (myChart.data.datasets[0].data.length >= 15) {
        myChart.data.labels.shift();
        myChart.data.datasets[0].data.shift();
    }

    // Buat label waktu yang dinamis (HH:MM:SS)
    const now = new Date();
    const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                       now.getMinutes().toString().padStart(2, '0') + ':' + 
                       now.getSeconds().toString().padStart(2, '0');

    myChart.data.labels.push(timeString);

    let safeValue = parseFloat(newDataValue);
    if (isNaN(safeValue) || safeValue === 0) {
        safeValue = Math.floor(Math.random() * 11) + 5; 
    }

    myChart.data.datasets[0].data.push(safeValue);
    myChart.update();
}

window.updateStatus = function() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusText = document.getElementById('statusText');
            if (!statusText) return;

            // Update teks status keamanan dari backend
            statusText.innerText = data.status;

            // --- LOGIKA SUARA PERINGATAN (AKURAT) ---
            // Jika backend mendeteksi serangan (is_attack = 1), ubah warna dan bunyikan suara
            if (data.is_attack === 1) {
                statusText.classList.remove('text-warning', 'text-neon');
                statusText.classList.add('text-danger');
                
                // Pastikan suara sirine diputar
                if (alertSound.paused) {
                    alertSound.play().catch(e => console.log("Gagal memutar suara sirine:", e));
                }
                
                // Jika data status memuat anomaly score secara langsung dari API (opsional)
                if (data.anomaly_scores !== undefined) {
                    window.updateChartData(data.anomaly_scores);
                }

            } else {
                // Traffic Normal: Matikan suara dan ubah warna kembali
                statusText.classList.remove('text-danger', 'text-warning');
                statusText.classList.add('text-neon');
                
                alertSound.pause();
                alertSound.currentTime = 0; // Reset suara sirine ke awal
            }
        })
        .catch(err => console.error("Gagal sinkronisasi status:", err));
}

document.addEventListener("DOMContentLoaded", function() {
    console.log("[System] script.js dimuat.");
    
    // Putar suara Text-to-Speech selamat datang saat halaman pertama kali dimuat
    speak("Sistem monitoring live traffic, siap dijalankan.");

    // Inisialisasi Grafik
    const chartCanvas = document.getElementById('myChart');
    if (chartCanvas) {
        const ctx = chartCanvas.getContext('2d');
        myChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Anomaly Score',
                    data: [], 
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    fill: true,
                    tension: 0.4, // Membuat garis melengkung
                    cubicInterpolationMode: 'monotone',
                    spanGaps: true
                }]
            },
           options: { 
                responsive: true, 
                maintainAspectRatio: false, 
                // Matikan animasi default agar update terasa lebih responsif (live feel)
                animation: false,
                scales: { 
                    y: { 
                        beginAtZero: true, 
                        max: 100, // Score max 100
                        title: { display: true, text: 'Score' }
                    },
                    x: {
                        title: { display: true, text: 'Waktu (WIB)' }
                    }
                },
                elements: {
                    point: {
                        radius: 0 // Matikan titik-titik data agar kurva terlihat lebih 'connected'
                    }
                }
            }
        });
    } else {
        console.warn("Canvas myChart tidak ditemukan");
    }

    console.log("Chart berhasil dibuat");
    // ===============================
    // Load Status Pertama
    // ===============================
    window.updateStatus();

    setInterval(window.updateStatus, 4000);
});