# PeopleCounterNew: Real-Time People Detection, Tracking, and Counting

## Overview
The `PeopleCounterNew` class is designed for real-time people detection, tracking, and counting in video streams using [YOLO](https://github.com/ultralytics/ultralytics). It leverages **multi-threading** and **queues** for optimization, ensuring efficient frame capture, inference, and output generation.

## Features
- **Real-time object detection and tracking** using YOLO and ByteTrack.
- **Zone-based counting**, allowing users to define multiple areas of interest.
- **Threading for optimized performance**, with separate threads for:
  - Frame capture
  - Inference
  - Annotated output generation
  - Performance monitoring
- **Queue-based processing** to prevent bottlenecks.
- **Customizable parameters** (confidence threshold, zones, video source, output streaming).
## Walkthrough: How the System Works

### 1. Initialization
When an instance of `PeopleCounterNew` is created:
- The **YOLO model** is loaded into CUDA if available.
- **Thread-safe queues** (`frame_queue`, `results_queue`, `output_queue`) are initialized.
- Video source is prepared, and tracking history is stored.
- User-defined **zones** are processed for people counting.

### 2. Threaded Processing Pipeline
Once `start()` is called, four threads are created:

| Thread | Function |
|--------|----------|
| **Capture Thread** | Reads frames from the video source and puts them in `frame_queue`. |
| **Inference Thread** | Runs YOLO detection and tracking, pushing results into `results_queue`. |
| **Output Thread** | Generates annotated frames and updates people counts. |
| **Monitor Thread** | Prints performance metrics every few seconds. |

### 3. Frame Processing Steps
1. **Capture Frames**  
   - Reads frames from a live streaming footage.
   - Resizes frames for efficient processing.
   - Pushes frames into `frame_queue`.

2. **Inference (YOLO + ByteTrack)**  
   - Retrieves a frame from `frame_queue`.
   - Runs **YOLO detection and ByteTrack tracking**.
   - Stores detected person locations and tracking IDs.
   - Pushes results into `results_queue`.

3. **Zone-Based Counting**  
   - Retrieves processed results from `results_queue`.
   - Checks if each detected person is inside a **user-defined zone**.
   - Updates entry, exit, and current count per zone.
   - Annotates the frame with bounding boxes and statistics.
   - Pushes the annotated frame into `output_queue`.

4. **Output Generation & Streaming**  
   - Reads the latest processed frame.
   - Optionally writes it to a streaming server or file.

5. **Performance Monitoring**  
   - Tracks FPS, processing time, and queue sizes.
   - Ensures smooth operation by avoiding queue overflows.

## Key Class Components

### Initialization (`__init__`)
```python
def __init__(self, video_source=0, model_path="yolov11n.pt", target_fps=30, buffer_size=5, zones=[]):

```

-   `video_source`: Webcam (0) or video file path.
-   `model_path`: Path to YOLO model weights.
-   `target_fps`: Target frame rate.
-   `buffer_size`: Maximum number of frames stored in queues.
-   `zones`: List of predefined zones for people counting.

----------

### Zone Management

#### Add a Zone

```python
def add_zone(self, points, name=None, id=None, initial_entries=0, initial_exits=0, initial_count=0):

```

-   Defines a new **counting zone** with a polygon shape.

#### Update a Zone

```python
def update_single_zone(self, zone_id, **kwargs):

```

-   Modifies an existing zone (e.g., name, shape, counts).

#### Delete a Zone

```python
def delete_zone(self, zone_id):

```

-   Removes a zone from the system.

#### Check if a Point is in a Zone

```python
def point_in_zone(self, point, zone_id):

```

-   Returns `True` if a person is inside a defined zone.

----------

### Threaded Processing Methods

#### Start the System

```python
def start(self):

```

-   Launches **frame capture, inference, output generation, and monitoring** in separate threads.

#### Stop the System

```python
def stop(self):

```

-   Stops all threads and releases resources.

#### Capture Frames (Capture Thread)

```python
def capture_frames(self):

```

-   Reads frames from the video source and adds them to `frame_queue`.

#### Process Frames (Inference Thread)

```python
def process_frames(self):

```

-   Runs YOLO detection and tracking on frames from `frame_queue`.
-   Outputs results to `results_queue`.

#### Generate Annotated Output (Output Thread)

```python
def generate_output(self):

```

-   Overlays bounding boxes and statistics onto frames.
-   Updates **people count per zone**.
-   Pushes annotated frames into `output_queue`.

#### Monitor Performance (Monitor Thread)

```python
def monitor_performance(self):

```

-   Logs **FPS, processing time, and queue sizes** every 5 seconds.

## Optimization Techniques

### 1. **Multithreading**

Using **separate threads** for capture, inference, output, and monitoring ensures that:

-   Frame processing is **non-blocking**.
-   The system remains **responsive** even under high load.

### 2. **Queue-Based Processing**

Three queues help **decouple** different stages:

| Queue| Purpose |
|--------|----------|
| `frame_queue` | Stores captured frames before processing.. |
| `results_queue` | Holds detection and tracking results. |
| `output_queue` | Stores annotated frames for display or streaming. |

### 3. **GPU Acceleration**

-   YOLO inference runs on **CUDA** if available (`torch.cuda.is_available()`).
-   `torch.backends.cudnn.benchmark = True` optimizes performance.

### 4. **Adaptive Frame Skipping**

-   If `frame_queue` is **full**, new frames are skipped to **maintain real-time processing**.

----------

## Performance Metrics

The **monitor thread** prints live system stats:

```
Performance: 29.5 FPS (instant), 28.7 FPS (average)
Processing time: 33.9ms per frame
Capture queue: 5/5, Results queue: 5/5, Output queue: 5/5
--------------------------------------------------

```