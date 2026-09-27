import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Fallback to OpenAI if desired, but we prefer Gemini as requested.
# The user will run the submission and we expect an API key in the environment.

def get_llm_response(prompt: str, system_instruction: str) -> str:
    """Calls the LLM API using available environment variables."""
    # Try Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json"
                ),
            )
            return response.text
        except ImportError:
            logger.warning("google-genai not installed. Falling back to next provider.")
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            
    # Try OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except ImportError:
            logger.warning("openai not installed. Falling back.")
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")

    # Fallback for local testing without API keys
    logger.warning("No LLM API keys found or APIs failed. Using fallback mock.")
    return json.dumps({
        "body": "This is a fallback message because no LLM API key was provided.",
        "cta": "binary_yes_no",
        "rationale": "Fallback mode active.",
        "template_name": "fallback"
    })

def compose_with_llm(
    trigger: Dict[str, Any],
    merchant: Dict[str, Any],
    category: Dict[str, Any],
    customer: Dict[str, Any] = None,
    conversation_history: list = None
) -> Dict[str, Any]:
    
    # 1. Gather facts
    merchant_name = merchant.get("identity", {}).get("name", "Merchant")
    owner_name = merchant.get("identity", {}).get("owner_first_name", "Partner")
    metrics = merchant.get("performance", {})
    offers = merchant.get("offers", [])
    
    cat_voice = category.get("voice", {})
    tone = cat_voice.get("tone", "professional")
    taboos = cat_voice.get("vocab_taboo", [])
    allowed = cat_voice.get("vocab_allowed", [])
    
    scope = trigger.get("scope", "merchant")
    send_as = "merchant_on_behalf" if scope == "customer" else "vera"
    
    # 2. Build system instruction
    system_instruction = f"""You are VERA, an AI assistant for local merchants.
Your goal is to write a highly specific, engaging WhatsApp message based on a trigger event.
You must return a raw JSON object with exactly these keys: 'body' (string), 'cta' (string), 'rationale' (string), 'template_name' (string).

RULES:
1. NEVER invent facts, metrics, names, or URLs. Only use the data provided in the context.
2. Tone: {tone}. Allowed vocabulary: {allowed}.
3. TABOO WORDS TO AVOID: {taboos}. Do not use these words under any circumstance.
4. Keep the message concise, suitable for WhatsApp.
5. If send_as is "merchant_on_behalf", you are speaking as the merchant TO a customer. If send_as is "vera", you are speaking TO the merchant.
6. `cta` must be one of: binary_yes_no, binary_confirm_cancel, multi_choice_slot, open_ended, none.
7. `template_name` can be a generic string like "vera_dynamic_message".
"""

    # 3. Build Prompt
    prompt = f"""
--- TRIGGER EVENT ---
{json.dumps(trigger, indent=2)}

--- MERCHANT CONTEXT ---
Name: {merchant_name}
Owner: {owner_name}
Performance Metrics: {json.dumps(metrics, indent=2)}
Active Offers: {json.dumps(offers, indent=2)}

--- CATEGORY CONTEXT ---
{json.dumps(category.get("peer_stats", {}), indent=2)}

"""
    if customer:
        prompt += f"""
--- CUSTOMER CONTEXT ---
{json.dumps(customer, indent=2)}
"""

    if conversation_history:
        prompt += f"""
--- RECENT CONVERSATION HISTORY ---
{json.dumps(conversation_history[-5:], indent=2)}
"""

    prompt += "\nNow generate the JSON response."

    # 4. Get LLM response
    response_text = get_llm_response(prompt, system_instruction)
    
    # 5. Parse and validate
    try:
        # Strip markdown block if present
        if response_text.startswith("```json"):
            response_text = response_text[7:-3]
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
            
        result = json.loads(response_text)
        
        # Ensure required fields
        body = result.get("body", "")
        cta = result.get("cta", "open_ended")
        rationale = result.get("rationale", "LLM composed")
        
        # Determine suppression key from trigger
        cust_id = customer.get("id", "none") if customer else "none"
        merch_id = merchant.get("id", "none")
        suppression_key = trigger.get("suppression_key", f"{trigger.get('kind', 'unknown')}:{merch_id}:{cust_id}")
        
        return {
            "body": body,
            "cta": cta,
            "template_name": result.get("template_name", "dynamic_template"),
            "template_params": [],
            "send_as": send_as,
            "rationale": rationale,
            "suppression_key": suppression_key
        }
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}\nResponse: {response_text}")
        # Fallback
        return {
            "body": "We noticed an update for your business. Would you like to review the details?",
            "cta": "binary_yes_no",
            "template_name": "fallback",
            "template_params": [],
            "send_as": send_as,
            "rationale": "Parsing error fallback",
            "suppression_key": trigger.get("suppression_key", "fallback_key")
        }
