import { Request, MessageDraft } from '@/types/requests'

export interface PageState {
  // Data
  flaggedRequests: Request[]
  selectedRequest: Request | null
  selectedRequestDrafts: MessageDraft[]
  
  // UI State
  isLoadingRequests: boolean
  isLoadingDrafts: boolean
  error: string | null
  lastUpdated: string | null
  
  // Actions in progress
  isApprovingDraft: boolean
  isGeneratingDraft: boolean
}