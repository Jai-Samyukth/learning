import google.generativeai as genai
from datetime import datetime
from fastapi import HTTPException
from config.settings import settings
from utils.storage import pdf_contexts, chat_histories
from models.chat import (
    ChatMessage,
    ChatResponse,
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
    QuizSubmissionRequest,
    QuizSubmissionResponse,
    QuizAnswer
)
import sys
import os
import logging
import asyncio
import concurrent.futures
from threading import Lock
from utils.logger import chat_logger

# Add the parent directory to the path to import from api_rotation
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from api_rotation.api_key_rotator import api_key_rotator
    ROTATION_ENABLED = True
    logging.info("API key rotation enabled")
except ImportError as e:
    logging.warning(f"API key rotation not available: {e}")
    ROTATION_ENABLED = False

# Thread-safe locks for concurrent access
storage_lock = Lock()
model_cache = {}
model_cache_lock = Lock()

# Thread pool for AI operations - increased for better concurrency
# Each AI request gets its own thread, allowing true parallel processing
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=50)

def get_rotated_model():
    """
    Get a Gemini model instance with a rotated API key.
    Falls back to settings API key if rotation is not available.
    Thread-safe with caching for better performance.
    """
    api_key = None

    if ROTATION_ENABLED:
        api_key = api_key_rotator.get_next_key()
        if not api_key:
            chat_logger.warning("API rotation failed, using settings key")

    # Fallback to settings key if rotation fails or is disabled
    if not api_key:
        api_key = settings.GEMINI_API_KEY

    if not api_key:
        raise HTTPException(status_code=500, detail="No API key available")

    # Cache models by API key for better performance
    with model_cache_lock:
        if api_key not in model_cache:
            genai.configure(api_key=api_key)
            model_cache[api_key] = genai.GenerativeModel(settings.GEMINI_MODEL)
        return model_cache[api_key]

async def generate_content_async(model, context: str) -> str:
    """
    Generate content asynchronously using thread pool to avoid blocking.
    """
    loop = asyncio.get_event_loop()
    try:
        # Run the blocking generate_content in a thread pool
        response = await loop.run_in_executor(
            thread_pool,
            lambda: model.generate_content(context)
        )
        return response.text
    except Exception as e:
        chat_logger.error(f"Error generating AI response: {str(e)}")
        raise

def safe_storage_access(operation, *args, **kwargs):
    """
    Thread-safe wrapper for storage operations.
    """
    with storage_lock:
        return operation(*args, **kwargs)

