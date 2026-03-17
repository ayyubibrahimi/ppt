# FOIA-agent

# Public Records Automation

A work-in-progress automation tool for streamlining public records requests across government agencies.

## Overview

This project aims to automate the public records request process from start to finish, reducing manual effort and ensuring consistent follow-through on information requests.


## Current Features
- **Portal Discovery**: Automatically locate public records request portals for government agencies
- **Authentication**: Sign into agency portals programmatically  
- **View**: Can view and summarize open and closed public records requests
- **Response**: Can flag responses as important and draft and submit responses to government agencies who house public records 

## Planned Features
- **Correspondence Management**: Autonomous handling of ongoing communication with agencies throughout the request lifecycle
- **Record Verification**: Validate that submitted records match the original request requirements

## Architecture Goals

The system is designed with modularity in mind to support:
- Multiple government agency portal types
- Easy integration with third-party platforms (e.g., MuckRock)
- Extensible request templates and workflows

## Status

🚧 **Work in Progress** - Initial development phase

## Getting Started

*Documentation will be added as development progresses*

## Questions for Katey
1. We need a better system for monitoring changes. What types of changes should result in the request being flagged? 
2. We need more examples of how the model should respond

# Order
1. Submit
2. Bulk analysis
3. Monitor
4. Draft 
5. Send
6. Monitor


# done

2. stop updating drafts if there is already a draft that needs to be reviewed 
5. refactor script so that we don't re-download and re-ocr pdfs, however, we should re-download tables because we need them to be stored locally in order to do the eda. 
7. fix file_extension parsing when adding data to document_downloads table
8. bulk add credentials

# improvements
1. Use the CLAUDE SDK
2. Use the alerts sent to email to monitor 
3. Use the API for pre-existing accounts
4. create an agent thats good at reading logs 

# to-dos
1. downloading, ocr, and summarization doesn't seem to be followed by classification
2. if records downloaded, request is complete 
3. plumas fails silently. we need to raise a flag gthat a account needs to be manually created
4. for requests that fail, link to the original request in the submission status tab so that its easy for users to create an acct and submit that request
5. if portal creds fail, change verified to unverified on front-end for that portals creds 
6. the input to the memory log should be a coarse summary (input a summary of all or half of the doc). The question is how to account for granular docs, such as IA reports, and complaint logs. 
7. add mimetype to document_downloads table
8. the comparison, between pdf and timeline, will be difficult the longer the pdf is. we should introduce more complex processing logic. 
9. We should not monitor any requests that have docs uploaded to g drive
10. only draft message if last draft was written before any changes made to request
11. monitor through email
12. claude sdk for opengov 
13. we should regularly run bulk analysis on all portals in case a request is submitted for us
14. some input requests are too long, at which point the llm might have difficulty reading the timeline, therefore, we should just input the request based on the input to the submission_queue tablke 
15. requests table should link to portal by id not url. this is a fuck up for situations where there are multiple agencies associated with the same portal. if we don't have creds for all portals, the logic may think we don't have creds \

feats:
1. add filter for request denied, request closed, requested closed and recoerds received, etc
2. add feat for automatic follow up after 30 days

KNOWN ISSUE: Message Draft Deduplication

  Problem: The monitoring workflow currently updates the requests.updated_at timestamp on every
  monitoring cycle, even when no substantive changes are detected. This breaks timestamp-based draft
   deduplication logic.

  Current Behavior:
  - monitoring_agent.py line 287-288: When no changes detected, calls _update_last_portal_check()
  - _update_last_portal_check() line 651: Sets both last_portal_check AND updated_at
  - Result: updated_at changes daily even when request content is unchanged

  Impact:
  - Cannot reliably use requests.updated_at to prevent duplicate message drafts
  - System may generate redundant drafts for the same request state
  - Timestamp-based validation (Option 2) requires fixing this first

  Recommended Fix:
  1. Option A (Quick Fix): Remove updated_at update from _update_last_portal_check() - only update
  last_portal_check
  2. Option B (Better): Reserve updated_at for actual content changes, use last_portal_check for
  monitoring heartbeat
  3. Option C (Best): Implement content hash comparison or use last_analyzed + change detection for
  draft validation

  Alternative Workaround:
  Use timestamp-based cooldown (Option 1) with 7-day minimum between drafts, or compare
  message_drafts.created_at against requests.last_analyzed instead of updated_at.

  Files Affected:
  - monitoring_agent.py:651 - Updates updated_at on every check
  - supabase_integration.py:90 - Updates updated_at on content changes
  - message_coordinator.py - Needs validation logic to prevent duplicate drafts

  ---
  Status: Needs architectural decision on timestamp semantics before implementing draft
  deduplication.


# non functioning portals Y
- fairfieldcapd.nextrequest.com
- https://cityofwatsonvilleca.nextrequest.com/

  pkill -9 -f "run_playwright_discovery"
  pkill -9 -f "claude_agent_sdk/_bundled/claude"
  pkill -9 -f "mcp-server-playwright"