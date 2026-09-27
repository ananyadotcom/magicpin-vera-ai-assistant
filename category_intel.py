import logging
import re
from typing import Dict, Any, Optional, Callable, List, Tuple

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CATEGORY_CONFIG
# -----------------------------------------------------------------------------
CATEGORY_CONFIG: Dict[str, Dict[str, Any]] = {
    "dentists": {
        "salutation": lambda name: f"Dr. {name}" if name else "Doctor",
        "tone_descriptor": "Professional, scientific, evidence-based, concise",
        "taboo_words": ["customers", "deals", "sales", "buyers", "shop", "promos"],
        "safe_replacements": {
            "customers": "patients",
            "deals": "treatment plans",
            "sales": "consultations",
            "buyers": "patients",
            "shop": "clinic",
            "promos": "offers"
        }
    },
    "salons": {
        "salutation": lambda name: f"{name}" if name else "Partner",
        "tone_descriptor": "Friendly, aesthetic, trendy, relationship-driven",
        "taboo_words": ["patients", "prescriptions", "clinical"],
        "safe_replacements": {
            "patients": "clients",
            "prescriptions": "recommendations",
            "clinical": "professional"
        }
    },
    "restaurants": {
        "salutation": lambda name: f"{name}" if name else "Chef",
        "tone_descriptor": "Fast-paced, appetizing, local, experiential",
        "taboo_words": ["patients", "appointments", "clients", "sessions", "prescriptions"],
        "safe_replacements": {
            "patients": "diners",
            "appointments": "reservations",
            "clients": "guests",
            "sessions": "visits",
            "prescriptions": "recommendations"
        }
    },
    "gyms": {
        "salutation": lambda name: f"{name}" if name else "Coach",
        "tone_descriptor": "Motivating, energetic, community-focused, results-oriented",
        "taboo_words": ["patients", "diners", "treatment", "eaters"],
        "safe_replacements": {
            "patients": "members",
            "diners": "members",
            "treatment": "training",
            "eaters": "members"
        }
    },
    "pharmacies": {
        "salutation": lambda name: f"{name}" if name else "Partner",
        "tone_descriptor": "Clinical, reassuring, efficient, trust-building",
        "taboo_words": ["diners", "clients", "fun", "deals", "party"],
        "safe_replacements": {
            "diners": "patients",
            "clients": "patients",
            "fun": "care",
            "deals": "savings",
            "party": "community"
        }
    }
}

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def get_merchant_salutation(category_slug: str, merchant: Dict[str, Any]) -> str:
    """Returns appropriate salutation for the merchant based on category."""
    identity = merchant.get("identity", {})
    first_name = identity.get("owner_first_name") or identity.get("name", "")
    # Fallback if config is missing
    if category_slug not in CATEGORY_CONFIG:
        return first_name if first_name else "Partner"
    
    salutation_fn = CATEGORY_CONFIG[category_slug].get("salutation")
    if salutation_fn:
        return salutation_fn(first_name)
    return first_name if first_name else "Partner"

def check_taboos(body: str, category_slug: str) -> str:
    """Checks body for category taboo words and replaces them."""
    if not body or category_slug not in CATEGORY_CONFIG:
        return body
    
    config = CATEGORY_CONFIG[category_slug]
    taboo_words = config.get("taboo_words", [])
    replacements = config.get("safe_replacements", {})
    
    safe_body = body
    for word in taboo_words:
        # Case-insensitive replacement using word boundaries
        pattern = re.compile(rf'\b{word}\b', re.IGNORECASE)
        replacement = replacements.get(word, "")
        if replacement:
            # Match case of the original word if possible
            def match_case(match):
                orig = match.group(0)
                if orig.isupper():
                    return replacement.upper()
                elif orig.istitle():
                    return replacement.capitalize()
                return replacement.lower()
            
            safe_body = pattern.sub(match_case, safe_body)
            
    return safe_body

