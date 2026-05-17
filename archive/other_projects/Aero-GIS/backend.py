#!/usr/bin/env python3
"""
AeroGis AI Backend API
Flask application with WebSocket support for real-time pipeline execution
"""

import os
import sys
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import tempfile
import shutil

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'aerogis-ai-secret-key-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Global state
current_execution = None
execution_status = {
    'running': False,
    'stage': 0,
    'progress': 0,
    'message': 'Ready',
    'start_time': None,
    'output_dir': None
}

# Ensure output directory exists
OUTPUT_BASE_DIR = Path('Outputs')
OUTPUT_BASE_DIR.mkdir(exist_ok=True)

# Temporary directory for uploaded files
UPLOAD_DIR = Path('temp_uploads')
UPLOAD_DIR.mkdir(exist_ok=True)

@app.route('/')
def index():
    """Serve the main UI"""
    return send_from_directory('.', 'ui.html')

@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('.', filename)

@app.route('/api/status')
def get_status():
    """Get current execution status"""
    return jsonify(execution_status)

@app.route('/api/results/<run_id>')
def get_results(run_id):
    """Get results for a specific run"""
    run_dir = OUTPUT_BASE_DIR / f"Run_{run_id}"
    if not run_dir.exists():
        return jsonify({'error': 'Run not found'}), 404

    results = {}
    try:
        # Read site_details.json
        site_details_file = run_dir / 'site_details.json'
        if site_details_file.exists():
            with open(site_details_file, 'r') as f:
                results['site_details'] = json.load(f)

        # Read optimal_layout.json
        layout_file = run_dir / 'optimal_layout.json'
        if layout_file.exists():
            with open(layout_file, 'r') as f:
                results['optimal_layout'] = json.load(f)

        # List all files in the run directory
        results['files'] = []
        for file_path in run_dir.glob('*'):
            if file_path.is_file():
                results['files'].append({
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(results)

@app.route('/api/runs')
def get_runs():
    """Get list of all runs"""
    runs = []
    for run_dir in OUTPUT_BASE_DIR.glob('Run_*'):
        if run_dir.is_dir():
            run_id = run_dir.name.replace('Run_', '')
            runs.append({
                'id': run_id,
                'path': str(run_dir),
                'created': datetime.fromtimestamp(run_dir.stat().st_ctime).isoformat(),
                'files_count': len(list(run_dir.glob('*')))
            })

    # Sort by creation time (newest first)
    runs.sort(key=lambda x: x['created'], reverse=True)
    return jsonify(runs)

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status_update', execution_status)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('start_pipeline')
def handle_start_pipeline(data):
    """Handle pipeline start request"""
    global current_execution, execution_status

    if execution_status['running']:
        emit('error', {'message': 'Pipeline is already running'})
        return

    # Check if all required files are uploaded
    required_files = ['DEM_UTM.tif', 'LULC_UTM.tif', 'roads_hyd.geojson',
                     'exclusion_mask_UTM.tif', 'flood_map_UTM.tif']

    missing_files = []
    for filename in required_files:
        if not (UPLOAD_DIR / filename).exists():
            missing_files.append(filename)

    if missing_files:
        emit('error', {'message': f'Missing required files: {", ".join(missing_files)}'})
        return

    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_BASE_DIR / f"Run_{timestamp}"
    output_dir.mkdir(exist_ok=True)

    # Copy uploaded files to Data/Hyd directory
    data_dir = Path('Data/Hyd')
    data_dir.mkdir(exist_ok=True)

    for filename in required_files:
        src = UPLOAD_DIR / filename
        dst = data_dir / filename
        shutil.copy2(src, dst)

    # Update execution status
    execution_status.update({
        'running': True,
        'stage': 0,
        'progress': 0,
        'message': 'Starting pipeline execution...',
        'start_time': datetime.now().isoformat(),
        'output_dir': str(output_dir)
    })

    # Emit status update
    emit('status_update', execution_status, broadcast=True)

    # Start pipeline execution in background thread
    current_execution = threading.Thread(target=run_pipeline, args=(output_dir,))
    current_execution.daemon = True
    current_execution.start()

def run_pipeline(output_dir):
    """Execute the three-stage pipeline"""
    global execution_status

    try:
        # Set environment variable for output directory
        env = os.environ.copy()
        env['AEROGIS_OUTPUT_DIR'] = str(output_dir)

        # Stage 1: Site Selection
        execution_status.update({'stage': 1, 'message': 'Stage 1: Site Selection - Analyzing terrain and constraints'})
        socketio.emit('status_update', execution_status)

        process1 = subprocess.Popen(
            [sys.executable, 'airport_selector.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
            cwd=os.getcwd()
        )

        # Monitor progress
        while process1.poll() is None:
            line = process1.stdout.readline()
            if line:
                # Parse progress from output (you might need to modify the Python scripts to emit progress)
                socketio.emit('log', {'stage': 1, 'message': line.strip()})
            time.sleep(0.1)

        if process1.returncode != 0:
            raise Exception(f"Stage 1 failed with return code {process1.returncode}")

        # Stage 2: Genetic Architecture
        execution_status.update({'stage': 2, 'message': 'Stage 2: Genetic Architecture - Optimizing runway and terminal layouts'})
        socketio.emit('status_update', execution_status)

        process2 = subprocess.Popen(
            [sys.executable, 'genetic_designer.py', f"{output_dir}/site_details.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
            cwd=os.getcwd()
        )

        while process2.poll() is None:
            line = process2.stdout.readline()
            if line:
                socketio.emit('log', {'stage': 2, 'message': line.strip()})
            time.sleep(0.1)

        if process2.returncode != 0:
            raise Exception(f"Stage 2 failed with return code {process2.returncode}")

        # Stage 3: Flood Engineering
        execution_status.update({'stage': 3, 'message': 'Stage 3: Flood Engineering - Designing flood defense systems'})
        socketio.emit('status_update', execution_status)

        process3 = subprocess.Popen(
            [sys.executable, 'bioswale_designer.py', f"{output_dir}/site_details.json", f"{output_dir}/optimal_layout.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
            cwd=os.getcwd()
        )

        while process3.poll() is None:
            line = process3.stdout.readline()
            if line:
                socketio.emit('log', {'stage': 3, 'message': line.strip()})
            time.sleep(0.1)

        if process3.returncode != 0:
            raise Exception(f"Stage 3 failed with return code {process3.returncode}")

        # Pipeline completed successfully
        execution_status.update({
            'running': False,
            'stage': 3,
            'progress': 100,
            'message': 'Pipeline completed successfully!'
        })

        socketio.emit('status_update', execution_status)
        socketio.emit('pipeline_complete', {'output_dir': str(output_dir)})

    except Exception as e:
        execution_status.update({
            'running': False,
            'message': f'Pipeline failed: {str(e)}'
        })
        socketio.emit('status_update', execution_status)
        socketio.emit('error', {'message': str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file uploads"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    file_type = request.form.get('file_type')

    if not file or not file_type:
        return jsonify({'error': 'Missing file or file_type'}), 400

    # Validate file type
    allowed_extensions = {
        'dem': ['tif', 'tiff'],
        'lulc': ['tif', 'tiff'],
        'roads': ['geojson', 'json'],
        'exclusion': ['tif', 'tiff'],
        'flood': ['tif', 'tiff']
    }

    if file_type not in allowed_extensions:
        return jsonify({'error': 'Invalid file type'}), 400

    filename = file.filename.lower()
    extension = filename.split('.')[-1] if '.' in filename else ''

    if extension not in allowed_extensions[file_type]:
        return jsonify({'error': f'Invalid file extension for {file_type}. Allowed: {allowed_extensions[file_type]}'}), 400

    # Save file with correct name
    filename_map = {
        'dem': 'DEM_UTM.tif',
        'lulc': 'LULC_UTM.tif',
        'roads': 'roads_hyd.geojson',
        'exclusion': 'exclusion_mask_UTM.tif',
        'flood': 'flood_map_UTM.tif'
    }

    save_path = UPLOAD_DIR / filename_map[file_type]
    file.save(save_path)

    return jsonify({
        'success': True,
        'filename': filename_map[file_type],
        'size': save_path.stat().st_size
    })

@app.route('/api/files')
def list_uploaded_files():
    """List currently uploaded files"""
    files = {}
    filename_map = {
        'DEM_UTM.tif': 'dem',
        'LULC_UTM.tif': 'lulc',
        'roads_hyd.geojson': 'roads',
        'exclusion_mask_UTM.tif': 'exclusion',
        'flood_map_UTM.tif': 'flood'
    }

    for filepath in UPLOAD_DIR.glob('*'):
        if filepath.is_file() and filepath.name in filename_map:
            files[filename_map[filepath.name]] = {
                'name': filepath.name,
                'size': filepath.stat().st_size,
                'uploaded': True
            }

    return jsonify(files)

@app.route('/api/clear_uploads', methods=['POST'])
def clear_uploads():
    """Clear all uploaded files"""
    try:
        for filepath in UPLOAD_DIR.glob('*'):
            if filepath.is_file():
                filepath.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting AeroGis AI Backend Server...")
    print("📁 Output directory:", OUTPUT_BASE_DIR.absolute())
    print("📁 Upload directory:", UPLOAD_DIR.absolute())

    # Run with SocketIO support
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
