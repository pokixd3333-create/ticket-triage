Your previous response failed JSON or schema validation.

Original output:
---
{raw_output}
---

Validation error:
---
{validation_error}
---

Fix the output so that it is strictly valid JSON matching all required fields and constraints:
- "category": one of ["billing", "technical", "account", "feature_request", "other"]
- "priority": one of ["low", "medium", "high", "urgent"]
- "summary": exactly 1 sentence, 20 words or fewer
- "reply_draft": polite reply, 2 to 4 sentences, no unconfirmed promises
- "confidence": float between 0.0 and 1.0

Return ONLY the corrected JSON object.