def get_send_as(trigger: Dict[str, Any]) -> str:
    """Determines send_as based on trigger scope."""
    scope = trigger.get("scope", "merchant")
    if scope == "customer":
        return "merchant_on_behalf"
    return "vera"

# -----------------------------------------------------------------------------
# TRIGGER TEMPLATES DICTIONARY
# -----------------------------------------------------------------------------
# We construct the nested dictionary of format: TRIGGER_TEMPLATES[trigger_kind][category_slug]
TRIGGER_TEMPLATES: Dict[str, Dict[str, Dict[str, Any]]] = {}

def _register_template(
    trigger_kind: str,
    category_slug: str,
    template_name: str,
    compose_body: Callable,
    compose_rationale: Callable,
    compose_cta: str,
    send_as_override: Optional[str] = None
):
    if trigger_kind not in TRIGGER_TEMPLATES:
        TRIGGER_TEMPLATES[trigger_kind] = {}
    TRIGGER_TEMPLATES[trigger_kind][category_slug] = {
        "template_name": template_name,
        "compose_body": compose_body,
        "compose_rationale": compose_rationale,
        "compose_cta": compose_cta,
        "send_as_override": send_as_override
    }

# --- 1. research_digest ---
def _rd_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    topic = ctx.get("topic", "industry trends")
    insight = ctx.get("insight", "Interesting new data is out.")
    return f"{salutation}, I reviewed the latest report on {topic}. {insight} Want me to summarize the top 3 takeaways for your business?"

def _rd_default_rationale(merchant, category, trigger, customer=None):
    return "Sharing an interesting industry digest to show value and establish Vera as a proactive intelligence partner."

_register_template(
    "research_digest", "default", "vera_research_digest_default",
    _rd_default_body, _rd_default_rationale, "binary_yes_no"
)

def _rd_dentist_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("dentists", merchant)
    ctx = trigger.get("context", {})
    journal = ctx.get("journal", "recent dental journals")
    trial = ctx.get("trial_info", "A new clinical trial shows promising preventive care results.")
    return f"{salutation}, {journal} just published new findings. {trial} Worth a look for your practice. Want me to pull the abstract?"

_register_template(
    "research_digest", "dentists", "vera_research_digest_dentist",
    _rd_dentist_body, _rd_default_rationale, "binary_yes_no"
)

# --- 2. regulation_change ---
def _rc_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    reg = ctx.get("regulation", "a compliance update")
    impact = ctx.get("impact", "It may affect your daily operations.")
    return f"{salutation}, heads up on {reg}. {impact} Should I draft a quick checklist so your team stays compliant?"

def _rc_default_rationale(merchant, category, trigger, customer=None):
    return "Notifying merchant of regulation changes helps protect their business from penalties."

_register_template(
    "regulation_change", "default", "vera_regulation_change_default",
    _rc_default_body, _rc_default_rationale, "binary_yes_no"
)

def _rc_pharmacy_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("pharmacies", merchant)
    ctx = trigger.get("context", {})
    reg = ctx.get("regulation", "a new FDA guideline")
    impact = ctx.get("impact", "Requires updated storage logging.")
    return f"{salutation}, critical update: {reg}. {impact} Want me to generate the new logging format for your pharmacy staff?"

_register_template(
    "regulation_change", "pharmacies", "vera_regulation_change_pharmacy",
    _rc_pharmacy_body, _rc_default_rationale, "binary_yes_no"
)

# --- 3. recall_due --- (Customer-scoped)
def _recall_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "our business")
    ctx = trigger.get("context", {})
    service = ctx.get("service", "your next visit")
    return f"Hi {cust_name}, it's {merchant_name}. It's been a while since your last visit. You're due for {service}. Would you like to check our available times for this week?"

def _recall_default_rationale(merchant, category, trigger, customer=None):
    return "Driving returning traffic by politely reminding customers of due services."

_register_template(
    "recall_due", "default", "merchant_recall_due_default",
    _recall_default_body, _recall_default_rationale, "open_ended", "merchant_on_behalf"
)

