import logging
from typing import Dict, Any, List
from dataclasses import dataclass
from pydantic import BaseModel, Field
import json
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class DocumentClassificationResult(BaseModel):
    """Structured output from LLM classification"""
    documents_ready_for_download: bool = Field(
        description="TRUE if documents are newly available and ready to download, FALSE otherwise"
    )
    reasoning: str = Field(
        description="Brief explanation of why documents are or are not ready"
    )


@dataclass
class DocumentClassification:
    """Result of document classification"""
    documents_ready: bool
    reasoning: str


class DocumentClassifier:
    """
    Classifies whether a flagged request has documents ready for download.
    Uses LLM to analyze request context and make intelligent decisions.
    
    SIMPLIFIED: Just determines TRUE/FALSE - no document list extraction needed.
    """
    
    def __init__(self, llm_client):
        """
        Initialize classifier with LLM client.
        
        Args:
            llm_client: LLM client (e.g., gpt_4o from llm.py)
        """
        self.llm_client = llm_client
        
    def classify_request(self, request_data: Dict[str, Any]) -> DocumentClassification:
        """
        Classify if a request has documents ready for download.
        
        Args:
            request_data: Request record from database with latest_analysis
            
        Returns:
            DocumentClassification with TRUE/FALSE decision
        """
        try:
            # Handle joined query structure (when users table is joined)
            if 'users' in request_data and isinstance(request_data['users'], dict):
                actual_request_data = {k: v for k, v in request_data.items() if k != 'users'}
            else:
                actual_request_data = request_data
            
            request_number = actual_request_data.get('request_number', 'Unknown')
            portal_type = actual_request_data.get('portal_type', 'portal')
            logger.info(f"🔍 Classifying request {request_number} (type: {portal_type})")

            # Extract key information
            current_status = actual_request_data.get('current_status', 'Unknown')
            attention_reason = actual_request_data.get('agent_attention_reason', '')

            # Get analysis from correct field based on portal type
            if portal_type == 'email':
                latest_analysis = actual_request_data.get('latest_analysis_gmail', {})
            else:
                latest_analysis = actual_request_data.get('latest_analysis', {})
            
            # Parse latest_analysis if it's a string
            if isinstance(latest_analysis, str):
                try:
                    latest_analysis = json.loads(latest_analysis)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse latest_analysis for {request_number}")
                    latest_analysis = {}
            
            # Ensure latest_analysis is a dict
            if not isinstance(latest_analysis, dict):
                logger.warning(f"latest_analysis is not a dict for {request_number}, type: {type(latest_analysis)}")
                latest_analysis = {}
            
            # Extract documents and timeline from analysis
            documents_available = latest_analysis.get('documents_available', [])
            timeline_events = latest_analysis.get('all_timeline_events', [])
            
            # If no documents listed at all, return FALSE immediately
            if not documents_available:
                logger.info(f"No documents available in analysis for {request_number}")
                return DocumentClassification(
                    documents_ready=False,
                    reasoning="No documents listed in latest analysis"
                )
            
            # Build context for LLM
            context = self._build_classification_context(
                request_number=request_number,
                current_status=current_status,
                attention_reason=attention_reason,
                documents_available=documents_available,
                timeline_events=timeline_events
            )
            
            # Call LLM for classification
            classification_result = self._call_llm_for_classification(context)
            
            result = DocumentClassification(
                documents_ready=classification_result.documents_ready_for_download,
                reasoning=classification_result.reasoning
            )
            
            logger.info(f"✅ Classification for {request_number}: ready={result.documents_ready}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Classification failed for request {request_data.get('request_number', 'Unknown')}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Return safe default (don't download on errors)
            return DocumentClassification(
                documents_ready=False,
                reasoning=f"Classification error: {str(e)}"
            )
    
    def _build_classification_context(
        self,
        request_number: str,
        current_status: str,
        attention_reason: str,
        documents_available: List,
        timeline_events: List
    ) -> str:
        """Build context string for LLM classification"""
        
        # Format documents list (handle both string and dict formats)
        docs_list = []
        doc_count = 0
        
        for doc in documents_available[:15]:  # Show up to 15 documents
            if isinstance(doc, str):
                docs_list.append(f"- {doc}")
                doc_count += 1
            elif isinstance(doc, dict):
                title = doc.get('title', 'Untitled')
                doc_info = f"- {title}"
                if 'date' in doc:
                    doc_info += f" (Date: {doc['date']})"
                if 'size' in doc:
                    doc_info += f" [{doc['size']}]"
                docs_list.append(doc_info)
                doc_count += 1
        
        docs_summary = "\n".join(docs_list)
        if len(documents_available) > 15:
            docs_summary += f"\n... and {len(documents_available) - 15} more documents"
        
        # Format recent timeline events
        timeline_summary = "No recent timeline events"
        if timeline_events:
            recent_events = timeline_events[-5:]  # Last 5 events
            events_list = []
            for event in recent_events:
                if isinstance(event, str):
                    events_list.append(f"- {event}")
                elif isinstance(event, dict):
                    event_text = event.get('event', 'Unknown event')
                    event_date = event.get('date', 'Unknown date')
                    events_list.append(f"- [{event_date}] {event_text}")
            timeline_summary = "\n".join(events_list)
        
        context = f"""Analyze this FOIA request to determine if documents are ready for download FROM THE PORTAL.

REQUEST: {request_number}
STATUS: {current_status}
ATTENTION REASON: {attention_reason}

DOCUMENTS AVAILABLE ({len(documents_available)} total):
{docs_summary}

RECENT TIMELINE:
{timeline_summary}

DECISION CRITERIA:
Return TRUE for documents_ready_for_download ONLY if:
✓ Documents are NEWLY available (status changed to indicate availability)
✓ Timeline shows recent document release/upload event with actual file attachments
✓ Attention reason explicitly mentions documents being ready FOR DOWNLOAD
✓ Status indicates "Records Available", "Partially Fulfilled", "Fulfilled", etc.
✓ Documents have actual filenames with extensions (e.g., .pdf, .xlsx, .docx)

Return FALSE if:
✗ Status is still "Open", "In Progress", "Under Review"
✗ Documents listed are original request attachments (not responses)
✗ No clear evidence documents are newly available
✗ Unclear or ambiguous situation
✗ Agency directs requester to an EXTERNAL website, portal, or data source
✗ Agency provides instructions to access data elsewhere (e.g., "visit our website", "go to the DOJ portal")
✗ Response only contains URLs or web links instead of actual file attachments
✗ Documents are listed as web pages or external links (e.g., https://...)
✗ Agency states records are available for "in-person inspection" or "by appointment"
✗ Response indicates "no responsive records found" or "no disclosable records"

CRITICAL: Only return TRUE if there are ACTUAL FILES uploaded to the portal that can be downloaded.
External links, website directions, or instructions to access data elsewhere = FALSE.

Be conservative: when in doubt, return FALSE.

NOTE: You only need to determine TRUE/FALSE. If TRUE, the system will download ALL documents for this request."""

        return context
    
    def _call_llm_for_classification(self, context: str) -> DocumentClassificationResult:
        """Call LLM to classify the request using LangChain structured output"""
        try:
            logger.info("🤖 Calling LLM for document classification")
            
            # Create structured LLM with function calling
            structured_llm = self.llm_client.with_structured_output(
                DocumentClassificationResult, 
                method="function_calling"
            )
            
            # Build messages using LangChain
            messages = [
                SystemMessage(content=(
                    "You are a FOIA document classification expert. "
                    "Determine if documents are newly available and ready for download. "
                    "Be conservative: only return TRUE if there is clear evidence. "
                    "If TRUE, ALL documents for this request will be downloaded."
                )),
                HumanMessage(content=context)
            ]
            
            # Invoke LLM with structured output
            result = structured_llm.invoke(messages)
            
            logger.info(f"✅ LLM decision: {result.documents_ready_for_download}")
            logger.info(f"📝 Reasoning: {result.reasoning}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ LLM call failed: {str(e)}")
            raise
    
    def classify_batch(self, requests: List[Dict[str, Any]]) -> List[DocumentClassification]:
        """
        Classify multiple requests in batch.
        
        Args:
            requests: List of request records from database
            
        Returns:
            List of DocumentClassification results (same order as input)
        """
        logger.info(f"🔍 Classifying {len(requests)} requests in batch")
        
        results = []
        for i, request in enumerate(requests, 1):
            request_number = request.get('request_number', f'Request_{i}')
            logger.info(f"Processing {i}/{len(requests)}: {request_number}")
            
            result = self.classify_request(request)
            results.append(result)
            
            # Brief pause between classifications to avoid rate limits
            if i < len(requests):
                import time
                time.sleep(0.5)
        
        # Summary statistics
        ready_count = sum(1 for r in results if r.documents_ready)
        
        logger.info(f"📊 Batch classification complete:")
        logger.info(f"   Requests with documents ready: {ready_count}/{len(requests)}")
        
        return results


# Convenience function for single-request classification
def classify_single_request(llm_client, request_data: Dict[str, Any]) -> DocumentClassification:
    """
    Convenience function to classify a single request.
    
    Args:
        llm_client: LLM client instance (gpt_4o from llm.py)
        request_data: Request record from database
        
    Returns:
        DocumentClassification result
    """
    classifier = DocumentClassifier(llm_client)
    return classifier.classify_request(request_data)