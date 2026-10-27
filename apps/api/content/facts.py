"""
MediaCompile — Structured Fact Extraction, Indexing, and Conflict Detection.
Source of Truth: MediaCompile-prompt.md (Step 3, Step 4, Step 5)

Responsibilities:
1. Deterministic Extraction: Extracts exact dates, DOB, currency amounts, identifiers (passport, SSN, invoices),
   contacts, and key-value properties from notes, documents, and web/video content.
2. Canonical Provenance: Every fact is linked to ContentItem, ContentChunk, character offsets, and source locations.
3. Multi-Tenant Safety: All facts are strictly user-scoped (ContentFact.user = user).
4. Conflict Detection: Explicitly detects and flags diverging values across sources instead of hallucinating.
5. Exact Value Preservation: Never reformats, truncates, or invents values.
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from .models import ContentItem, ContentChunk, ContentFact

logger = logging.getLogger(__name__)

# Canonical synonym mapping for query and fact normalization
SYNONYM_ATTRIBUTE_MAP = {
    # Date of birth / Birth
    "dob": "date_of_birth",
    "d.o.b.": "date_of_birth",
    "d.o.b": "date_of_birth",
    "date of birth": "date_of_birth",
    "birth date": "date_of_birth",
    "birthdate": "date_of_birth",
    "birthday": "date_of_birth",
    "birth day": "date_of_birth",
    "born": "date_of_birth",
    "born on": "date_of_birth",
    
    # Identifiers
    "ssn": "ssn",
    "social security": "ssn",
    "social security number": "ssn",
    "social security no": "ssn",
    "passport": "passport_number",
    "passport number": "passport_number",
    "passport no": "passport_number",
    "invoice": "invoice_number",
    "invoice number": "invoice_number",
    "invoice id": "invoice_number",
    "invoice #": "invoice_number",
    "order": "order_id",
    "order id": "order_id",
    "order number": "order_id",
    "account": "account_number",
    "account number": "account_number",
    "account no": "account_number",
    "license": "license_number",
    "driver license": "license_number",
    "drivers license": "license_number",
    
    # Contact
    "phone": "phone_number",
    "phone number": "phone_number",
    "mobile": "phone_number",
    "mobile number": "phone_number",
    "cell": "phone_number",
    "telephone": "phone_number",
    "email": "email",
    "email address": "email",
    "address": "address",
    "home address": "address",
    
    # Compensation / Finance
    "salary": "salary",
    "compensation": "salary",
    "pay": "salary",
    "wage": "salary",
    "annual salary": "salary",
    "price": "amount",
    "cost": "amount",
    "total": "amount",
    "amount": "amount",
    "fee": "amount",
    "rent": "amount",
}

# Reverse map: attribute -> all query search keys
ATTRIBUTE_TO_KEYS: Dict[str, List[str]] = {}
for k, attr in SYNONYM_ATTRIBUTE_MAP.items():
    ATTRIBUTE_TO_KEYS.setdefault(attr, []).append(k)


def compute_sha256(text: str) -> str:
    """Compute SHA-256 hexadecimal hash of input string."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_deterministic_facts(text: str, location_meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Extract structured facts from text using high-precision patterns.
    Preserves the exact literal string matched from source text.
    """
    if not text:
        return []

    facts = []
    loc = location_meta or {}

    # 1. Date of Birth (DOB) patterns
    # Matches e.g. "My date of birth is 15 March 2005", "DOB: 15 March 2005", "Born on May 20, 1998", "born 2005-03-15"
    dob_patterns = [
        r'(?:my\s+)?(?:date\s+of\s+birth|dob|birth\s*date|birthday|born\s*(?:on)?)\s*(?:is|was|:|-|=)?\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+[0-9]{4})',
        r'(?:my\s+)?(?:date\s+of\s+birth|dob|birth\s*date|birthday|born\s*(?:on)?)\s*(?:is|was|:|-|=)?\s*([A-Za-z]+\s+[0-9]{1,2}(?:st|nd|rd|th)?,?\s+[0-9]{4})',
        r'(?:my\s+)?(?:date\s+of\s+birth|dob|birth\s*date|birthday|born\s*(?:on)?)\s*(?:is|was|:|-|=)?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})',
        r'(?:my\s+)?(?:date\s+of\s+birth|dob|birth\s*date|birthday|born\s*(?:on)?)\s*(?:is|was|:|-|=)?\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})',
        r'([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+[0-9]{4})\s*(?:is\s+my\s+(?:date\s+of\s+birth|dob|birthday))',
    ]

    for pat in dob_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            val = m.group(1).strip()
            if val and len(val) >= 4:
                facts.append({
                    "entity": "user",
                    "attribute": "date_of_birth",
                    "fact_key": "dob",
                    "exact_value": val,
                    "confidence": 0.98,
                    "location": loc
                })

    # 2. Identifiers: Passport, SSN, Invoices, Orders, Accounts
    id_specs = [
        (r'\bpassport\s*(?:no|number|#|id)?\s*[:=\s]\s*([A-Z0-9]{6,12})\b', 'passport_number', 'passport_number', 'identification'),
        (r'\b(?:ssn|social\s+security\s*(?:no|number)?)\s*[:=\s]\s*([0-9]{3}-?[0-9]{2}-?[0-9]{4})\b', 'ssn', 'ssn', 'identification'),
        (r'\binvoice\s*(?:no|number|#|id)?\s*[:=\s]\s*([A-Za-z0-9\-_]{3,24})\b', 'invoice_number', 'invoice_number', 'document'),
        (r'\border\s*(?:id|no|number|#)?\s*[:=\s]\s*([A-Za-z0-9\-_]{3,24})\b', 'order_id', 'order_id', 'order'),
        (r'\baccount\s*(?:no|number|#)?\s*[:=\s]\s*([A-Za-z0-9\-_]{4,24})\b', 'account_number', 'account_number', 'account'),
        (r'\blicense\s*(?:no|number|#)?\s*[:=\s]\s*([A-Za-z0-9\-_]{4,20})\b', 'license_number', 'license_number', 'identification'),
    ]

    for pat, attr, key, ent in id_specs:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            val = m.group(1).strip()
            if val:
                facts.append({
                    "entity": ent,
                    "attribute": attr,
                    "fact_key": key,
                    "exact_value": val,
                    "confidence": 0.95,
                    "location": loc
                })

    # 3. Currency / Monetary Amounts & Compensation
    amt_specs = [
        (r'\b(?:salary|compensation|annual\s+salary)\s*(?:is|was|:|-|=)?\s*([$€£¥₹]\s*[\d,]+(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s*(?:usd|eur|gbp|dollars))\b', 'salary', 'salary', 'finance'),
        (r'\b(?:total|price|cost|amount|balance|fee|rent)\s*(?:is|was|:|-|=)?\s*([$€£¥₹]\s*[\d,]+(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s*(?:usd|eur|gbp|dollars))\b', 'amount', 'amount', 'finance'),
        # Standalone invoice amounts: "Invoice #12345: $4,250.75" or "Total: $4,250.75"
        (r'(?:total|amount|due|balance|paid):\s*([$€£¥₹]\s*[\d,]+(?:\.\d{1,2})?)', 'amount', 'amount', 'finance'),
    ]

    for pat, attr, key, ent in amt_specs:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            val = m.group(1).strip()
            if val:
                facts.append({
                    "entity": ent,
                    "attribute": attr,
                    "fact_key": key,
                    "exact_value": val,
                    "confidence": 0.92,
                    "location": loc
                })

    # 4. Contact Information: Email, Phone
    email_pat = r'\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b'
    for m in re.finditer(email_pat, text):
        val = m.group(1).strip()
        facts.append({
            "entity": "user",
            "attribute": "email",
            "fact_key": "email",
            "exact_value": val,
            "confidence": 0.90,
            "location": loc
        })

    phone_pat = r'\b(?:phone|telephone|mobile|cell|contact)?\s*[:=\s]\s*(\+?[0-9]{1,3}[-.\s]?(?:\([0-9]{2,4}\)[-.\s]?)?[0-9]{3,4}[-.\s]?[0-9]{3,4})\b'
    for m in re.finditer(phone_pat, text, flags=re.IGNORECASE):
        val = m.group(1).strip()
        if len(val) >= 7:
            facts.append({
                "entity": "user",
                "attribute": "phone_number",
                "fact_key": "phone_number",
                "exact_value": val,
                "confidence": 0.90,
                "location": loc
            })

    # 5. Key-Value metadata lines: e.g. "Blood Type: O+", "Hometown: Seattle, WA", "Contract Term: 12 months"
    kv_pat = r'^\s*([A-Za-z][A-Za-z0-9\s]{1,32}):\s*([^\n\r]{1,160})$'
    for line in text.splitlines():
        line_match = re.match(kv_pat, line)
        if line_match:
            raw_key = line_match.group(1).strip()
            raw_val = line_match.group(2).strip()
            normalized_key = raw_key.lower().replace(" ", "_")

            # Avoid noise tags
            if normalized_key in ("http", "https", "note", "source", "source_url", "url"):
                continue

            attr = SYNONYM_ATTRIBUTE_MAP.get(raw_key.lower(), normalized_key)
            facts.append({
                "entity": "general",
                "attribute": attr,
                "fact_key": normalized_key,
                "exact_value": raw_val,
                "confidence": 0.88,
                "location": loc
            })

    # Deduplicate facts within the same chunk by (attribute, exact_value)
    unique_facts = []
    seen = set()
    for f in facts:
        sig = (f["attribute"], f["exact_value"])
        if sig not in seen:
            seen.add(sig)
            unique_facts.append(f)

    return unique_facts


def index_item_facts(item: ContentItem, chunks: List[ContentChunk]) -> List[ContentFact]:
    """
    Extract and atomically persist structured facts for a ContentItem and its ContentChunks.
    Deletes any previously extracted facts for this item first (idempotent re-indexing).
    """
    all_facts_data = []

    # 1. Extract from full raw_text
    raw_facts = extract_deterministic_facts(item.raw_text, location_meta={"source": "raw_text"})
    for f in raw_facts:
        f["chunk"] = None
        all_facts_data.append(f)

    # 2. Extract from chunks preserving chunk locations (page_number, timestamp, slide_number, row_number)
    for chunk in chunks:
        meta = chunk.metadata or {}
        loc = {
            "chunk_id": str(chunk.id),
            "chunk_index": chunk.chunk_index,
            "page_number": meta.get("page_number"),
            "slide_number": meta.get("slide_number"),
            "sheet_name": meta.get("sheet_name"),
            "row_number": meta.get("row_number"),
            "timestamp": meta.get("timestamp"),
            "timestamp_seconds": meta.get("timestamp_seconds"),
        }
        loc = {k: v for k, v in loc.items() if v is not None}

        chunk_facts = extract_deterministic_facts(chunk.text, location_meta=loc)
        for f in chunk_facts:
            f["chunk"] = chunk
            all_facts_data.append(f)

    # Deduplicate across item and chunks
    fact_objs = []
    seen_sigs = set()
    for fd in all_facts_data:
        chunk_id = str(fd["chunk"].id) if fd.get("chunk") else "none"
        sig = (fd["attribute"], fd["exact_value"], chunk_id)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)

        fact_objs.append(
            ContentFact(
                user=item.user,
                content_item=item,
                content_chunk=fd.get("chunk"),
                entity=fd["entity"],
                attribute=fd["attribute"],
                fact_key=fd["fact_key"],
                exact_value=fd["exact_value"],
                source_location=fd["location"],
                confidence=fd["confidence"],
                version=item.version,
            )
        )

    with transaction.atomic():
        item.facts.all().delete()
        if fact_objs:
            ContentFact.objects.bulk_create(fact_objs)

    logger.info(
        f"[DIAGNOSTIC] Extracted and indexed {len(fact_objs)} facts for item {item.id} (user {item.user_id})"
    )
    return fact_objs


def detect_query_attributes(query_text: str) -> List[str]:
    """
    Map user questions to candidate normalized attributes.
    Supports exact, abbreviation, and paraphrased query variations.
    Example:
    - "What is my DOB?" -> ["date_of_birth"]
    - "When was I born?" -> ["date_of_birth"]
    - "What is my birth date?" -> ["date_of_birth"]
    - "Tell me my DOB" -> ["date_of_birth"]
    - "What is my passport number?" -> ["passport_number"]
    - "How much is my salary?" -> ["salary"]
    """
    q_lower = query_text.lower().strip()
    matched_attrs = set()

    # Check for direct phrase matches in synonym dictionary
    for phrase, attr in SYNONYM_ATTRIBUTE_MAP.items():
        # Match as whole word or phrase boundary
        pattern = r'(?:\b|^)' + re.escape(phrase) + r'(?:\b|$)'
        if re.search(pattern, q_lower):
            matched_attrs.add(attr)

    # Paraphrased DOB query triggers: "born", "birthday", "birth date", "birth year"
    if any(trigger in q_lower for trigger in ["when was i born", "date i was born", "day i was born", "my birthday", "birth date", "my dob"]):
        matched_attrs.add("date_of_birth")

    return list(matched_attrs)


def find_facts_for_query(user, query_text: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Search structured fact index strictly for authenticated user.
    Returns:
    - facts_list: List of matching facts with exact values and source provenance.
    - conflict_report: Dict with conflicting values and cited sources if disagreement is detected.
    """
    target_attrs = detect_query_attributes(query_text)
    if not target_attrs:
        return [], None

    # Retrieve facts for authenticated user matching candidate attributes
    facts_qs = ContentFact.objects.filter(
        user=user,
        attribute__in=target_attrs,
        content_item__ingestion_status__in=[ContentItem.STATUS_COMPLETED, ContentItem.STATUS_PARTIAL]
    ).select_related('content_item', 'content_chunk')

    facts_list = []
    values_by_attr: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for f in facts_qs:
        item = f.content_item
        chunk = f.content_chunk
        fact_dict = {
            "fact_id": str(f.id),
            "attribute": f.attribute,
            "fact_key": f.fact_key,
            "exact_value": f.exact_value,
            "entity": f.entity,
            "confidence": f.confidence,
            "item_id": str(item.id),
            "item_title": item.title or "Saved Source",
            "content_type": item.content_type,
            "source_url": item.source_url,
            "chunk_id": str(chunk.id) if chunk else None,
            "chunk_index": chunk.chunk_index if chunk else None,
            "source_location": f.source_location,
            "updated_at": f.updated_at.isoformat()
        }
        facts_list.append(fact_dict)

        val_norm = f.exact_value.strip().lower()
        values_by_attr.setdefault(f.attribute, {}).setdefault(val_norm, []).append(fact_dict)

    # Conflict detection: If multiple distinct values exist for the same attribute
    conflict_report = None
    for attr, vals_map in values_by_attr.items():
        if len(vals_map) > 1:
            conflict_report = {
                "attribute": attr,
                "conflicting_values": [
                    {
                        "value": facts_in_group[0]["exact_value"],
                        "sources": [
                            {"item_id": fi["item_id"], "item_title": fi["item_title"]}
                            for fi in facts_in_group
                        ]
                    }
                    for facts_in_group in vals_map.values()
                ]
            }
            logger.warning(
                f"[CONFLICT DETECTED] Attribute '{attr}' has conflicting values for user {user.id}: "
                f"{[c['value'] for c in conflict_report['conflicting_values']]}"
            )
            break

    return facts_list, conflict_report
