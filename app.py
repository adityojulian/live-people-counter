import base64
from flask import Flask, Response, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import cv2
import threading
import time
from datetime import datetime, timedelta
import pytz
from instance.models import db, Zone, ZoneCount, Camera
from modules.people_counter_new import PeopleCounterNew
import os
from pathlib import Path
from sqlalchemy.sql import func


app = Flask(__name__, static_folder='static')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///secondary.db'
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
current_camera_id = None

# Add this near the top with other global variables
AVAILABLE_MODELS = {
    'yolov8n': {
        'path': 'yolov8n.pt',
        'description': 'Fastest, lowest accuracy'
    },
    'yolo11n': {
        'path': 'yolo11n.pt',
        'description': 'Balance of speed and accuracy'
    },
    'yolo11s': {
        'path': 'yolo11s.pt',
        'description': 'Leaning towards accuracy, slower but still fast'
    },
}

# Default model
CURRENT_MODEL = 'yolo11s'

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
    global counter, camera_url, is_running, current_camera_id
    
    if counter is not None:
        counter.stop()
        
    # Retrieve zones and their last counts from the database
    with app.app_context():
        # Get current camera
        if current_camera_id is None:
            camera = Camera.query.filter_by(active=True).first()
            if camera:
                current_camera_id = camera.id
            else:
                print("No active cameras found")
                return
        else:
            camera = Camera.query.get(current_camera_id)
            if not camera or not camera.active:
                print("Selected camera not available")
                return
        
        # Get zones for current camera
        active_zones = Zone.query.filter_by(
            active=True, 
            camera_id=current_camera_id
        ).order_by(Zone.id).all()
        
        active_zone_ids = [zone.id for zone in active_zones]

        latest_counts = db.session.query(
            ZoneCount,
            Zone.name,
            Zone.camera_id
        ).join(
            Zone,
            ZoneCount.zone_id == Zone.id
        ).filter(
            Zone.id.in_(active_zone_ids),
            Zone.camera_id == current_camera_id
        ).filter(
            ZoneCount.id.in_(
                db.session.query(func.max(ZoneCount.id))
                .group_by(ZoneCount.zone_id)
            )
        ).all()
        
        # Create a dictionary of last counts by zone_id using joined results
        last_counts_dict = {count[0].zone_id: count[0] for count in latest_counts}
        # print("LAST COUNT: ", last_counts_dict[14].exits)
        
        zones_data = []
        for zone in active_zones:
            zone_data = {
                'id': zone.id,
                'points': zone.points,
                'name': zone.name
            }
            
            # Add last known counts if available from joined results
            if zone.id in last_counts_dict:
                last_count = last_counts_dict[zone.id]
                zone_data.update({
                    'initial_entries': last_count.entries,
                    'initial_exits': last_count.exits,
                    'initial_count': last_count.current_count
                })
                # print("ZONE DATA: ", zone_data)
            else:
                # If no previous counts exist, start from 0
                zone_data.update({
                    'initial_entries': 0,
                    'initial_exits': 0,
                    'initial_count': 0
                })
            
            zones_data.append(zone_data)

    counter = PeopleCounterNew(
        video_source=camera.url,
        model_path=AVAILABLE_MODELS[CURRENT_MODEL]['path'],
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
    global current_camera_id
    
    zone_id = request.args.get('zone_id', type=int)
    time_range = request.args.get('range')  # in minutes
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    with app.app_context():
        try:
            # Check if we have an active camera
            if current_camera_id is None:
                return jsonify({"error": "No active camera"}), 400
                
            # Get active zones for current camera
            active_zones = Zone.query.filter_by(
                active=True, 
                camera_id=current_camera_id
            ).order_by(Zone.id).all()
            
            active_zone_ids = [zone.id for zone in active_zones]
            
            if time_range or (start_time and end_time):
                # Calculate time range
                end_dt = datetime.now(pytz.UTC)
                
                if start_time and end_time:
                    # Remove 'Z' and handle timezone
                    start_time = start_time.replace('Z', '+00:00')
                    end_time = end_time.replace('Z', '+00:00')
                    
                    try:
                        start_dt = datetime.fromisoformat(start_time)
                        end_dt = datetime.fromisoformat(end_time)
                    except ValueError:
                        # Fallback for older Python versions
                        start_dt = datetime.strptime(start_time.split('.')[0], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC)
                        end_dt = datetime.strptime(end_time.split('.')[0], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC)
                else:
                    start_dt = end_dt - timedelta(minutes=int(time_range))
                
                stats = {}
                for zone in active_zones:
                    # Get counts within the time range
                    counts_in_range = db.session.query(ZoneCount).filter(
                        ZoneCount.zone_id == zone.id,
                        ZoneCount.timestamp.between(start_dt, end_dt)
                    ).order_by(ZoneCount.timestamp.asc()).all()
                    
                    if counts_in_range:
                        first_count = counts_in_range[0]
                        last_count = counts_in_range[-1]
                        
                        entries_diff = last_count.entries - first_count.entries
                        exits_diff = last_count.exits - first_count.exits
                        peak_count = max(c.current_count for c in counts_in_range)
                        
                        stats[zone.id] = {
                            'name': zone.name,
                            'entry': entries_diff,
                            'exit': exits_diff,
                            'peak': peak_count,
                            'current': last_count.current_count,
                            'camera_id': zone.camera_id
                        }
                    else:
                        stats[zone.id] = {
                            'name': zone.name,
                            'entry': 0,
                            'exit': 0,
                            'peak': 0,
                            'current': None,
                            'camera_id': zone.camera_id
                        }
                
                return jsonify(stats)
            else:
                # Get latest counts for current camera's zones
                latest_counts = db.session.query(
                    ZoneCount,
                    Zone.name,
                    Zone.camera_id
                ).join(
                    Zone,
                    ZoneCount.zone_id == Zone.id
                ).filter(
                    Zone.id.in_(active_zone_ids),
                    Zone.camera_id == current_camera_id
                ).filter(
                    ZoneCount.id.in_(
                        db.session.query(func.max(ZoneCount.id))
                        .group_by(ZoneCount.zone_id)
                    )
                ).all()

                stats = {}
                for count, zone_name, camera_id in latest_counts:
                    stats[count.zone_id] = {
                        'name': zone_name,
                        'entry': count.entries,
                        'exit': count.exits,
                        'current': count.current_count,
                        'camera_id': camera_id
                    }
                
                return jsonify(stats)
                    
        except Exception as e:
            print(f"Error in get_stats: {str(e)}")
            return jsonify({"error": "Server error"}), 500


@app.route('/zones', methods=['GET', 'POST'])
def manage_zones():
    """Get or set zone configurations"""
    global counter, current_camera_id
    
    if request.method == 'POST':
        try:
            zones_data = request.json
            print("Received zones data:", zones_data)
            
            # Check if we have an active camera
            if current_camera_id is None:
                return jsonify({
                    "status": "error", 
                    "message": "No active camera selected"
                }), 400
            
            with app.app_context():
                try:
                    # Get existing zones indexed by ID for current camera
                    existing_zones = {
                        zone.id: zone 
                        for zone in Zone.query.filter_by(camera_id=current_camera_id).all()
                    }
                    
                    # Track which zones to keep active
                    zones_to_update = []
                    
                    for zone_data in zones_data:
                        try:
                            # Convert points to proper format
                            points = []
                            for point in zone_data['points']:
                                if isinstance(point, dict) and 'x' in point and 'y' in point:
                                    points.append([int(point['x']), int(point['y'])])
                                elif isinstance(point, list) and len(point) == 2:
                                    points.append([int(point[0]), int(point[1])])
                                else:
                                    raise ValueError(f"Invalid point format: {point}")
                            
                            zone_name = zone_data.get('name', f'Zone {len(zones_to_update)+1}')
                            zone_id = zone_data.get('id')
                            
                            if zone_id and zone_id in existing_zones:
                                # Update existing zone
                                zone = existing_zones[zone_id]
                                zone.points = points
                                zone.name = zone_name
                                zone.active = True
                                zones_to_update.append(zone)
                            else:
                                # Create new zone with camera_id
                                zone = Zone(
                                    name=zone_name,
                                    points=points,
                                    active=True,
                                    camera_id=current_camera_id
                                )
                                db.session.add(zone)
                                zones_to_update.append(zone)
                            
                        except Exception as e:
                            print(f"Error processing zone data:", e)
                            raise ValueError(f"Invalid zone data: {str(e)}")
                    
                    # Deactivate zones not in the update for current camera only
                    for zone in existing_zones.values():
                        if zone not in zones_to_update:
                            zone.active = False
                    
                    # Commit changes
                    db.session.commit()
                    
                    # Update counter with active zones
                    with lock:
                        if counter is not None:
                            zone_configs = [{
                                'points': zone.points,
                                'name': zone.name,
                                'id': zone.id
                            } for zone in zones_to_update]
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
                zones = current_camera_id.all()
                return jsonify([zone.to_dict() for zone in zones])
        except Exception as e:
            print(f"Error fetching zones: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500
        
@app.route('/zones/<int:zone_id>', methods=['PUT', 'DELETE'])
def manage_single_zone(zone_id):
    """Manage individual zone operations"""
    global counter
    
    try:
        with app.app_context():
            zone = Zone.query.filter_by(camera_id=current_camera_id).get(zone_id)
            if not zone:
                return jsonify({"status": "error", "message": "Zone not found"}), 404

            if request.method == 'DELETE':
                # Deactivate zone instead of deleting
                zone.active = False
                db.session.commit()
                
                # Update counter
                with lock:
                    if counter is not None:
                        counter.delete_zone(zone_id)
                
                return jsonify({"status": "success"})

            elif request.method == 'PUT':
                data = request.json
                
                # Update zone in database
                if 'name' in data:
                    zone.name = data['name']
                if 'points' in data:
                    zone.points = data['points']
                db.session.commit()
                
                # Update counter
                with lock:
                    if counter is not None:
                        last_count = ZoneCount.query.filter_by(zone_id=zone_id).order_by(ZoneCount.timestamp.desc()).first()
                        counter.update_single_zone(
                            zone_id,
                            name=zone.name,
                            points=zone.points,
                            initial_entries=last_count.entries if last_count else 0,
                            initial_exits=last_count.exits if last_count else 0,
                            initial_count=last_count.current_count if last_count else 0
                        )
                
                return jsonify({"status": "success"})
                
    except Exception as e:
        print(f"Error managing zone {zone_id}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/zones/new', methods=['POST'])
def add_zone():
    """Add a new zone"""
    global counter, current_camera_id
    
    try:
        data = request.json
        with app.app_context():
            points = []
            for point in data['points']:
                if isinstance(point, dict) and 'x' in point and 'y' in point:
                    points.append([int(point['x']), int(point['y'])])
                elif isinstance(point, list) and len(point) == 2:
                    points.append([int(point[0]), int(point[1])])
                else:
                    raise ValueError(f"Invalid point format: {point}")
            # Create new zone in database
            zone = Zone(
                name=data.get('name', f'Zone {Zone.query.filter_by(camera_id=current_camera_id).count() + 1}'),
                points=points,
                active=True,
                camera_id=current_camera_id  # Add this line
            )
            db.session.add(zone)
            db.session.commit()
            
            # Add to counter
            with lock:
                if counter is not None:
                    counter.add_single_zone(
                        points=zone.points,
                        name=zone.name,
                        id=zone.id
                    )
            
            return jsonify({"status": "success", "zone_id": zone.id})
            
    except Exception as e:
        print(f"Error adding zone: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setup-polygons', methods=['GET'])
def setup_polygons():
    """Handle polygon setup page"""
    try:
        with app.app_context():
            zones = Zone.query.filter_by(active=1, camera_id=current_camera_id).all()
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
                    # print("STATS FROM COUNTER", stats)
                
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
        
@app.route('/graph-data', methods=['GET'])
def get_graph_data():
    """Get historical data for graph visualization"""
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        with app.app_context():
            # Get active zones first
            active_zones = Zone.query.filter_by(active=True, camera_id=current_camera_id).all()
            
            # Convert times to UTC datetime
            start_dt = datetime.fromisoformat(start_time).replace(tzinfo=pytz.UTC) if start_time else None
            end_dt = datetime.fromisoformat(end_time).replace(tzinfo=pytz.UTC) if end_time else None
            
            # Build query
            query = ZoneCount.query
            if start_dt:
                query = query.filter(ZoneCount.timestamp >= start_dt)
            if end_dt:
                query = query.filter(ZoneCount.timestamp <= end_dt)
            
            # Get data for each zone
            data = {}
            for zone in active_zones:
                zone_counts = query.filter_by(zone_id=zone.id).order_by(ZoneCount.timestamp).all()
                data[zone.id] = {
                    'name': zone.name,
                    'entries': [{'t': count.timestamp.isoformat(), 'y': count.entries} for count in zone_counts],
                    'exits': [{'t': count.timestamp.isoformat(), 'y': count.exits} for count in zone_counts],
                    'current': [{'t': count.timestamp.isoformat(), 'y': count.current_count} for count in zone_counts]
                }
            
            return jsonify(data)
            
    except Exception as e:
        print(f"Error getting graph data: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/graph')
def show_graph():
    """Render graph visualization page"""
    return render_template('graph.html')

@app.route('/model', methods=['GET', 'POST'])
def manage_model():
    """Get or set the model configuration"""
    global CURRENT_MODEL, counter
    
    if request.method == 'POST':
        try:
            data = request.json
            model_key = data.get('model')
            
            if model_key not in AVAILABLE_MODELS:
                return jsonify({'error': 'Invalid model selection'}), 400
            
            CURRENT_MODEL = model_key
            
            # Reinitialize counter with new model
            with lock:
                if counter is not None:
                    counter.stop()
                initialize_counter()
            
            return jsonify({
                'status': 'success',
                'message': f'Model changed to {model_key}',
                'description': AVAILABLE_MODELS[model_key]['description']
            })
        except Exception as e:
            print(f"Error changeing model: {e}")
            return jsonify({"error": str(e)}), 500
            
    elif request.method == 'GET':
        return jsonify({
            'current': CURRENT_MODEL,
            'available': AVAILABLE_MODELS,
            'description': AVAILABLE_MODELS[CURRENT_MODEL]['description']
        })
    
@app.route('/cameras', methods=['GET', 'POST'])
def manage_cameras():
    """Manage camera sources"""
    global current_camera_id
    
    if request.method == 'POST':
        try:
            data = request.json
            with app.app_context():
                camera = Camera(
                    name=data['name'],
                    url=data['url']
                )
                db.session.add(camera)
                db.session.commit()
                
                # Set as current if no camera is selected
                if current_camera_id is None:
                    current_camera_id = camera.id
                    initialize_counter()
                
                return jsonify(camera.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'GET':
        try:
            with app.app_context():
                cameras = Camera.query.filter_by(active=True).all()
                return jsonify({
                    'cameras': [c.to_dict() for c in cameras],
                    'current': current_camera_id
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
@app.route('/cameras/<int:camera_id>', methods=['PUT', 'DELETE'])
def manage_single_camera(camera_id):
    """Manage individual camera"""
    global current_camera_id, counter
    
    try:
        with app.app_context():
            camera = Camera.query.get(camera_id)
            if not camera:
                return jsonify({"error": "Camera not found"}), 404
                
            if request.method == 'DELETE':
                camera.active = False
                db.session.commit()
                
                if current_camera_id == camera_id:
                    # Switch to another camera if available
                    another_camera = Camera.query.filter_by(active=True).first()
                    if another_camera:
                        current_camera_id = another_camera.id
                        initialize_counter()
                    else:
                        current_camera_id = None
                        if counter:
                            counter.stop()
                
                return jsonify({"status": "success"})
                
            elif request.method == 'PUT':
                data = request.json
                if 'name' in data:
                    camera.name = data['name']
                if 'url' in data:
                    camera.url = data['url']
                    if current_camera_id == camera_id:
                        initialize_counter()  # Reinitialize with new URL
                db.session.commit()
                return jsonify(camera.to_dict())
                
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/cameras/switch/<int:camera_id>', methods=['POST'])
def switch_camera(camera_id):
    """Switch to a different camera"""
    global current_camera_id, counter
    
    try:
        with app.app_context():
            camera = Camera.query.get(camera_id)
            if not camera or not camera.active:
                return jsonify({"error": "Camera not found"}), 404
            
            current_camera_id = camera.id
            initialize_counter()
            
            return jsonify({
                "status": "success",
                "message": f"Switched to camera: {camera.name}"
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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