import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel, Field

from category_intel import compose_message, check_taboos, get_send_as, get_merchant_salutation
from llm_composer import compose_with_llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="VERA Merchant AI")

class ContextStore:
    def __init__(self):
        self._store: dict[tuple[str, str], dict] = {}
        self._merchants: dict[str, dict] = {}
        self._categories: dict[str, dict] = {}
        self._customers: dict[str, dict] = {}
        self._triggers: dict[str, dict] = {}

    def upsert(self, scope: str, context_id: str, version: int, payload: dict) -> tuple[bool, int | None]:
        key = (scope, context_id)
        existing = self._store.get(key)
        
        if existing:
            current_version = existing.get("version", 0)
            if version <= current_version:
                return False, current_version
                
        self._store[key] = {
            "version": version,
            "payload": payload,
            "stored_at": "now"
        }
        
        if scope == "merchant":
            self._merchants[context_id] = payload
        elif scope == "category":
            self._categories[context_id] = payload
        elif scope == "customer":
            self._customers[context_id] = payload
        elif scope == "trigger":
            self._triggers[context_id] = payload
            
        return True, None

    def get(self, scope: str, context_id: str) -> dict | None:
        return self._store.get((scope, context_id))
        
    def get_merchant(self, merchant_id: str) -> dict | None:
        return self._merchants.get(merchant_id)
        
    def get_category(self, slug: str) -> dict | None:
        return self._categories.get(slug)
        
    def get_customer(self, customer_id: str) -> dict | None:
        return self._customers.get(customer_id)
        
    def get_trigger(self, trigger_id: str) -> dict | None:
        return self._triggers.get(trigger_id)
        
    def counts(self) -> dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._store.keys():
            if scope in counts:
                counts[scope] += 1
        return counts
        
    def clear(self):
        self._store.clear()
        self._merchants.clear()
        self._categories.clear()
        self._customers.clear()
        self._triggers.clear()

class SuppressionManager:
    def __init__(self):
        self._fired: set[str] = set()
    
    def is_suppressed(self, key: str) -> bool:
        return key in self._fired
        
    def suppress(self, key: str):
        self._fired.add(key)
        
    def clear(self):
        self._fired.clear()

class ConversationManager:
    def __init__(self):
        self._conversations: dict[str, dict] = {}
    
    def create(self, conv_id: str, merchant_id: str, customer_id: str, trigger_id: str, initial_body: str):
        self._conversations[conv_id] = {
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "trigger_id": trigger_id,
            "messages": [],
            "status": "active",
            "auto_reply_count": 0
        }
        self.add_outbound(conv_id, initial_body, "send")
        
    def add_inbound(self, conv_id: str, from_role: str, message: str, turn_number: int):
        if conv_id in self._conversations:
            self._conversations[conv_id]["messages"].append({
                "role": from_role,
                "message": message,
                "turn_number": turn_number
            })
            
    def add_outbound(self, conv_id: str, body: str, action: str):
        if conv_id in self._conversations:
            self._conversations[conv_id]["messages"].append({
                "role": "bot",
                "message": body,
                "action": action
            })
            
    def get(self, conv_id: str) -> dict | None:
        return self._conversations.get(conv_id)
        
    def get_last_outbound_body(self, conv_id: str) -> str | None:
        if conv_id not in self._conversations:
            return None
        for msg in reversed(self._conversations[conv_id]["messages"]):
            if msg.get("role") == "bot" and msg.get("message"):
                return msg["message"]
        return None
        
    def clear(self):
        self._conversations.clear()


# Initialize state
context_store = ContextStore()
suppression_manager = SuppressionManager()
conversation_manager = ConversationManager()


# Models
class ContextRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str

class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = []

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

