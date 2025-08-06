# Learning App - Setup and Usage Guide

This guide provides a comprehensive overview of the Learning App, a system designed for AI-assisted learning through PDF document interaction. It covers the architecture, setup, configuration, and usage of both the backend and frontend components.

## 🚀 Project Overview

The Learning App consists of two main parts:

1.  **Backend (FastAPI)**: A Python-based server that handles all core logic, including PDF processing, AI model interactions (Google Gemini), user authentication, and API endpoints.
2.  **Frontend (Next.js)**: A React-based web application that provides the user interface for interacting with the backend, including PDF uploads, chat, and learning tools.

The application allows users to upload PDFs, ask questions about the content, receive AI-generated answers, and evaluate their own knowledge through quizzes.


## ✨ Key Features


-   **Question Generation & Evaluation**: Generate questions from the PDF content and evaluate user-provided answers for accuracy and detail.
-   **Quiz Functionality**: Submit a set of answers to be evaluated and receive overall feedback and study suggestions.

-   **Optimized Performance**: Backend is configured for high performance using `uvloop` (Unix) or `WindowsProactorEventLoop` (Windows).

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

-   **Python 3.11+**: For the backend.
-   **Node.js 18+ & npm **: For the frontend.
-   **Git**: For cloning the repository.

## ⚙️ Setup Guide

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/learning.git
cd learning
```

### 2. Backend Setup

The backend is the heart of the application, responsible for all data processing and AI interactions.

#### 2.1. Navigate to Backend Directory

```bash
cd backend
```

#### 2.2. Create and Activate a Virtual Environment (Recommended)

```bash
# Create
python -m venv venv

# Activate
# On Windows
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

#### 2.3. Install Dependencies

Choose the appropriate `requirements.txt` file for your operating system.

```bash
# For Windows
pip install -r requirements_windows.txt

# For macOS/Linux
pip install -r requirements.txt
```

-   **`LOGIN_USERNAME` / `LOGIN_PASSWORD`**: Credentials for accessing the backend's protected routes.
-   **`GEMINI_API_KEY`**: Your API key from Google AI Studio. **Note**: If `api_rotation/API_Keys.txt` is populated, this single key will be overridden by the rotation system.
-   **`GEMINI_MODEL`**: The specific Gemini model to use for AI tasks.

#### 2.5. Understanding `backend/config/settings.py`

This central configuration file defines how your backend application behaves.

-   **`HOST = "0.0.0.0"`**: Binds the server to all network interfaces, allowing it to be accessed from other machines on your local network using its IP address.
-   **`PORT = 8000`**: The default port the server will run on.
-   **`BOOKS_DIR = "S:\\software\\PDFFiles"`**: **⚠️ Important!** This is the directory where uploaded PDFs will be stored. **You must ensure this directory exists on your system and is writable.** Change the path to a suitable location for your setup.
-   **`CORS_ORIGINS`**: A list of allowed origins for cross-origin requests. It's dynamically configured to include common development URLs (`localhost`, `127.0.0.1`) and your machine's detected IP, allowing the frontend to connect seamlessly.
-   **`GEMINI_API_KEY` / `GEMINI_MODEL`**: Default values that can be overridden by the `.env` file.

#### 2.6. Running the Backend

You have two primary scripts to start the server:


 Optimized Mode (`python start_optimized.py`)

This is suitable for production-like environments or when you don't need the automatic frontend configuration.

-   **Performance-focused**: Uses performance-oriented settings and event loops.
-   You will need to manually configure ip `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env`.
-   **Command**: `python start_optimized.py`

#### 2.7. Windows Firewall Configuration (If Applicable)

If you are on Windows and want to access the backend from other devices, you may need to allow port `8000` through the firewall.

1.  Right-click on [`setup_firewall.bat`](setup_firewall.bat) and select "Run as administrator".
2.  This script will add the necessary rules to your Windows Firewall.

### 3. Frontend Setup

The frontend provides the user interface for interacting with the backend services.

#### 3.1. Navigate to Frontend Directory

```bash
cd ../frontend
```

#### 3.2. Install Dependencies

```bash
npm install
# or
yarn install
```

#### 3.3. Configure Frontend Environment (`frontend/.env`)

The frontend needs to know the URL of your backend API.