def _recall_dentist_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "the clinic")
    salutation = get_merchant_salutation("dentists", merchant) # Not used directly in message as it's to customer, but we can use Dr. Name
    dr_name = CATEGORY_CONFIG["dentists"]["salutation"](merchant.get("identity", {}).get("owner_first_name"))
    return f"Hi {cust_name}, this is {dr_name}'s office ({merchant_name}). Our records show you're due for your routine 6-month checkup and cleaning. Proactive care is the best care! Can we schedule you in for next week?"

_register_template(
    "recall_due", "dentists", "merchant_recall_due_dentist",
    _recall_dentist_body, _recall_default_rationale, "binary_yes_no", "merchant_on_behalf"
)

# --- 4. perf_dip ---
def _pdip_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    metric = ctx.get("metric", "profile views")
    drop = ctx.get("drop_percentage", "20%")
    return f"{salutation}, I noticed a {drop} dip in your {metric} this week. This isn't unusual for this time of month, but we can counter it. Want me to suggest 2 quick marketing moves to boost engagement?"

def _pdip_default_rationale(merchant, category, trigger, customer=None):
    return "Addressing performance dips proactively helps merchants feel supported and prevents churn."

_register_template(
    "perf_dip", "default", "vera_perf_dip_default",
    _pdip_default_body, _pdip_default_rationale, "binary_yes_no"
)

def _pdip_gym_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("gyms", merchant)
    ctx = trigger.get("context", {})
    metric = ctx.get("metric", "leads")
    drop = ctx.get("drop_percentage", "30%")
    return f"{salutation}, {metric} dropped {drop} this week — standard for metro gyms in this season (-25% to -35% is normal). Suggest pausing acquisition spend; focus on retaining members. Want me to draft a summer fitness challenge?"

_register_template(
    "perf_dip", "gyms", "vera_perf_dip_gym",
    _pdip_gym_body, _pdip_default_rationale, "binary_yes_no"
)

# --- 5. perf_spike ---
def _pspike_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    metric = ctx.get("metric", "customer visits")
    growth = ctx.get("growth_percentage", "40%")
    return f"{salutation}, great news! Your {metric} spiked by {growth} this week. Whatever you're doing is working. Should I analyze what drove this so we can double down on it?"

def _pspike_default_rationale(merchant, category, trigger, customer=None):
    return "Celebrating wins builds a positive relationship and encourages merchants to engage more with Vera."

_register_template(
    "perf_spike", "default", "vera_perf_spike_default",
    _pspike_default_body, _pspike_default_rationale, "binary_yes_no"
)

# --- 6. renewal_due ---
def _renewal_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    days = ctx.get("days_left", 7)
    return f"{salutation}, your subscription with us renews in {days} days. You've generated great traction this quarter. Want me to send over a quick ROI report before your renewal?"

def _renewal_default_rationale(merchant, category, trigger, customer=None):
    return "Pre-empting renewals with proof of value reduces friction and churn."

_register_template(
    "renewal_due", "default", "vera_renewal_due_default",
    _renewal_default_body, _renewal_default_rationale, "binary_yes_no"
)

# --- 7. festival_upcoming ---
def _fest_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    festival = ctx.get("festival", "the upcoming holidays")
    return f"{salutation}, {festival} is just around the corner! It's a high-intent period. Should I draft a festive promo message you can blast to your top 100 customers?"

def _fest_default_rationale(merchant, category, trigger, customer=None):
    return "Capitalizing on seasonal/festival spikes helps merchants maximize revenue."

_register_template(
    "festival_upcoming", "default", "vera_festival_upcoming_default",
    _fest_default_body, _fest_default_rationale, "binary_yes_no"
)

def _fest_restaurant_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("restaurants", merchant)
    ctx = trigger.get("context", {})
    festival = ctx.get("festival", "Diwali")
    return f"{salutation}, {festival} means large family gatherings and heavy orders. Should we push a 'Family Feast Combo' to your local neighborhood starting tomorrow? I can draft the menu suggestions."