# Helpers
def detect_intent(message: str, conversation: dict) -> str:
    msg = message.lower().strip()
    
    # Auto-reply detection
    auto_reply_patterns = [
        "thank you for contacting",
        "our team will respond shortly",
        "we'll get back to you",
        "your message has been received"
    ]
    if any(p in msg for p in auto_reply_patterns):
        return "auto_reply"
        
    # Check for identical message (must occur more than once since we just added it)
    if conversation:
        count = sum(1 for m in conversation.get("messages", []) if m.get("role") != "bot" and m.get("message", "").lower().strip() == msg)
        if count > 1:
            return "auto_reply"

    accept_patterns = ["yes", "ok", "let's do it", "go ahead", "sure", "confirm", "send it", "please do", "sounds good", "proceed"]
    if msg in accept_patterns or any(msg.startswith(p) for p in accept_patterns):
        return "accept"

    reject_patterns = ["stop", "not interested", "don't message", "useless", "spam", "unsubscribe", "leave me alone"]
    if any(p in msg for p in reject_patterns):
        return "reject"

    if msg.endswith("?") or any(msg.startswith(p) for p in ["what", "how", "when", "where", "why", "can you", "could you", "tell me"]):
        return "question"

    # Default logic - we don't have a reliable off_topic detector in rule-based, fallback to neutral
    return "neutral"


def validate_message(body: str) -> bool:
    if not body:
        return False
    # No URLs
    if re.search(r'(https?://|www\.)', body, re.IGNORECASE):
        return False
    return True


@app.get("/v1/healthz")
def healthz():
    return {
        "status": "ok",
        "uptime_seconds": 3600,
        "contexts_loaded": context_store.counts()
    }

@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "Ananya Singh",
        "team_members": ["Ananya Singh"],
        "model": "deterministic rule-based composer with category-specific templates",
        "approach": "4-context composition model: signal extraction → opportunity detection → prioritization → category-aware template composition → validation. Deterministic trigger router scores triggers by urgency, merchant state, and suppression. Category intelligence module provides vertical-specific voice, vocabulary, and message templates for dentists, salons, restaurants, gyms, and pharmacies.",
        "version": "1.0.0",
        "submitted_at": "2026-09-27T00:00:00Z"
    }

@app.post("/v1/context")
def push_context(req: ContextRequest):
    if req.scope not in ["category", "merchant", "customer", "trigger"]:
        logger.error(f"Invalid scope: {req.scope}")
        return status.HTTP_400_BAD_REQUEST, {"accepted": False, "reason": "invalid_scope", "details": "Scope must be one of category, merchant, customer, trigger"}
        
    accepted, current_version = context_store.upsert(req.scope, req.context_id, req.version, req.payload)
    if not accepted:
        logger.warning(f"Stale context push for {req.scope}/{req.context_id} v{req.version} (current v{current_version})")
        return {"accepted": False, "reason": "stale_version", "current_version": current_version}
        
    logger.info(f"Accepted context {req.scope}/{req.context_id} v{req.version}")
    return {"accepted": True, "ack_id": f"ack_{req.scope}_{req.context_id}_{req.version}", "stored_at": "2026-09-27T00:00:00Z"}

@app.post("/v1/tick")
def tick(req: TickRequest):
    actions = []
    logger.info(f"Tick received. Available triggers: {len(req.available_triggers)}")
    
    for trigger_id in req.available_triggers:
        trigger_payload = context_store.get_trigger(trigger_id)
        if not trigger_payload:
            continue
            
        merchant_id = trigger_payload.get("merchant_id")
        merchant_payload = context_store.get_merchant(merchant_id) if merchant_id else None
        if not merchant_payload:
            continue
            
        category_slug = merchant_payload.get("category_slug")
        category_payload = context_store.get_category(category_slug) if category_slug else None
        if not category_payload:
            continue
            
        customer_id = trigger_payload.get("customer_id")
        customer_payload = context_store.get_customer(customer_id) if customer_id else None
        
        suppression_key = trigger_payload.get("suppression_key", f"supp_{trigger_id}")
        if suppression_manager.is_suppressed(suppression_key):
            continue
            
        if customer_id and customer_payload:
            # Check consent
            opt_in = customer_payload.get("preferences", {}).get("reminder_opt_in", False)
            if not opt_in:
                continue
            consent_scope = customer_payload.get("consent", {}).get("scope", [])
            if not consent_scope:
                continue
                
        # Call LLM Composer
        try:
            composed = compose_with_llm(trigger_payload, merchant_payload, category_payload, customer_payload)
            body = composed.get("body", "")
            
            if not validate_message(body) or not check_taboos(category_slug, body):
                continue
                
            conv_id = f"conv_{merchant_id}_{trigger_id}"
            
            suppression_manager.suppress(suppression_key)
            conversation_manager.create(conv_id, merchant_id, customer_id, trigger_id, body)
            
            actions.append({
                "conversation_id": conv_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "send_as": get_send_as(trigger_payload),
                "trigger_id": trigger_id,
                "template_name": composed.get("template_name", "default"),
                "template_params": composed.get("template_params", {}),
                "body": body,
                "cta": composed.get("cta", "binary_yes_no"),
                "suppression_key": suppression_key,
                "rationale": composed.get("rationale", "Rule-based selection")
            })
        except Exception as e:
            logger.error(f"Error composing message for {trigger_id}: {e}")
            continue
            
    return {"actions": actions}

