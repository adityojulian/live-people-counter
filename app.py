import base64
from flask import Flask, Response, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import cv2
import threading
import time
from datetime import datetime
import pytz
from instance.models import db, Zone, ZoneCount
from modules.people_counter_new import PeopleCounterNew
import os
from pathlib import Path
from sqlalchemy.sql import func


app = Flask(__name__, static_folder='static')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Global variables
counter = None
lock = threading.Lock()
camera_url = "https://cctvjss.jogjakota.go.id/malioboro/NolKm_Utara.stream/playlist.m3u8"
# camera_url = "https://cctvjss.jogjakota.go.id/malioboro/NolKm_GdAgung.stream/playlist.m3u8"
# camera_url = "https://eofficev2.bekasikota.go.id/backupcctv/m3/Depan_SMP_Strada_Budi_luhur.m3u8"
zones_data = []
is_running = True

def init_database():
    """Initialize database tables"""
    try:
        with app.app_context():
            db.create_all()
            print(f"Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def initialize_counter():
    """Initialize or reinitialize the people counter"""
    global counter, camera_url, is_running
    
    if counter is not None:
        counter.stop()
        
    # Retrieve zones from the database
    with app.app_context():
        zones = Zone.query.filter_by(active=True).all()
        zones_data = [{
            'id': zone.id,
            'points': zone.points,
            'name': zone.name
        } for zone in zones]
    
    counter = PeopleCounterNew(
        video_source=camera_url,
        model_path="yolov8n.pt",
        target_fps=30,
        buffer_size=5,
        zones=zones_data
    )
    
    if is_running:
        counter.start()
        # Start database update thread
        threading.Thread(target=update_zone_counts, daemon=True).start()

def generate_frames():
    """Generate video frames for streaming"""
    global counter, is_running
    
    # Ensure counter is initialized
    if counter is None:
        initialize_counter()
    
    # Make sure processing is started
    if not is_running:
        counter.start()
        is_running = True
    
    while True:
        # Get processed frame
        frame, _ = counter.process_frame()
        
        # If no frame is available, wait a bit
        if frame is None:
            time.sleep(0.01)
            continue
        
        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        # Yield frame for streaming
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stats')
def get_stats():
    """Get zone statistics with optional time filtering"""
    zone_id = request.args.get('zone_id', type=int)
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    with app.app_context():
        try:
            if zone_id and (start_time or end_time):
                # Historical data request
                try:
                    start_dt = datetime.fromisoformat(start_time).replace(tzinfo=pytz.UTC) if start_time else None
                    end_dt = datetime.fromisoformat(end_time).replace(tzinfo=pytz.UTC) if end_time else None
                    counts = ZoneCount.get_counts(zone_id, start_dt, end_dt)
                    return jsonify([count.to_dict() for count in counts])
                except ValueError as e:
                    return jsonify({"error": f"Invalid datetime format: {str(e)}"}), 400
            else:
                # Current stats - get most recent count for each active zone using subquery
                try:
                    # Get active zones in order
                    active_zones = Zone.query.filter_by(active=True).order_by(Zone.id).all()
                    active_zone_ids = [zone.id for zone in active_zones]

                    # Get latest counts for active zones
                    latest_counts = db.session.query(
                        ZoneCount,
                        Zone.name
                    ).join(
                        Zone,
                        ZoneCount.zone_id == Zone.id
                    ).filter(
                        Zone.id.in_(active_zone_ids)
                    ).filter(
                        ZoneCount.id.in_(
                            db.session.query(func.max(ZoneCount.id))
                            .group_by(ZoneCount.zone_id)
                        )
                    ).all()

                    # Build response using counter-style indexing
                    stats = {}
                    for i, (count, zone_name) in enumerate(latest_counts):
                        stats[count.zone_id] = {  # Convert to string to match counter output
                            'name': zone_name,
                            'entry': count.entries,
                            'exit': count.exits,
                            'current': count.current_count
                        }
                    
                    return jsonify(stats)
                    
                except Exception as e:
                    print(f"Error getting current stats: {str(e)}")
                    return jsonify({"error": "Database error"}), 500
                    
        except Exception as e:
            print(f"Error in get_stats: {str(e)}")
            return jsonify({"error": "Server error"}), 500


@app.route('/zones', methods=['GET', 'POST'])
def manage_zones():
    """Get or set zone configurations"""
    global counter
    
    if request.method == 'POST':
        try:
            zones_data = request.json
            print("Received zones data:", zones_data)  # Debug log
            
            with app.app_context():
                try:
                    # Deactivate all existing zones
                    Zone.query.update({"active": False})
                    db.session.flush()
                    
                    # Add new zones
                    new_zones = []
                    for i, zone_data in enumerate(zones_data):
                        try:
                            # Validate zone data
                            if not isinstance(zone_data.get('points'), list):
                                raise ValueError("Points must be a list")
                            
                            # Convert points to proper format
                            points = []
                            for point in zone_data['points']:
                                if isinstance(point, dict) and 'x' in point and 'y' in point:
                                    points.append([int(point['x']), int(point['y'])])
                                elif isinstance(point, list) and len(point) == 2:
                                    points.append([int(point[0]), int(point[1])])
                                else:
                                    raise ValueError("Invalid point format")
                            
                            # Create zone with validated data
                            zone = Zone(
                                name=zone_data.get('name', f'Zone {i+1}'),
                                points=points,
                                active=True
                            )
                            new_zones.append(zone)
                            db.session.add(zone)
                            
                        except Exception as e:
                            print(f"Error processing zone {i}:", e)  # Debug log
                            raise ValueError(f"Invalid zone data format at index {i}: {str(e)}")
                    
                    # Commit the transaction
                    db.session.commit()
                    
                    # Update counter with new zones
                    with lock:
                        if counter is not None:
                            zone_configs = [{
                                'points': zone.points,
                                'name': zone.name,
                                'id': zone.id
                            } for zone in new_zones]
                            counter.update_zones(zone_configs)
                    
                    return jsonify({"status": "success"})
                    
                except Exception as e:
                    db.session.rollback()
                    raise e
                    
        except Exception as e:
            print(f"Error managing zones: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500
            
    elif request.method == 'GET':
        try:
            with app.app_context():
                zones = Zone.query.filter_by(active=True).all()
                return jsonify([zone.to_dict() for zone in zones])
        except Exception as e:
            print(f"Error fetching zones: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setup-polygons', methods=['GET'])
def setup_polygons():
    """Handle polygon setup page"""
    try:
        with app.app_context():
            zones = Zone.query.filter_by(active=1).all()
            zones_data = [zone.to_dict() for zone in zones]
            print("ZONE DATA", zones_data)
            
            return render_template('setup_polygons.html', 
                                existing_zones=zones_data)
    except Exception as e:
        print(f"Error in setup_polygons: {e}")
        return "Error loading setup page", 500
    
@app.route('/setup-feed')
def setup_feed():
    """Video streaming route for setup page with current zones overlay"""
    def generate():
        while True:
            frame, _ = counter.process_frame()  # This already includes zone visualization
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.01)
            
    return Response(generate(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

# Database update thread
def update_zone_counts():
    """Update zone counts in database periodically"""
    while True:
        if counter and is_running:
            try:
                with lock:
                    _, stats = counter.process_frame()
                    print("STATS FROM COUNTER", stats)
                
                current_time = datetime.now(pytz.UTC)
                        
                with app.app_context():
                    for zone_id, zone_data in stats.items():
                        count = ZoneCount(
                            zone_id=zone_id,
                            timestamp=current_time,
                            entries=zone_data['entry'],
                            exits=zone_data['exit'],
                            current_count=zone_data['current']
                        )
                        db.session.add(count)
                    db.session.commit()
            except Exception as e:
                print(f"Error updating database: {e}")
                
        time.sleep(1.0)  # Update every second

@app.route('/camera', methods=['POST'])
def set_camera():
    """Set camera source"""
    global camera_url, is_running
    
    data = request.json
    new_url = data.get('url', 0)
    
    # Update camera URL
    camera_url = new_url
    
    # Reinitialize counter with new source
    with lock:
        is_running = False  # Pause processing during reinitialization
        initialize_counter()
    
    return jsonify({"status": "success", "message": f"Camera set to {new_url}"})

# @app.route('/start', methods=['POST'])
# def start_processing():
#     """Start people counting process"""
#     global counter, is_running
    
#     if counter is None:
#         initialize_counter()
    
#     with lock:
#         if not is_running:
#             counter.start()
#             is_running = True
    
#     return jsonify({"status": "success", "message": "Processing started"})

# @app.route('/stop', methods=['POST'])
# def stop_processing():
#     """Stop people counting process"""
#     global counter, is_running
    
#     with lock:
#         if counter is not None and is_running:
#             counter.stop()
#             is_running = False
    
#     return jsonify({"status": "success", "message": "Processing stopped"})

# @app.route('/stream', methods=['POST'])
# def set_stream_output():
#     """Configure RTMP streaming output"""
#     global counter
    
#     data = request.json
#     stream_url = data.get('url')
    
#     if not stream_url:
#         return jsonify({"status": "error", "message": "No stream URL provided"})
    
#     with lock:
#         if counter is not None:
#             counter.set_output(stream_url)
    
#     return jsonify({"status": "success", "message": f"Streaming to {stream_url}"})

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Initialize counter
    initialize_counter()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, threaded=True)
    
    # Cleanup on exit
    if counter is not None:
        counter.stop()