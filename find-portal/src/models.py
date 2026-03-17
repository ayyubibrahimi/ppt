from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the page is the correct index page")
    confidence: float = Field(description="Confidence score between 0 and 1")
    reasoning: str = Field(description="Detailed explanation of the validation decision")
    recommendations: Optional[List[str]] = Field(description="Suggestions for alternative links if validation fails")

class AgentState(BaseModel):
    """Represents the current state of an individual exploration agent"""
    agent_id: str = Field(description="Unique identifier for this agent")
    current_url: str = Field(description="Current URL being explored")
    current_depth: int = Field(description="Current exploration depth")
    visited_urls: List[str] = Field(description="URLs visited by this agent")
    validation_result: Optional[ValidationResult] = Field(description="Latest validation result")
    parent_url: Optional[str] = Field(description="Parent URL of current page")
    depth_value: Optional[float] = Field(description="Depth value of current page")

class MultiAgentDecision(BaseModel):
    """High-level orchestrator decision based on all agents' results"""
    action: str = Field(description="Global action: 'terminate', 'explore_new', 'explore_deeper'")
    target_agent_ids: List[str] = Field(description="Agents that should take action")
    target_urls: Optional[Dict[str, str]] = Field(description="New URLs for each agent to explore")
    rationale: str = Field(description="Detailed explanation of the decision")
    confidence: float = Field(description="Confidence in the decision (0-1)")
    winner_agent_id: Optional[str] = Field(description="Agent ID that found the index page")

# Models for structured output
class ExplorationLink(BaseModel):
    url: str = Field(description="The URL to explore")
    rationale: str = Field(description="Explanation of why this link contains the news index")

class ExplorationLinks(BaseModel):
    selected_links: List[ExplorationLink] = Field(description="List of selected links to explore")

class ExtractedLink(BaseModel):
    url: str = Field(description="The URL of the extracted link")
    context: str = Field(description="Surrounding text/context of the link")
    depth_value: float = Field(description="Calculated promise/depth value between 0-1")
    parent_url: str = Field(description="URL of the page where this link was found")

class ExtractedLinks(BaseModel):
    links: List[ExtractedLink] = Field(description="Collection of extracted links with metadata")

class OrchestratorDecision(BaseModel):
    action: str = Field(description="Next action to take: 'continue', 'retry', or 'terminate'")
    feedback: str = Field(description="Reasoning behind the decision")
    alternative_strategy: Optional[str] = Field(description="Suggested strategy for finding the correct page")

class NextLinkSelection(BaseModel):
    selected_url: str = Field(description="URL of the next link to explore")
    rationale: str = Field(description="Detailed explanation of why this link was chosen")
    confidence: float = Field(description="Confidence score for this selection (0-1)")
