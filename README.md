# Photo-Reminder — Backend  
Flask · MongoDB · JWT  
> Part of the **Mobile Development (MobDev)** exam project – BSc in Information Engineering (IET), University of Parma (UNIPR).

---

## Table of Contents
1. [Project overview](#project-overview)  
2. [Tech stack](#tech-stack)  
3. [Quick start](#quick-start)  
4. [Configuration](#configuration)  
5. [API reference](#api-reference)  
6. [Data model](#data-model)  
7. [Soft-delete & TTL garbage collection](#soft-delete--ttl)  
8. [License](#license)

---

## Project overview
This micro-REST API stores **photo-markers** (GPS point + camera settings) and user credentials.  
The Android client lives in the companion repo **[`Photo-Reminder`](https://github.com/davekingdoms/Photo-Reminder)** and consumes the endpoints below.

Main features

| Feature | Details |
|---------|---------|
| **JWT authentication** | HS-256, 30-day expiry, `Authorization: Bearer <token>` |
| **User management** | `/register`, `/login` |
| **Marker CRUD** | `/markers` list / create / update / soft-delete |
| **Offline-first sync** | Client marks records `LOCAL_ONLY / DIRTY / PENDING_DELETE`; a background worker pushes & pulls deltas |
| **TTL cleanup** | Soft-deleted docs auto-purged by MongoDB after **15 days** |

---

## Tech stack
* Python 3.12  
* Flask 2.x  
* PyMongo  
* bcrypt  
* PyJWT  

---

## Quick start

### 1 · Clone & install
```bash
git clone https://github.com/<user>/Photo-Reminder-Backend.git
cd Photo-Reminder-Backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 2 · Start MongoDB
Use a local instance on **port 27017** or set `MONGODB_URI` (see below).

### 3 · Run in development
```bash
python app.py
# → http://localhost:5000/
```

The first request creates the **TTL index** on `deleted_at`.

---

## Configuration
All settings are declared in `app.py`.  
You may override them via environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | JWT signing key | hard-coded demo key |
| `MONGODB_URI` | connection string | `mongodb://localhost:27017` |
| `PORT` | Flask port | `5000` |
| `DEBUG` | Flask debug mode | `true` |

Example:

```bash
export SECRET_KEY="REPLACE_ME"
export MONGODB_URI="mongodb://mongo:27017"
python app.py
```

---

## API reference

### Auth
| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| `POST` | `/register` | `{ "username": "...", "password": "..." }` | `{ "message": "...", "token": "..." }` |
| `POST` | `/login`    | same | same |

### Markers (JWT required)
| Method | Endpoint | Query / Body | Success response |
|--------|----------|--------------|------------------|
| `GET`  | `/markers` | `updatedSince=epochMillis` *(optional)* | `{ "markers": [ … ] }` |
| `POST` | `/markers` | Marker JSON | `{ "marker": { … } }` |
| `PUT`  | `/markers/<id>` | Marker JSON (fields to patch) | `{ "marker": { … } }` |
| `DELETE` | `/markers/<id>` | — | `{ "marker": { … } }` |

All timestamps use **epoch-milliseconds UTC**.

---

## Data model
```jsonc
{
  "_id": "60f1…",          // Mongo ObjectId (string on wire)
  "username": "alice",
  "lat": 44.76,
  "lng": 10.31,
  "title": "Sunset bridge",
  "genre": "Street",
  "shutterSpeed": "1/125",
  "aperture": "f/8",
  "iso": "200",
  "focalLength": 35,
  "tag": "GoldenHour",
  "notes": "Tripod on wall",
  "photoUrl": "https://…",  // optional
  "angle": 45.0,
  "created_at": "2025-06-04T18:20:00Z",
  "updated_at": "2025-06-04T18:30:00Z",
  "deleted": false,
  "deleted_at": null        // set only when deleted = true
}
```

---

## Soft-delete & TTL garbage collection
Deleting a marker sets:

```json
{ "deleted": true, "deleted_at": "<utc_datetime>" }
```

A **TTL index** automatically removes these tombstones after **15 days**:

```js
db.markers.createIndex(
  { deleted_at: 1 },
  {
    name: "deleted_ttl_15d",
    expireAfterSeconds: 60*60*24*15,      // 1 296 000 s
    partialFilterExpression: { deleted: true }
  }
)
```

Clients that sync at least once in 15 days will receive the tombstone and purge their local copy; after that window the document disappears permanently.

---