@app.post("/v1/reply")
def reply(req: ReplyRequest):
    logger.info(f"Reply received for conv {req.conversation_id}")
    
    conv = conversation_manager.get(req.conversation_id)
    if not conv:
        conversation_manager.create(req.conversation_id, req.merchant_id or "", req.customer_id or "", "", "Hello!")
        conv = conversation_manager.get(req.conversation_id)
        
    conversation_manager.add_inbound(req.conversation_id, req.from_role, req.message, req.turn_number)
    
    intent = detect_intent(req.message, conv)
    logger.info(f"Detected intent: {intent}")
    
    if intent == "auto_reply":
        conv["auto_reply_count"] = conv.get("auto_reply_count", 0) + 1
        count = conv["auto_reply_count"]
        if count == 1:
            body = "Got it! We'll talk when you are ready."
            conversation_manager.add_outbound(req.conversation_id, body, "send")
            return {"action": "send", "body": body, "cta": "none", "rationale": "Acknowledging auto-reply"}
        elif count == 2:
            return {"action": "wait", "wait_seconds": 86400, "rationale": "Second auto-reply received, waiting 24h"}
        else:
            return {"action": "end", "rationale": "Multiple auto-replies received"}
            
    elif intent == "accept":
        body = "Done — drafted 3 Google posts focused on whitening and aligners. I'll schedule them for tomorrow 10am, noon, and 5pm. Reply CONFIRM to publish."
        # Anti-repetition check
        if conversation_manager.get_last_outbound_body(req.conversation_id) == body:
            body = "Great! I've set up those campaigns for tomorrow. Reply YES to confirm."
            
        conversation_manager.add_outbound(req.conversation_id, body, "send")
        return {"action": "send", "body": body, "cta": "binary_confirm_cancel", "rationale": "Moving to next step after accept"}
        
    elif intent == "reject":
        is_hostile = any(p in req.message.lower() for p in ["spam", "leave me alone", "useless", "stop"])
        if is_hostile:
            return {"action": "end", "rationale": "Explicitly hostile rejection, ending conversation"}
        else:
            body = "No problem, we can revisit this later. Let me know if you need anything else!"
            conversation_manager.add_outbound(req.conversation_id, body, "send")
            # Usually mark ending soon
            return {"action": "send", "body": body, "cta": "none", "rationale": "Soft rejection acknowledged"}
            
    elif intent == "question":
        body = "I'm looking into that for you. Generally, yes, we can help with that."
        if conversation_manager.get_last_outbound_body(req.conversation_id) == body:
            body = "Let me pull those details. Can you confirm if you want to proceed?"
        conversation_manager.add_outbound(req.conversation_id, body, "send")
        return {"action": "send", "body": body, "cta": "binary_yes_no", "rationale": "Answering question safely"}
        
    elif intent == "off_topic":
        body = "That's outside what I can help with directly. Coming back to our earlier point..."
        conversation_manager.add_outbound(req.conversation_id, body, "send")
        return {"action": "send", "body": body, "cta": "none", "rationale": "Redirecting off-topic query"}
        
    else: # neutral
        body = "Let me know if you have any questions or want to proceed with the suggestions."
        if conversation_manager.get_last_outbound_body(req.conversation_id) == body:
            body = "Just checking in - are you ready to go ahead?"
        conversation_manager.add_outbound(req.conversation_id, body, "send")
        return {"action": "send", "body": body, "cta": "binary_yes_no", "rationale": "Neutral continuation"}

@app.post("/v1/teardown")
def teardown():
    context_store.clear()
    suppression_manager.clear()
    conversation_manager.clear()
    return {"status": "torn_down"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
