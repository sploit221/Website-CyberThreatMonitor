import os
import datetime
import sqlite3
import joblib
import numpy as np
import pandas as pd
import requests
import random
import io # <--- TAMBAHKAN INI
from fpdf import FPDF # <--- TAMBAHKAN INI
from flask import Flask, render_template, request, jsonify, send_file, Response

app = Flask(__name__)
# ... sisa konfigurasi path tetap sama ...

# --- KONFIGURASI PATH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'model', 'model_ref.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'model', 'scaler.pkl')
DB_PATH = os.path.join(BASE_DIR, 'traffic_logs.db')

# --- INISIALISASI GLOBAL ---
model = joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None
scaler = joblib.load(SCALER_PATH) if os.path.exists(SCALER_PATH) else None
current_status = {"status": "System Ready", "is_attack": 0}

# --- FUNGSI DATABASE & LOGGING ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                waktu TEXT,
                packet_length REAL,
                anomaly_scores REAL,
                source_port REAL,
                destination_port REAL,
                is_attack INTEGER,
                status TEXT,
                latitude REAL,
                longitude REAL,
                country TEXT
            )
        ''')
        conn.commit()
    print("Database logs siap.")

def log_visitor_traffic(status, ip_address="Unknown"):
    """Fungsi pembantu untuk mencatat pengunjung atau aktivitas"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (waktu, status, packet_length, anomaly_scores, source_port, destination_port, is_attack)
            VALUES (?, ?, 0, 0, 0, 0, 0)
        ''', (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), f"{status} (IP: {ip_address})"))
        conn.commit()

init_db()

# --- ROUTES ---

@app.route('/')
def index():
    """Halaman Utama"""
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip and ',' in user_ip:
        user_ip = user_ip.split(',')[0].strip()
    
    # Mencatat traffic kunjungan
    log_visitor_traffic(status="Normal Kunjungan", ip_address=user_ip)
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/predict', methods=['GET', 'POST'])
def predict():

    prediction = None
    confidence = 0.0

    if request.method == 'POST':
        try:
            # PERBAIKAN UTAMA: Mendeteksi secara otomatis kiriman berupa JSON atau Form Data
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form

            # Ambil nilai menggunakan .get() agar aman dari KeyError (Penyebab utama Error 400)
            p_length = float(data.get('packet_length') or data.get('Packet Length') or 0)
            a_score = float(data.get('anomaly_scores') or data.get('Anomaly Scores') or 0)
            s_port = int(data.get('source_port') or data.get('Source Port') or 0)
            d_port = int(data.get('destination_port') or data.get('Destination Port') or 0)
            
            # Ambil variabel geolokasi tambahan dari demo dashboard
            lat = float(data.get('latitude') or 0)
            lon = float(data.get('longitude') or 0)
            country = data.get('country') or 'Unknown'
            attack_type_csv = data.get('Attack Type') or data.get('attack_type') or 'Unknown'

            # --- Logika Prediksi Model Machine Learning ---
            prediction = "Normal"
            confidence = 0.0
            is_attack = 0
            status_text = "Traffic Normal"
            pred = 0

            if model and scaler:
                # Susun fitur sesuai struktur input model pkl milikmu
                features = np.array([[p_length, a_score, s_port, d_port]])
                features_scaled = scaler.transform(features)
                pred = model.predict(features_scaled)[0]
                
                if pred == 1:
                    is_attack = 1
                    prediction = "Attack"
                    status_text = "Peringatan! Terdeteksi aktivitas mencurigakan."
                
                if hasattr(model, "predict_proba"):
                    confidence = float(np.max(model.predict_proba(features_scaled)[0]))
                # Rule-based threshold fallback jika model gagal termuat
            if pred == 1 or a_score > 50.0:
                is_attack = 1
                prediction = "Attack"
                
                if attack_type_csv.lower() not in ['unknown', 'none', '']:
                    status_text = f"Peringatan! Terdeteksi Serangan {attack_type_csv}!"
                else:
                    status_text = "Peringatan! Terdeteksi aktivitas mencurigakan."

            current_status['status'] = status_text
            current_status['is_attack'] = is_attack

            # Simpan log ke database SQLite (Variabel disesuaikan akurat dengan skema tabel kamu)
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO logs (waktu, packet_length, anomaly_scores, source_port, destination_port, is_attack, status, latitude, longitude, country)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                      p_length, a_score, s_port, d_port, is_attack, 
                      status_text, lat, lon, country))
                conn.commit()

            if not request.is_json:
                return render_template('predict.html', prediction=prediction, confidence=confidence)

            # Mengembalikan response lengkap ke frontend
            return jsonify({
                'status': 'success', 
                'is_attack': is_attack, 
                'prediction': prediction, 
                'confidence': confidence,
                'message': 'Prediksi berhasil diproses'
            })
                
        except Exception as e:
            if request.is_json:
                return jsonify({'status': 'error', 'message': str(e)}), 400
            # Jika error form biasa, tetap kembalikan ke HTML tanpa nilai hasil
            return render_template('predict.html', prediction=None, confidence=0.0)
            
    return render_template('predict.html', prediction=prediction, confidence=confidence)

@app.route('/api/status')
def get_status():
    return jsonify(current_status)

@app.route('/admin')
def admin_dashboard():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM logs ORDER BY id DESC", conn)
        total_logs = len(df)
        total_attacks = len(df[df['is_attack'] == 1])
        logs = df.to_dict(orient='records')
    
    return render_template('admin.html', logs=logs, total_logs=total_logs, total_attacks=total_attacks)

