from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import hashlib
import asyncio
from models.chat import (
    ChatMessage,
    ChatResponse,
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
    QuizSubmissionRequest,
    QuizSubmissionResponse
)
from services.chat_service import ChatService
import sys
import os

# Add the parent directory to the path to import from api_rotation
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from api_rotation.api_key_rotator import api_key_rotator
    ROTATION_AVAILABLE = True
except ImportError:
    ROTATION_AVAILABLE = False

router = APIRouter(prefix="/api/chat", tags=["chat"])

def get_simple_user_id(request: Request) -> str:
    """
    Create a simple user ID based on client IP to isolate users.
    Each user gets their own chat history and PDF context.
    """
    client_ip = request.client.host if request.client else "unknown"
    # Create a simple hash of the IP for session isolation
    user_id = hashlib.md5(client_ip.encode()).hexdigest()[:12]
    return f"user_{user_id}"

class QuestionGenerationRequest(BaseModel):
    topic: Optional[str] = None
    count: Optional[int] = 25
    mode: Optional[str] = "practice"  # "quiz" for MCQ, "practice" for open-ended

@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage, request: Request):
    """Send a message to the AI assistant about the selected PDF - each request processed in parallel"""
    user_session = get_simple_user_id(request)
    
    # Create an independent async task for this request to ensure parallel processing
    # This guarantees that multiple users get responses simultaneously
    task = asyncio.create_task(ChatService.chat(message, user_session))
    return await task

@router.get("/history")
async def get_chat_history(request: Request):
    """Get the chat history for the current session"""
    user_session = get_simple_user_id(request)
    return ChatService.get_chat_history(user_session)

@router.delete("/history")
async def clear_chat_history(request: Request):
    """Clear the chat history for the current session"""
    user_session = get_simple_user_id(request)
    return ChatService.clear_chat_history(user_session)

@router.post("/generate-questions", response_model=ChatResponse)
async def generate_questions(request: QuestionGenerationRequest, http_request: Request):
    """Generate Q&A questions from the selected PDF content, optionally focused on a specific topic - parallel processing"""
    user_session = get_simple_user_id(http_request)
    
    # Create independent async task for parallel processing
    task = asyncio.create_task(ChatService.generate_questions(user_session, request.topic, request.count, request.mode))
    return await task

@router.post("/evaluate-answer", response_model=AnswerEvaluationResponse)
async def evaluate_answer(request: AnswerEvaluationRequest, http_request: Request):
    """Evaluate a single user answer using AI - parallel processing"""
    user_session = get_simple_user_id(http_request)
    
    # Create independent async task for parallel processing
    task = asyncio.create_task(ChatService.evaluate_answer(request, user_session))
    return await task

@router.post("/evaluate-quiz", response_model=QuizSubmissionResponse)
async def evaluate_quiz(request: QuizSubmissionRequest, http_request: Request):
    """Evaluate a complete quiz submission with overall feedback - parallel processing"""
    user_session = get_simple_user_id(http_request)
    
    # Create independent async task for parallel processing
    task = asyncio.create_task(ChatService.evaluate_quiz(request, user_session))
    return await task

@router.get("/api-rotation-status")
async def get_api_rotation_status():
    """Get the current status of API key rotation"""
    if not ROTATION_AVAILABLE:
        return {
            "enabled": False,
            "message": "API key rotation is not available"
        }

    stats = api_key_rotator.get_current_stats()
    return {
        "enabled": True,
        "stats": stats,
        "message": f"API rotation active with {stats['total_keys']} keys"
    }