_register_template(
    "festival_upcoming", "restaurants", "vera_festival_upcoming_restaurant",
    _fest_restaurant_body, _fest_default_rationale, "binary_yes_no"
)

# --- 8. wedding_package_followup --- (Customer-scoped)
def _wpf_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "our salon")
    return f"Hi {cust_name}, it's {merchant_name}. You inquired about our bridal and wedding packages recently. We have a few slots left for the upcoming season. Would you like to schedule a quick free consultation?"

def _wpf_default_rationale(merchant, category, trigger, customer=None):
    return "Wedding packages are high-ticket items; timely follow-ups capture high-intent leads."

_register_template(
    "wedding_package_followup", "default", "merchant_wedding_followup_default",
    _wpf_default_body, _wpf_default_rationale, "open_ended", "merchant_on_behalf"
)

# --- 9. curious_ask_due ---
def _cad_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    topic = ctx.get("topic", "your current priorities")
    return f"{salutation}, quick question to help me serve you better: what's your biggest focus for {topic} right now? More footfall, higher ticket size, or customer retention?"

def _cad_default_rationale(merchant, category, trigger, customer=None):
    return "Periodic curious asks help refine Vera's understanding of merchant priorities."

_register_template(
    "curious_ask_due", "default", "vera_curious_ask_default",
    _cad_default_body, _cad_default_rationale, "open_ended"
)

# --- 10. winback_eligible ---
def _we_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    return f"{salutation}, we've missed you! Since you left, we've added new AI tools to drive more local traffic. If you're open to it, I'd love to show you a 2-minute demo of what's new. Sound fair?"

def _we_default_rationale(merchant, category, trigger, customer=None):
    return "Re-engaging churned merchants by highlighting new features and low-friction re-entry."

_register_template(
    "winback_eligible", "default", "vera_winback_eligible_default",
    _we_default_body, _we_default_rationale, "binary_yes_no"
)

# --- 11. ipl_match_today ---
def _ipl_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    teams = ctx.get("teams", "the match")
    return f"{salutation}, big IPL match today ({teams}). High footfall expected around match time. Want me to draft a quick 'Match Day' special offer for you to share?"

def _ipl_default_rationale(merchant, category, trigger, customer=None):
    return "Capitalizing on live sports events for localized marketing."

_register_template(
    "ipl_match_today", "default", "vera_ipl_default",
    _ipl_default_body, _ipl_default_rationale, "binary_yes_no"
)

def _ipl_restaurant_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("restaurants", merchant)
    ctx = trigger.get("context", {})
    teams = ctx.get("teams", "DC vs MI")
    stadium = ctx.get("stadium", "Arun Jaitley Stadium")
    return f"{salutation}, {teams} at {stadium} tonight. Saturday IPL = more home viewers, fewer dine-ins. Your BOGO pizza deal could crush on delivery instead. Want me to draft a Swiggy banner?"

_register_template(
    "ipl_match_today", "restaurants", "vera_ipl_restaurant",
    _ipl_restaurant_body, _ipl_default_rationale, "binary_yes_no"
)

# --- 12. review_theme_emerged ---
def _rte_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    theme = ctx.get("theme", "customer service")
    sentiment = ctx.get("sentiment", "positive")
    return f"{salutation}, I'm noticing a strong {sentiment} theme in your recent reviews around '{theme}'. Want me to generate a summary and suggested actions based on this feedback?"

def _rte_default_rationale(merchant, category, trigger, customer=None):
    return "Helping merchants act on aggregate feedback without reading every review manually."

_register_template(
    "review_theme_emerged", "default", "vera_review_theme_default",
    _rte_default_body, _rte_default_rationale, "binary_yes_no"
)

# --- 13. milestone_reached ---
def _mr_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    milestone = ctx.get("milestone", "1,000 customers")
    return f"{salutation}, congratulations! You just hit {milestone}. This is a huge win. Shall I draft a quick 'Thank You' post for your social media to celebrate with your community?"

def _mr_default_rationale(merchant, category, trigger, customer=None):
    return "Acknowledging merchant milestones builds loyalty and provides an excuse for positive brand marketing."