class ChatService:
    @staticmethod
    async def chat(message: ChatMessage, token: str) -> ChatResponse:
        # Thread-safe check for PDF context
        def check_pdf_context():
            if token not in pdf_contexts:
                raise HTTPException(status_code=400, detail="No PDF selected. Please select a PDF first.")
            return pdf_contexts[token]
        
        pdf_context = safe_storage_access(check_pdf_context)

        # Thread-safe initialization of chat history
        def init_chat_history():
            if token not in chat_histories:
                chat_histories[token] = []
            return chat_histories[token]
        
        chat_history = safe_storage_access(init_chat_history)

        # Check if this is a Q&A generation request (needs full content)
        is_qa_generation = any(keyword in message.message.lower() for keyword in [
            'generate', 'create', 'analyze this document', 'questions', 'sections', 'comprehensive'
        ])

        # Use more content for Q&A generation, limited content for regular chat
        content_limit = 50000 if is_qa_generation else 15000
        pdf_content = pdf_context['content'][:content_limit]

        # Add indication if content was truncated
        content_suffix = "..." if len(pdf_context['content']) > content_limit else ""

        # Get recent chat history safely
        def get_recent_history():
            return chat_histories[token][-3:] if token in chat_histories else []
        
        recent_history = safe_storage_access(get_recent_history)

        # Prepare context for Gemini
        context = f"""
        You are an AI assistant helping students learn from their selected PDF document.

        Document: {pdf_context['filename']}
        Content: {pdf_content}{content_suffix}

        Previous conversation:
        {chr(10).join([f"User: {msg['user']}{chr(10)}Assistant: {msg['assistant']}" for msg in recent_history])}

        Current question: {message.message}

        Please provide a helpful, educational response based on the document content and conversation history.
        """

        try:
            # Generate response using async Gemini with rotated API key
            rotated_model = get_rotated_model()
            ai_response = await generate_content_async(rotated_model, context)

            # Store in chat history thread-safely
            def store_chat_entry():
                chat_histories[token].append({
                    "user": message.message,
                    "assistant": ai_response,
                    "timestamp": datetime.now().isoformat()
                })
            
            safe_storage_access(store_chat_entry)

            return ChatResponse(
                response=ai_response,
                timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            chat_logger.error(f"Failed to generate response for token {token}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to generate response: {str(e)}")

    @staticmethod
    def get_chat_history(token: str) -> dict:
        if token not in chat_histories:
            return {"history": []}

        return {"history": chat_histories[token]}
    
    @staticmethod
    def clear_chat_history(token: str) -> dict:
        if token in chat_histories:
            chat_histories[token] = []
        return {"message": "Chat history cleared"}

    @staticmethod
    async def generate_questions(token: str, topic: str = None, count: int = 25, mode: str = "practice") -> ChatResponse:
        chat_logger.info("Generating questions", 
                        token=token, 
                        topic=topic, 
                        count=count, 
                        mode=mode)
        
        # Get PDF context
        if token not in pdf_contexts:
            chat_logger.error("No PDF context found", token=token)
            raise HTTPException(status_code=400, detail="No PDF selected")
        
        pdf_context = pdf_contexts[token]
        full_content = pdf_context['content']
        
        chat_logger.info("Processing PDF for questions", 
                        filename=pdf_context['filename'],
                        content_length=len(full_content))

        # Check if content is too short
        if len(full_content.strip()) < 100:
            raise HTTPException(status_code=400, detail="Document content is too short to generate meaningful questions")

        # Prepare context for Gemini with full content
        topic_instruction = ""
        if topic and topic.strip():
            topic_instruction = f"""
        SPECIFIC TOPIC FOCUS: "{topic.strip()}"
        Focus your questions specifically on this topic, but use the full document content as context to ensure accuracy and completeness.
        """

        # Format instructions based on mode
        if mode == "quiz":
            format_instruction = """
        FORMAT: Create Multiple Choice Questions (MCQ) with 4 options each.

        CRITICAL JSON REQUIREMENTS:
        - Respond with ONLY a valid JSON object
        - Do not include any text, explanations, or markdown before or after the JSON
        - Use proper JSON syntax with double quotes for all strings
        - Ensure all brackets and braces are properly closed
        - Do not include trailing commas

        EXACT JSON FORMAT (copy this structure):
        {
          "questions": [
            {
              "question": "What is the main concept of Ikigai according to the document?",
              "options": ["A) A Japanese martial art", "B) A reason for being or life purpose", "C) A type of meditation", "D) A business strategy"],
              "correctAnswer": "B"
            },
            {
              "question": "Which of the following is mentioned as a Blue Zone in the document?",
              "options": ["A) Tokyo, Japan", "B) New York, USA", "C) Okinawa, Japan", "D) London, UK"],
              "correctAnswer": "C"
            }
          ]
        }

        MCQ CONTENT REQUIREMENTS:
        - Each question must have exactly 4 options labeled A), B), C), D)
        - Only ONE option should be correct based on the document content
        - Make incorrect options plausible but clearly wrong based on the text
        - Ensure the correctAnswer field contains only the letter (A, B, C, or D)
        - All questions must be answerable from the document content provided
        - Each option should be a complete, standalone answer choice

        JSON SYNTAX RULES:
        - Use double quotes (") for all strings, never single quotes
        - Separate array items with commas, but no comma after the last item
        - Ensure proper nesting of objects and arrays
        - No comments or extra text allowed in JSON
        """
        else:
            format_instruction = """
        FORMAT: Create open-ended questions for practice. Respond with ONLY a valid JSON object:
        {
          "questions": [
            "What is the main concept of Ikigai according to the document?",
            "Explain the characteristics of Blue Zones mentioned in the text.",
            "How does the document relate Ikigai to logotherapy?"
          ]
        }
        """

        context = f"""
        You are an educational AI assistant. Analyze the following document content and create comprehensive questions for learning.

        Document: {pdf_context['filename']}
        {topic_instruction}

        FULL DOCUMENT CONTENT:
        {full_content}

        TASK: Create exactly {count} educational questions based on the document content above{' focusing on the specified topic' if topic and topic.strip() else ''}.

        REQUIREMENTS:
        1. Read and analyze the ENTIRE document content provided above
        2. {'Focus specifically on the topic: "' + topic.strip() + '" while using the full document as context' if topic and topic.strip() else 'Create questions that cover the full scope of the document'}
        3. Include questions about:
           - Key concepts and definitions from the text
           - Important details and facts mentioned
           - Practical applications discussed
           - Examples and case studies provided
           - Critical thinking questions about the content
           - Main themes and ideas
           - Specific processes or methods described
           - Important people, places, or events mentioned
           - Cause and effect relationships
           - Comparisons and contrasts made in the text

        {format_instruction}

        Make sure:
        - Questions are specific to the actual document content provided above
        - Each question can be answered using information from the document
        - Questions progress from basic to advanced understanding
        - {'Focus specifically on the topic "' + topic.strip() + '" while ensuring all questions can be answered from the document content' if topic and topic.strip() else 'Cover all major topics and themes in the document'}
        - Use actual terms, concepts, and examples from the text provided
        - Questions are diverse and cover different aspects of the {'specified topic' if topic and topic.strip() else 'content'}

        Generate exactly {count} questions now based on the full document content provided above{' focusing on the specified topic' if topic and topic.strip() else ''}.
        """

        try:
            # Generate response using Gemini with rotated API key
            chat_logger.info("Sending request to Gemini AI")
            rotated_model = get_rotated_model()
            response = rotated_model.generate_content(context)
            chat_logger.info("Gemini AI response received")

            if not response or not response.text:
                chat_logger.error("No response from Gemini AI")
                raise HTTPException(status_code=500, detail="No response from AI")

            ai_response = response.text.strip()
            chat_logger.info("Gemini AI response received", 
                           response_length=len(ai_response))

            # Clean and validate JSON response
            cleaned_response = ai_response.strip()

            # Remove markdown code blocks if present
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]

            cleaned_response = cleaned_response.strip()

            # Validate that response contains JSON-like structure
            if '{' not in cleaned_response or '}' not in cleaned_response:
                chat_logger.warning("Response doesn't contain JSON structure", response=ai_response)
                
                # Fallback: create a simple question structure
                fallback_questions = [
                    {
                        "question": f"What is the main topic discussed in this document?",
                        "options": ["Main topic", "Secondary topic", "Supporting detail", "Conclusion"],
                        "correct_answer": "Main topic",
                        "explanation": "This is a fallback question based on the document content."
                    }
                ]
                return fallback_questions

            # Try to extract JSON from the response
            import json
            import re

            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', ai_response)
            if json_match:
                try:
                    evaluation_data = json.loads(json_match.group())

                    return ChatResponse(
                        response=json.dumps(evaluation_data),
                        timestamp=datetime.now().isoformat()
                    )
                except json.JSONDecodeError:
                    pass

            # Fallback if JSON parsing fails

                # Ensure it has the expected structure
                if 'questions' not in parsed_json:
                    raise ValueError("JSON missing 'questions' field")

        except Exception as e:
            chat_logger.error("Error generating questions", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")

    @staticmethod
    async def evaluate_answer(request: AnswerEvaluationRequest, token: str) -> AnswerEvaluationResponse:
        """Evaluate a single user answer using AI"""
        if token not in pdf_contexts:
            raise HTTPException(status_code=400, detail="No PDF selected. Please select a PDF first.")

        pdf_context = pdf_contexts[token]

        # Get evaluation level settings
        evaluation_level = request.evaluation_level or "medium"

        # Define evaluation criteria based on level
        if evaluation_level == "easy":
            criteria_text = """
        EVALUATION LEVEL: EASY (Lenient)
        - Focus on basic understanding and effort
        - Give credit for partial answers and good attempts
        - Be encouraging and supportive in feedback

        SCORING SCALE (0-10):
        - 8-10: Shows basic understanding, good effort
        - 6-7: Partially correct, some understanding shown
        - 4-5: Minimal understanding but attempted
        - 2-3: Little understanding but some effort
        - 0-1: No answer or completely off-topic"""
        elif evaluation_level == "strict":
            criteria_text = """
        EVALUATION LEVEL: STRICT (Rigorous)
        - Require precise, detailed, and comprehensive answers
        - Expect specific examples and thorough explanations
        - Be critical of incomplete or vague responses

        SCORING SCALE (0-10):
        - 9-10: Exceptional - Precise, comprehensive, with specific examples
        - 7-8: Very Good - Accurate and detailed, minor gaps acceptable
        - 5-6: Adequate - Correct but lacks depth or detail
        - 3-4: Below Standard - Significant gaps or inaccuracies
        - 1-2: Poor - Major errors or very incomplete
        - 0: No answer or completely wrong"""
        else:  # medium
            criteria_text = """
        EVALUATION LEVEL: MEDIUM (Balanced)
        - Expect reasonable understanding and adequate detail
        - Balance between being supportive and maintaining standards
        - Look for key concepts and main points

        SCORING SCALE (0-10):
        - 9-10: Excellent - Accurate, complete, demonstrates deep understanding
        - 7-8: Good - Mostly accurate, covers main points, good understanding
        - 5-6: Satisfactory - Partially correct, basic understanding shown
        - 3-4: Needs Improvement - Some correct elements but significant gaps
        - 1-2: Poor - Mostly incorrect or irrelevant
        - 0: No answer provided or completely wrong

        IMPORTANT: If the student's answer is empty, blank, or just says "No answer provided", give a score of 0."""

        # Check if answer is empty and give 0 score
        if not request.user_answer or request.user_answer.strip() == "" or request.user_answer.strip().lower() == "no answer provided":
            return AnswerEvaluationResponse(
                question_id=request.question_id,
                score=0,
                max_score=10,
                feedback="No answer was provided for this question.",
                suggestions="Please provide an answer based on the document content to receive a score."
            )

        # This logic will be handled in the quiz evaluation method instead
        # Individual answer evaluation continues with the original logic for open-ended questions

        # Prepare context for evaluation
        evaluation_context = f"""
        You are an expert educational evaluator. Your task is to evaluate a student's answer to a question based on the provided document content.

        Document: {pdf_context['filename']}
        Document Content: {pdf_context['content'][:20000]}

        Question: {request.question}
        Student's Answer: {request.user_answer}

        EVALUATION CRITERIA:
        1. Accuracy: How correct is the answer based on the document content?
        2. Completeness: Does the answer cover all important aspects?
        3. Understanding: Does the student demonstrate clear understanding?
        4. Relevance: Is the answer relevant to the question asked?

        {criteria_text}

        Please provide your evaluation in the following JSON format:
        {{
            "score": [0-10 integer],
            "feedback": "[Detailed feedback explaining the score, highlighting what was correct and what was missing]",
            "suggestions": "[Specific suggestions for improvement]",
            "correct_answer_hint": "[Brief hint about the correct answer without giving it away completely]"
        }}

        Be constructive and encouraging in your feedback while being honest about areas for improvement.
        """

        try:
            rotated_model = get_rotated_model()
            response = rotated_model.generate_content(evaluation_context)
            ai_response = response.text

            # Try to extract JSON from the response
            import json
            import re

            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', ai_response)
            if json_match:
                try:
                    evaluation_data = json.loads(json_match.group())

                    return AnswerEvaluationResponse(
                        question_id=request.question_id,
                        score=min(max(evaluation_data.get('score', 0), 0), 10),  # Ensure score is 0-10
                        feedback=evaluation_data.get('feedback', 'No feedback provided'),
                        suggestions=evaluation_data.get('suggestions', 'No suggestions provided'),
                        correct_answer_hint=evaluation_data.get('correct_answer_hint')
                    )
                except json.JSONDecodeError:
                    pass

            # Fallback if JSON parsing fails
            return AnswerEvaluationResponse(
                question_id=request.question_id,
                score=5,  # Default middle score
                feedback=ai_response,
                suggestions="Please review the document content for more accurate information.",
                correct_answer_hint="Refer to the relevant sections in the document."
            )

        except Exception as e:
            chat_logger.error("Error evaluating answer", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to evaluate answer: {str(e)}")

    @staticmethod
    async def evaluate_quiz(request: QuizSubmissionRequest, token: str) -> QuizSubmissionResponse:
        """Evaluate a complete quiz submission"""
        if token not in pdf_contexts:
            raise HTTPException(status_code=400, detail="No PDF selected. Please select a PDF first.")

        pdf_context = pdf_contexts[token]

        # Evaluate each answer individually
        individual_results = []
        total_score = 0

        for answer in request.answers:
            # Handle MCQ questions with binary scoring
            if answer.question_type == 'mcq' and answer.correct_answer:
                user_answer_clean = answer.user_answer.strip().upper()
                correct_answer_clean = answer.correct_answer.strip().upper()

                # We need to get the actual answer text from the question to provide meaningful feedback
                # For now, we'll use AI to get the correct answer explanation
                try:
                    # Get the correct answer explanation using AI
                    explanation_context = f"""
                    You are an educational AI providing feedback on a multiple choice question.

                    Document: {pdf_context['filename']}
                    Document Content: {pdf_context['content'][:15000]}

                    Question: {answer.question}
                    Correct Answer: Option {correct_answer_clean}

                    Please provide a brief explanation (1-2 sentences) of why option {correct_answer_clean} is the correct answer based on the document content.
                    Focus on the specific information from the document that supports this answer.

                    Respond with just the explanation, no additional formatting.
                    """

                    rotated_model = get_rotated_model()
                    explanation_response = rotated_model.generate_content(explanation_context)
                    correct_answer_explanation = explanation_response.text.strip() if explanation_response and explanation_response.text else f"Option {correct_answer_clean} is the correct answer according to the document."

                except Exception as e:
                    print(f"Error getting answer explanation: {e}")
                    correct_answer_explanation = f"Option {correct_answer_clean} is the correct answer according to the document."

                # Get the actual option texts for better feedback
                user_option_text = ""
                correct_option_text = ""

                if answer.options:
                    # Find the option texts
                    for option in answer.options:
                        if option.startswith(f"{user_answer_clean})"):
                            user_option_text = option
                        if option.startswith(f"{correct_answer_clean})"):
                            correct_option_text = option

                # Binary scoring for MCQ: either full marks or zero
                if user_answer_clean == correct_answer_clean:
                    score = 10  # Full marks for correct answer
                    feedback = f"✅ Correct! You selected '{user_option_text or f'Option {user_answer_clean}'}'. {correct_answer_explanation}"
                    suggestions = "Great job! Continue studying to maintain this level of understanding."
                elif not answer.user_answer or answer.user_answer.strip() == "" or answer.user_answer.strip().lower() == "no answer provided":
                    score = 0  # Zero marks for no answer
                    feedback = f"❌ No answer was provided for this question. The correct answer is '{correct_option_text or f'Option {correct_answer_clean}'}'. {correct_answer_explanation}"
                    suggestions = "Please provide an answer based on the document content to receive a score."
                else:
                    score = 0  # Zero marks for incorrect answer
                    feedback = f"❌ Incorrect. You selected '{user_option_text or f'Option {user_answer_clean}'}', but the correct answer is '{correct_option_text or f'Option {correct_answer_clean}'}'. {correct_answer_explanation}"
                    suggestions = "Review the relevant section in the document to understand the correct answer."

                result = AnswerEvaluationResponse(
                    question_id=answer.question_id,
                    score=score,
                    max_score=10,
                    feedback=feedback,
                    suggestions=suggestions
                )
            else:
                # Handle open-ended questions with AI evaluation
                eval_request = AnswerEvaluationRequest(
                    question=answer.question,
                    user_answer=answer.user_answer,
                    question_id=answer.question_id,
                    evaluation_level=request.evaluation_level
                )
                result = await ChatService.evaluate_answer(eval_request, token)

            individual_results.append(result)
            total_score += result.score

        # Calculate overall metrics
        max_possible_score = len(request.answers) * 10
        percentage = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0

        # Determine grade
        if percentage >= 90:
            grade = "A"
        elif percentage >= 80:
            grade = "B"
        elif percentage >= 70:
            grade = "C"
        elif percentage >= 60:
            grade = "D"
        else:
            grade = "F"

        # Generate overall feedback using AI
        overall_context = f"""
        You are an educational AI providing comprehensive feedback on a student's quiz performance.

        Document: {pdf_context['filename']}
        Topic: {request.topic or 'General'}

        Quiz Results:
        - Total Score: {total_score}/{max_possible_score} ({percentage:.1f}%)
        - Grade: {grade}
        - Number of Questions: {len(request.answers)}

        Individual Question Performance:
        """

        for i, (answer, result) in enumerate(zip(request.answers, individual_results), 1):
            overall_context += f"""
        Question {i}: {answer.question}
        Student Answer: {answer.user_answer}
        Score: {result.score}/10
        """

        overall_context += f"""

        Based on this performance, provide:
        1. Overall feedback (2-3 sentences about the student's performance)
        2. Study suggestions (3-4 specific recommendations)
        3. Strengths (2-3 areas where the student performed well)
        4. Areas for improvement (2-3 specific areas needing work)

        Provide your response in JSON format:
        {{
            "overall_feedback": "[Overall assessment of performance]",
            "study_suggestions": ["suggestion1", "suggestion2", "suggestion3"],
            "strengths": ["strength1", "strength2"],
            "areas_for_improvement": ["area1", "area2", "area3"]
        }}

        Be encouraging and constructive while providing actionable feedback.
        """

        try:
            rotated_model = get_rotated_model()
            response = rotated_model.generate_content(overall_context)
            ai_response = response.text

            # Parse AI response
            import json
            import re

            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', ai_response)
            if json_match:
                try:
                    feedback_data = json.loads(json_match.group())

                    return QuizSubmissionResponse(
                        overall_score=total_score,
                        max_score=max_possible_score,
                        percentage=round(percentage, 1),
                        grade=grade,
                        individual_results=individual_results,
                        overall_feedback=feedback_data.get('overall_feedback', f'You scored {total_score}/{max_possible_score} ({percentage:.1f}%)'),
                        study_suggestions=feedback_data.get('study_suggestions', ['Review the document content', 'Practice more questions']),
                        strengths=feedback_data.get('strengths', ['Attempted all questions']),
                        areas_for_improvement=feedback_data.get('areas_for_improvement', ['Focus on accuracy', 'Provide more detailed answers'])
                    )
                except json.JSONDecodeError:
                    pass

            # Fallback response
            return QuizSubmissionResponse(
                overall_score=total_score,
                max_score=max_possible_score,
                percentage=round(percentage, 1),
                grade=grade,
                individual_results=individual_results,
                overall_feedback=f'You scored {total_score}/{max_possible_score} ({percentage:.1f}%). {"Great job!" if percentage >= 80 else "Keep practicing to improve your understanding."}',
                study_suggestions=['Review the document content thoroughly', 'Focus on key concepts and definitions', 'Practice explaining concepts in your own words'],
                strengths=['Completed all questions', 'Showed effort in answering'],
                areas_for_improvement=['Accuracy of responses', 'Depth of understanding', 'Use of specific examples from the text']
            )

        except Exception as e:
            print(f"Error generating overall feedback: {str(e)}")
            # Return basic response without AI-generated feedback
            return QuizSubmissionResponse(
                overall_score=total_score,
                max_score=max_possible_score,
                percentage=round(percentage, 1),
                grade=grade,
                individual_results=individual_results,
                overall_feedback=f'Quiz completed. Score: {total_score}/{max_possible_score} ({percentage:.1f}%)',
                study_suggestions=['Review the document content', 'Practice more questions'],
                strengths=['Completed the quiz'],
                areas_for_improvement=['Continue studying the material']
            )