# --- ROUTE TAMBAHAN: ANALISIS PREDIKSI POLA SERANGAN ---

@app.route('/api/analyze_pola')
def analyze_pola():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Ambil 20 log serangan terakhir untuk dianalisis polanya
            df = pd.read_sql_query(
                "SELECT status, destination_port, waktu FROM logs WHERE is_attack = 1 ORDER BY id DESC LIMIT 20", 
                conn
            )
        
        if df.empty or len(df) < 2:
            return jsonify({
                'status': 'waiting',
                'message': 'Mengumpulkan data serangan yang cukup untuk analisis pola...'
            })
        
        # Ekstrak nama serangan dari kolom status text
        def extract_attack(status_str):
            if "Terdeteksi Serangan " in status_str:
                return status_str.split("Terdeteksi Serangan ")[1].replace("!", "")
            return "Aktivitas Mencurigakan"
        
        df['attack_type'] = df['status'].apply(extract_attack)
        
        # Membalik urutan agar runtut dari waktu yang lebih lama ke yang paling baru
        attack_sequence = df['attack_type'].iloc[::-1].tolist()
        
        # 1. LOGIKA PREDIKSI POLA SERANGAN (Simple Transition Probability)
        last_attack = attack_sequence[-1]
        transitions = []
        
        for i in range(len(attack_sequence) - 1):
            if attack_sequence[i] == last_attack:
                transitions.append(attack_sequence[i+1])
                
        # Jika ada pola transisi berulang, ambil yang paling sering muncul setelah serangan terakhir
        if transitions:
            predicted_attack = max(set(transitions), key=transitions.count)
        else:
            # Fallback: jika pola acak, ambil jenis serangan yang paling dominan secara keseluruhan
            predicted_attack = max(set(attack_sequence), key=attack_sequence.count)
            
        # Mencari port yang paling sering menjadi target dari rentetan serangan terakhir
        predicted_port = int(df['destination_port'].mode()[0]) if not df['destination_port'].empty else 80
        
        # 3. STRATEGI MITIGASI OTOMATIS (REKOMENDASI)
        tingkat_risiko = "Tinggi" if len(df) >= 10 else "Sedang"
        rekomendasi = f"Siapkan rule firewall untuk memblokir aktivitas berpola '{predicted_attack}' dan perketat monitoring pada Port {predicted_port}."
        
        return jsonify({
            'status': 'analyzed',
            'predicted_attack': predicted_attack,
            'predicted_port': predicted_port,
            'risk_level': tingkat_risiko,
            'recommendation': rekomendasi
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/export/excel')
def export_excel():
    import io
    try:
        # 1. Ambil data dari database SQLite
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("""
                SELECT waktu, packet_length, anomaly_scores, source_port, destination_port, is_attack, status 
                FROM logs 
                ORDER BY id DESC
            """, conn)
        
        # 2. Rename nama kolom agar rapi saat dibuka di Excel
        df.columns = ['Waktu/Timestamp', 'Packet Length', 'Anomaly Scores', 'Source Port', 'Destination Port', 'Is Attack (0/1)', 'Status Analisis']
        
        # 3. Proses konversi ke Excel (.xlsx) di dalam memori
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Traffic Logs')
        output.seek(0)
        
        filename = f"Traffic_Logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Gagal cetak Excel ({e}), beralih otomatis ke format CSV...")
        # Fallback otomatis ke CSV jika library openpyxl belum di-install di laptop target
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT waktu, packet_length, anomaly_scores, source_port, destination_port, is_attack, status FROM logs ORDER BY id DESC", conn)
        
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        from flask import Response
        filename = f"Traffic_Logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )

@app.route('/admin/export/pdf')
def export_pdf():
    try:
        # 1. Ambil data dari database
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM logs ORDER BY id DESC", conn)

        # 2. Buat PDF menggunakan FPDF
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Judul
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Laporan Keamanan Cyber Threat", 0, 1, 'C')
        pdf.ln(5)

        # Header Tabel
        pdf.set_font("Arial", 'B', 9)
        # Lebar disesuaikan agar muat di landscape A4
        col_widths = [10, 35, 25, 20, 20, 20, 50, 20] 
        headers = ['ID', 'Waktu', 'Packet Len', 'Scores', 'Src Port', 'Dest Port', 'Status', 'Attack']
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1)
        pdf.ln()

        # Isi Tabel
        pdf.set_font("Arial", '', 8)
        for _, row in df.iterrows():
            pdf.cell(col_widths[0], 7, str(row['id']), 1)
            pdf.cell(col_widths[1], 7, str(row['waktu'])[:19], 1)
            pdf.cell(col_widths[2], 7, str(round(float(row['packet_length']), 2)), 1)
            pdf.cell(col_widths[3], 7, str(round(float(row['anomaly_scores']), 2)), 1)
            pdf.cell(col_widths[4], 7, str(int(row['source_port'])), 1)
            pdf.cell(col_widths[5], 7, str(int(row['destination_port'])), 1)
            pdf.cell(col_widths[6], 7, str(row['status']), 1)
            
            is_attack_text = "Yes" if row['is_attack'] == 1 else "No"
            pdf.cell(col_widths[7], 7, is_attack_text, 1)
            pdf.ln()

        # 3. Kirim output sebagai file
        pdf_output = pdf.output(dest='S').encode('latin-1')
        
        return Response(
            pdf_output,
            mimetype='application/pdf',
            as_attachment=True,
            headers={'Content-Disposition': 'attachment;filename=Laporan_Cyber_Threat.pdf'}
        )
    except Exception as e:
        return f"Terjadi kesalahan saat membuat PDF: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)