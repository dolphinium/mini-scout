# Mini Scout

A lightweight alternative to Nightscout for LibreLink Up data, built with FastAPI, Celery, MongoDB, and Chart.js.

## Features

- Fetches glucose data from LibreLink Up every minute
- Stores data in MongoDB for historical viewing
- Displays real-time glucose values and trends
- Visualizes glucose data with interactive charts
- Customizable time ranges and alert thresholds
- Responsive design for desktop and mobile devices

## Technology Stack

- **Backend Framework**: FastAPI
- **Background Tasks/Scheduling**: Celery with Redis
- **Database**: MongoDB
- **API Interaction**: requests (for LibreLink Up)
- **DB Interaction**: pymongo
- **Containerization**: Docker & Docker Compose
- **Frontend**: HTML/CSS/JavaScript with Chart.js

## Prerequisites

- Docker and Docker Compose
- LibreLink Up account credentials

## Setup

1. Clone this repository:
   ```
   git clone <repository-url>
   cd mini_nightscout
   ```

2. Create a `.env` file with your LibreLink Up credentials:
   ```
   LINK_UP_USERNAME=your_email@example.com
   LINK_UP_PASSWORD=your_password
   LINK_UP_REGION=EU  # Change to your region (EU, US, etc.)
   LINK_UP_CONNECTION=  # Optional: Specific patient ID to use
   
   # These can be left as defaults
   MONGO_URI=mongodb://mongo:27017/mini_nightscout
   REDIS_URL=redis://redis:6379/0
   LOG_LEVEL=INFO
   GLUCOSE_FETCH_INTERVAL=60
   ```

3. Build and start the containers:
   ```
   docker-compose up -d
   ```

4. Access the web interface at [http://localhost:8000](http://localhost:8000)

## Project Structure

```
mini_nightscout/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app creation and core setup
│   ├── config.py                # Configuration loading (from env vars)
│   ├── celery_app.py            # Celery application instance setup
│   ├── routers/
│   │   ├── __init__.py
│   │   └── entries.py           # Router for glucose entry endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── librelinkup.py       # Module for LLU API interaction
│   │   └── database.py          # Module for MongoDB connection and operations
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── glucose.py           # Celery task for fetching and saving data
│   └── static/                  # Frontend files
│       ├── index.html
│       ├── css/style.css
│       └── js/script.js
├── Dockerfile                   # Instructions to build the application container
├── docker-compose.yml           # Defines services (app, worker, beat, mongo, redis)
├── .env                         # Stores secrets (LLU credentials, etc.)
└── requirements.txt             # Lists Python dependencies
```

## API Endpoints

- `GET /api/entries/latest` - Get the latest glucose reading
- `GET /api/entries?hours=24` - Get glucose readings for the past 24 hours
- `GET /api/entries/stats?hours=24` - Get glucose statistics for the past 24 hours
- `GET /health` - Health check endpoint
- `GET /test-llu-connection` - Test LibreLink Up connection

## Development

To run the application in development mode:

```
docker-compose up
```

This will start all services with code hot-reloading enabled.

## Troubleshooting

### Connection Issues

If you encounter connection issues with LibreLink Up:

1. Verify your credentials and region in the `.env` file
2. Check the logs for authentication errors:
   ```
   docker-compose logs app
   docker-compose logs worker
   ```
3. Test the connection using the `/test-llu-connection` endpoint

### Database Issues

If you need to reset the database:

```
docker-compose down -v
docker-compose up -d
```

## License

This project is open-source and available under the MIT License.

## Acknowledgments

This project was inspired by Nightscout and uses code adapted from various LibreLink Up API implementations.