_register_template(
    "milestone_reached", "default", "vera_milestone_default",
    _mr_default_body, _mr_default_rationale, "binary_yes_no"
)

# --- 14. active_planning_intent ---
def _api_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    intent = ctx.get("intent", "expanding your services")
    return f"{salutation}, you previously mentioned looking into {intent}. I've compiled a quick 3-step action plan to get started. Want me to send it over?"

def _api_default_rationale(merchant, category, trigger, customer=None):
    return "Following up on past intent shows memory and persistence, moving merchants down the funnel."

_register_template(
    "active_planning_intent", "default", "vera_active_intent_default",
    _api_default_body, _api_default_rationale, "binary_yes_no"
)

# --- 15. customer_lapsed_hard --- (Customer-scoped)
def _clh_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "our store")
    ctx = trigger.get("context", {})
    return f"Hi {cust_name}, it's {merchant_name}. We haven't seen you in a while and we genuinely miss having you around! If you're planning a visit soon, reply 'YES' and I'll send over a special welcome-back surprise."

def _clh_default_rationale(merchant, category, trigger, customer=None):
    return "Hard-lapsed customers need a strong, incentive-driven nudge to return."

_register_template(
    "customer_lapsed_hard", "default", "merchant_lapsed_hard_default",
    _clh_default_body, _clh_default_rationale, "binary_yes_no", "merchant_on_behalf"
)

# --- 16. trial_followup --- (Customer-scoped)
def _tf_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "us")
    return f"Hi {cust_name}, thanks for visiting {merchant_name} for your trial! We'd love to know how your experience was. Any quick feedback, or questions about our regular plans?"

def _tf_default_rationale(merchant, category, trigger, customer=None):
    return "Immediate follow-up post-trial converts warm leads into paying customers."

_register_template(
    "trial_followup", "default", "merchant_trial_followup_default",
    _tf_default_body, _tf_default_rationale, "open_ended", "merchant_on_behalf"
)

# --- 17. supply_alert ---
def _sa_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    item = ctx.get("item", "key inventory")
    return f"{salutation}, there's an industry alert regarding {item} supply chain delays. You might want to stock up or inform clients. Need me to draft a quick advisory?"

def _sa_default_rationale(merchant, category, trigger, customer=None):
    return "Providing timely supply alerts acts as a crucial risk-mitigation service."

_register_template(
    "supply_alert", "default", "vera_supply_alert_default",
    _sa_default_body, _sa_default_rationale, "binary_yes_no"
)

def _sa_pharmacy_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("pharmacies", merchant)
    ctx = trigger.get("context", {})
    drug = ctx.get("drug", "atorvastatin")
    batches = ctx.get("batches", "AT2024-1102 and AT2024-1108")
    mfr = ctx.get("manufacturer", "MfrZ")
    issue = ctx.get("issue", "sub-potency")
    return f"{salutation}, urgent: voluntary recall on {drug} batches {batches} ({mfr}, {issue}). Want me to filter your customer list for affected prescriptions so you can alert them?"

_register_template(
    "supply_alert", "pharmacies", "vera_supply_alert_pharmacy",
    _sa_pharmacy_body, _sa_default_rationale, "binary_yes_no"
)

# --- 18. chronic_refill_due --- (Customer-scoped)
def _crd_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "the pharmacy")
    ctx = trigger.get("context", {})
    medication = ctx.get("medication", "regular medication")
    return f"Hi {cust_name}, this is {merchant_name}. Our records show your refill for {medication} is due soon. Shall we prepare it for you to pick up tomorrow?"

def _crd_default_rationale(merchant, category, trigger, customer=None):
    return "Chronic refills ensure patient adherence and guarantee recurring pharmacy revenue."

_register_template(
    "chronic_refill_due", "default", "merchant_chronic_refill_default",
    _crd_default_body, _crd_default_rationale, "binary_yes_no", "merchant_on_behalf"
)