```env
# frontend/.env
NEXT_PUBLIC_API_BASE_URL=http://YOUR_BACKEND_IP:8000/api
```

-   **`NEXT_PUBLIC_API_BASE_URL`**: This variable is crucial. It tells the frontend where to find the backend.
    -   If you ran the backend in **Development Mode** (`python run.py`), this file will be **automatically updated** with your correct local IP address.
    -   If you ran the backend in **Optimized Mode** or are deploying, you **must manually set this** to the IP address or domain of your backend server.

#### 3.4. Running the Frontend

Start the Next.js development server:

```bash
npm run dev
# or
yarn dev
```

The application will typically be available at `http://localhost:3000`and System Ip


## 🚀 Usage

1.  **Access the Application**: Open your browser and go to `http://localhost:3000` (or the configured frontend URL).
2.  **Login**: Use the `LOGIN_USERNAME` and `LOGIN_PASSWORD` you set in your `backend/.env` file.
3.  **Upload a PDF**: Navigate to the upload page and select a PDF file from your computer. It will be saved in the `BOOKS_DIR` you configured in `settings.py`.
4.  **Select a PDF**: Choose the uploaded PDF from the list to make it active for AI interactions.
5.  **Interact**:
    -   **Chat**: Ask questions about the PDF's content in the chat interface.
    -   **Q&A**: Generate questions or submit your own answers for evaluation.
    -   **Quiz**: Take a quiz based on the document and receive detailed feedback.

## 🛠️ Troubleshooting

-   **"Connection Refused" or CORS Errors**:
    -   Ensure the backend server is running.
    -   Verify that `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env` is correct, especially the IP address.
    -   If on Windows, confirm you've run [`setup_firewall.bat`](setup_firewall.bat) as an administrator.
-   **Backend Won't Start**:
    -   Check that all Python dependencies are installed.
    -   Ensure the `BOOKS_DIR` in [`backend/config/settings.py`](backend/config/settings.py) exists and is writable.
    -   Look for error messages in the terminal.
-   **API Issues (e.g., "Invalid API Key")**:
    -   Confirm your `GEMINI_API_KEY` in `backend/.env` is valid.
    -   If using API rotation, ensure [`api_rotation/API_Keys.txt`](api_rotation/API_Keys.txt) contains valid keys.
-   **Frontend Shows "Page Not Found"**:
    -   Make sure you are running the frontend from the `frontend/` directory.

## 📂 Project Structure

```
.
├── README.md                   # This guide
├── setup_firewall.bat          # Windows firewall configuration script
├── update_frontend_env.py      # Script to update frontend .env with backend IP
├── api_rotation/               # API Key Rotation System
│   ├── API_Keys.txt            # List of Gemini API keys (one per line)
│   ├── api_key_rotator.py      # Core logic for rotating keys
│   ├── current_index.txt       # Stores the current key index (auto-generated)
│   └── README.md               # Documentation for the rotation system
├── backend/                    # FastAPI Backend Application
│   ├── main.py                 # Main application entry point
│   ├── run.py                  # Development server script (with IP detection)
│   ├── start_optimized.py      # Production-optimized server script
│   ├── requirements*.txt       # Python dependencies
│   ├── config/                 # Application configuration
│   │   └── settings.py         # Core settings (paths, API keys, CORS)
│   ├── routes/                 # API endpoint definitions (auth, pdf, chat)
│   ├── services/               # Business logic and AI interaction handlers
│   ├── models/                 # Pydantic data models
│   ├── utils/                  # Utility functions (cache, IP detection)
│   ├── cache/                  # Application cache storage
│   └── logs/                   # Application log files
├── frontend/                   # Next.js Frontend Application
│   ├── package.json            # Node.js dependencies and scripts
│   ├── next.config.ts          # Next.js configuration
│   ├── .env                    # Frontend environment variables (auto-generated by backend)
│   ├── .env.example            # Example .env file
│   ├── src/                    # Frontend source code
│   │   ├── app/                # Next.js pages and layouts
│   │   ├── components/         # Reusable React components
│   │   ├── contexts/           # React contexts (e.g., for authentication)
│   │   └── lib/                # Utility functions and API client
│   └── public/                 # Static assets (images, etc.)
└── books/                      # Default directory for uploaded PDFs (configurable in settings.py)
