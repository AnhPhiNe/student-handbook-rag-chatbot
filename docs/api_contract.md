# API Contract

Base application:

```bash
python -m uvicorn src.api.main:app --reload
```

## Health

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "student_handbook_rag",
  "version": "0.1.0"
}
```

This endpoint must stay lightweight. It should not load the retrieval pipeline
or call Gemini.

## Chat

```http
POST /chat
```

Request:

```json
{
  "query": "Email Phong Dao tao la gi?",
  "include_debug": false
}
```

Response fields mirror the `AnswerService.answer()` result and keep debug
payloads limited when requested. The API must not duplicate retrieval,
guardrail, citation, cache, or answer-generation logic.
