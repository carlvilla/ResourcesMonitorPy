# ResourcesMonitorPy
A Python web application for monitoring system resources and processes such as CPU usage, memory consumption or process overhead. The application includes a web interface to display the collected information in real-time and a LLM-powered analysis of the collected data to provide insights and recommendations for optimizing system performance.

## Installation and Usage

The application is formed by two components: a dockerized backend and frontend to persist and display system/processes information, and a Python script to collect the data and send it to the backend. The reason for this separation is to collect information from the processes in the host and not from the docker container. A future implementation will solve this issue.

The installation and deployment of the necessary docker containers and the data collection script can be done by running the following command in the project root:
```bash
./start.sh
```

The system will require a sudo password, this is necessary to collect certain system metrics. Once the containers are running, the web interface can be accessed at `http://localhost:<STREAMLIT_PORT>`, where `STREAMLIT_PORT` is the port defined in the `.env` file (by default, `8088`). Note that the application is constantly collecting and showing data, disable the Auto-refresh option to see an static view of the data and interact easily with the application.

All the applications can be stopped by running the following command in the project root:
```bash
./stop.sh
```

Note that the application and scripts were tested on a MacOS host. Future implementations will be tested on other operating systems. In addition, dates are currently stored and displayed in UTC.

## Environment Variables
The application uses environment variables to configure the Streamlit port and the MySQL database connection. The required environment variables are defined in the `.env.example` file, which can be copied to `.env` and modified as needed. The environment variables include:
- `STREAMLIT_PORT`: The port on which the Streamlit application will run (default: `8088`).
- `MYSQL_HOST`: The hostname of the MySQL database (default: `127.0.0.1`).
- `MYSQL_PORT`: The port on which the MySQL database will run (default: `3307`).
- `MYSQL_NAME`: The name of the MySQL database (default: `resources_monitor_py`).
- `MYSQL_USER`: The username for the MySQL database (default: `monitor`).
- `MYSQL_PASSWORD`: The password for the MySQL database (default: `monitor123`).
- `MYSQL_ROOT_PASSWORD`: The root password for the MySQL database (default: `rootpass`).
- `LLM_MODEL`: The name of the LLM model to be used for analysis.
- `LLM_API_KEY`: The API key for accessing the LLM model.
- `DEBUGPY`: A flag to enable or disable debug mode (default: `0`).
- `DEBUGPY_PORT`: The port on which the debug server will run (default: `8056`).

## Software architecture
See [docs/architecture.md](docs/architecture.md) for an overviewt of the software architecture.

## Testing
The application includes a unit test using Pytest. To run the tests, use the following command in the project root:
```bash
pytest
```

Future implementations will include more unit and integration tests to ensure the robustness of the application.