# --- 19. category_seasonal ---
def _cs_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    season = ctx.get("season", "the upcoming season")
    trend = ctx.get("trend", "shifting consumer habits")
    return f"{salutation}, as we enter {season}, we typically see {trend}. I've got a couple of proactive strategies to stay ahead. Want to hear them?"

def _cs_default_rationale(merchant, category, trigger, customer=None):
    return "Seasonal prep keeps merchants ahead of the curve."

_register_template(
    "category_seasonal", "default", "vera_category_seasonal_default",
    _cs_default_body, _cs_default_rationale, "binary_yes_no"
)

# --- 20. gbp_unverified ---
def _gbp_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    return f"{salutation}, I noticed your Google Business Profile isn't fully verified yet. You're missing out on local search traffic! I can guide you through the 3-step verification process right now. Ready?"

def _gbp_default_rationale(merchant, category, trigger, customer=None):
    return "Verification is step 0 for local SEO. Nudging this has high long-term ROI."

_register_template(
    "gbp_unverified", "default", "vera_gbp_unverified_default",
    _gbp_default_body, _gbp_default_rationale, "binary_yes_no"
)

# --- 21. cde_opportunity ---
def _cde_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    course = ctx.get("course_name", "a new continuing education course")
    return f"{salutation}, {course} was just announced in your area. Earning these credits early might be useful. Want me to send the registration details?"

def _cde_default_rationale(merchant, category, trigger, customer=None):
    return "Alerting professionals to CDE helps them maintain licenses and shows deep vertical understanding."

_register_template(
    "cde_opportunity", "default", "vera_cde_default",
    _cde_default_body, _cde_default_rationale, "binary_yes_no"
)

def _cde_dentist_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("dentists", merchant)
    ctx = trigger.get("context", {})
    topic = ctx.get("topic", "Advanced Endodontics")
    credits = ctx.get("credits", 4)
    return f"{salutation}, IDA is hosting a virtual session on {topic} next week ({credits} CDE points). Given your focus on preventive care, it might be relevant. Want the link to register?"

_register_template(
    "cde_opportunity", "dentists", "vera_cde_dentist",
    _cde_dentist_body, _cde_default_rationale, "binary_yes_no"
)

# --- 22. competitor_opened ---
def _co_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    distance = ctx.get("distance", "nearby")
    return f"{salutation}, quick market update: a new competitor just opened {distance}. It's a great time to launch a loyalty campaign to lock in your regulars. Shall I draft one?"

def _co_default_rationale(merchant, category, trigger, customer=None):
    return "Alerting merchants to local competition positions Vera as a vital local intelligence partner."

_register_template(
    "competitor_opened", "default", "vera_competitor_opened_default",
    _co_default_body, _co_default_rationale, "binary_yes_no"
)

# --- 23. dormant_with_vera ---
def _dwv_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    return f"{salutation}, we haven't chatted in a bit! I've been analyzing your local market data while you were away. I found one quick tweak that could increase your footfall this week. Want to hear it?"

def _dwv_default_rationale(merchant, category, trigger, customer=None):
    return "Re-activating the merchant-Vera relationship with a curiosity hook."

_register_template(
    "dormant_with_vera", "default", "vera_dormant_default",
    _dwv_default_body, _dwv_default_rationale, "binary_yes_no"
)

# --- 24. seasonal_perf_dip ---
def _spd_default_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation(category.get("slug", ""), merchant)
    ctx = trigger.get("context", {})
    month = ctx.get("month", "this month")
    return f"{salutation}, historically, {month} brings a slight dip in traffic across your category. We can offset this with a targeted win-back campaign. Want me to set that up?"

def _spd_default_rationale(merchant, category, trigger, customer=None):
    return "Normalizing seasonal dips prevents panic and provides actionable counter-strategies."

_register_template(
    "seasonal_perf_dip", "default", "vera_seasonal_dip_default",
    _spd_default_body, _spd_default_rationale, "binary_yes_no"
)

