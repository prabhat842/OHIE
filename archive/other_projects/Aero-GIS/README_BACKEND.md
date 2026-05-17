# AeroGis AI Backend Integration

This document describes the backend integration for the AeroGis AI airport design automation system.

## Architecture Overview

The system consists of:
- **Frontend**: HTML/CSS/JavaScript UI with real-time WebSocket connections
- **Backend**: Flask API server with SocketIO for real-time communication
- **Pipeline**: Three Python scripts for airport design automation

## Backend Components

### Flask API Server (`backend.py`)
- **REST API**: File upload, status checking, results retrieval
- **WebSocket**: Real-time progress updates and logging
- **Process Management**: Executes Python pipeline scripts
- **File Handling**: Uploads GIS data files and serves results

### Key API Endpoints

#### REST API
- `GET /` - Serves the main UI
- `GET /api/status` - Get current execution status
- `POST /api/upload` - Upload GIS data files
- `GET /api/files` - List uploaded files
- `POST /api/clear_uploads` - Clear uploaded files
- `GET /api/runs` - List all completed runs
- `GET /api/results/<run_id>` - Get results for specific run

#### WebSocket Events
- `status_update` - Real-time execution status
- `log` - Live log streaming from pipeline
- `pipeline_complete` - Pipeline completion notification
- `error` - Error notifications

## Installation & Setup

### Prerequisites
- Python 3.8+
- Virtual environment (created automatically)

### Installation Steps

1. **Activate virtual environment:**
   ```bash
   source aerogis/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install flask flask-socketio python-socketio gevent gevent-websocket
   ```

3. **Start the backend server:**
   ```bash
   python backend.py
   ```
   Or use the launcher:
   ```bash
   python run_backend.py
   ```

4. **Access the UI:**
   Open http://localhost:5000 in your browser

## Usage Workflow

### 1. File Upload
- Frontend validates and uploads files to `/api/upload`
- Backend stores files in `temp_uploads/` directory
- Files are copied to `Data/Hyd/` before pipeline execution

### 2. Pipeline Execution
- User clicks "Start Pipeline" → WebSocket event `start_pipeline`
- Backend validates file availability and starts pipeline
- Real-time updates sent via WebSocket during execution

### 3. Progress Monitoring
- Stage-by-stage progress via `status_update` events
- Live logging via `log` events
- Error handling via `error` events

### 4. Results Access
- Completed pipeline triggers `pipeline_complete` event
- Results stored in timestamped `Outputs/Run_YYYYMMDD_HHMMSS/` directories
- Frontend can retrieve results via `/api/results/<run_id>`

## Directory Structure

```
aerogis-ai/
├── backend.py              # Flask backend server
├── run_backend.py          # Backend launcher script
├── ui.html                 # Frontend UI
├── temp_uploads/           # Uploaded files (temporary)
├── Data/Hyd/              # GIS data files
├── Outputs/               # Pipeline results
│   └── Run_YYYYMMDD_HHMMSS/
│       ├── stage1_selector.log
│       ├── stage2_architect.log
│       ├── stage3_engineer.log
│       ├── site_details.json
│       ├── optimal_layout.json
│       ├── stakeholder_report.png
│       ├── 3d_excavation_report.png
│       ├── final_airport_design.kml
│       └── final_airport_design.glb
└── aerogis/               # Virtual environment
```

## Development Mode

When backend is not running, the UI automatically falls back to "Demo Mode" with simulated pipeline execution.

## API Reference

### File Upload
```javascript
const formData = new FormData();
formData.append('file', file);
formData.append('file_type', 'dem|lulc|roads|exclusion|flood');

fetch('/api/upload', {
    method: 'POST',
    body: formData
});
```

### WebSocket Connection
```javascript
const socket = io();

// Listen for events
socket.on('status_update', (data) => {
    console.log('Status:', data);
});

socket.on('log', (data) => {
    console.log(`Stage ${data.stage}:`, data.message);
});

// Send commands
socket.emit('start_pipeline', {});
```

## Troubleshooting

### Backend Connection Issues
- Ensure virtual environment is activated
- Check that all dependencies are installed
- Verify port 5000 is not in use
- Check firewall settings

### File Upload Issues
- Ensure files are valid GIS formats
- Check file size limits (1GB max)
- Verify coordinate systems are compatible

### Pipeline Execution Issues
- Check that all required files are uploaded
- Monitor logs for error messages
- Ensure sufficient disk space for outputs

## Security Considerations

- File uploads are validated for type and size
- No authentication implemented (add for production)
- CORS enabled for development (restrict in production)
- Temporary files cleaned up after pipeline completion

## Performance Notes

- GIS file processing can be memory-intensive
- WebSocket connections maintained throughout execution
- Large result files served directly from disk
- Concurrent executions not supported (single-threaded)

## Future Enhancements

- User authentication and authorization
- Multi-user support with session management
- Batch processing queue
- Advanced error recovery
- Performance monitoring and metrics
- API rate limiting and security

