export interface PendingAction {
    action_type: string
    metadata: Record<string, any>
  }

  export interface WorkflowState {
    lifecycle_state: 'active' | 'closed' | 'complete'
    pending_actions: PendingAction[]
    state_summary: string
  }

  export interface Request {
    id: string
    user_id: string
    request_number: string
    request_text: string
    user_notes?: string
    portal_name: string
    current_status: string
    action_required: boolean
    agent_attention_needed: boolean
    agent_attention_reason: string | null
    agent_attention_priority: string
    message_approved: boolean
    latest_analysis: string
    analysis_summary: string
    last_analyzed: string
    last_portal_check: string
    created_at: string
    updated_at: string
    workflow_state?: string | WorkflowState // Can be JSON string or parsed object
    approved_draft?: {
      id: string
      draft_subject: string
      draft_status: string
      user_approved: boolean
    } | null
  }
  
  export interface RequestChange {
    id: string
    request_id: string
    field_changed: string
    old_value: string
    new_value: string
    change_severity: string
    triggered_attention_flag: boolean
    attention_reason: string
    created_at: string
  }
  
  export interface MessageDraft {
    id: string
    request_id: string
    draft_subject: string
    draft_message: string
    message_type: string
    change_context: string
    draft_status: string
    user_approved: boolean
    created_at: string
    updated_at: string
    sent_at?: string
  }
  
  export interface RequestDetailData {
    request: Request
    changes: RequestChange[]
    messageHistory: MessageDraft[]
    timelineEvents: string[]
    documents: string[]
    payments: string[]
    staffContact: string
    deadlines: string[]
  }
  
  export interface UserProfile {
    id: string
    email: string
    full_name: string
    phone?: string
    organization?: string
    is_active: boolean
    last_login: string
    created_at: string
    updated_at: string
  }

  export interface UploadedDocument {
    id: string
    request_id: string
    user_id: string
    portal_name: string
    document_id: string
    document_title: string
    file_extension: string | null
    download_status: string
    google_drive_file_id: string
    google_drive_folder_id: string
    google_drive_web_link: string
    created_at: string
    downloaded_at: string | null
    uploaded_to_drive_at: string | null
    // OCR and Summarization
    ocr_status: string | null
    summary_status: string | null
    num_pages: number | null
    document_data: {
      summary?: {
        summary_text: string
        summary_timestamp?: string
        num_pages?: number
        num_intervals?: number
      }
      ocr_data?: {
        page_texts?: Array<{
          page_number: number
          text: string
        }>
      }
    } | null
    // Classification
    classification_status: string | null
    records_match_request: boolean | null
    classification_explanation: string | null
    classification_completed_at: string | null
  }