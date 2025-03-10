# API Documentation for Live People Counter

This section provides detailed documentation for all API endpoints in the **Live People Counter** system.

## **📌 Base URL**

By default, the API runs on:
```http
http://localhost:5000
```
If deployed on a server, replace `localhost` with the server IP or domain.

## **📌 API Endpoints Overview**
| Endpoint | Method | Description | 
|------------------------|--------|------------------------------------------------------|
| **Camera Management** |
| `/cameras` | `GET` | Get list of available cameras. |
| `/cameras` | `POST` | Add a new camera. |
| `/cameras/<camera_id>` | `DELETE` | Deactivate a camera. |
| `/cameras/switch/<camera_id>` | `POST` | Switch to a different camera. |
| **Model Management** |
| `/model` | `GET` | Get available models and current selection. |
| `/model` | `POST` | Change the active model. |
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

## **📌 1️⃣ Camera Management**

### **📍 `GET /cameras`**

#### **Description**
Retrieves all available cameras and their configurations.

#### **Response**
```json
{
  "cameras": [
    {
      "id": 1,
      "name": "Malioboro North",
      "url": "https://example.com/stream1.m3u8",
      "active": true
    }
  ],
  "current": 1
}
```

### **📍 `POST /cameras`**

#### **Description**
Adds a new camera source.

#### **Request**
```json
{
  "name": "City Square",
  "url": "https://example.com/stream2.m3u8"
}
```

#### **Response**
```json
{
  "id": 2,
  "name": "City Square",
  "url": "https://example.com/stream2.m3u8",
  "active": true
}
```

#### **Response**
```json
{
  "id": 1,
  "name": "Updated Name",
  "url": "https://example.com/new-stream.m3u8",
  "active": true
}
```

### **📍 `DELETE /cameras/<camera_id>`**

#### **Description**
Deactivates a camera (soft delete).

#### **Response**
```json
{
  "status": "success"
}
```

### **📍 `POST /cameras/switch/<camera_id>`**

#### **Description**
Switches to a different camera source.

#### **Response**
```json
{
  "status": "success",
  "message": "Switched to camera: City Square"
}
```

## **📌 2️⃣ Model Management**

### **📍 `GET /model`**

#### **Description**
Gets available models and current selection.

#### **Response**
```json
{
  "current": "yolov8n",
  "description": "Fastest, lowest accuracy",
  "available": {
    "yolov8n": {
      "path": "yolov8n.pt",
      "description": "Fastest, lowest accuracy"
    },
    "yolo11n": {
      "path": "yolo11n.pt",
      "description": "Balance of speed and accuracy"
    },
    "yolo11s": {
      "path": "yolo11s.pt",
      "description": "Leaning towards accuracy, slower but still fast"
    }
  }
}
```

### **📍 `POST /model`**

#### **Description**
Changes the active model.

#### **Request**
```json
{
  "model": "yolo11s"
}
```

#### **Response**
```json
{
  "status": "success",
  "message": "Model changed to yolo11s",
  "description": "Leaning towards accuracy, slower but still fast"
}
```

## **📌 3️⃣ Video Streaming**

### **📍 `GET /video_feed`**

#### **Description**

Streams the processed video feed with **live detection and tracking**.

#### **Request**

```http
GET /video_feed HTTP/1.1
Host: localhost:5000
```

#### **Response**

-   **Content-Type:** `multipart/x-mixed-replace`
-   **Body:** Returns a **continuous MJPEG video stream**.

#### **Example Usage**
```html
<img src="http://localhost:5000/video_feed">
```

## **📌 4️⃣ Zone Management**

### **📍 `GET /zones`**

#### **Description**

Fetches all **active zones** with their configurations.

#### **Request**

```http
GET /zones HTTP/1.1
Host: localhost:5000
```

#### **Response**

```json
[
  {
    "id": 1,
    "name": "Entrance",
    "points": [[100, 200], [300, 200], [300, 400], [100, 400]],
    "entry": 0,
    "exit": 0,
    "current": 0,
  },
  {
    "id": 2,
    "name": "Exit",
    "points": [[500, 600], [700, 600], [700, 800], [500, 800]]
    "entry": 0,
    "exit": 0,
    "current": 0,
  }
]
```

### **📍 `POST /zones`**

#### **Description**

Creates or updates **multiple zones**.

#### **Request**

```http
POST /zones HTTP/1.1
Content-Type: application/json
```

```json
[
  {
    "id": 1,
    "name": "Entrance",
    "points": [[100, 200], [300, 200], [300, 400], [100, 400]]
  }
]
```

#### **Response**

```json
{"status": "success"}
```

----------

### **📍 `PUT /zones/<zone_id>`**

#### **Description**

Updates **a specific zone**.

#### **Request**

```http
PUT /zones/1 HTTP/1.1
Content-Type: application/json
```

```json
{
  "name": "Main Entrance",
  "points": [[120, 220], [320, 220], [320, 420], [120, 420]]
}
```

#### **Response**

```json
{"status": "success"}
```

----------

### **📍 `DELETE /zones/<zone_id>`**

#### **Description**

Deactivates (soft deletes) a zone.

#### **Request**

```http
DELETE /zones/1 HTTP/1.1
```

#### **Response**

```json
{"status": "success"}
```

----------

### **📍 `POST /zones/new`**

#### **Description**

Creates a new **counting zone**.

#### **Request**

```http
POST /zones/new HTTP/1.1
Content-Type: application/json
```

```json
{
  "name": "Parking Lot",
  "points": [[400, 500], [600, 500], [600, 700], [400, 700]]
}

```

#### **Response**

```json
{"status": "success", "zone_id": 3}
```

----------

## **📌 5️⃣ People Count Statistics**

### **📍 `GET /stats`**

#### **Description**

Retrieves **real-time or historical** people count statistics.

#### **Query Parameters**


| Parameter| Type | Description | 
|------------------------|--------|------------------------------------------------------| 
| `zone_id` | `int` | (Optional) Fetch stats for a specific zone.|
| `start_time` | `String` | (Optional) Start time in ISO format (`YYYY-MM-DDTHH:MM:SSZ`) to determine the starting count|
| `end_time` | `String` | (Optional) End time in ISO format (`YYYY-MM-DDTHH:MM:SSZ`) to determine the end of the count. Later, we substract the count value at `end_time` and `start_time`|

```http
GET /stats?start_time=2024-03-01T00:00:00Z&end_time=2024-03-02T00:00:00Z HTTP/1.1
```

#### **Response**

```json
{
  "1": {
    "name": "Entrance",
    "entry": 25,
    "exit": 20,
    "current": 5
  }
}
```

----------

### **📍 `GET /graph-data`**

#### **Description**

Fetches **historical zone data** for visualization.

#### **Request**

```http
GET /graph-data?start_time=2024-03-01T00:00:00Z&end_time=2024-03-02T00:00:00Z HTTP/1.1
```

#### **Response**

```json
{
  "1": {
    "name": "Entrance",
    "entries": [{"t": "2024-03-01T12:00:00Z", "y": 10}],
    "exits": [{"t": "2024-03-01T12:05:00Z", "y": 8}],
    "current": [{"t": "2024-03-01T12:10:00Z", "y": 2}]
  }
}
```

## **📌 Notes**

-   **All API responses** return `application/json` unless stated otherwise.
-   **Video feeds** return MJPEG streams and should be used in an `<img>` tag.
-   **Data queries** are in **ISO 8601 timestamp format** (UTC).