# --- 25. customer_lapsed_soft --- (Customer-scoped)
def _cls_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "our store")
    return f"Hi {cust_name}, it's {merchant_name}. It's been a little while! Just wanted to share our latest catalog with you. Let me know if you want to pop in this weekend!"

def _cls_default_rationale(merchant, category, trigger, customer=None):
    return "Soft lapsing customers just need a friendly nudge before they churn entirely."

_register_template(
    "customer_lapsed_soft", "default", "merchant_lapsed_soft_default",
    _cls_default_body, _cls_default_rationale, "open_ended", "merchant_on_behalf"
)

# --- 26. appointment_tomorrow --- (Customer-scoped)
def _at_default_body(merchant, category, trigger, customer=None):
    cust_name = customer.get("identity", {}).get("name", "there") if customer else "there"
    merchant_name = merchant.get("identity", {}).get("name", "our office")
    ctx = trigger.get("context", {})
    time = ctx.get("time", "tomorrow")
    return f"Hi {cust_name}, just a friendly reminder from {merchant_name} about your appointment at {time}. Please reply 'YES' to confirm or let us know if you need to reschedule."

def _at_default_rationale(merchant, category, trigger, customer=None):
    return "Reducing no-shows via timely reminders is an instant ROI generator for service businesses."

_register_template(
    "appointment_tomorrow", "default", "merchant_appointment_default",
    _at_default_body, _at_default_rationale, "binary_yes_no", "merchant_on_behalf"
)

# --- Extra specific overrides ---
def _salon_curious_ask_body(merchant, category, trigger, customer=None):
    salutation = get_merchant_salutation("salons", merchant)
    return f"{salutation}, which service has been most requested this week? I'll turn the answer into a Google post + a WhatsApp reply template for pricing queries. Takes 5 min."

_register_template(
    "curious_ask_due", "salons", "vera_curious_ask_salon",
    _salon_curious_ask_body, _cad_default_rationale, "open_ended"
)

# -----------------------------------------------------------------------------
# MAIN COMPOSITION ENTRY POINT
# -----------------------------------------------------------------------------
def compose_message(
    trigger_kind: str,
    category_slug: str,
    merchant: Dict[str, Any],
    category: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Main composition function.
    
    Returns a dict with body, cta, template_name, template_params, send_as, 
    rationale, and suppression_key.
    """
    
    # 1. Resolve template
    kind_templates = TRIGGER_TEMPLATES.get(trigger_kind, {})
    if not kind_templates:
        # Fallback if unknown trigger
        logger.warning(f"Unknown trigger kind: {trigger_kind}")
        kind_templates = TRIGGER_TEMPLATES.get("curious_ask_due", {})
        
    tpl_config = kind_templates.get(category_slug)
    if not tpl_config:
        tpl_config = kind_templates.get("default")
        
    if not tpl_config:
        raise ValueError(f"No valid template found for {trigger_kind} in category {category_slug} or default.")

    # 2. Determine send_as
    default_send_as = get_send_as(trigger)
    send_as = tpl_config.get("send_as_override") or default_send_as

    # 3. Generate raw content
    raw_body = tpl_config["compose_body"](merchant, category, trigger, customer)
    rationale = tpl_config["compose_rationale"](merchant, category, trigger, customer)
    cta = tpl_config["compose_cta"]
    template_name = tpl_config["template_name"]

    # 4. Apply category-specific taboo filtering (only if Vera is speaking, or always?)
    # Generally, apply taboos to ensure safety, even on behalf of merchant.
    safe_body = check_taboos(raw_body, category_slug)

    # 5. Build suppression key to avoid duplicate sends
    cust_id = customer.get("id", "none") if customer else "none"
    merch_id = merchant.get("id", "none")
    suppression_key = f"{trigger_kind}:{merch_id}:{cust_id}"

    return {
        "body": safe_body,
        "cta": cta,
        "template_name": template_name,
        "template_params": {}, # Reserved for actual WhatsApp template variables if integrated
        "send_as": send_as,
        "rationale": rationale,
        "suppression_key": suppression_key
    }
