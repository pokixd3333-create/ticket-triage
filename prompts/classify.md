Examples:

Input: "Our checkout API is returning 500 errors for all users right now."
Output: {"category": "technical", "priority": "urgent", "summary": "Checkout API is returning 500 errors for all users.", "reply_draft": "Thank you for alerting us to the 500 errors on your checkout API. We have flagged this issue for immediate investigation by our engineering team.", "confidence": 0.96}

Input: "Could you add dark mode themes for the weekly PDF summary?"
Output: {"category": "feature_request", "priority": "low", "summary": "User requests dark mode themes for the weekly PDF summary.", "reply_draft": "Thank you for sharing your idea about dark mode themes for weekly PDF summaries. We have logged your suggestion with our product team for future consideration.", "confidence": 0.94}

Now classify and triage the following customer support message:

---
{message}
---
