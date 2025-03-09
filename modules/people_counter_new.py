from collections import defaultdict
import cv2
import numpy as np
import torch
from ultralytics import YOLO
import threading
import time
from queue import Queue

class PeopleCounterNew:
    def __init__(self, video_source=0, model_path="yolov11n.pt", 
                 target_fps=30, buffer_size=5, zones=[]):
        """Initialize the people counter system with optimized pipeline."""
        # Threading and queues
        self.frame_queue = Queue(maxsize=buffer_size)
        self.results_queue = Queue(maxsize=buffer_size)
        self.output_queue = Queue(maxsize=buffer_size)
        self.stop_event = threading.Event()
        
        # Initialize YOLO model
        self.model = YOLO(model_path)
        if torch.cuda.is_available():
            self.model.to('cuda')
            torch.backends.cudnn.benchmark = True  # Enable for improved performance
        
        # Model parameters
        self.model.conf = 0.5  # Confidence threshold
        self.model.iou = 0.45  # NMS IOU threshold
        
        # Video parameters
        self.video_source = video_source
        self.target_fps = target_fps
        self.cap = None  # Will be initialized in the capture thread
        
        # Initialize tracking and counting
        self.polygons = {}  # {zone_id: {points: [], name: str, entry: int, exit: int, current: int}}
        self.track_history = defaultdict(lambda: {})  # {track_id: {zone_id: [history]}}
        self.polygon_arrays = {}  # Pre-computed numpy arrays for polygons
        
        # Performance metrics
        self.processing_times = []
        self.frame_count = 0
        self.start_time = None
        self.output_fps = 0
        
        # Output writer
        self.writer = None
        self.output_url = None

        # Add initial zones
        self.update_zones(zones)

    def set_output(self, output_url):
        """Set output streaming URL"""
        self.output_url = output_url

    def add_zone(self, points, name=None, id=None, initial_entries=0, initial_exits=0, initial_count=0):
        """Add a new counting zone with initial counts."""
        zone_id = id if id is not None else len(self.polygons)
        # Convert points to integers if they aren't already
        points = [[int(x), int(y)] for x, y in points]
        
        self.polygons[zone_id] = {
            "points": points,
            "name": name or f"Zone {zone_id + 1}",
            "entry": initial_entries,
            "exit": initial_exits,
            "current": 0
        }
        self.polygon_arrays[zone_id] = np.array(points)
        return zone_id
    
    def update_zones(self, zones_data):
        """Update zones from web interface data."""
        self.clear_zones()
        for zone in zones_data:
            # Convert points format if needed
            if isinstance(zone.get('points', [])[0], dict):
                points = [[p['x'], p['y']] for p in zone['points']]
            else:
                points = zone['points']
            
            # Add zone with initial counts if available
            self.add_zone(
                points=points,
                name=zone.get('name', f'Zone {len(self.polygons) + 1}'),
                id=zone.get('id'),
                initial_entries=zone.get('initial_entries', 0),
                initial_exits=zone.get('initial_exits', 0),
                initial_count=zone.get('initial_count', 0)
            )
            
    def add_single_zone(self, points, name=None, id=None, initial_entries=0, initial_exits=0, initial_count=0):
        """Add a single new counting zone without affecting existing zones."""
        zone_id = id if id is not None else max(self.polygons.keys(), default=-1) + 1
        points = [[int(x), int(y)] for x, y in points]
        
        self.polygons[zone_id] = {
            "points": points,
            "name": name or f"Zone {zone_id + 1}",
            "entry": initial_entries,
            "exit": initial_exits,
            "current": initial_count
        }
        self.polygon_arrays[zone_id] = np.array(points)
        return zone_id

    def update_single_zone(self, zone_id, **kwargs):
        """Update an existing zone's properties without affecting other zones."""
        if zone_id not in self.polygons:
            raise ValueError(f"Zone {zone_id} does not exist")
            
        if 'points' in kwargs:
            points = [[int(x), int(y)] for x, y in kwargs['points']]
            self.polygons[zone_id]['points'] = points
            self.polygon_arrays[zone_id] = np.array(points)
            
        if 'name' in kwargs:
            self.polygons[zone_id]['name'] = kwargs['name']

        # Don't update counts unless explicitly provided
        if 'initial_entries' in kwargs:
            self.polygons[zone_id]['entry'] = kwargs['initial_entries']
        if 'initial_exits' in kwargs:
            self.polygons[zone_id]['exit'] = kwargs['initial_exits']
        if 'initial_count' in kwargs:
            self.polygons[zone_id]['current'] = kwargs['initial_count']

    def delete_zone(self, zone_id):
        """Delete a specific zone without affecting others."""
        if zone_id in self.polygons:
            del self.polygons[zone_id]
            del self.polygon_arrays[zone_id]
            # Clean up track history for this zone
            for track in self.track_history.values():
                if zone_id in track:
                    del track[zone_id]

    def clear_zones(self):
        """Clear all counting zones."""
        self.polygons.clear()
        self.polygon_arrays.clear()
        self.track_history.clear()

    def point_in_zone(self, point, zone_id):
        """Check if a point is inside a specific zone."""
        if zone_id not in self.polygon_arrays:
            return False
        return cv2.pointPolygonTest(self.polygon_arrays[zone_id], point, False) >= 0

    def start(self):
        """Start all processing threads"""
        self.start_time = time.time()
        
        # Start threads
        self.capture_thread = threading.Thread(target=self.capture_frames, daemon=True)
        self.inference_thread = threading.Thread(target=self.process_frames, daemon=True)
        self.output_thread = threading.Thread(target=self.generate_output, daemon=True)
        self.monitor_thread = threading.Thread(target=self.monitor_performance, daemon=True)
        
        self.capture_thread.start()
        self.inference_thread.start()
        self.output_thread.start()
        self.monitor_thread.start()

    def stop(self):
        """Stop all processing threads"""
        self.stop_event.set()
        
        # Wait for threads to finish
        if hasattr(self, 'capture_thread'):
            self.capture_thread.join(timeout=1.0)
        if hasattr(self, 'inference_thread'):
            self.inference_thread.join(timeout=1.0)
        if hasattr(self, 'output_thread'):
            self.output_thread.join(timeout=1.0)
        
        # Release resources
        if self.cap is not None:
            self.cap.release()
        if self.writer is not None:
            self.writer.release()

    def capture_frames(self):
        """Thread function to capture frames from source"""
        # Initialize video capture
        self.cap = cv2.VideoCapture(self.video_source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer to reduce latency
        
        frame_time = 1.0 / self.target_fps
        prev_time = time.time()
        
        while not self.stop_event.is_set():
            current_time = time.time()
            
            # Maintain consistent capture rate
            if current_time - prev_time >= frame_time:
                ret, frame = self.cap.read()
                if not ret:
                    print("Failed to read frame from source")
                    time.sleep(0.1)  # Wait before retrying
                    continue
                
                # Resize for faster processing
                # frame = cv2.resize(frame, (640, 480))
                frame = cv2.resize(frame, (1280, 720))
                
                # If queue is full, skip frame to avoid backing up
                if not self.frame_queue.full():
                    self.frame_queue.put((frame, current_time))
                else:
                    print("Warning: Frame queue full, dropping frame")
                
                prev_time = current_time
            else:
                # Small sleep to avoid busy waiting
                time.sleep(0.001)

    def process_frames(self):
        """Thread function to process frames with YOLO detection and tracking"""
        while not self.stop_event.is_set():
            try:
                # Get frame from queue with timeout
                frame, timestamp = self.frame_queue.get(timeout=0.1)
                
                # Start processing timer
                start_process = time.time()
                
                # Run detection and tracking
                results = self.model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    classes=[0],  # Only detect people
                    verbose=False
                )
                
                # Record processing time
                process_time = time.time() - start_process
                self.processing_times.append(process_time)
                
                # Keep only last 100 measurements for stats
                if len(self.processing_times) > 100:
                    self.processing_times.pop(0)
                
                # Put results in queue if not full
                if not self.results_queue.full():
                    self.results_queue.put((frame, results, timestamp, process_time))
                else:
                    print("Warning: Results queue full, dropping processed frame")
                
                self.frame_count += 1
                
            except Exception as e:
                if not self.stop_event.is_set():  # Only print if not stopping
                    print(f"Error processing frame: {e}")
                    time.sleep(0.1)

    def generate_output(self):
        """Thread function to generate annotated output frames"""
        target_interval = 1.0 / self.target_fps
        last_write_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # Get processed results with timeout
                frame, results, timestamp, process_time = self.results_queue.get(timeout=0.1)
                
                # Create annotated frame
                annotated_frame = frame.copy()
                
                # Reset current counts for all zones
                for zone_data in self.polygons.values():
                    zone_data["current"] = 0
                
                # Process detections if any
                if results and hasattr(results[0].boxes, 'id') and results[0].boxes.id is not None:
                    boxes = results[0].boxes.xywh.cpu().numpy()
                    track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                    
                    # Process each detection
                    for box, track_id in zip(boxes, track_ids):
                        x, y, w, h = box
                        centroid = (int(x), int(y))
                        
                        # Check each zone
                        for zone_id in self.polygons:
                            is_inside = self.point_in_zone(centroid, zone_id)
                            
                            # Initialize track history for this zone
                            if zone_id not in self.track_history[track_id]:
                                self.track_history[track_id][zone_id] = []
                            
                            # Update track history
                            self.track_history[track_id][zone_id].append(is_inside)
                            history = self.track_history[track_id][zone_id]
                            
                            # Update counts
                            if len(history) > 1:
                                if not history[-2] and history[-1]:  # Entered zone
                                    self.polygons[zone_id]["entry"] += 1
                                elif history[-2] and not history[-1]:  # Exited zone
                                    self.polygons[zone_id]["exit"] += 1
                            
                            # Update current count
                            if is_inside:
                                self.polygons[zone_id]["current"] += 1
                            
                            # Limit history length
                            if len(history) > 5:
                                self.track_history[track_id][zone_id].pop(0)
                        
                        # Draw detection box
                        x1, y1 = int(x - w/2), int(y - h/2)
                        x2, y2 = int(x + w/2), int(y + h/2)
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
                        cv2.putText(annotated_frame, f"ID: {track_id}", (x1, y1 - 5),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                # Draw zones and counts
                self._draw_zones(annotated_frame)
                
                # Add performance metrics to frame
                self._add_performance_metrics(annotated_frame, process_time)
                
                # Get stats to return
                stats = self._get_stats()
                
                # Put in output queue
                self.output_queue.put((annotated_frame, stats))
                
                # Write to stream if configured
                current_time = time.time()
                if self.output_url and current_time - last_write_time >= target_interval:
                    self._write_to_stream(annotated_frame)
                    last_write_time = current_time
                
            except Exception as e:
                if not self.stop_event.is_set():  # Only print if not stopping
                    print(f"Error generating output: {e}")
                    time.sleep(0.1)

    def _write_to_stream(self, frame):
        """Write frame to output stream"""
        if self.writer is None:
            # Initialize video writer on first frame
            height, width = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
            self.writer = cv2.VideoWriter(self.output_url, fourcc, self.target_fps, (width, height))
        
        self.writer.write(frame)

    def _draw_zones(self, frame):
        """Draw zones and their stats on the frame."""
        for zone_id, zone_data in self.polygons.items():
            points = self.polygon_arrays[zone_id]
            
            # Draw zone polygon
            cv2.polylines(frame, [points], True, (255, 0, 0), 2)
            
            # Calculate centroid for text placement
            centroid = np.mean(points, axis=0).astype(int)
            
            # Draw zone information
            info = [
                zone_data["name"],
                f"In: {zone_data['entry']} Out: {zone_data['exit']}",
                f"Current: {zone_data['current']}"
            ]
            
            for i, text in enumerate(info):
                cv2.putText(frame, text, (centroid[0], centroid[1] + i*15 - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    def _add_performance_metrics(self, frame, process_time):
        """Add performance metrics to the frame"""
        # Calculate fps
        if self.processing_times:
            avg_process_time = np.mean(self.processing_times)
            self.output_fps = 1.0 / avg_process_time if avg_process_time > 0 else 0
        
        # Add text to frame
        metrics = [
            f"FPS: {self.output_fps:.1f}",
            f"Process time: {process_time*1000:.1f}ms",
            f"Queue sizes: {self.frame_queue.qsize()}/{self.results_queue.qsize()}/{self.output_queue.qsize()}"
        ]
        
        for i, text in enumerate(metrics):
            cv2.putText(frame, text, (10, 20 + i*20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    def _get_stats(self):
        """Get current statistics for all zones."""
        return {
            zone_id: {
                'name': data['name'],
                'entry': data['entry'],
                'exit': data['exit'],
                'current': data['current']
            } for zone_id, data in self.polygons.items()
        }

    def process_frame(self):
        """Process a single frame and return the annotated frame with stats (non-threaded version)."""
        # Check if there's a processed frame available
        try:
            # Non-blocking get
            frame, stats = self.output_queue.get_nowait()
            return frame, stats
        except:
            # Return placeholder if no processed frame is available
            return None, self._get_stats()

    def monitor_performance(self):
        """Thread function to monitor and print performance metrics"""
        while not self.stop_event.is_set():
            time.sleep(5)  # Update every 5 seconds
            
            # Calculate metrics
            if self.processing_times:
                avg_process_time = np.mean(self.processing_times)
                avg_fps = 1.0 / avg_process_time if avg_process_time > 0 else 0
                elapsed = time.time() - self.start_time
                overall_fps = self.frame_count / elapsed if elapsed > 0 else 0
                
                queue_status = (
                    f"Capture queue: {self.frame_queue.qsize()}/{self.frame_queue.maxsize}, "
                    f"Results queue: {self.results_queue.qsize()}/{self.results_queue.maxsize}, "
                    f"Output queue: {self.output_queue.qsize()}/{self.output_queue.maxsize}"
                )
                
                print(f"Performance: {avg_fps:.1f} FPS (instant), {overall_fps:.1f} FPS (average)")
                print(f"Processing time: {avg_process_time*1000:.1f}ms per frame")
                print(queue_status)
                print("-" * 50)