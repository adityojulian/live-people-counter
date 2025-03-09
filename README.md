# Live People Counter from CCTV Footage

## Table of Contents
[1. Database Structure and Diagram]()
 

## 1. Database Structure and Diagram

The system uses **SQLite** to store data related to **zones** and **counting logs**.

### Database Schema

-   **Zone Table (`Zone`)**
    -   Stores **polygonal areas** (zones) where counting occurs.
    -   Fields: `id`, `name`, `points`, `created_at`, `active`
-   **Zone Count Table (`ZoneCount`)**
    -   Stores **entry/exit counts** for each zone.
    -   Fields: `id`, `zone_id (id, foreign from Zone table)`, `timestamp`, `entries`, `exits`, `current_count`


-   The **`Zone`** table stores **polygon coordinates** and **zone name**.
-   The **`ZoneCount`** table tracks **how many people enter/exit each zone**.
-   When a person is detected inside a zone:
    -   The **entry count** increases when a person **enters**.
    -   The **exit count** increases when a person **leaves**.
-   This ensures that **historical zone data** is stored for analytics.

## 2. Object Detection & Tracking Process
This mechanism is heavily influenced by the `PoepleCounterNew()` class. The documentation for this class can be found [here](https://github.com/adityojulian/live-people-counter/tree/main/modules). In general, the implementation utilizes multi-threading for capturing frame from CCTV, inferencing, and output generating. There are several queues being utilized to support the multi-threading implementation: `frame_queue`, `results_queue`, and `output_queue`. These queues ensure real-time processing for the system. 
### **Step-by-Step Process**

1.  **Capture Video Frames**
    -   Reads frames from a [**live CCTV footage**](https://cctvjss.jogjakota.go.id/malioboro/NolKm_Utara.stream/playlist.m3u8).
2.  **Detect People with YOLO**
    
    -  Runs **YOLO object detection** to find **people in the frame**.
    - By default, the model being used is the yolo11-small or `yolo11s` from [Ultralytics](https://docs.ultralytics.com/models/yolo11/). If the program becomes too heavy to run, try changing to a smaller model by modifying the `Dockerfile` like as specified [here]().
3.  **Track Individuals with ByteTrack**
    -   Assigns **unique tracking IDs** to detected people.
4.  **Check If Inside a Zone**
    -   Extracts the **centroid of the bounding box**.
    -   Uses **OpenCV polygon test** to determine if a person is inside a polygon zone.
5.  **Update Counter & Store Data**
    -   Updates **entry/exit counts** for each zone. A person is considered to have entered the zone if and only if their state change from `isInside() = False` to `isInside() = True`. These states are stored in a variable for each detected and tracked person, though it only stores the last five states. Automatic deletion or popping is implemented for this variable.
    -   Saves the **zone count logs** to the database.
6.  **Generate Overlay & Stream to Web**
    
    -   Draws **bounding boxes and counters** on the video.
    -   Streams the **processed video** to the web dashboard.

## 3. Video/Dataset Source

The **video stream** is obtained from **CCTV cameras**.

-   **Example CCTV Source:**
    
    ```plaintext
    https://cctvjss.jogjakota.go.id/malioboro/NolKm_Utara.stream/playlist.m3u8 # Currently used
    ```

## 4. API Endpoints
A more detailed  API documentation can be found [here]().
| Endpoint | Method | Description | 
|------------------------|--------|------------------------------------------------------| 
| **Video Streaming** | 
 |  `/video_feed` | `GET` | Stream processed video with detection and tracking. |
| **Zone Management** |
 | `/zones` | `GET` | Get a list of active counting zones. | 
 | `/zones` | `POST` | Create or update multiple counting zones. |
 | `/zones/<zone_id>` | `PUT` | Update an existing zone. | 
 | `/zones/<zone_id>` | `DELETE` | Deactivate a zone. | | `/zones/new` | `POST` | Create a new zone. |
 | **People Count Statistics** |
 | `/stats` | `GET` | Retrieve the latest or historical zone statistics. |
 | `/graph-data` | `GET` | Get historical data for visualization. |

## 7. Dashboard Overview**

-   **Live Video Feed** 📹
    - Displays **real-time people tracking** with a bounding box.
    - Displays all zone in the live feed.
- **Zone Configuration** 🔳
	- User can draw and add a new zone from the dashboard.
	- User can rename or delete existing zone from the dashboard.
-   **Zone Statistics** 📊
    - It shows **entry/exit counts** for each zone.
    - It also shows the number of people who are currently in the zone.
    - Zone statistics can be filtered using quick presets (e.g., last 5s, last 1m, last 1h) or a custom datetime range.
-   **Graph Visualization** 📈
    -   Provides **historical trends** of people movement with datetime range filters.

## 8. How to Run the System
### Pre-requisites
-  [Docker](https://docs.docker.com/get-docker/)
-  [Docker Compose](https://docs.docker.com/compose/install/)
- NVIDIA GPU with CUDA support (recommended)


### **Using Docker (Recommended)**

1.  **Clone the repository**
    
    ```bash
    git clone https://github.com/adityojulian/live-people-counter.git
    cd live-people-counter
    ```
    
2.  **Start the system**
    
    ```bash
    docker-compose up --build
    ```
    
3.  **Access the web dashboard**
    
    -   Open: **[http://localhost:5000](http://localhost:5000/)**
    - 
### **Changing YOLO Model**

Change to lighter model if the program becomes too heavy to run by modifying the `Dockerfile`:
```Dockerfile
...
# Existing command

# Command to run the application
CMD ["python3", "app.py", "yolov8n"] # To use YOLO8-Nano
``` 

### **Running Without GPU**

If you **don’t have a GPU**, update the `Dockerfile`:

```Dockerfile
FROM python:3.9-slim
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

## **9. Troubleshooting**

### **1. Cannot Access Web Interface**
-   Ensure the container is **running**:
    
    ```bash
    docker-compose ps
    ```
    
-   Check logs:
    ```bash
    docker-compose logs people-counter
    ```
    

### **2. Slow Performance**
-   Verify **GPU acceleration**:
    ```bash
    docker exec -it people-counter_people-counter_1 nvidia-smi
    ```
    

### **3. No Camera Feed**
-   Ensure the **camera URL** is valid.
- Live footage from CCTV can be laggy or not available. Kindly change the URL if that's the case.
----------